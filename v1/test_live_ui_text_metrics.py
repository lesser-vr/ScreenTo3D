"""Guard diagnostic image comparison against overflow and missed displacement."""

import unittest

import numpy as np

from test_live_ui_text import difference


class UiTextDifferenceTests(unittest.TestCase):
    def test_identical(self):
        values = np.array([0, 127, 255], np.uint8)
        self.assertEqual(difference(values, values)["changed_channels"], 0)

    def test_single_level(self):
        actual = np.array([0, 128, 255], np.uint8)
        expected = np.array([1, 127, 254], np.uint8)
        result = difference(actual, expected)
        self.assertEqual(result["maximum_channel_delta"], 1)
        self.assertEqual(result["changed_channels"], 3)
        self.assertEqual(result["channels_over_one"], 0)

    def test_displaced_stroke_and_unsigned_wrap(self):
        actual = np.array([0, 255, 255, 0], np.uint8)
        expected = np.array([0, 0, 255, 255], np.uint8)
        result = difference(actual, expected)
        self.assertEqual(result["maximum_channel_delta"], 255)
        self.assertEqual(result["channels_over_one"], 2)


if __name__ == "__main__":
    unittest.main()
