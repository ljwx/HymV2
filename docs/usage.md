# 使用说明

PyCharm 可直接运行根目录 `main.py`，流程日志会实时显示在 Run 控制台。调试单轮时在
运行参数中添加 `--once --direct`；正式多设备运行不加 `--direct`。

## 运行前准备

1. 打开手机的 USB 调试，执行 `adb devices` 确认设备在线。
2. 在 `config/automation.json` 中填写设备序列号；`device_id` 用于日志和状态隔离，`connection` 是实际连接串。
3. 确保当前 Python 环境已经安装项目原来使用的 Airtest、Poco 依赖。图片定位还需要 OpenCV；OCR 默认关闭，启用时需要额外安装 PaddleOCR。

先执行不接触手机的检查：

```bash
.venv/bin/python -m hym --check-config
.venv/bin/python -m hym --list-apps
```

单轮运行适合首次验证：

```bash
.venv/bin/python -m hym --once
```

持续运行时去掉 `--once`。多台设备会各自运行在独立进程中，单台设备异常退出不会打断其他设备：

```bash
.venv/bin/python -m hym
```

只运行某台设备可重复使用 `--device`，只验证某个 App 可重复使用 `--app`；`--direct` 不创建工作进程，仅用于单设备调试：

```bash
.venv/bin/python -m hym --once --device NAB0220416035468
.venv/bin/python -m hym --once --direct --device NAB0220416035468
.venv/bin/python -m hym --once --direct --device NAB0220416035468 --app kuaishou
```

## 常用配置

配置优先级为“全局 `behavior` < 设备 `behavior` < App `behavior`”，因此可以统一调速，也可以只调整某台设备或某个 App。

- `timing_scale`：普通等待总倍率，`0.6` 会把基准 5 秒缩短到约 3 秒。
- `jitter_ratio`：没有独立范围的固定等待所使用的随机浮动比例；设为 `0` 时只做固定倍率缩放。
- `operation_delay_min/center/max/stddev`：点击、返回、切页后的短等待分布。
- `app_rest_seconds_min/center/max/stddev`：一个 App 完整结束后、下一个 App 启动前的桌面休息分布；当前为 4～8 分钟、中心值 6 分钟。
- `reward_wait_scale`：广告奖励等待的独立倍率，避免普通调速导致奖励计时不足。
- `touch_offset_ratio`：在目标内部加入很小的点击位置浮动。
- `health_check_interval_seconds`：默认 `0`，表示不额外轮询设备；操作失败时才触发重连。无线调试不稳定时可以改为较大的正数。
- `enable_ocr`：默认 `false`。OCR 只作为目标自身声明的后备定位，不会对每次操作全屏识别。
- `console_level` / `jsonl_level`：分别控制控制台与结构化日志级别，可选 `debug`、`info`、`warning`、`error`。
- `consecutive_failure_threshold`：同一设备、App、工作流和步骤连续失败多少次后保存现场，默认 3。

同一种失败连续出现时只保存一次现场；步骤恢复成功后才重新计数，避免截图目录持续增长。

顶层 `interruptions` 控制任务插空，不属于某个 App 的业务配置：

- `enabled`：是否启用安全点插空。
- `checkpoint_probability`：每个安全点触发插空的概率。
- `desktop_pause_probability`：触发后返回桌面的概率；其余情况切换到另一个未完成 App。
- `desktop_wait_seconds_min/center/max/stddev`：桌面随机停留时间分布。
- `min_interval_seconds`：两次插空的最短间隔。
- `max_per_cycle`：同一设备单轮最多插空次数；达到上限后直接完成剩余任务。

插空只在完整内容或独立步骤结束后检查一次，不增加 UI 轮询、截图或 OCR。运行中的视频、新闻和音频进度可以续跑；广告计时、签到提交和奖励领取过程中不会插空。只有一个待办 App 时，App 切换请求会自动改为桌面停留。

App 间休息与随机插空相互独立。只有一个 App 的工作流完整结束且仍有待执行 App 时，系统才返回桌面并按 `app_rest_seconds_*` 等待；临时插空切换不触发，最后一个 App 结束后也不会再等待。

