import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from PySide6.QtCore import QRect
from depthsbs_app.output_placement import OutputPlacement, fit_rect


class OutputPlacementTests(unittest.TestCase):
    def test_disconnected_screen_rect_is_reachable(self):
        available = QRect(0, 0, 1920, 1040)
        fitted = fit_rect(QRect(-3840, -2000, 4000, 2160), available)
        self.assertTrue(available.contains(fitted))
        self.assertGreaterEqual(fitted.top(), 32)

    def test_negative_desktop_and_small_screen(self):
        available = QRect(-1280, 0, 1280, 680)
        self.assertTrue(available.contains(fit_rect(QRect(5000, 5000, 800, 600), available)))

    def test_saved_placement_round_trip_and_disconnected_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'placement.json'
            placement = OutputPlacement(path)
            placement.rect = QRect(2020, 150, 900, 600)
            placement.screen_name = 'External'
            placement.save()
            restored = OutputPlacement(path)
            self.assertEqual(restored.rect, placement.rect)
            main = Mock(); main.name.return_value = 'Main'
            external = Mock(); external.name.return_value = 'External'
            self.assertEqual(restored.screen_index([main, external], main), 1)
            self.assertEqual(restored.screen_index([main], main), 0)
            path.write_text('{invalid', encoding='utf-8')
            self.assertEqual(OutputPlacement(path).screen_name, '')

    def test_invalid_values_do_not_reach_qrect(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'placement.json'
            path.write_text('{"screen":"x", "rect":[1,2,-3,4]}')
            self.assertEqual(OutputPlacement(path).rect.width(), 1280)


if __name__ == '__main__':
    unittest.main()
