"""各 App 独立的业务流程与页面标记声明。"""

from hym.apps.app_specs.douyin import douyin_spec
from hym.apps.app_specs.kuaishou import kuaishou_spec
from hym.apps.app_specs.qutoutiao import qutoutiao_spec
from hym.apps.app_specs.ximalaya import ximalaya_spec

__all__ = ("kuaishou_spec", "douyin_spec", "qutoutiao_spec", "ximalaya_spec")