每个 App 的 `options` 负责业务差异，常用项包括：

- `first_check_in_probability`：签到放在内容浏览前的概率，其余情况放在内容浏览后。
- `content_count_min/center/max/stddev`：每轮浏览内容数量分布。
- `normal_duration_min/center/max/stddev`、`long_duration_min/center/max/stddev`：普通和长视频浏览时长分布。
- `auto_advance_probability`：短剧播放器自动续播时，不额外上滑并继续停留观察的概率。
- `uninterested_video_probability`：普通视频低概率快速划过的比例，当前默认 `0.08`。
- `full_watch_attempt_probability`：普通视频进入较长完整观看尝试的比例，当前默认 `0.25`。
- `uninterested_duration_*`、`full_watch_fallback_duration_*`：快速划过和完整观看尝试各自的时长分布。
- `treat_unclassified_as_suspected_ad`：视频流存在但关键分类标记均未命中时，是否按疑似广告快速划过。快手已有真机推广证据，当前开启；抖音普通标记覆盖不足，当前关闭并按未分类内容保守浏览。
- `suspected_ad_duration_*`：疑似广告的短暂停留分布，和明确广告、普通视频分别配置。
- `normal/full_watch/long/unclassified_post_classification_min_seconds`：完成内容分类后至少继续停留多久，避免识别结束后立刻滑走。
- `like_probability`、`comment_probability`、`works_probability`：点赞、查看评论、浏览作者作品的概率。
- `follow_probability`：关注作者的概率，默认 `0.002`，可按 App 独立调整。
- `read_to_bottom_probability`：新闻是否继续阅读到底部的概率。
- `execute_ad_probability`、`ad_task_count_min/center/max/stddev`：是否执行广告任务及单轮次数。
- `ad_entry_search_swipes`：广告入口不在当前屏幕时最多向上查找几次，默认 2。
- `ad_extra_rounds_min/center/max/stddev`：奖励弹窗明确支持续看时，随机追加的广告轮数；只对已实测支持该分支的 App 配置。
- `ad_completion_check_interval_seconds_min/center/max/stddev`：广告完成信号的低频检查间隔。
- `ad_completion_settle_seconds_min/center/max/stddev`：确认广告完成后继续停留的时间；当前为 `1~10` 秒、中心值 `5` 秒。
- `ad_fallback_wait_seconds`：没有可靠完成信号或在时限内始终未命中时的奖励等待兜底。
- `allow_interruptions`：是否允许当前 App 参与安全点插空；长时任务可按真实规则单独关闭。
- `stop_app_probability`：轮次内部完成单个 App 后立即停止它的概率。整轮结束时仍会统一停止本轮涉及的所有 App，并锁定屏幕。
- `skip_content`：临时跳过该 App 的内容浏览。
- `audio_session_seconds_min/center/max/stddev`：长时音频单轮保持播放的时长分布，会应用 `timing_scale`。
- `audio_check_interval_seconds`：音频会话低频确认前台状态的间隔，最小 15 秒。

所有用户行为相关的任务次数和时长范围统一支持四个参数：`*_min`、`*_center`、`*_max`、`*_stddev`。系统以 `center` 为正态分布中位数，极端值会被限制在边界内，`stddev` 越小越集中在中心附近。只写 `min/max` 时会自动使用范围中点和 `(max-min)/6`，旧配置仍可运行。范围采样只做一次，不再叠加 `jitter_ratio`；应用 `timing_scale` 后，结果不会越过同比缩放的边界。定位超时、失败重试次数和奖励保底计时仍按确定性边界执行，不属于模拟用户节奏。

所有以 `_probability` 结尾的值必须在 0 到 1 之间，所有 `*_min/max`、中心值和标准差会在启动前校验。概率仍按独立事件判断，不使用正态分布。随机节奏用于流程多样性，不承诺规避应用的风控规则。

激励广告优先低频检查 App 已声明且真机确认过的完成信号。命中后按完成停留分布再等一小段时间，然后执行退出；没有可靠信号或始终未命中才等待 `ad_fallback_wait_seconds`。正常轮询只取完成标记需要的数据，不额外执行全屏 OCR。

