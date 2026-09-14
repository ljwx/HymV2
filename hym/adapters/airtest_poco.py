from __future__ import annotations

from collections.abc import Callable, Mapping
import logging
import re
from typing import Any
from xml.etree import ElementTree

from hym.core.models import (
    ActionResult,
    ActionStatus,
    ActivityInfo,
    AppIdentity,
    DeviceDescriptor,
    HealthReport,
    HealthState,
    ImageFrame,
    Observation,
    ObservationRequest,
    ObservationResult,
    Point,
    Rect,
    SwipeGesture,
    SystemKey,
    UiTreeSource,
    UiNode,
    utc_now,
)

ManagerFactory = Callable[[DeviceDescriptor], Any]
_ACTIVITY_COMPONENT = re.compile(
    r"(?P<package>[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)/(?P<activity>\.?[A-Za-z0-9_.$]+)"
)
_PIXEL_BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
_UI_DUMP_PATH = "/sdcard/hym-window.xml"


def create_legacy_device_manager(descriptor: DeviceDescriptor):
    """按需加载旧设备实现，导入模块时不会连接手机。"""

    from device.DeviceInfo import DeviceInfo
    from device.DeviceManager import DeviceManager

    # Airtest 默认输出每条 ADB 命令，文本输入时可能泄露内容且日志噪声很大。
    logging.getLogger("airtest").setLevel(logging.WARNING)
    logging.getLogger("poco").setLevel(logging.WARNING)
    serial = descriptor.connection or descriptor.device_id
    return DeviceManager(DeviceInfo(serial))


class AirtestPocoDeviceFactory:
    def __init__(self, manager_factory: ManagerFactory = create_legacy_device_manager) -> None:
        self._manager_factory = manager_factory

    def create(self, descriptor: DeviceDescriptor) -> AirtestPocoDeviceAdapter:
        return AirtestPocoDeviceAdapter(descriptor, manager_factory=self._manager_factory)


