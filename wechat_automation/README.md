# 微信基本操作

该目录提供独立的微信操作入口，复用 Hym 的设备连接、原生 UI 定位、中文日志和失败诊断能力。

当前微信版本没有暴露可用 UI 树，因此查看流程采用 Activity、macOS Vision OCR 和已校准归一化坐标组合；OCR 只用于固定导航入口，不用于动态内容操作。

默认执行查看朋友圈和记录零钱页面，运行前应确保微信已经登录。聊天真实发送默认关闭，配置好友后可先用预览模式验证只会进入正确的聊天页。

```bash
./wechat_automation/run_wechat.sh --check-config
./wechat_automation/run_wechat.sh
```

编辑 `config/wechat.local.json`：

- `behavior.timing_scale` 统一调整操作节奏，小于 `1` 更快，大于 `1` 更慢。
- `moments.swipes_min`、`swipes_center`、`swipes_max`、`swipes_stddev` 控制朋友圈滑动次数；对应的 `pause_min_seconds`、`pause_center_seconds`、`pause_max_seconds`、`pause_stddev_seconds` 控制每次停留。
- `wallet.capture_once_per_day` 控制零钱页面每天是否只记录一次。
- `chat.friend_name` 填写微信中的准确好友名称。
- 先设置 `chat.enabled=true`、`chat.send=false` 验证能否进入正确聊天。
- 确认后设置 `chat.send=true`，每次从 `message_groups` 随机选一组，最多发送两条。
- `chat.interval_min_seconds`、`interval_center_seconds`、`interval_max_seconds`、`interval_stddev_seconds` 控制两条消息之间的有界正态等待；聊天默认关闭。

零钱截图、页面结构和执行日志保存在公共配置指定的 `runtime/` 目录。它们可能包含隐私信息，只应保存在可信设备；Hym 业务日志不会写入好友名、消息正文或零钱金额，Airtest/Poco 的命令调试日志也会被关闭。

流程不会输入支付密码、验证码，也不会执行转账、提现或付款。好友匹配不唯一或聊天标题不一致时会停止发送；普通步骤连续失败达到公共诊断阈值后才保存现场。

朋友圈流程只停留和滑动，不点赞、不评论。个人微信使用时建议保持 `chat.enabled=false`。
