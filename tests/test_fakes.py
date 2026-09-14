import unittest

from hym.core.models import (
    ActionResult,
    ActionStatus,
    AppIdentity,
    DeviceDescriptor,
    ObservationRequest,
    Point,
)
from hym.core.ports import DevicePort
from hym.testing.fakes import FakeDevice


class FakeDeviceTest(unittest.TestCase):
    def setUp(self):
        self.device = FakeDevice(DeviceDescriptor("device-1"))
        self.app = AppIdentity("douyin", "com.example.douyin", "抖音")

    def test_implements_device_port_and_records_operations(self):
        self.assertIsInstance(self.device, DevicePort)

        self.device.connect()
        self.device.start_app(self.app)
        self.device.tap(Point(0.5, 0.5))

        self.assertEqual(["connect", "start_app", "tap"], [item.name for item in self.device.operations])

    def test_scripted_failure_is_returned_once(self):
        self.device.script_action(
            "start_app",
            ActionResult.failure(
                "start_app",
                "连接中断",
                status=ActionStatus.UNAVAILABLE,
                retryable=True,
            ),
        )

        first = self.device.start_app(self.app)
        second = self.device.start_app(self.app)

        self.assertFalse(first.succeeded)
        self.assertTrue(first.retryable)
        self.assertTrue(second.succeeded)

    def test_default_observation_does_not_need_a_real_device(self):
        result = self.device.observe(ObservationRequest())

        self.assertTrue(result.succeeded)
        self.assertEqual("device-1", result.observation.device_id)


if __name__ == "__main__":
    unittest.main()
