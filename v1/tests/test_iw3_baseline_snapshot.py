from pathlib import Path
import tempfile
import unittest

from snapshot_iw3_baseline import read_settings


class Iw3SnapshotTests(unittest.TestCase):
    def test_only_quality_settings_are_returned(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "settings.cfg"
            source.write_text(
                "[Persistence_Options/ComboBox/cbo_depth_model]\n"
                "Selection=('str', 'Any_V2_S')\n"
                "[Persistence_Options/TextCtrl/txt_auth_password]\n"
                "Value=('str', 'private-fixture')\n", encoding="utf-8")
            result = read_settings(source)
        self.assertEqual(result["cbo_depth_model"], "Any_V2_S")
        self.assertNotIn("txt_auth_password", result)
        self.assertNotIn("private-fixture", str(result))
        self.assertIsNone(result["cbo_method"])

    def test_invalid_value_is_not_evaluated(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "settings.cfg"
            source.write_text(
                "[Persistence_Options/ComboBox/cbo_depth_model]\n"
                "Selection=some_function()\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_settings(source)


if __name__ == "__main__":
    unittest.main()
