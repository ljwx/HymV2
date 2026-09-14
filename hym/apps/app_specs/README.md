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
| App 出现现有模型完全表达不了的独有任务 | 本 App 文件增加插件子类并实现 `build_app_steps` | 不需要改公共执行器 |
| 出现视频、新闻、音频之外的新内容形态 | 新增内容策略及处理器 | 需要先按真实流程设计 |

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
并禁止点赞、关注、评论和进入主页。无法分类的视频默认只短暂停留且不互动。

新闻类 App 的新列表项 ID 放进 `feed_item`，新详情页特征放进 `detail_marker`。
只有打开后命中详情标记才计为成功浏览，避免把广告卡片或无效卡片算作文章。

## 新增 App 独有任务

只有现有签到、余额、时段奖励、广告和内容规格确实无法表达时，才增加专用代码。
每个 App 文件底部都有 `create_plugin()`，注册表只调用它。可以在同一文件中这样扩展：

```python
from hym.runtime.workflow import StepDefinition, StepOutcome


class KuaishouPlugin(ConfiguredAppPlugin):
    def build_app_steps(self, context):
        return (
            StepDefinition(
                "快手独有任务",
                "执行快手独有任务",
                self._run_unique_task,
                recovery=self._recover_home,
            ),
        )

    def _run_unique_task(self, context):
        # 在这里按真实页面状态执行，成功、跳过和失败必须明确返回。
        return StepOutcome.skipped("当前没有可执行的快手独有任务")


def create_plugin():
    return KuaishouPlugin(kuaishou_spec())
```

`build_app_steps` 返回的步骤默认放在公共奖励任务之后，余额仍可能随机插入。步骤失败后会沿用
公共链路日志、连续失败诊断和恢复机制。不可重复的新任务要像签到一样在点击前记录每日动作检查点，
不能只在成功后记录；这类任务最好先结合真实页面设计，不要凭空抽象。

## 修改后的检查

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m hym --check-config
.venv/bin/python -m hym --list-apps
codegraph sync
```

单元测试通过只表示声明结构和公共逻辑没有被破坏，不表示新标记一定适配真机。新分支仍需要在
真实页面上快速验证，并把命中的 `target_id`、`strategy_id`、页面截图和 UI 树作为校准依据。
