import importlib
import unittest
from dataclasses import replace

from hym.apps import catalog
from hym.apps.app_specs import douyin_spec, kuaishou_spec, qutoutiao_spec, ximalaya_spec
from hym.apps.app_specs.douyin import create_plugin as create_douyin_plugin
from hym.apps.app_specs.kuaishou import create_plugin as create_kuaishou_plugin
from hym.apps.app_specs.qutoutiao import create_plugin as create_qutoutiao_plugin
from hym.apps.app_specs.ximalaya import create_plugin as create_ximalaya_plugin
from hym.apps.plugin import ConfiguredAppPlugin
from hym.apps.registry import AppRegistry, create_default_registry
from hym.core.models import AppIdentity
from hym.runtime.workflow import StepDefinition, StepOutcome


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
                self.assertEqual(factory().app_id, app_id)

    def test_app_specific_steps_can_be_added_without_changing_common_scheduler(self):
        class CustomPlugin(ConfiguredAppPlugin):
            def build_app_steps(self, context):
                return (
                    StepDefinition(
                        "应用独有任务",
                        "应用独有任务",
                        lambda _: StepOutcome.success("完成"),
                    ),
                )

        plugin = CustomPlugin(ximalaya_spec())
        step_ids = [step.step_id for step in plugin._business_steps(object())]

        self.assertEqual(["浏览内容", "应用独有任务"], step_ids)

    def test_default_specs_have_globally_unique_target_ids(self):
        self.assertEqual(
            ("kuaishou", "douyin", "qutoutiao", "ximalaya"),
            create_default_registry().app_ids(),
        )

    def test_registry_rejects_cross_app_target_id_collision(self):
        first_spec = kuaishou_spec()
        second_spec = replace(
            first_spec,
            identity=AppIdentity("copy", "com.example.copy", "副本"),
            display_name="副本",
        )
        registry = AppRegistry()
        registry.register(ConfiguredAppPlugin(first_spec))

        with self.assertRaisesRegex(ValueError, "定位目标 ID 跨应用重复"):
            registry.register(ConfiguredAppPlugin(second_spec))


if __name__ == "__main__":
    unittest.main()
