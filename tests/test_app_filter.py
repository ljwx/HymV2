import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hym.cli import main
from hym.core.config import AppRunSettings, DeviceRunSettings
from hym.core.models import DeviceDescriptor
from hym.runtime.runner import run_device_from_config


class AppFilterTest(unittest.TestCase):
    def setUp(self):
        self.device = DeviceRunSettings(
            DeviceDescriptor("device-1", "android", "device-1"),
            (
                AppRunSettings("kuaishou"),
                AppRunSettings("douyin"),
                AppRunSettings("disabled", enabled=False),
            ),
        )
        self.settings = SimpleNamespace(devices=(self.device,))

    @patch("hym.runtime.runner.DeviceWorker")
    @patch("hym.runtime.runner.load_runtime_settings")
    def test_runner_passes_only_selected_enabled_apps(self, load_settings, worker_type):
        load_settings.return_value = self.settings
        worker_type.return_value.run.return_value = 0

        result = run_device_from_config(
            "config.json",
            "device-1",
            True,
            app_ids=("kuaishou",),
        )

        self.assertEqual(0, result)
        selected_device = worker_type.call_args.args[1]
        self.assertEqual(["kuaishou"], [app.app_id for app in selected_device.apps])

    @patch("hym.runtime.runner.load_runtime_settings")
    def test_runner_rejects_missing_or_disabled_app(self, load_settings):
        load_settings.return_value = self.settings

        with self.assertRaisesRegex(ValueError, "没有匹配到已启用 App"):
            run_device_from_config(
                "config.json",
                "device-1",
                True,
                app_ids=("disabled", "missing"),
            )

    @patch("hym.cli.run_device_from_config")
    @patch("hym.cli.load_runtime_settings")
    def test_direct_cli_forwards_app_filter(self, load_settings, run_device):
        load_settings.return_value = self.settings
        run_device.return_value = 0

        result = main(
            [
                "--config",
                "config.json",
                "--once",
                "--direct",
                "--device",
                "device-1",
                "--app",
                "kuaishou",
            ]
        )

        self.assertEqual(0, result)
        run_device.assert_called_once_with(
            Path("config.json").resolve(),
            "device-1",
            True,
            app_ids=["kuaishou"],
        )

    @patch("hym.cli.run_manual_flow_recording")
    @patch("hym.cli.load_runtime_settings")
    def test_manual_recorder_uses_one_selected_device(self, load_settings, run_recorder):
        load_settings.return_value = self.settings
        run_recorder.return_value = 0

        result = main(
            [
                "--config",
                "config.json",
                "--device",
                "device-1",
                "--record-flow",
                "新奖励",
                "--record-app",
                "kuaishou",
            ]
        )

        self.assertEqual(0, result)
        run_recorder.assert_called_once_with(
            self.settings,
            device_id="device-1",
            flow_name="新奖励",
            app_label="kuaishou",
        )


if __name__ == "__main__":
    unittest.main()
