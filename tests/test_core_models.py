import unittest

from hym.core.models import Point, Rect
from hym.core.targets import LocatorKind, LocatorSpec, TargetSpec


class GeometryTest(unittest.TestCase):
    def test_rect_center_uses_normalized_coordinates(self):
        rect = Rect(0.1, 0.2, 0.5, 0.8)

        self.assertEqual(Point(0.3, 0.5), rect.center)

    def test_point_rejects_pixel_coordinates(self):
        with self.assertRaises(ValueError):
            Point(100, 200)


class TargetSpecTest(unittest.TestCase):
    def test_target_requires_at_least_one_locator(self):
        with self.assertRaises(ValueError):
            TargetSpec("task_center", ())

    def test_locator_confidence_is_validated(self):
        with self.assertRaises(ValueError):
            LocatorSpec("ocr", LocatorKind.OCR_TEXT, query="任务中心", min_confidence=1.1)


if __name__ == "__main__":
    unittest.main()
