import unittest

from hym.core.models import ImageFrame
from hym.locators.vision import _parse_macos_vision_ocr


class MacOsVisionOcrParserTest(unittest.TestCase):
    def test_crop_coordinates_are_mapped_back_to_full_frame(self):
        frame = ImageFrame(1000, 2000, b"x", "BGR")
        raw = [
            {
                "text": "朋友圈",
                "confidence": 0.99,
                "left": 0.2,
                "top": 0.25,
                "right": 0.6,
                "bottom": 0.75,
            }
        ]

        items = tuple(_parse_macos_vision_ocr(raw, frame, 100, 200, 500, 400))

        self.assertEqual("朋友圈", items[0].text)
        self.assertAlmostEqual(0.2, items[0].bounds.left)
        self.assertAlmostEqual(0.15, items[0].bounds.top)
        self.assertAlmostEqual(0.4, items[0].bounds.right)
        self.assertAlmostEqual(0.25, items[0].bounds.bottom)


if __name__ == "__main__":
    unittest.main()
