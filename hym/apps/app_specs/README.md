# App 业务规格维护说明

每个 App 的真实流程、任务限制和匹配标记都放在同名 Python 文件顶部。修改前先核对该说明，
修改后把新观察到的页面分支和证据一起补进去，不要只改代码而不记录真实场景。

## 先判断改哪一层

| 真实变化 | 修改位置 | 是否需要改公共执行器 |
| --- | --- | --- |
| 同一个按钮换了 ID 或文案 | 原 `target(...)` 内新增 locator | 不需要 |
| 同一个页面多了一种可靠特征 | 对应页面 marker 的原 `target(...)` 内新增 locator | 不需要 |
| 多了一种广告、普通内容或长内容标记 | 对应 `*_markers` 元组新增 target | 不需要 |
| 签到多了一个页面层级或另一条路径 | `CheckInSpec.stages` 新增 `CheckInStageSpec` | 不需要 |
| 多了启动弹窗或首页拦截 | `launch_intercepts` 或 `home_intercepts` 新增 `PopupDismissSpec` | 不需要 |
| 请求获取已安装应用列表等非必要系统权限 | 先复用公共拒绝策略；只有 App 特殊文案才在本 App 增加精确弹窗标记 | 通常不需要 |
| 重复点击已选中的首页会刷新或切换模式 | 对应 `NavigationSpec` 设置 `reselect_home_tab=False` | 不需要改公共执行器 |
| App 的某一个任务机制不同 | 本 App 文件实现任务并替换 `DailyTaskSet` 对应字段 | 不需要改公共执行器 |
| App 的任务集合或顺序完全不同 | 本 App 文件实现工作流构建器并调用 `create_custom_plugin` | 不需要改公共执行器 |
| 出现视频、新闻、音频之外的新内容形态 | 新增内容策略及处理器 | 需要先按真实流程设计 |

公共权限策略不会自动同意任何权限。App 自绘权限弹窗必须有明确权限标记才会点拒绝；系统权限弹窗必须先确认前台属于系统权限控制器。某个奖励流程确实依赖权限时，不要把“允许”塞进公共层，先记录真实路径并确认取舍。

## target 和 locator

`target` 表示一个业务目标，例如“快手立即签到”。它里面的多个 locator 是备选关系，
命中任意一个就认为找到了同一个目标：

```python
target(
    "快手立即签到",  # 稳定业务名称，会进入日志，不要随意改名
    id_locator("新版签到按钮ID", prefix + "new_sign_button"),
    text_locator("签到按钮文本", "立即签到"),
    ocr_locator("签到按钮OCR", "立即签到", mode="exact"),
)
```

如果只是按钮从 `old_sign_button` 改成 `new_sign_button`，应该在同一个 target 内追加
`id_locator`，不要新建一个签到阶段。旧标记可以继续保留，除非已有充分实测证明它会误点。

`target_id` 是定位日志和历史命中策略的关联键：同一业务目标不要改名，不同业务目标不要复用。
注册表会拒绝两个 App 使用相同的 `target_id`，所以新增 App 时应带上 App 名称前缀。locator 的
策略名称也应保持稳定，但同一目标新增策略不需要修改 `target_id`。

`id_locator` 必须填写完整 resource-id。各 App 文件已定义 `prefix`，通常写成：

```python
id_locator("新版金币入口ID", prefix + "new_coin_entry")
```

第一个字符串是定位策略名称，也会写入日志。名称应说明版本或页面含义，例如
“新版金币入口ID”，不要都写成“ID1”。

定位优先级数字越小越先尝试；某台设备上次成功的策略会在下一次优先复用。默认顺序是：
ID 10、文字/描述 20、正则 30、结构 60、图片 70、OCR 80、固定坐标 200。
一般不需要手工填写 priority。固定坐标只适合作为已经校准的最后兜底，不能单独用来识别页面。

## 页面标记

页面不能只靠一个容易重复的按钮判断。`PageSpec` 会同时检查包名、Activity、正向标记和排除标记：

```python
PageSpec(
    "example.home",
    package_name,
    (home_marker, feed_marker),
    forbidden_markers=(task_marker,),
    activity_patterns=(r"MainActivity$",),
    minimum_markers=2,
)
```

