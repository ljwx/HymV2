"""各 App 独立的业务流程与页面标记声明。"""

from hym.apps.app_specs.baidu_lite import baidu_lite_spec
from hym.apps.app_specs.douyin import douyin_spec
from hym.apps.app_specs.fanqie_audio import fanqie_audio_spec
from hym.apps.app_specs.fanqie_novel import fanqie_novel_spec
from hym.apps.app_specs.kuaishou import kuaishou_spec
from hym.apps.app_specs.qutoutiao import qutoutiao_spec
from hym.apps.app_specs.toutiao_lite import toutiao_lite_spec
from hym.apps.app_specs.wukong_browser import wukong_browser_spec
from hym.apps.app_specs.ximalaya import ximalaya_spec

__all__ = (
    "kuaishou_spec",
    "douyin_spec",
    "qutoutiao_spec",
    "ximalaya_spec",
    "fanqie_novel_spec",
    "toutiao_lite_spec",
    "fanqie_audio_spec",
    "baidu_lite_spec",
    "wukong_browser_spec",
)