当前快手的 `milano_player_seekbar` 只暴露控件位置和尺寸，没有进度值、最大值或总时长。系统因此不会声称精确看完，而是按概率执行较长的“完整观看尝试”。当前普通视频约 8% 停留 `3~7` 秒、67% 停留 `10~30` 秒、25% 尝试停留 `25~65` 秒；明确广告停留 `0.5~2.5` 秒，疑似广告停留 `1~4` 秒。日志中的 `classification_kind`、`classification_reason`、`watch_mode`、`planned_duration_seconds`、`classification_seconds` 和 `post_classification_wait_seconds` 可以还原每条视频为何在该时间切换。未来某个版本若暴露可靠结束标记，再按“结果优先、超时兜底”接入，不使用高频截图猜进度。

每条视频从滑动开始计时。先按对应范围的正态分布生成计划时长，再计算“计划时长减去分类耗时”；同时保证分类完成后至少继续停留配置的最短时间，两者取较大值。抖音当前多数内容因缺少稳定普通视频标记而使用未分类策略：按普通观看节奏计划 `10~30` 秒、中心值 `18` 秒，分类完成后至少再停留 `5` 秒，并且默认不互动；明确广告仍使用 `0.5~2.5` 秒。修改抖音 `unclassified_duration_*` 即可单独调整这类视频，不影响快手。

## 记录新流程

发现新的奖励入口或页面分支时，可以先用手动流程记录器保存事实，不必先写代码：

```bash
.venv/bin/python -m hym --record-flow "快手新奖励" --record-app kuaishou --device 23a6524e
```

命令会先保存初始页面。每在手机上完成一步操作，就在终端输入一句说明，例如“点击去领取”并回车；系统随后保存当前 Activity、UI 树、截图、候选定位标记，以及相对上一步新增和消失的节点。输入 `:done` 正常结束，输入 `:cancel` 取消但保留已有证据，直接回车会保存“未说明操作”的检查点。

记录保存在 `runtime/artifacts/<设备ID>/手动流程/<记录ID>/manifest.json`，各步骤的页面结构和截图由清单中的绝对路径引用。清单每一步原子更新，记录过程中断时已完成的步骤不会丢失。它不能从物理触摸中可靠推断业务意图，因此操作说明仍应写清楚；页面截图和 UI 文本可能含隐私信息，不要在私人聊天页面使用或对外发送未经检查的记录。

## 日志与诊断

默认文件位置：

```text
runtime/
  logs/<设备ID>.jsonl
  state/<设备ID>.json
  artifacts/<设备ID>/<日期>/
    页面结构/*.json
    页面截图/*.png
    执行上下文/*.json
  artifacts/<设备ID>/手动流程/<记录ID>/
    manifest.json
    现场/<日期>/{页面结构,页面截图,执行上下文}/
```

控制台日志使用中文，`事件码` 保留稳定英文值，便于筛选。例如：

```bash
rg 'workflow.finished|workflow.suspended|runtime.interruption|diagnostic.threshold.reached|app.failed' runtime/logs
```

步骤偶发失败只记录结果并执行有限恢复。同一步骤以相同原因连续失败达到阈值后，系统才保存截图、当前 UI 树、链路信息和最近 50 次定位尝试；失败原因改变时重新计数。排查时提供同一时间段的 JSONL，以及 `artifacts` 中对应的三类文件即可。

每日签到和余额状态保存在 `runtime/state`。签到点击前会先保存动作检查点；若点击后无法确认结果，当天不会盲目重复点击。余额只有成功定位并记录后才会标记为当日完成；随机位置记录失败时，流程收尾还会再尝试一次。业务日期在一轮开始时冻结，跨午夜的长流程不会在同一轮切换状态日期。

快手任务页当前以“底栏容器 + 首页标签”共同区分首页，作者主页仅保留底栏容器时会先恢复再执行奖励任务。独立广告优先点击“领福利”，任务标题“看广告得金币”只作为备用入口。签到、余额页和时段奖励的页面稳定时间分别保留在 `hym/apps/app_specs/kuaishou.py`，只调整快手即可，不影响其他 App 或公共导航。

