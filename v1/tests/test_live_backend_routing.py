import unittest
from unittest.mock import Mock, patch

from screento3d_app.live_backend import binding, choices, default_model, validate_snapshot


class LiveBackendRoutingTests(unittest.TestCase):
    def snapshot(self, model, **changes):
        value = {
            "model": model,
            "engine": "C:/validated-engine",
            "runtime": "C:/TensorRT",
            "noncommercial": False,
        }
        value.update(changes)
        return value

    def test_model_defined_defaults(self):
        self.assertEqual(default_model("performance"), "da2-small")
        self.assertEqual(default_model("balanced"), "da2-base")
        self.assertEqual(default_model("video-quality"), "vda-small")
        self.assertEqual(
            choices("video-quality"), ("ovda-small-c16", "vda-small")
        )

    def test_offline_is_not_a_live_mode(self):
        with self.assertRaisesRegex(ValueError, "files only"):
            choices("offline-quality")

    def test_cross_mode_model_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "do not match"):
            validate_snapshot(self.snapshot("da2-small"), "balanced")
        with self.assertRaisesRegex(ValueError, "do not match"):
            validate_snapshot(self.snapshot("da2-base"), "video-quality")

    def test_ovda_requires_explicit_license_confirmation(self):
        with self.assertRaisesRegex(ValueError, "license"):
            validate_snapshot(self.snapshot("ovda-small-c16"), "video-quality")
        selected = validate_snapshot(
            self.snapshot("ovda-small-c16", noncommercial=True), "video-quality"
        )
        self.assertTrue(selected["noncommercial"])

    def test_no_implicit_engine_or_runtime(self):
        for key in ("engine", "runtime"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_snapshot(
                    self.snapshot("da2-base", **{key: ""}), "balanced"
                )

    def test_live_ovda_requests_owned_device_depth_engine(self):
        backend = Mock()
        backend.spec.model_id = "ovda-small-c16"
        backend.input_validator = Mock()
        with patch("screento3d_app.ovda.binding", return_value=backend) as create:
            result = binding(
                self.snapshot("ovda-small-c16", noncommercial=True),
                "video-quality",
                {"width": 1920, "height": 1080},
                Mock(),
                Mock(),
            )
        self.assertIs(result, backend)
        self.assertTrue(create.call_args.kwargs["device_depth"])
        backend.input_validator.assert_called_once_with(
            {"width": 1920, "height": 1080}
        )

    def test_live_vda_requests_owned_device_depth_engine(self):
        backend = Mock()
        backend.spec.model_id = "vda-small"
        backend.input_validator = Mock()
        with patch(
            "screento3d_app.depth_backend.vda_binding", return_value=backend
        ) as create:
            result = binding(
                self.snapshot("vda-small"),
                "video-quality",
                {"width": 1920, "height": 1080},
                Mock(),
                Mock(),
            )
        self.assertIs(result, backend)
        self.assertTrue(create.call_args.kwargs["device_depth"])

    def test_live_base_requests_device_depth_without_changing_file_default(self):
        backend = Mock()
        with patch("screento3d_app.da2_base.binding", return_value=backend) as create:
            self.assertIs(binding(self.snapshot("da2-base"), "balanced",
                                  {"width": 3440, "height": 1440}, Mock(), Mock()), backend)
        self.assertTrue(create.call_args.kwargs["device_depth"])
        backend.input_validator.assert_called_once_with({"width": 3440, "height": 1440})


if __name__ == "__main__":
    unittest.main()