class AirtestPocoDeviceAdapter:
    """把现有 DeviceManager 转换成平台无关接口。"""

    def __init__(
        self,
        descriptor: DeviceDescriptor,
        *,
        manager_factory: ManagerFactory = create_legacy_device_manager,
        manager: Any | None = None,
    ) -> None:
        self._descriptor = descriptor
        self._manager_factory = manager_factory
        self._manager = manager

    @property
    def descriptor(self) -> DeviceDescriptor:
        return self._descriptor

    def connect(self) -> ActionResult:
        started = utc_now()
        try:
            if self._manager is None:
                self._manager = self._manager_factory(self.descriptor)
            if not getattr(self._manager, "device_ready", False):
                return ActionResult.failure(
                    "connect",
                    "设备未就绪",
                    started_at=started,
                    retryable=True,
                    status=ActionStatus.UNAVAILABLE,
                )
            return ActionResult.success("connect", started_at=started)
        except Exception as error:
            self._manager = None
            return ActionResult.failure("connect", str(error), started_at=started, retryable=True)

    def disconnect(self) -> ActionResult:
        started = utc_now()
        try:
            # Airtest 的 Android.disconnect 会执行 ADB transport 断开，USB 设备也会从
            # adb devices 消失。会话结束只释放本地引用，进程退出会清理 Poco 资源。
            self._manager = None
            return ActionResult.success("disconnect", started_at=started)
        except Exception as error:
            self._manager = None
            return ActionResult.failure("disconnect", str(error), started_at=started, retryable=True)

    def health_check(self) -> HealthReport:
        if self._manager is None or not getattr(self._manager, "device_ready", False):
            return HealthReport(HealthState.DISCONNECTED, message="设备未连接")
        try:
            activity = self._read_activity()
            self._manager.get_screen_size()
            shell = getattr(self._manager.dev, "shell", None)
            if callable(shell):
                response = shell("echo hym_health")
                if "hym_health" not in str(response):
                    return HealthReport(HealthState.DEGRADED, message="ADB 健康检查没有返回预期结果")
            return HealthReport(
                HealthState.HEALTHY,
                details={
                    "package_name": activity.package_name,
                    "activity_name": activity.activity_name,
                },
            )
        except Exception as error:
            return HealthReport(HealthState.DEGRADED, message=str(error))

    def start_app(self, app: AppIdentity) -> ActionResult:
        return self._run_action("start_app", lambda manager: manager.start_app(app.package_name))

    def stop_app(self, app: AppIdentity) -> ActionResult:
        return self._run_action("stop_app", lambda manager: manager.stop_app(app.package_name))

    def tap(self, point: Point, duration_seconds: float = 0.1) -> ActionResult:
        def execute(manager) -> None:
            width, height = manager.get_screen_size()
            position = (round(point.x * width), round(point.y * height))
            manager.dev.touch(position, duration=duration_seconds)

        return self._run_action("tap", execute)

    def swipe(self, gesture: SwipeGesture) -> ActionResult:
        def execute(manager) -> None:
            width, height = manager.get_screen_size()
            start = (round(gesture.start.x * width), round(gesture.start.y * height))
            end = (round(gesture.end.x * width), round(gesture.end.y * height))
            manager.dev.swipe(start, end, duration=gesture.duration_seconds)

        return self._run_action("swipe", execute)

    def press(self, key: SystemKey) -> ActionResult:
        key_events = {
            SystemKey.BACK: "BACK",
            SystemKey.HOME: "HOME",
            SystemKey.APP_SWITCH: "APP_SWITCH",
            SystemKey.VOLUME_UP: "VOLUME_UP",
            SystemKey.VOLUME_DOWN: "VOLUME_DOWN",
            SystemKey.POWER: "POWER",
        }
        return self._run_action("press", lambda manager: manager.dev.keyevent(key_events[key]))

    def input_text(self, value: str) -> ActionResult:
        """使用 Airtest 输入法写入文本，支持中文且不暴露给上层流程。"""

        return self._run_action("input_text", lambda manager: manager.dev.text(value, enter=False))

    def observe(self, request: ObservationRequest) -> ObservationResult:
        if self._manager is None:
            return ObservationResult(ActionStatus.UNAVAILABLE, message="设备未连接", retryable=True)

        try:
            activity = self._read_activity()
            ui_nodes: tuple[UiNode, ...] = ()
            screenshot: ImageFrame | None = None
            warnings: list[str] = []

            # 一轮观察只采集一次 UI 树和截图，后续定位器共享结果。
            if request.include_ui_tree:
                try:
                    if request.ui_tree_source is UiTreeSource.ACCESSIBILITY:
                        ui_nodes = tuple(self._dump_accessibility_tree())
                    else:
                        hierarchy = self._manager.poco.dump()
                        ui_nodes = tuple(_flatten_hierarchy(hierarchy))
                except Exception as error:
                    warnings.append(f"UI 树获取失败: {error}")

            if request.include_screenshot:
                try:
                    raw = self._manager.dev.snapshot(max_size=request.screenshot_max_size)
                    screenshot = _to_image_frame(raw)
                except Exception as error:
                    warnings.append(f"截图失败: {error}")

            observation = Observation(
                device_id=self.descriptor.device_id,
                activity=activity,
                ui_nodes=ui_nodes,
                screenshot=screenshot,
                metadata={
                    "warnings": warnings,
                    "ui_tree_source": request.ui_tree_source.value,
                },
            )
            return ObservationResult(ActionStatus.SUCCESS, observation=observation)
        except Exception as error:
            return ObservationResult(ActionStatus.FAILED, message=str(error), retryable=True)

    def _run_action(self, operation: str, callback: Callable[[Any], None]) -> ActionResult:
        started = utc_now()
        if self._manager is None:
            return ActionResult.failure(
                operation,
                "设备未连接",
                started_at=started,
                retryable=True,
                status=ActionStatus.UNAVAILABLE,
            )
        try:
            callback(self._manager)
            return ActionResult.success(operation, started_at=started)
        except Exception as error:
            return ActionResult.failure(operation, str(error), started_at=started, retryable=True)

    def _read_activity(self) -> ActivityInfo:
        shell = getattr(self._manager.dev, "shell", None)
        if callable(shell):
            try:
                output = shell("dumpsys activity activities")
                parsed = _parse_resumed_activity(output)
                if parsed is not None:
                    return parsed
            except Exception:
                pass
        package_name, activity_name = self._manager.get_top_activity()
        return ActivityInfo(package_name=package_name, activity_name=activity_name)

    def _dump_accessibility_tree(self) -> list[UiNode]:
        shell = getattr(self._manager.dev, "shell", None)
        if not callable(shell):
            raise RuntimeError("当前设备不支持原生 UI 树")
        command = f"uiautomator dump {_UI_DUMP_PATH} >/dev/null && cat {_UI_DUMP_PATH}"
        raw = shell(command)
        return _flatten_accessibility_hierarchy(raw, self._manager.get_screen_size())


def _parse_resumed_activity(raw: Any) -> ActivityInfo | None:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    for line in str(raw).splitlines():
        if "topResumedActivity" not in line and "mResumedActivity" not in line:
            continue
        match = _ACTIVITY_COMPONENT.search(line)
        if match is None:
            continue
        package_name = match.group("package")
        activity_name = match.group("activity")
        if activity_name.startswith("."):
            activity_name = activity_name[1:]
        return ActivityInfo(package_name, activity_name)
    return None