同一设备不能同时运行普通任务和微信任务。后启动的进程会输出 `runtime.device.busy` 并退出，避免两个 Poco 会话交叉点击。

## 上报到 JDCR Server

运行数据默认只写本地。需要在 JDCR KMP App 中查看时，开启顶层 `reporting`：

```json
{
  "reporting": {
    "enabled": true,
    "server_url": "http://192.168.1.10:8080",
    "ingest_key_env": "JDCR_AUTOMATION_INGEST_KEY",
    "ingest_key_file": "~/.config/hymv2/automation-ingest-key",
    "level": "info",
    "batch_size": 100,
    "timeout_seconds": 10.0,
    "retry_interval_seconds": 30.0,
    "upload_artifacts": true,
    "control_enabled": true,
    "control_timeout_seconds": 1.0,
    "control_poll_interval_seconds": 10.0
  }
}
```

上报密钥优先从 `ingest_key_env` 指定的环境变量读取；环境变量为空时，再读取 `ingest_key_file`。本机长期运行建议把 Server 的写入密钥保存到用户配置目录，并限制文件权限：

```bash
mkdir -p ~/.config/hymv2
install -m 600 /path/to/automation-ingest-key ~/.config/hymv2/automation-ingest-key
.venv/bin/python -m hym --once
```

也可以不配置密钥文件，只在启动前执行 `export JDCR_AUTOMATION_INGEST_KEY="服务端上报密钥"`。写入密钥只用于上报，不能读取 Server 数据，也不要直接写进配置文件。事件先追加到 `runtime/report_queue/<设备ID>.jsonl`，本轮结束时按 `batch_size` 分批发送。网络失败、服务不可用或证据上传失败不会中断 App 任务，本地队列会保留；失败后至少等待 `retry_interval_seconds` 才再试，避免断网时每条事件都消耗超时。事件以 `event_id` 去重。

`upload_artifacts` 开启后，达到重复失败阈值产生的截图、UI 树和执行上下文会跟随事件上传。正常流程不会为上报额外截图。Android App 登录同一 Server 后，从“设置 > 数据 > 运行中心”查看今天或近 7 天的数据。“执行”页的当天总表按 App 展示启动次数、确认奖励次数、总耗时、签到状态、余额和提现门槛；“微信资产”页展示零钱和最近 10 笔去重账单。从第二个业务日起，余额行会显示“较昨日”；中间日期缺失时显示“较上次”。

支持提现信息的 App 默认每天只读打开一次提现页，单次截图只执行一次 OCR，并上报可提现金额、最低门槛和是否达标。运行中心按 App 中文名称展示最近快照；采集周期可在 App 的 `WithdrawalSpec.refresh_days` 调成两天。流程不会保存整页 OCR 文本，也不会点击提现、兑换、支付或银行卡相关按钮。

“确认奖励次数”只统计已经命中结果证据的签到、广告完成和通用领奖事件。普通内容浏览、仅点击奖励按钮、未命中完成信号的兜底等待均不计数。统计复用流程已经获得的结果，不增加截图、OCR、页面轮询或等待；运行中只多追加一条很小的本地事件，仍在整轮结束时批量上报。

### KMP 设备控制台

持续运行时不要添加 `--once`。运行中心的“控制”页可以按设备暂停/继续，或下发单 App 完整任务、签到、余额、广告奖励、主线任务，以及全部 App 的多轮完整任务。单 App 只显示它已经上报的能力；新增 App 的任务步骤需要声明对应 `task_scope`。

暂停只在步骤结束或内容单元安全点生效，不会截断正在播放的奖励广告或正在提交的签到动作。进入暂停后设备返回桌面，再次点击继续即可恢复；即使没有手动继续，45 分钟后也会自动恢复。控制状态每 5 秒低频读取，单次网络超时默认 1 秒，Server 不可用时按 `retry_interval_seconds` 退避，不增加截图、OCR 或 UI 树读取。

