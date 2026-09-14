"""兼容旧导入；新的 App 业务规格统一放在 app_specs 独立文件中。"""

from hym.apps.app_specs import douyin_spec, kuaishou_spec, qutoutiao_spec, ximalaya_spec

__all__ = ("kuaishou_spec", "douyin_spec", "qutoutiao_spec", "ximalaya_spec")
