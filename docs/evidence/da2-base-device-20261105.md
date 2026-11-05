# DA2 Base device-depth/SBS delivery — 2026-11-05

This historical record describes a source-checkout optimization, not general
real-time support. Current behavior and support limits belong to PRODUCT.md and
implementation-status.md.

## Change and comparison contract

The live binding selects Da2BaseDeviceEngine, keeping the existing FP32 model,
allowlisted plan hashes, float64 OpenCV preprocessing, model-only aspect padding,
depth unpadding and align_corners=True bilinear source-size interpolation.
The engine lends one contiguous CUDA tensor and retains its input/output resources
until same-stream consumer completion. Owner/thread/device/generation/shape/stream
validation rejects stale or foreign results; pending inference cannot be reused.
File binding defaults to the original host engine. Explicit reference live mode
calls the inherited host infer implementation.

LiveSourceGpuCandidate and LiveSourceGpuTexture are reused without changing their
postprocessing algorithms. On source resize the worker retires native leases and
destroys the consumer before replacing the engine's borrowed stream. Normal GPU
host output remains the default; native output remains explicit and experimental.
Capture and model input still cross host memory; zero-copy is not claimed.

## Correctness

`out/da2-base-device-parity-stage-matched-20261105/report.json` contains24 cases:
six frames each at1920x1080,3440x1440,1080x1920,3840x2160. The fixture resizes a
pinned public FloorballGame excerpt and includes an inverted-frame cut and a
generated flat-background case. These shape fixtures are not native portrait or
native4K photographic detail.

- Original raw depth versus device raw depth: exact24/24.
- GPU host SBS versus native texture readback: exact24/24, opaque alpha.
- Against actual legacy StereoSynthesizer + LiveProjection: existing gate unchanged
  (guided-depth MAE≤1e-6/max≤1e-4; RGB channel MAE≤0.05 and changed-pixel fraction≤0.001).
- Observed worst guided-depth MAE2.54e-8/max1.94e-6; RGB MAE0.000161/255;
  changed-pixel fraction0.000191. No threshold relaxation.
- Pending-token reuse and use-after-completion rejection verified on real engines.
- Selected original/GPU SBS stills inspected for eye order, color and geometry;
  no visible regression found in these frames. Continuous natural-content/VR
  quality acceptance was not performed.

60 scoped tests passed across test_da2_base_device, test_da2_base_profiles,
test_live_backend_routing, test_live_source_gpu_candidate and test_live_controller.
Actual native GUI lifecycle evidence: `out/base-native-lifecycle-20261105/report.json`.
It covers both consumers, hide/show, tab changes, fullscreen/Escape, source resize,
texture retirement, stop/clear/restart, source minimize/loss and owned-worker crash.
Assertions verified no remaining native pools/nodes after cleanup.

The initial harness attempts are retained: `out/da2-base-device-parity-20261105`
used the upstream rather than prepared-clip hash; `...-verified-20261105` selected
the file projection adapter instead of the live paired adapter; `...-final-20261105`
compared pre-background GPU guided depth with post-background legacy depth. That
last case had exact final RGB. The final harness taps matching pre-background
guide stages and independently compares final RGB. These were harness corrections,
not relaxed quality gates or hidden product failures.

## Matched actual-GUI measurements

RTX5090, driver621.14, TensorRT11.2.1.2, Qt6.10.2, Windows11,150%DPI. Existing
working tree intentionally retained earlier user work; no clean-commit claim.
The three paths ran sequentially without concurrent test inference, using
FloorballGame in a separate source process at approximately62.3 painted fps.
Input sizes1920x1080/3840x2160, corresponding Full SBS3840x1080/7680x2160.
Target60Hz, six-second discarded warmup, five six-second windows per condition.
Readback review frames and lifecycle probes were outside throughput windows.
Each environment.json records artifacts, environment, source provenance and GPU
preflight (0% activity for all three runs). The existing TensorRT device-plan
compatibility warning was emitted. Multiple-engine parity also emitted the existing
TensorRT logger warning.

| Path | Input | Processed median | Output median | Output range |
|---|---|---:|---:|---:|
| Reference |1920x1080|10.43|10.43|10.41–10.59|
| GPU host |1920x1080|18.02|18.02|17.56–18.04|
| GPU native |1920x1080|20.83|20.67|20.50–20.86|
| Reference |3840x2160|2.15|2.15|2.15–2.32|
| GPU host |3840x2160|6.46|6.46|6.29–6.60|
| GPU native |3840x2160|8.43|8.43|8.10–8.60|

Units are fps. Host output is a callback submission proxy; native output counts
distinct afterFrameEnd IDs, not physical scanout. The displayed window was fitted
to1400×650 logical pixels; this is not1:1 Full SBS display validation.4K uses the
upscaled prepared public1080p excerpt. Default application target remains30Hz;
60Hz was explicitly selected for matched measurement without that ceiling.

Sampled latest-frame stage medians(ms), not pure CUDA kernel timings:

| Input | Path | Aggregate depth | SBS | Worker total |
|---|---|---:|---:|---:|
|1920x1080|Reference|48.70|41.76|94.08|
|1920x1080|GPU host|46.16|8.28|55.68|
|1920x1080|GPU native|44.34|3.18|48.06|
|3840x2160|Reference|124.00|323.41|456.14|
|3840x2160|GPU host|103.45|45.11|156.36|
|3840x2160|GPU native|98.46|15.84|115.68|

Aggregate depth includes preprocessing, inference, resizing and validation. Further
profiling must split those before attributing the remaining98ms to the model.
No new weights, FP16 conversion, frame generation, reduced source resolution or
silent fallback were introduced.4K remains visibly low-rate despite3.92× output
improvement;30/60fps, long-run behavior and Owl3D/VR acceptance remain unverified.

Raw evidence:

- `out/base-live-reference-20261105/{runs.json,environment.json,gpu-samples.csv,review/}`
- `out/base-live-gpu-20261105/{runs.json,environment.json,gpu-samples.csv,review/}`
- `out/base-live-native-20261105/{runs.json,environment.json,gpu-samples.csv,review/}`
- `out/base-device-20261105/summary.json` and its aggregation script.

Reproduction: `v1/benchmark_live_modes.py --sizes 1920x1080,3840x2160 --modes balanced
--source FloorballGame --source-process --hz 60`,
`--seconds 6 --repeats 5 --hide-main --sample-gpu --capture-telemetry --save-review-frames`,
one fresh `--output` per `--path reference`, `--path gpu`, `--path gpu-texture`.
Parity: `v1/test_da2_base_live_product.py --output <fresh-directory>`.
Lifecycle: `v1/test_native_live.py --mode balanced --hz 60 --output <fresh-directory>`.