def _flatten_hierarchy(root: Any) -> list[UiNode]:
    """把 Poco 树转换为可序列化的扁平节点。"""

    if not isinstance(root, Mapping):
        return []

    nodes: list[UiNode] = []

    def visit(raw_node: Mapping[str, Any], path: str, parent_id: str | None) -> None:
        payload = raw_node.get("payload")
        attributes = _json_safe(payload if isinstance(payload, Mapping) else {})
        position = _pair(attributes.get("pos"))
        size = _pair(attributes.get("size"))
        bounds = _bounds_from_center(position, size)
        name = _text(attributes.get("name") or raw_node.get("name"))
        resource_id = _text(attributes.get("resourceId"))
        if resource_id is None and name and ":id/" in name:
            resource_id = name

        # 节点路径同时充当稳定的父子关系标识。
        nodes.append(
            UiNode(
                node_id=path,
                parent_id=parent_id,
                class_name=_text(attributes.get("type")),
                resource_id=resource_id,
                text=_text(attributes.get("text")),
                description=_text(attributes.get("desc")),
                bounds=bounds,
                clickable=_first_bool(attributes.get("clickable"), attributes.get("touchable")),
                enabled=_optional_bool(attributes.get("enabled")),
                selected=_optional_bool(attributes.get("selected")),
                visible=_optional_bool(attributes.get("visible")),
                attributes=attributes,
            )
        )

        children = raw_node.get("children")
        if not isinstance(children, list):
            return
        for index, child in enumerate(children):
            if isinstance(child, Mapping):
                visit(child, f"{path}/{index}", path)

    visit(root, "0", None)
    return nodes


def _flatten_accessibility_hierarchy(
    raw: Any,
    screen_size: tuple[int, int],
) -> list[UiNode]:
    """转换 Android 原生 UIAutomator XML，供 WebView 等页面按需使用。"""

    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    xml = str(raw)
    start = xml.find("<?xml")
    if start < 0:
        raise ValueError("原生 UI 树没有返回 XML")
    root = ElementTree.fromstring(xml[start:])
    width, height = screen_size
    nodes: list[UiNode] = []

    def visit(element: ElementTree.Element, path: str, parent_id: str | None) -> None:
        attributes = dict(element.attrib)
        nodes.append(
            UiNode(
                node_id=path,
                parent_id=parent_id,
                class_name=_empty_to_none(attributes.get("class")),
                resource_id=_empty_to_none(attributes.get("resource-id")),
                text=_empty_to_none(attributes.get("text")),
                description=_empty_to_none(attributes.get("content-desc")),
                bounds=_bounds_from_pixels(attributes.get("bounds"), width, height),
                clickable=_xml_bool(attributes.get("clickable")),
                enabled=_xml_bool(attributes.get("enabled")),
                selected=_xml_bool(attributes.get("selected")),
                visible=_xml_bool(attributes.get("visible-to-user")),
                attributes=attributes,
            )
        )
        for index, child in enumerate(element):
            visit(child, f"{path}/{index}", path)

    visit(root, "0", None)
    return nodes


def _bounds_from_pixels(value: str | None, width: int, height: int) -> Rect | None:
    if not value or width <= 0 or height <= 0:
        return None
    match = _PIXEL_BOUNDS.fullmatch(value)
    if match is None:
        return None
    left, top, right, bottom = (int(item) for item in match.groups())
    left = min(width, max(0, left)) / width
    right = min(width, max(0, right)) / width
    top = min(height, max(0, top)) / height
    bottom = min(height, max(0, bottom)) / height
    if left >= right or top >= bottom:
        return None
    return Rect(left, top, right, bottom)


def _empty_to_none(value: str | None) -> str | None:
    return value if value else None


def _xml_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.lower() == "true"


def _to_image_frame(raw: Any) -> ImageFrame | None:
    """只保留尺寸、像素格式和字节，不泄漏 NumPy 类型。"""

    if raw is None or not hasattr(raw, "shape") or not hasattr(raw, "tobytes"):
        return None
    shape = raw.shape
    if len(shape) < 2:
        return None
    height, width = int(shape[0]), int(shape[1])
    channels = int(shape[2]) if len(shape) > 2 else 1
    pixel_format = {1: "GRAY", 3: "BGR", 4: "BGRA"}.get(channels, f"CHANNELS_{channels}")
    return ImageFrame(width=width, height=height, data=raw.tobytes(), pixel_format=pixel_format)


def _bounds_from_center(position: tuple[float, float] | None, size: tuple[float, float] | None) -> Rect | None:
    if position is None or size is None:
        return None
    x, y = position
    width, height = size
    left = max(0.0, x - width / 2)
    top = max(0.0, y - height / 2)
    right = min(1.0, x + width / 2)
    bottom = min(1.0, y + height / 2)
    if left >= right or top >= bottom:
        return None
    return Rect(left, top, right, bottom)


def _pair(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        return None
    try:
        return float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _first_bool(*values: Any) -> bool | None:
    """保留明确的 False，避免布尔值被 or 表达式吞掉。"""

    for value in values:
        if isinstance(value, bool):
            return value
    return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
