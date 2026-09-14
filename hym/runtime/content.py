from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from hym.runtime.context import AppContext
from hym.runtime.workflow import StepOutcome


ContentHandler = Callable[[AppContext], StepOutcome]


@dataclass(frozen=True, slots=True)
class ContentTask:
    """统一处理内容跳过开关，具体内容行为由注入的处理器负责。"""

    handler: ContentHandler

    def run(self, context: AppContext) -> StepOutcome:
        if bool(context.option("skip_content", False)):
            return StepOutcome.skipped("配置为跳过内容浏览")
        return self.handler(context)
