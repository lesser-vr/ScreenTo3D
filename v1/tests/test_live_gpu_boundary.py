import unittest

from analyze_live_gpu_boundary import analyze, percentile


class LiveGpuBoundaryTests(unittest.TestCase):
    def test_percentile_interpolates(self):
        self.assertEqual(percentile([1, 2, 3], 0.5), 2)
        self.assertEqual(percentile([0, 10], 0.95), 9.5)

    def test_exact_native_transfer_formula(self):
        width, height, frames = 32, 16, 3
        per_frame = 518 * 518 * 3 + width * height * 3
        report = {
            "processing_path": "gpu-texture",
            "processed_frames": frames,
            "inference_frames": frames + 1,
            "duration_seconds": 2.0,
            "explicit_cuda_h2d_bytes": frames * per_frame,
            "explicit_cuda_d2h_bytes": frames * 4,
            "explicit_cuda_syncs": frames * 2,
        }
        run = {
            "size": f"{width}x{height}",
            "mode": "balanced",
            "report": report,
            "gpu_stage_samples_ns": [[1_000_000] * 8, [2_000_000] * 8],
            "host_bridge_samples_ns": [[0, 500_000, 0, 0]],
        }
        result = analyze([run])
        transfers = result["explicit_transfers"]
        self.assertEqual(transfers["h2d_bytes_per_processed_frame"], per_frame)
        self.assertEqual(transfers["d2h_bytes_per_processed_frame"], 4)
        self.assertEqual(transfers["syncs_per_processed_frame"], 2)
        self.assertTrue(all(transfers["formula_checks"].values()))
        self.assertEqual(
            result["workload"]["counter_skew_inference_minus_processed"], 1
        )

    def test_rejects_mixed_workloads(self):
        base = {
            "size": "32x16",
            "mode": "balanced",
            "report": {"processing_path": "gpu-texture"},
        }
        with self.assertRaises(ValueError):
            analyze([base, {**base, "size": "64x32"}])


if __name__ == "__main__":
    unittest.main()
