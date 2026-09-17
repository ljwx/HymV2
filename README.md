# HymV2

面向 Android 内容应用的可扩展自动任务运行器。当前内置并启用快手极速版、抖音极速版、趣头条和喜马拉雅极速版，覆盖短视频、新闻和长时音频三类内容。

```bash
# 只校验配置，不连接设备
.venv/bin/python -m hym --check-config

# 查看已注册插件
.venv/bin/python -m hym --list-apps

# 每个启用的 App 执行一轮
.venv/bin/python -m hym --once

# PyCharm 可直接运行根目录 main.py；调试单轮时添加参数 --once --direct

# 手工操作新流程，并记录每一步前后的页面证据
.venv/bin/python -m hym --record-flow "新奖励流程" --record-app kuaishou
```

项目边界和验收标准见 [项目目的与要求](docs/project-requirements.md)，运行参数、调速方式和故障材料位置见 [使用说明](docs/usage.md)，分层与扩展方式见 [架构说明](docs/architecture.md)，补充 App 标记和流程见 [App 业务规格维护说明](hym/apps/app_specs/README.md)。新架构入口统一为 `python -m hym`，旧的 `launch/AppLaunch.py` 仅保留作行为参考。

微信朋友圈、零钱记录和指定好友聊天使用独立入口：

```bash
./wechat_automation/run_wechat.sh --check-config
./wechat_automation/run_wechat.sh
```

聊天默认不会真实发送，配置方式和隐私边界见 [微信操作说明](wechat_automation/README.md)。
