import importlib
import unittest
from dataclasses import replace
from types import SimpleNamespace

from hym.apps import catalog
from hym.apps.app_specs import douyin_spec, kuaishou_spec, qutoutiao_spec, ximalaya_spec
from hym.apps.app_specs.douyin import create_plugin as create_douyin_plugin
from hym.apps.app_specs.kuaishou import create_plugin as create_kuaishou_plugin
from hym.apps.app_specs.qutoutiao import create_plugin as create_qutoutiao_plugin
from hym.apps.app_specs.ximalaya import create_plugin as create_ximalaya_plugin
from hym.apps.plugin import (
    ComposedAppPlugin,
    create_custom_plugin,
    create_daily_plugin,
    create_daily_task_set,
)
from hym.apps.registry import AppRegistry, create_default_registry
from hym.core.models import AppIdentity
from hym.runtime.navigation import NavigationController
from hym.runtime.workflow import StepDefinition, StepOutcome, WorkflowDefinition


class AppSpecLayoutTest(unittest.TestCase):
    def test_each_app_owns_an_independent_business_spec(self):
        factories = (
            (kuaishou_spec, "hym.apps.app_specs.kuaishou"),
            (douyin_spec, "hym.apps.app_specs.douyin"),
            (qutoutiao_spec, "hym.apps.app_specs.qutoutiao"),
            (ximalaya_spec, "hym.apps.app_specs.ximalaya"),
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

    def test_each_app_owns_its_plugin_factory(self):
        factories = (
            (create_kuaishou_plugin, "kuaishou"),
            (create_douyin_plugin, "douyin"),
            (create_qutoutiao_plugin, "qutoutiao"),
            (create_ximalaya_plugin, "ximalaya"),
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

    def test_default_specs_have_globally_unique_target_ids(self):
        self.assertEqual(
            ("kuaishou", "douyin", "qutoutiao", "ximalaya"),
            create_default_registry().app_ids(),
        )

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