上例要求两个正向标记都命中，并且不能命中任务页标记。新增第三个辅助标记但只要求其中两个时，
把它加入 `markers`，继续保持 `minimum_markers=2`。页面标记优先使用稳定 ID、Activity 或固定标题，
不要使用每天变化的金额、倒计时或任意文章标题作为唯一依据。

如果 App 重复点击已经选中的首页标签会刷新内容或切换展示模式，在该 App 的 `NavigationSpec`
设置 `reselect_home_tab=False`。页面已经满足 `home_page` 时会直接返回；只有未进入目标首页时，
导航才会点击一次首页标签。

## 新增签到分支

签到阶段不是固定顺序执行。执行器每次观察当前页面，从尚未执行的阶段中选择实际命中的一个：

```python
CheckInSpec(
    stages=(
        CheckInStageSpec(
            "打开签到面板",
            (text_target("去签到", "去签到"),),
            commit_action=False,  # 只是导航，不会消耗每日领取机会
        ),
        CheckInStageSpec(
            "确认领取",
            (text_target("立即签到", "立即签到"),),
            # 默认 commit_action=True，点击前写入每日检查点
        ),
    ),
    success_targets=(text_target("签到成功", "明日再来"),),
)
```

新增签到页面层级时增加 stage；同一阶段按钮换 ID 时只在原 target 内增加 locator。
真正领取奖励的阶段保持 `commit_action=True`，纯导航阶段必须写 `False`。成功标记必须是领取后
才会出现的证据，不能把签到区域容器或活动标题直接当成功。

提交动作点击前会记录“待确认”。即使进程中断或没识别到成功文案，当天也不会盲目重复点击。
因此新分支必须正确区分导航动作和提交动作。

## 新增弹窗

有明确弹窗特征时，同时声明弹窗标记和关闭目标：

```python
PopupDismissSpec(
    marker=text_target("新版邀请弹窗", "邀请好友得金币", contains=True),
    close_target=target(
        "新版邀请弹窗关闭",
        id_locator("关闭按钮ID", prefix + "invite_close"),
    ),
)
```

没有可靠弹窗标记时可以只配置关闭目标，但关闭目标本身必须足够独特，避免误点页面中的普通叉号。
启动时出现的放 `launch_intercepts`，返回首页过程中出现的放 `home_intercepts`。

“添加到桌面”一类低概率弹窗也按这个方式处理，但必须先从真机现场确认所属 App、出现页面、
弹窗标记和关闭目标。不要只凭弹窗文案猜一个全局关闭按钮，也不要增加后台轮询。运行器会在启动边界
做一次轻量检查，或在正常页面未命中时复用已有 UI 树检查拦截分支；只有结构无法识别且该目标确实
声明了视觉策略时，才允许补一次截图识别。

## 新增内容分类标记

视频类 App 的 `ad_markers`、`long_markers`、`normal_markers` 是三组不同业务分类。
例如发现新的广告 ID：

```python
ad_markers=(
    # 保留已有标记
    target("新版下载广告", id_locator("下载按钮ID", prefix + "new_download_button")),
)
```

新广告标记只能放进 `ad_markers`。同一个页面同时命中广告和普通标记时，广告分类优先，
并禁止点赞、关注、评论和进入主页。无法分类的视频按该 App 配置选择保守观看或疑似广告短暂停留，
默认不互动。

新闻类 App 的新列表项 ID 放进 `feed_item`，新详情页特征放进 `detail_marker`。
只有打开后命中详情标记才计为成功浏览，避免把广告卡片或无效卡片算作文章。

## 新增 App 独有任务

只有现有签到、余额、时段奖励、广告和内容规格确实无法表达时，才增加专用代码。
每个 App 文件底部都有 `create_plugin()`，注册表只调用它。单独增加一个任务时，通过组合函数注入：

