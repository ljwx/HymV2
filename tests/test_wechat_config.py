import json
import tempfile
import unittest
from pathlib import Path

from wechat_automation.config import ChatSettings, load_wechat_settings


class WechatConfigTest(unittest.TestCase):
    def test_relative_runtime_config_and_message_groups_are_parsed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wechat.json"
            path.write_text(
                json.dumps(
                    {
                        "runtime_config": "automation.json",
                        "chat": {
                            "enabled": True,
                            "send": True,
                            "friend_name": "测试好友",
                            "message_groups": [["第一条", "第二条"]],
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            settings = load_wechat_settings(path)

            self.assertEqual((Path(directory) / "automation.json").resolve(), settings.runtime_config)
            self.assertEqual((("第一条", "第二条"),), settings.chat.message_groups)

    def test_real_send_requires_a_friend_and_message_group(self):
        with self.assertRaisesRegex(ValueError, "friend_name"):
            ChatSettings(enabled=True, send=True)

    def test_old_range_only_config_infers_normal_parameters(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wechat.json"
            path.write_text(
                json.dumps(
                    {
                        "moments": {"swipes_min": 6, "swipes_max": 12},
                        "chat": {"interval_min_seconds": 5, "interval_max_seconds": 11},
                    }
                ),
                encoding="utf-8",
            )

            settings = load_wechat_settings(path)

        self.assertEqual(9, settings.moments.swipes_center)
        self.assertEqual(1, settings.moments.swipes_stddev)
        self.assertEqual(8, settings.chat.interval_center_seconds)
        self.assertEqual(1, settings.chat.interval_stddev_seconds)

    def test_message_group_cannot_exceed_two_messages(self):
        with self.assertRaisesRegex(ValueError, "一到两条"):
            ChatSettings(
                enabled=True,
                send=True,
                friend_name="测试好友",
                message_groups=(("一", "二", "三"),),
            )


if __name__ == "__main__":
    unittest.main()
