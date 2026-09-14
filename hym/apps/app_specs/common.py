"""App 规格声明使用的少量公共常量和目标构造器。"""

from __future__ import annotations

from hym.apps.targets import ocr_locator, target, text_locator
from hym.core.targets import TargetSpec

TEXT = "android.widget.TextView"
BUTTON = "android.widget.Button"
IMAGE = "android.widget.ImageView"
GROUP = "android.view.ViewGroup"
FRAME = "android.widget.FrameLayout"
RECYCLER = "androidx.recyclerview.widget.RecyclerView"


def text_target(
    target_id: str,
    text: str,
    *,
    contains: bool = False,
    required: bool = False,
    ui_tree_source: str | None = None,
) -> TargetSpec:
    """优先匹配文字节点，结构树不可用时再用 OCR 补充。"""

    return target(
        target_id,
        text_locator(f"{target_id}-Poco", text, contains=contains),
        ocr_locator(
            f"{target_id}-OCR",
            text,
            mode="contains" if contains else "exact",
        ),
        required=required,
        metadata={"ui_tree_source": ui_tree_source} if ui_tree_source else None,
    )
