import unittest

from hym.core.config import RetrySettings
from hym.core.events import InMemoryEventSink
from hym.core.models import DeviceDescriptor, Point
from hym.runtime.session import DeviceSession
from hym.testing import FakeClock, FakeDeviceFactory


class DeviceSessionTest(unittest.TestCase):
    def test_health_check_is_not_repeated_for_every_action(self):
        factory = FakeDeviceFactory()
        session = DeviceSession(
            DeviceDescriptor("device-1"),
            factory,
            InMemoryEventSink(),
            FakeClock(),
            RetrySettings(health_check_interval_seconds=60),
        )
        self.assertTrue(session.connect())

        session.tap(Point(0.5, 0.5), 0.1)
        session.tap(Point(0.5, 0.5), 0.1)

        names = [operation.name for operation in factory.created[0].operations]
        self.assertEqual(["connect", "tap", "tap"], names)

    def test_text_input_is_forwarded_without_plaintext_in_fake_record(self):
        factory = FakeDeviceFactory()
        session = DeviceSession(
            DeviceDescriptor("device-1"),
            factory,
            InMemoryEventSink(),
            FakeClock(),
            RetrySettings(health_check_interval_seconds=60),
        )
        self.assertTrue(session.connect())

        result = session.input_text("私密消息")

        self.assertTrue(result.succeeded)
        operation = factory.created[0].operations[-1]
        self.assertEqual("input_text", operation.name)
        self.assertEqual({"text_length": 4}, operation.arguments)


if __name__ == "__main__":
    unittest.main()
