import json
import tempfile
import unittest
from pathlib import Path

from hym.adapters.local import AtomicJsonStateStore
from hym.core.config import BehaviorSettings, InterruptionSettings, load_runtime_settings
from hym.core.randomness import bounded_normal
from hym.runtime.behavior import BehaviorTiming
from hym.testing import DeterministicRandom, FakeClock


class BehaviorTimingTest(unittest.TestCase):
    def test_bounded_normal_clamps_extreme_value_without_resampling(self):
        random_source = DeterministicRandom()
        random_source.normalvariate = lambda center, stddev: 99.0

        self.assertEqual(10.0, bounded_normal(random_source, 1.0, 10.0, center=5.0))

    def test_lower_scale_turns_five_seconds_into_three(self):
        timing = BehaviorTiming(
            BehaviorSettings(timing_scale=0.6, jitter_ratio=0),
            FakeClock(),
            DeterministicRandom(),
        )

        self.assertEqual(3.0, timing.scaled_seconds(5.0))

    def test_reward_wait_jitter_never_shortens_required_time(self):
        timing = BehaviorTiming(
            BehaviorSettings(jitter_ratio=0.12),
            FakeClock(),
            DeterministicRandom(),
        )

        self.assertGreaterEqual(timing.scaled_seconds(35.0, reward_wait=True), 35.0)

    def test_reward_fallback_uses_exact_baseline_without_jitter(self):
        timing = BehaviorTiming(
            BehaviorSettings(jitter_ratio=0.5, reward_wait_scale=1.1),
            FakeClock(),
            DeterministicRandom(),
        )

        self.assertEqual(38.5, timing.baseline_seconds(35.0, reward_wait=True))

    def test_device_and_app_behavior_overrides_are_layered(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "automation.json"
            path.write_text(
                json.dumps(
                    {
                        "behavior": {"timing_scale": 1.0},
                        "devices": [
                            {
                                "device_id": "d1",
                                "behavior": {"timing_scale": 0.8},
                                "apps": [
                                    {"app_id": "a1", "behavior": {"timing_scale": 0.6}}
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            settings = load_runtime_settings(path)
            behavior = settings.behavior_for(settings.devices[0], settings.devices[0].apps[0])

            self.assertEqual(0.6, behavior.timing_scale)

    def test_range_uses_configured_normal_center_without_crossing_bounds(self):
        timing = BehaviorTiming(
            BehaviorSettings(timing_scale=0.6, minimum_delay=0, jitter_ratio=0.5),
            FakeClock(),
            DeterministicRandom(),
        )

        sampled = timing.range_seconds(1.0, 10.0, center=5.0, stddev=1.5)

        self.assertEqual(3.0, sampled)

    def test_behavior_range_override_infers_center_and_standard_deviation(self):
        behavior = BehaviorSettings().merged(
            {"operation_delay_min": 3.0, "operation_delay_max": 9.0}
        )

        self.assertEqual(6.0, behavior.operation_delay_center)
        self.assertEqual(1.0, behavior.operation_delay_stddev)

    def test_invalid_probability_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "automation.json"
            path.write_text(
                json.dumps(
                    {
                        "devices": [
                            {
                                "device_id": "d1",
                                "apps": [
                                    {"app_id": "a1", "options": {"like_probability": 1.2}}
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "概率配置"):
                load_runtime_settings(path)

    def test_video_watch_probabilities_cannot_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "automation.json"
            path.write_text(
                json.dumps(
                    {
                        "devices": [
                            {
                                "device_id": "d1",
                                "apps": [
                                    {
                                        "app_id": "kuaishou",
                                        "options": {
                                            "uninterested_video_probability": 0.6,
                                            "full_watch_attempt_probability": 0.5,
                                        },
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "概率之和"):
                load_runtime_settings(path)

    def test_interruption_settings_validate_probability_and_range(self):
        with self.assertRaisesRegex(ValueError, "插空概率"):
            InterruptionSettings(checkpoint_probability=1.1)
        with self.assertRaisesRegex(ValueError, "桌面等待时间范围"):
            InterruptionSettings(
                desktop_wait_seconds_min=60,
                desktop_wait_seconds_max=20,
            )

    def test_interruption_settings_are_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "automation.json"
            path.write_text(
                json.dumps(
                    {
                        "interruptions": {
                            "enabled": True,
                            "checkpoint_probability": 0.2,
                            "max_per_cycle": 3,
                        },
                        "devices": [{"device_id": "d1", "apps": []}],
                    }
                ),
                encoding="utf-8",
            )

            settings = load_runtime_settings(path)

            self.assertTrue(settings.interruptions.enabled)
            self.assertEqual(0.2, settings.interruptions.checkpoint_probability)
            self.assertEqual(3, settings.interruptions.max_per_cycle)

    def test_reporting_key_can_be_loaded_from_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ingest-key").write_text("file-secret\n", encoding="utf-8")
            path = root / "automation.json"
            path.write_text(
                json.dumps(
                    {
                        "reporting": {
                            "enabled": True,
                            "server_url": "http://server:8080",
                            "ingest_key_env": "HYM_TEST_MISSING_INGEST_KEY",
                            "ingest_key_file": "ingest-key",
                        },
                        "devices": [{"device_id": "d1", "apps": []}],
                    }
                ),
                encoding="utf-8",
            )

            settings = load_runtime_settings(path)

            self.assertEqual("file-secret", settings.reporting.ingest_key)

    def test_project_video_classification_policy_matches_device_observations(self):
        config_path = Path(__file__).resolve().parents[1] / "config" / "automation.json"
        settings = load_runtime_settings(config_path)
        apps = {
            app.app_id: app
            for device in settings.devices
            for app in device.apps
        }

        self.assertTrue(apps["kuaishou"].options["treat_unclassified_as_suspected_ad"])
        self.assertFalse(apps["douyin"].options["treat_unclassified_as_suspected_ad"])
        self.assertEqual(0.002, apps["kuaishou"].options["follow_probability"])
        self.assertEqual(0.002, apps["douyin"].options["follow_probability"])
        self.assertFalse(apps["ximalaya"].options["allow_interruptions"])

    def test_old_top_level_ranges_infer_normal_parameters(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "automation.json"
            path.write_text(
                json.dumps(
                    {
                        "behavior": {
                            "operation_delay_min": 4,
                            "operation_delay_max": 10,
                        },
                        "interruptions": {
                            "desktop_wait_seconds_min": 80,
                            "desktop_wait_seconds_max": 140,
                        },
                        "devices": [{"device_id": "d1", "apps": []}],
                    }
                ),
                encoding="utf-8",
            )

            settings = load_runtime_settings(path)

        self.assertEqual(7, settings.behavior.operation_delay_center)
        self.assertEqual(1, settings.behavior.operation_delay_stddev)
        self.assertEqual(110, settings.interruptions.desktop_wait_seconds_center)
        self.assertEqual(10, settings.interruptions.desktop_wait_seconds_stddev)


class AtomicJsonStateStoreTest(unittest.TestCase):
    def test_round_trip_preserves_chinese_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            store = AtomicJsonStateStore(path)

            store.set("设备:快手", "签到", {"结果": "成功"})

            self.assertEqual({"结果": "成功"}, store.get("设备:快手", "签到"))
            self.assertNotIn("\\u", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
