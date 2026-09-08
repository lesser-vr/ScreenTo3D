import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from depthsbs_app.config import DEFAULT_MODE_MODELS, MODE_MODEL_CHOICES
from depthsbs_app.desktop_jobs import Job, ProcessingLease, unused_output


class DesktopJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ("input.mp4", "ffmpeg.exe", "ffprobe.exe", "nvinfer_11.dll"):
            (self.root / name).touch()
        self.job = Job(
            str(self.root / "input.mp4"),
            str(self.root / "out.mp4"),
            "balanced",
            "h264",
            "da2-base",
            "cuda",
            str(self.root),
            str(self.root),
            str(self.root),
        )

    def test_valid_job(self):
        self.job.validate()

    def test_product_mode_model_contract(self):
        self.assertEqual(DEFAULT_MODE_MODELS["performance"], "da2-small")
        self.assertEqual(DEFAULT_MODE_MODELS["balanced"], "da2-base")
        self.assertEqual(
            set(MODE_MODEL_CHOICES["video-quality"]),
            {"vda-small", "ovda-small-c16"},
        )
        self.assertEqual(MODE_MODEL_CHOICES["offline-quality"], ("vda-small",))
        with self.assertRaisesRegex(ValueError, "일치하지 않습니다"):
            replace(self.job, model="da2-small").validate()

    def test_no_input_overwrite(self):
        with self.assertRaises(ValueError):
            replace(self.job, output=self.job.source).validate()

    def test_invalid_options(self):
        for field in ("mode", "codec", "model", "renderer"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(self.job, **{field: "bad"}).validate()

    def test_missing_input(self):
        with self.assertRaises(ValueError):
            replace(self.job, source=str(self.root / "missing.mp4")).validate()

    def test_stateful_policy(self):
        for model in ("vda-small", "ovda-small-c16"):
            with self.subTest(model=model), self.assertRaises(ValueError):
                replace(
                    self.job, model=model, mode="performance", noncommercial=True
                ).validate()

    def test_nc_requires_explicit_confirmation(self):
        with self.assertRaises(ValueError):
            replace(
                self.job, model="ovda-small-c16", mode="video-quality"
            ).validate()
        replace(
            self.job,
            model="ovda-small-c16",
            mode="video-quality",
            noncommercial=True,
        ).validate()

    def test_no_implicit_license_flag(self):
        self.assertNotIn("--ovda-noncommercial", self.job.arguments("cancel"))

    def test_arguments_preserve_unicode_spaces(self):
        job = replace(self.job, source="C:/한 글/input & movie.mp4")
        args = job.arguments("cancel")
        self.assertEqual(args[args.index("--input") + 1], job.source)
        self.assertIn("--stereo-renderer", args)

    def test_unique_output(self):
        first = unused_output(self.job.source)
        Path(first).touch()
        second = unused_output(self.job.source)
        third = unused_output(self.job.source, [second])
        self.assertEqual(len({first, second, third}), 3)

    def test_exclusive_live_file_lease(self):
        lease = ProcessingLease()
        lease.acquire("live")
        with self.assertRaises(ValueError):
            lease.acquire("file")
        with self.assertRaises(ValueError):
            lease.release("file")
        lease.release("live")
        lease.acquire("file")

    def test_missing_media(self):
        (self.root / "ffmpeg.exe").unlink()
        with self.assertRaises(ValueError):
            self.job.validate()

    def test_snapshot_is_immutable(self):
        with self.assertRaises(AttributeError):
            self.job.mode = "performance"


if __name__ == "__main__":
    unittest.main()
