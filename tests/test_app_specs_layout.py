import importlib
import unittest
from dataclasses import replace
from types import SimpleNamespace

from hym.apps import catalog
from hym.apps.app_specs import (
    baidu_lite_spec,
    douyin_spec,
    fanqie_audio_spec,
    fanqie_novel_spec,
    hema_theater_spec,
    kuaishou_spec,
    qutoutiao_spec,
    toutiao_lite_spec,
    wukong_browser_spec,
    xifan_theater_spec,
    ximalaya_spec,
)
from hym.apps.app_specs.baidu_lite import create_plugin as create_baidu_lite_plugin
from hym.apps.app_specs.douyin import create_plugin as create_douyin_plugin
from hym.apps.app_specs.fanqie_audio import create_plugin as create_fanqie_audio_plugin
from hym.apps.app_specs.fanqie_novel import create_plugin as create_fanqie_novel_plugin
from hym.apps.app_specs.hema_theater import create_plugin as create_hema_theater_plugin
from hym.apps.app_specs.kuaishou import create_plugin as create_kuaishou_plugin
from hym.apps.app_specs.qutoutiao import create_plugin as create_qutoutiao_plugin
from hym.apps.app_specs.toutiao_lite import create_plugin as create_toutiao_lite_plugin
from hym.apps.app_specs.wukong_browser import create_plugin as create_wukong_browser_plugin
from hym.apps.app_specs.xifan_theater import create_plugin as create_xifan_theater_plugin
from hym.apps.app_specs.ximalaya import create_plugin as create_ximalaya_plugin
from hym.apps.plugin import (
    ComposedAppPlugin,
    create_custom_plugin,
    create_daily_plugin,
    create_daily_task_set,
)
from hym.apps.registry import AppRegistry, create_default_registry
from hym.core.models import ActionResult, AppIdentity
from hym.runtime.navigation import NavigationController
from hym.runtime.workflow import StepDefinition, StepOutcome, WorkflowDefinition