任务命令使用服务端持久队列。运行器在一轮任务结束后领取下一条命令；单 App 命令从启动步骤重新执行，全部 App 按配置顺序执行，应用之间仍保留配置的休息时间。命令状态会显示为排队中、执行中、已完成或失败。

## 趣头条

趣头条使用独立新闻工作流，包括随机文章、随机阅读到底部、点赞和查看评论，不发布评论。签到、余额和随机文章已有真机成功记录；最新整轮发现的两类广告 SDK Activity 已加入广告开始标记，待设备重连后复验退出链路。旧目录中的趣头条代码不会被新入口导入。

## 喜马拉雅

喜马拉雅使用长时音频会话，不按视频方式逐条滑动。当前只负责从首页恢复播放、低频确认前台状态和有限恢复，奖励入口尚未配置。短音频会话已有真机成功记录；最新长会话发现 App 返回后可能自动续播，恢复逻辑现同时接受“正在播放”和“开始播放”状态，待设备重连后复验。

## 新增五个 App

- `fanqie_novel`：主线为随机小说横向翻页，`novel_pages_*` 和 `novel_page_seconds_*` 控制页数与每页停留；阅读页优先按 `ReaderActivity` 确认，签到、余额和低概率广告仍走任务页。
- `toutiao_lite`：主线为新闻阅读，另以较低概率执行小说奖励；文章数量和阅读滑动由 `news_*` 参数控制。
- `fanqie_audio`：主线为长时收听，使用 `audio_session_seconds_*` 和低频检查参数；无论中间步骤是否成功，完整流程结束都会停止应用，避免后台继续播放。
- `baidu_lite`：主线为短视频，另执行签到、余额和广告奖励。当前版本签到入口需要在任务页向上滑动一次，这个分支只在百度文件中处理。
- `wukong_browser`：主线为短视频/短剧，另执行每日领取、时段奖励、余额、已达标待领取奖励和低概率广告；只认明确的领取结果或已完成状态，不把普通“今日”文案当成成功。

这些 App 已加入默认注册表和设备配置，可通过 `--app <app_id> --once --direct` 单独验证。视频、新闻、小说和音频的数量或时长都由各 App 配置独立控制；想提高收益时先调对应配置，不需要修改公共任务代码。

## 增加 App

新 App 通常只需要：

1. 在 `hym/apps/app_specs/` 新建该 App 的独立文件，在文件头写明每日流程、任务限制和匹配标记，再声明页面目标、导航、奖励和内容类型。
2. 在 `hym/apps/registry.py` 注册插件工厂。
3. 在配置文件的设备下加入 `app_id` 和业务参数。

默认视频、新闻和音频任务由 `create_daily_plugin()` 按内容规格组合。某个 App 的单项流程不同，可以在该 App 文件创建自己的任务并替换 `DailyTaskSet` 对应字段；整体流程不同则使用 `create_custom_plugin()` 注入独立工作流，不需要修改设备连接、事件、诊断或多进程代码。

已有 App 的 ID、文案、页面分支和独有任务如何维护，见 [`hym/apps/app_specs/README.md`](../hym/apps/app_specs/README.md)。每个 App 文件底部拥有自己的 `create_plugin()`；新增 App 只需在注册表增加一次工厂，后续流程变化保持在该 App 文件和配置块内。

App 和页面通过 `ObservationProfile` 选择应用界面树（`application`）或系统界面树（`system`），特殊目标仍可单独覆盖。同一 App 可以按页面混用。具体由 Airtest/Poco、Appium 或无障碍采集，由适配器负责映射；业务规格不感知驱动。OCR、图片和坐标是后备定位策略，不会默认参与每一次页面判断。

启动或恢复时若出现非必要系统权限，框架默认拒绝；“获取其他已安装应用”一类 App 自绘弹窗必须同时匹配权限文案和拒绝按钮。只有前台是系统权限控制器时才额外读取一次原生 UI 树，因此没有弹窗时不会增加截图或 OCR 成本。首次隐私协议、登录授权和确实影响奖励的必要权限仍由人工确认。