```python
from hym.apps.plugin import create_daily_plugin
from hym.core.control import TaskScope
from hym.runtime.workflow import StepDefinition, StepOutcome


def run_unique_task(context):
    # 在这里按真实页面状态执行，成功、跳过和失败必须明确返回。
    return StepOutcome.skipped("当前没有可执行的快手独有任务")


def extra_steps(context):
    return (
        StepDefinition(
            "快手独有任务",
            "执行快手独有任务",
            run_unique_task,
            task_scope=TaskScope.FULL_ONLY,
        ),
    )


def create_plugin():
    return create_daily_plugin(kuaishou_spec(), extra_steps=extra_steps)
```

`extra_steps` 位于余额和提现之前，适合 App 独有的领奖、浏览等业务。必须在所有业务之后执行的停止播放、
关闭会话等收尾步骤使用 `cleanup_steps`；不要再包装一层工作流只为追加最后一步：

```python
def create_plugin():
    return create_daily_plugin(
        example_spec(),
        cleanup_steps=lambda _: (
            StepDefinition(
                "停止应用",
                "停止后台播放",
                stop_playback,
                task_scope=TaskScope.CLEANUP,
            ),
        ),
    )
```

单个已有任务不同，使用 `create_daily_task_set()` 得到默认集合，再用 `dataclasses.replace()`
替换 `check_in`、`balance`、`duration_reward`、`ad_reward` 或 `content`。如果任务集合和顺序都不同，
在 App 文件实现带 `build(context)` 的工作流构建器，并通过 `create_custom_plugin()` 注册；不需要继承
公共插件。不可重复的新任务要像签到一样在点击前记录每日动作检查点，不能只在成功后记录。

需要从 KMP 控制台单独执行的步骤应声明 `task_scope`：主线、签到、余额和广告分别使用
`MAIN`、`CHECK_IN`、`BALANCE`、`AD_REWARD`；启动准备使用 `SETUP`，必须执行的收尾使用 `CLEANUP`。
只在完整流程运行的 App 独有任务保持默认 `FULL_ONLY`。这一分类只描述业务语义，不改变 App 自己的页面分支。

例如只有签到机制不同，其他任务继续复用：

```python
from dataclasses import replace

from hym.apps.plugin import create_daily_plugin, create_daily_task_set
from hym.runtime.navigation import NavigationController


def create_plugin():
    spec = example_spec()
    navigation = NavigationController(spec)
    tasks = create_daily_task_set(spec, navigation=navigation)
    tasks = replace(tasks, check_in=run_example_check_in)
    return create_daily_plugin(spec, navigation=navigation, tasks=tasks)
```

`run_example_check_in(context)` 只属于该 App，返回统一的 `StepOutcome`。以后发现新签到路径时只改
这个 App 文件；公共签到组件和其他 App 不受影响。

内容首页和带底栏主页面不是同一页时，在该 App 的 `NavigationSpec` 设置
`select_home_tab_before_task=False`。公共导航会先恢复主页面再进入任务页，不需要复制任务页导航器。

## 当前新增 App 的维护入口

| App ID | 文件 | 主线与独有分支 |
| --- | --- | --- |
| `fanqie_novel` | `fanqie_novel.py` | 横向翻页阅读；欢迎红包、签到红包弹窗 |
| `toutiao_lite` | `toutiao_lite.py` | 新闻阅读；低概率小说奖励、多种任务弹窗 |
| `fanqie_audio` | `fanqie_audio.py` | 长时收听；结束后强制停止应用 |
| `baidu_lite` | `baidu_lite.py` | 短视频；签到前单次上滑、到账弹窗 |
| `wukong_browser` | `wukong_browser.py` | 短视频/短剧；任务页自动每日领取、时段奖励 |

内容数量、停留时长和奖励概率优先改 `config/automation.json` 对应 App 块；页面文案、ID、坐标或流程分支只改表中对应文件。不要为了某一个 App 的偶发页面去修改公共导航、定位或任务执行器。

## 修改后的检查

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m hym --check-config
.venv/bin/python -m hym --list-apps
codegraph sync
```

单元测试通过只表示声明结构和公共逻辑没有被破坏，不表示新标记一定适配真机。新分支仍需要在
真实页面上快速验证，并把命中的 `target_id`、`strategy_id`、页面截图和 UI 树作为校准依据。