class AppSpecLayoutTest(unittest.TestCase):
    def test_each_app_owns_an_independent_business_spec(self):
        factories = (
            (kuaishou_spec, "hym.apps.app_specs.kuaishou"),
            (douyin_spec, "hym.apps.app_specs.douyin"),
            (qutoutiao_spec, "hym.apps.app_specs.qutoutiao"),
            (ximalaya_spec, "hym.apps.app_specs.ximalaya"),
            (fanqie_novel_spec, "hym.apps.app_specs.fanqie_novel"),
            (toutiao_lite_spec, "hym.apps.app_specs.toutiao_lite"),
            (fanqie_audio_spec, "hym.apps.app_specs.fanqie_audio"),
            (baidu_lite_spec, "hym.apps.app_specs.baidu_lite"),
            (wukong_browser_spec, "hym.apps.app_specs.wukong_browser"),
            (hema_theater_spec, "hym.apps.app_specs.hema_theater"),
            (xifan_theater_spec, "hym.apps.app_specs.xifan_theater"),
        )

        for factory, module_name in factories:
            with self.subTest(module=module_name):
                self.assertEqual(factory.__module__, module_name)
                module_doc = importlib.import_module(module_name).__doc__ or ""
                self.assertIn("每日流程", module_doc)
                self.assertIn("任务", module_doc)
                self.assertIn("标记", module_doc)

    def test_legacy_catalog_reexports_the_independent_specs(self):
        self.assertIs(catalog.kuaishou_spec, kuaishou_spec)
        self.assertIs(catalog.douyin_spec, douyin_spec)
        self.assertIs(catalog.qutoutiao_spec, qutoutiao_spec)
        self.assertIs(catalog.ximalaya_spec, ximalaya_spec)
        self.assertIs(catalog.fanqie_novel_spec, fanqie_novel_spec)
        self.assertIs(catalog.toutiao_lite_spec, toutiao_lite_spec)
        self.assertIs(catalog.fanqie_audio_spec, fanqie_audio_spec)
        self.assertIs(catalog.baidu_lite_spec, baidu_lite_spec)
        self.assertIs(catalog.wukong_browser_spec, wukong_browser_spec)
        self.assertIs(catalog.hema_theater_spec, hema_theater_spec)
        self.assertIs(catalog.xifan_theater_spec, xifan_theater_spec)

    def test_each_app_owns_its_plugin_factory(self):
        factories = (
            (create_kuaishou_plugin, "kuaishou"),
            (create_douyin_plugin, "douyin"),
            (create_qutoutiao_plugin, "qutoutiao"),
            (create_ximalaya_plugin, "ximalaya"),
            (create_fanqie_novel_plugin, "fanqie_novel"),
            (create_toutiao_lite_plugin, "toutiao_lite"),
            (create_fanqie_audio_plugin, "fanqie_audio"),
            (create_baidu_lite_plugin, "baidu_lite"),
            (create_wukong_browser_plugin, "wukong_browser"),
            (create_hema_theater_plugin, "hema_theater"),
            (create_xifan_theater_plugin, "xifan_theater"),
        )

        for factory, app_id in factories:
            with self.subTest(app_id=app_id):
                plugin = factory()
                self.assertEqual(plugin.app_id, app_id)
                self.assertIs(type(plugin), ComposedAppPlugin)

    def test_app_specific_steps_can_be_added_without_changing_common_scheduler(self):
        def extra_steps(context):
            return (
                StepDefinition(
                    "应用独有任务",
                    "应用独有任务",
                    lambda _: StepOutcome.success("完成"),
                ),
            )

        plugin = create_daily_plugin(ximalaya_spec(), extra_steps=extra_steps)
        step_ids = [step.step_id for step in plugin.build_workflow(object()).steps]

        self.assertEqual(
            ["启动应用", "处理启动弹窗", "浏览内容", "应用独有任务"],
            step_ids,
        )

    def test_completely_different_app_can_supply_its_own_workflow(self):
        class CustomWorkflow:
            def build(self, context):
                return WorkflowDefinition(
                    "custom",
                    "自定义流程",
                    (
                        StepDefinition(
                            "独立步骤",
                            "独立步骤",
                            lambda _: StepOutcome.success("完成"),
                        ),
                    ),
                )

        spec_without_content = replace(ximalaya_spec(), content=None)
        plugin = create_custom_plugin(spec_without_content, CustomWorkflow())

        self.assertEqual("", plugin.spec.content_kind)
        self.assertEqual(
            ["独立步骤"],
            [step.step_id for step in plugin.build_workflow(object()).steps],
        )

    def test_app_can_replace_or_remove_individual_tasks_without_inheritance(self):
        spec = ximalaya_spec()
        navigation = NavigationController(spec)
        tasks = create_daily_task_set(spec, navigation=navigation)
        tasks = replace(
            tasks,
            content=None,
            check_in=lambda _: StepOutcome.success("自定义签到完成"),
        )
        plugin = create_daily_plugin(spec, navigation=navigation, tasks=tasks)
        context = SimpleNamespace(
            option=lambda key, default: default,
            random=SimpleNamespace(random=lambda: 0.0, randint=lambda start, end: start),
        )

        self.assertEqual(
            ["启动应用", "处理启动弹窗", "每日签到"],
            [step.step_id for step in plugin.build_workflow(context).steps],
        )

    def test_ximalaya_stops_app_after_audio_task(self):
        stopped = []
        context = SimpleNamespace(
            session=SimpleNamespace(
                stop_app=lambda app: stopped.append(app) or ActionResult.success("stop_app")
            ),
        )
        steps = create_ximalaya_plugin().build_workflow(context).steps

        self.assertEqual("浏览内容", steps[-2].step_id)
        self.assertEqual("停止应用", steps[-1].step_id)
        outcome = steps[-1].handler(context)
        self.assertEqual("success", outcome.status.value)
        self.assertEqual("ximalaya", stopped[0].app_id)

    def test_default_specs_have_globally_unique_target_ids(self):
        self.assertEqual(
            (
                "kuaishou",
                "douyin",
                "qutoutiao",
                "ximalaya",
                "fanqie_novel",
                "toutiao_lite",
                "fanqie_audio",
                "baidu_lite",
                "wukong_browser",
                "hema_theater",
                "xifan_theater",
            ),
            create_default_registry().app_ids(),
        )

    def test_fanqie_audio_stops_after_single_balance_and_withdrawal_steps(self):
        context = SimpleNamespace(
            option=lambda key, default: default,
            random=SimpleNamespace(random=lambda: 0.0, randint=lambda start, end: start),
        )

        steps = create_fanqie_audio_plugin().build_workflow(context).steps

        self.assertEqual(1, sum(step.step_id == "记录余额" for step in steps))
        self.assertEqual("记录余额", steps[-3].step_id)
        self.assertEqual("更新提现信息", steps[-2].step_id)
        self.assertEqual("停止应用", steps[-1].step_id)

    def test_wukong_task_entry_uses_bottom_bar_instead_of_video_overlay(self):
        navigation = wukong_browser_spec().navigation
        home_strategies = {item.strategy_id for item in navigation.home_tab.locators}
        task_strategies = {item.strategy_id for item in navigation.task_entry.locators}

        self.assertNotIn("底栏赚钱入口坐标", home_strategies)
        self.assertIn("底栏赚钱入口坐标", task_strategies)
        self.assertTrue(navigation.reselect_home_tab)
        self.assertFalse(navigation.select_home_tab_before_task)
        self.assertEqual("wukong_browser.main", navigation.home_page.page_id)

    def test_baidu_task_entry_does_not_reselect_video_tab(self):
        spec = baidu_lite_spec()
        navigation = spec.navigation

        self.assertFalse(navigation.select_home_tab_before_task)
        self.assertEqual("baidu_lite.main", navigation.home_page.page_id)
        self.assertEqual(
            ("打开签到面板", "领取今日奖励"),
            tuple(stage.stage_id for stage in spec.check_in.stages),
        )
        self.assertFalse(spec.check_in.stages[0].commit_action)
        self.assertTrue(spec.check_in.stages[1].commit_action)
        self.assertTrue(
            any(
                locator.query == "明天"
                for locator in spec.check_in.success_targets[0].locators
            )
        )

    def test_new_theater_apps_use_distinct_welfare_navigation(self):
        hema = hema_theater_spec().navigation
        xifan = xifan_theater_spec().navigation

        self.assertEqual("com.dz.hmjc:id/iv_welfare_bottom", hema.task_entry.locators[0].query)
        self.assertEqual(
            "com.kwai.theater:id/welfare_pendant_bottom_text",
            xifan.task_entry.locators[0].query,
        )
        self.assertFalse(hema.select_home_tab_before_task)
        self.assertFalse(xifan.select_home_tab_before_task)
        self.assertEqual(2, hema.home_page.minimum_markers)
        self.assertEqual(
            ("河马剧场短剧流标记", "河马剧场首页标签"),
            tuple(marker.target_id for marker in hema.home_page.markers),
        )
        self.assertEqual(
            (
                "河马剧场青少年模式弹层",
                "河马剧场待领取奖励弹层",
                "河马剧场短剧流标记",
            ),
            tuple(item.marker.target_id for item in hema.home_intercepts),
        )
        self.assertEqual(
            "河马剧场退出沉浸播放器",
            hema.home_intercepts[-1].close_target.target_id,
        )

    def test_xifan_check_in_avoids_the_floating_chest(self):
        action = xifan_theater_spec().check_in.stages[0].action_targets[0]

        self.assertEqual("可领取", action.locators[0].query)
        self.assertLess(action.locators[0].region.right, 0.5)

    def test_kuaishou_home_rejects_pages_that_only_keep_bottom_bar(self):
        spec = kuaishou_spec()
        home_page = spec.navigation.home_page

        self.assertIsNotNone(home_page)
        self.assertEqual(2, home_page.minimum_markers)
        self.assertEqual(
            ("快手首页标记", "快手首页标签"),
            tuple(marker.target_id for marker in home_page.markers),
        )

    def test_kuaishou_ad_entry_prefers_the_action_button(self):
        spec = kuaishou_spec()

        self.assertEqual("广告福利按钮文本", spec.ad_entry.locators[0].strategy_id)
        self.assertEqual("领福利", spec.ad_entry.locators[0].query)

    def test_fanqie_novel_does_not_treat_generic_claim_as_ad_entry(self):
        spec = fanqie_novel_spec()

        self.assertEqual(1, len(spec.ad_entry.locators))
        self.assertEqual(
            "看视频赚金币",
            spec.ad_entry.locators[0].options["contains_text"],
        )

    def test_fanqie_novel_recognizes_canvas_check_in_and_claims_video_bonus(self):
        spec = fanqie_novel_spec()

        self.assertIn(
            "签到奖励加倍OCR",
            {
                locator.strategy_id
                for locator in spec.check_in.success_targets[0].locators
            },
        )
        self.assertEqual("番茄小说签到翻倍视频", spec.check_in.post_ad_target.target_id)
        self.assertIn(
            "签到翻倍视频OCR",
            {locator.strategy_id for locator in spec.check_in.post_ad_target.locators},
        )
        self.assertIn(
            "广告领取成功OCR",
            {locator.strategy_id for locator in spec.ad.completion_markers[0].locators},
        )
        self.assertEqual(50.0, spec.ad.completion_wait_seconds)

    def test_fanqie_novel_drains_canvas_popups_before_check_in(self):
        plugin = create_fanqie_novel_plugin()
        check_in_task = plugin.workflow.tasks.check_in.__self__
        task_page = check_in_task.go_task_page

        self.assertTrue(task_page.check_after_entry)
        self.assertEqual(5, task_page.max_dismissals)
        self.assertIn(
            "番茄小说跳一跳活动弹窗",
            {popup.marker.target_id for popup in task_page.popups},
        )

    def test_kuaishou_task_entry_has_visual_fallback(self):
        spec = kuaishou_spec()

        self.assertIn(
            "任务底部OCR",
            {locator.strategy_id for locator in spec.navigation.task_entry.locators},
        )

    def test_kuaishou_supports_video_streak_check_in_result(self):
        spec = kuaishou_spec()

        self.assertIn(
            "连续看视频签到完成",
            {
                locator.strategy_id
                for locator in spec.check_in.success_targets[0].locators
            },
        )

    def test_douyin_supports_the_newcomer_task_page(self):
        spec = douyin_spec()
        task_entry_strategies = {
            locator.strategy_id for locator in spec.navigation.task_entry.locators
        }
        task_marker_strategies = {
            locator.strategy_id for locator in spec.navigation.task_marker.locators
        }
        sign_in_strategies = {
            locator.strategy_id for locator in spec.check_in.success_targets[0].locators
        }
        reward_strategies = {
            locator.strategy_id for locator in spec.duration_reward.reward_target.locators
        }
        ad_entry_strategies = {
            locator.strategy_id for locator in spec.ad_entry.locators
        }
        completion_targets = {
            target.target_id for target in spec.ad.completion_markers
        }
        exit_prompt_targets = {
            target.target_id for target in spec.ad.exit_prompt_close_targets
        }
        final_close_targets = {
            target.target_id for target in spec.ad.final_close_targets
        }

        self.assertIn("赚钱入口OCR", task_entry_strategies)
        self.assertIn("新版任务内容描述", task_marker_strategies)
        self.assertIn("新人签到完成OCR", sign_in_strategies)
        self.assertIn("当前宝箱领取描述", reward_strategies)
        self.assertIn("广告去观看OCR", ad_entry_strategies)
        self.assertIn("抖音广告落地页", completion_targets)
        self.assertIn("抖音广告应用详情页", completion_targets)
        self.assertIn("抖音广告退出弹窗关闭", exit_prompt_targets)
        self.assertIn("抖音广告坚持退出", final_close_targets)
        self.assertEqual(
            "抖音广告坚持退出",
            spec.ad.exit_prompt_close_targets[0].target_id,
        )

    def test_registry_rejects_cross_app_target_id_collision(self):
        first_spec = kuaishou_spec()
        second_spec = replace(
            first_spec,
            identity=AppIdentity("copy", "com.example.copy", "副本"),
            display_name="副本",
        )
        registry = AppRegistry()
        registry.register(create_daily_plugin(first_spec))

        with self.assertRaisesRegex(ValueError, "定位目标 ID 跨应用重复"):
            registry.register(create_daily_plugin(second_spec))


if __name__ == "__main__":
    unittest.main()
