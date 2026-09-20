from __future__ import annotations

from hym.core.models import Rect
from hym.core.pages import PageSpec
from hym.core.targets import LocatorKind, LocatorSpec, TargetSpec

WECHAT_PACKAGE = "com.tencent.mm"
_NATIVE: dict[str, str] = {}


def _target(
    target_id: str,
    *locators: LocatorSpec,
    required: bool = True,
) -> TargetSpec:
    return TargetSpec(target_id, tuple(locators), required=required, metadata=_NATIVE)


def _text_locator(
    strategy_id: str,
    text: str,
    *,
    priority: int,
    region: Rect | None = None,
) -> LocatorSpec:
    return LocatorSpec(strategy_id, LocatorKind.UI_TEXT, text, region=region, priority=priority)


def _desc_locator(
    strategy_id: str,
    text: str,
    *,
    priority: int,
    region: Rect | None = None,
) -> LocatorSpec:
    return LocatorSpec(strategy_id, LocatorKind.UI_DESC, text, region=region, priority=priority)


def _ocr_locator(
    strategy_id: str,
    text: str,
    *,
    region: Rect,
    priority: int = 10,
    min_confidence: float = 0.8,
) -> LocatorSpec:
    return LocatorSpec(
        strategy_id,
        LocatorKind.OCR_TEXT,
        text,
        region=region,
        priority=priority,
        min_confidence=min_confidence,
    )


def _coordinate_locator(strategy_id: str, x: float, y: float, *, priority: int = 200) -> LocatorSpec:
    return LocatorSpec(
        strategy_id,
        LocatorKind.COORDINATE,
        priority=priority,
        options={"point": (x, y)},
    )


BOTTOM = Rect(0.0, 0.82, 1.0, 1.0)
TOP = Rect(0.0, 0.0, 1.0, 0.18)
CONTENT = Rect(0.0, 0.08, 1.0, 0.92)
SEARCH_RESULTS = Rect(0.0, 0.15, 1.0, 0.92)

HOME_MARKER = _target(
    "微信首页底栏",
    _text_locator("微信底栏文字", "微信", priority=10, region=BOTTOM),
    _ocr_locator("微信底栏OCR", "微信", region=Rect(0.0, 0.88, 0.25, 1.0), priority=20),
    required=False,
)
HOME_PAGE = PageSpec(
    "wechat.home",
    WECHAT_PACKAGE,
    (HOME_MARKER,),
    activity_patterns=(r"LauncherUI$",),
)
CHAT_TAB = _target("微信聊天标签", _text_locator("文字", "微信", priority=10, region=BOTTOM))
DISCOVER_TAB = _target(
    "微信发现标签",
    _text_locator("发现底栏文字", "发现", priority=10, region=BOTTOM),
    _ocr_locator("发现底栏OCR", "发现", region=Rect(0.48, 0.88, 0.76, 1.0), priority=20),
    _coordinate_locator("已校准底栏位置", 0.625, 0.935),
)
ME_TAB = _target(
    "微信我的标签",
    _text_locator("我的底栏文字", "我", priority=10, region=BOTTOM),
    _ocr_locator("我的底栏OCR", "我", region=Rect(0.74, 0.88, 1.0, 1.0), priority=20),
    _coordinate_locator("已校准底栏位置", 0.875, 0.935),
)

MOMENTS_ENTRY = _target(
    "朋友圈入口",
    _ocr_locator("OCR文字", "朋友圈", region=Rect(0.02, 0.10, 0.5, 0.18)),
    _coordinate_locator("已校准入口位置", 0.5, 0.14),
)
MOMENTS_PAGE = _target(
    "朋友圈页面",
    LocatorSpec(
        "页面Activity",
        LocatorKind.ACTIVITY,
        r"(?:SnsTimeLineUI|ImproveSnsTimelineUI)$",
        priority=10,
        options={"mode": "regex", "package_name": WECHAT_PACKAGE},
    ),
    _ocr_locator("OCR标题", "朋友圈", region=TOP, priority=20),
    required=False,
)
MOMENTS_PAGE_SPEC = PageSpec(
    "wechat.moments",
    WECHAT_PACKAGE,
    (MOMENTS_PAGE,),
    activity_patterns=(r"(?:SnsTimeLineUI|ImproveSnsTimelineUI)$",),
)

