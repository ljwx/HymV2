"""微信基本操作的独立入口。"""

from wechat_automation.config import WechatSettings, load_wechat_settings
from wechat_automation.plugin import WechatPlugin

__all__ = ["WechatPlugin", "WechatSettings", "load_wechat_settings"]
