from __future__ import annotations

import traceback
from typing import Any, Callable, Sequence

from hym.core.events import EventLevel
from hym.core.models import SystemKey


def finish_cycle(session, jobs: Sequence[Any], trace_id: str, emit_worker: Callable[..., None]) -> int:
    """停止本轮应用并锁屏；失败只计为一处收尾异常。"""

    failed: list[str] = []
    stopped = 0
    packages: set[str] = set()
    for job in jobs:
        app = job.plugin.spec.identity
        if app.package_name in packages:
            continue
        packages.add(app.package_name)
        result = session.stop_app(app)
        if result.succeeded:
            stopped += 1
        else:
            failed.append(app.display_name)

    locked = session.press(SystemKey.SLEEP)
    if not locked.succeeded:
        failed.append("锁屏")
    status = "success" if not failed else "partial"
    message = f"已停止 {stopped} 个应用并锁屏" if not failed else f"轮次收尾未完全成功: {'、'.join(failed)}"
    emit_worker(
        trace_id,
        "runtime.cycle.cleanup.finished",
        "轮次收尾",
        message,
        level=EventLevel.INFO if not failed else EventLevel.WARNING,
        status=status,
    )
    return int(bool(failed))


def record_unhandled_app_error(job: Any, error: Exception) -> None:
    context = job.context
    stack = traceback.format_exc()
    artifacts = context.diagnostics.capture(
        f"{job.plugin.app_id}-unhandled",
        metadata={
            "schema_version": "1.0",
            "trace_id": context.trace_id,
            "device_id": context.device_id,
            "app_id": context.app.app_id,
            "message": str(error),
            "traceback": stack,
            "recent_locator_attempts": list(context.recent_locator_attempts),
        },
    )
    context.emit(
        "app.failed",
        "应用任务异常",
        f"{job.plugin.spec.display_name}发生未处理异常: {error}",
        level=EventLevel.ERROR,
        status="failed",
        data={"traceback": stack},
        artifacts=artifacts,
    )


def next_pending_index(jobs: Sequence[Any], current_index: int) -> int | None:
    for offset in range(1, len(jobs) + 1):
        index = (current_index + offset) % len(jobs)
        if not jobs[index].completed:
            return index
    return None


def rest_before_next_app(
    clock,
    jobs: Sequence[Any],
    current_index: int,
    *,
    on_tick: Callable[[], bool] | None = None,
) -> int | None:
    """完整结束一个 App 后回到桌面休息，再调度下一个。"""

    next_index = next_pending_index(jobs, current_index)
    if next_index is None:
        return None
    current = jobs[current_index]
    target = jobs[next_index]
    context = current.context
    settings = context.timing.settings
    wait_seconds = context.timing.range_seconds(
        settings.app_rest_seconds_min,
        settings.app_rest_seconds_max,
        center=settings.app_rest_seconds_center,
        stddev=settings.app_rest_seconds_stddev,
    )
    context.emit(
        "runtime.app_rest.started",
        "应用间休息开始",
        (
            f"{current.plugin.spec.display_name}已结束，返回桌面休息约 "
            f"{wait_seconds / 60:.1f} 分钟后执行{target.plugin.spec.display_name}"
        ),
        workflow_id=current.execution.definition.workflow_id,
        status="waiting",
        data={"wait_seconds": round(wait_seconds, 2), "next_app_id": target.plugin.app_id},
    )
    context.actions.press(SystemKey.HOME)
    remaining = wait_seconds
    while remaining > 0:
        if on_tick is not None and not on_tick():
            context.emit(
                "runtime.app_rest.interrupted",
                "应用间休息已中断",
                "收到停止指令，取消后续应用任务",
                workflow_id=current.execution.definition.workflow_id,
                status="cancelled",
                data={"next_app_id": target.plugin.app_id},
            )
            return None
        sleep_seconds = min(10.0, remaining)
        clock.sleep(sleep_seconds)
        remaining -= sleep_seconds
    context.emit(
        "runtime.app_rest.finished",
        "应用间休息结束",
        f"桌面休息结束，准备执行{target.plugin.spec.display_name}",
        workflow_id=current.execution.definition.workflow_id,
        status="success",
        data={"wait_seconds": round(wait_seconds, 2), "next_app_id": target.plugin.app_id},
    )
    return next_index