SERVICE_ENTRIES = (
    _target(
        "微信服务入口",
        _ocr_locator(
            "OCR文字",
            "服务",
            region=Rect(0.02, 0.24, 0.5, 0.34),
            min_confidence=0.25,
        ),
        _coordinate_locator("已校准入口位置", 0.5, 0.294),
        required=False,
    ),
    _target(
        "微信支付入口",
        _ocr_locator("OCR文字", "支付", region=Rect(0.02, 0.24, 0.5, 0.34)),
        required=False,
    ),
)
WALLET_ENTRY = _target(
    "微信钱包入口",
    _ocr_locator("OCR文字", "钱包", region=Rect(0.55, 0.13, 0.92, 0.27)),
    _coordinate_locator("已校准入口位置", 0.72, 0.218),
)
BALANCE_ENTRY = _target(
    "微信零钱入口",
    _ocr_locator("OCR文字", "零钱", region=Rect(0.05, 0.09, 0.5, 0.19)),
    _coordinate_locator("已校准入口位置", 0.25, 0.14),
)
BALANCE_PAGE = _target(
    "微信零钱页面",
    _ocr_locator("OCR页面标记", "我的零钱", region=Rect(0.25, 0.22, 0.75, 0.34)),
    required=False,
)
BALANCE_PAGE_SPEC = PageSpec(
    "wechat.balance",
    WECHAT_PACKAGE,
    (BALANCE_PAGE,),
)

WALLET_PAGE = _target(
    "微信钱包页面",
    _ocr_locator("OCR标题", "钱包", region=TOP, min_confidence=0.4),
    required=False,
)
WALLET_PAGE_SPEC = PageSpec("wechat.wallet", WECHAT_PACKAGE, (WALLET_PAGE,))
BILL_ENTRY = _target(
    "微信账单入口",
    _ocr_locator("OCR文字", "账单", region=Rect(0.78, 0.04, 1.0, 0.14), min_confidence=0.4),
    _coordinate_locator("已校准右上角位置", 0.92, 0.09),
)
BILL_PAGE = _target(
    "微信账单页面",
    _ocr_locator("OCR标题", "账单", region=TOP, min_confidence=0.4),
    required=False,
)
BILL_PAGE_SPEC = PageSpec("wechat.bill", WECHAT_PACKAGE, (BILL_PAGE,))

SEARCH_ENTRY = _target(
    "微信搜索入口",
    _desc_locator("描述", "搜索", priority=10, region=TOP),
    _text_locator("文字", "搜索", priority=20, region=TOP),
    LocatorSpec(
        "包含搜索描述",
        LocatorKind.UI_REGEX,
        r"^搜索.*$",
        region=TOP,
        priority=30,
    ),
)
SEARCH_INPUT = _target(
    "微信搜索输入框",
    LocatorSpec(
        "输入框控件",
        LocatorKind.UI_QUERY,
        "android.widget.EditText",
        region=TOP,
        priority=10,
    ),
)
MESSAGE_INPUT = _target(
    "微信消息输入框",
    LocatorSpec(
        "输入框控件",
        LocatorKind.UI_QUERY,
        "android.widget.EditText",
        region=Rect(0.0, 0.68, 1.0, 1.0),
        priority=10,
    ),
)
SEND_BUTTON = _target(
    "微信发送按钮",
    _text_locator("文字", "发送", priority=10, region=BOTTOM),
    _desc_locator("描述", "发送", priority=20, region=BOTTOM),
)


def friend_result(friend_name: str) -> TargetSpec:
    # 目标 ID 不含好友名，避免姓名进入结构化日志。
    return _target(
        "微信好友搜索结果",
        _text_locator("好友名称", friend_name, priority=10, region=SEARCH_RESULTS),
    )


def conversation_title(friend_name: str) -> TargetSpec:
    return _target(
        "微信聊天标题",
        _text_locator("好友名称", friend_name, priority=10, region=TOP),
        required=False,
    )
