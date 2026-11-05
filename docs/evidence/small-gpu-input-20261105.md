# Small GPU capture and preprocessing — 2026-11-05

Historical implementation/test record. Product behavior is owned by PRODUCT.md;
current support and measurements are owned by implementation-status.md.

## Change and ownership

Small window GPU sessions now use the existing owned WGC/D3D11/CUDA capture and
same-stream RGB frame. A non-owning Torch ExternalStream wraps Small's existing
TensorRT-owned raw CUDA stream. The engine remains the sole stream owner.

`small_gpu_input.py` builds one 1036x4 float32 coefficient table (16,576 bytes)
per renderer size, using generated impulse images and the installed OpenCV/IPP
runtime. This is shape-only initialization: no captured pixels enter it.
`small_input.cu` performs uint8 518x518 cubic resize and the existing float32
normalization on the GPU. Left-edge accumulation order, folded right-edge taps
and unmerged vertical taps preserve the tested IPP rounding behavior.

`live_post_gpu` uses the identical Small postprocessing body, replacing only the
full RGB host-to-device copy with a device-to-device copy. Small uses a separate
pinned DLL with the same LiveDepth/native borrowed layout. The Base DLL is not
replaced. Input/coefficient tensors remain owned until stream completion;
native output slots retire before renderer/engine destruction. Constructor
failure cleanup preserves the primary error.

No new GUI option, model, precision, strength, source/per-eye size, inference
cadence or presentation default was introduced. Small remains the existing
FP16 ONNX/TensorRT model with FP32 I/O. Monitor/file/reference paths retain their
previous input. `DEPTHSBS_GPU_CAPTURE=0` is the explicit diagnostic control;
there is no automatic fallback on a GPU input failure. Ordinary app launch
retains its 30Hz presentation target.

## Local artifact/runtime envelope

- RTX 5090 / SM120, TensorRT 11.2.1.2, CUDA 13.1 build, Torch 2.7.1+cu128.
- OpenCV 4.13.0, IPP 2022.2.0; unsupported version/disabled IPP is rejected.
- `out/small-input/small_input.dll` SHA-256:
  `71fedc045926c1a59b129fb1cb7550e408b811bf6779f4a7a3da121000fe070a`.
- Build: `scripts/build-small-input.ps1`; source/compiler hashes and retained
  OpenCV notice: `out/small-input/build-manifest.json`, `OPENCV-NOTICE.txt`.
- GPU capture DLL:
  `adebe984ad7b66a35e007a99921e810694b1aa822f08ca0dea17b7afc6326a68`.
- Small model is unchanged:
  `2df6223f206b5164e21f664ace61dabeb9bb6a49b8b5a3e00510b4807d0f5b04`.
- Existing native texture runtime / Qt native module pins remain unchanged.

## Correctness and lifecycle evidence

- `out/small-gpu-input-final-parity-20261105d/report.json` and
  `strict-summary.json`: 27 random/gradient/flat cases, 16x16 through 4096x2160,
  compare GPU uint8 cubic resize against unmodified OpenCV/IPP. Every compared
  value is exact. Pitched BGRA matches RGB and 32x32 scene thumbnails match.
- The same run compares 72 image cases: FloorballGame, OfficeWalk, ParkingGarage;
  six spaced samples per clip (0/60/120/180/240/300), 1080p, 3440x1440,
  1080x1920 and 4K. Sample 3 is inverted for a cut; sample 5 is replaced with a
  flat-background fixture. Model input, raw depth, old/new postprocessing and
  native/host SBS are bit-exact in every case. Performance mode retains its
  disabled background refinement; the flat fixture does not claim that branch.
- Early analytical-coefficient candidates and incomplete boundary variants
  failed; they are not the installed implementation. Their results remain in
  earlier `small-gpu-input-*-20261105*` folders. Acceptance thresholds were not
  widened to accept those depth/SBS differences. Final tests require zero error.
- `out/small-input-final-unit-20261105.log`: 27 scoped tests cover selection,
  runtime/artifact rejection, failed-constructor cleanup, capture-stream drain,
  model routing, scene history and Base device ownership. Scoped Ruff passes.
- `out/small-input-base-regression-20261105/report.json`: six actual Base FP16
  GPU-input cases retain exact input/native parity and existing legacy-post
  tolerances after the shared frame/layout refactor.
- `out/small-input-final-lifecycle-20261105/` and its `.log`: actual Small default
  native startup, fullscreen/Escape, hide/restore, resize, stop/restart, source
  loss, worker crash and preparation cancellation pass. The harness asserts
  zero native pools/nodes after shutdown. Earlier five-second steady lifecycle
  run is in `out/small-gpu-input-lifecycle-20261105/`.

## Matched native measurements

Public FloorballGame in a separate source process; Performance/Small; target
60Hz; six-second discarded warmup then five six-second measurement windows.
No frame generation. Rates count distinct Qt afterFrameEnd output IDs, not
physical scanout. Source is a 1080p excerpt scaled to each processing size;
4K per eye produces 7680x2160 Full SBS in a fitted window.

| Per eye | Mapped/CPU input median (range) | GPU input median (range) |
|---|---:|---:|
| 1920x1080 | 59.96 (59.58–60.10) fps | 60.14 (59.77–60.17) fps |
| 3840x2160 | 50.90 (50.31–51.93) fps | 59.92 (59.77–60.08) fps |

4K median improves 17.7%. 1080p is presentation-limited in this test. Inputs:

- Control: `out/small-input-host-control-20261105/`.
- Initial GPU run, both sizes: `out/small-input-gpu-native-20261105/`.
  The 1080p number above is from this pre-boundary-fix DLL; no left horizontal
  border is sampled at that width. Its 4K median was 59.91fps.
- Final pinned DLL 4K confirmation: `out/small-input-final-native-20261105/`.

The initial paired runs reduce sampled worker CPU core-equivalent medians from
0.91 to 0.28 at 1080p and 2.68 to 0.50 at 4K. Submitted steady input H2D drops
from 7,025,772 / 25,688,172 bytes per processed frame to zero. This excludes the
one-time coefficient upload; it is not measured bus traffic or zero-copy.
Capture still copies D3D/CUDA resources, and thumbnails/scene checks read back
bounded data. Conditional background refinement remains an explicit CPU bridge
for policies that enable it. Async depth submission and downstream GPU wait
must not be interpreted as isolated inference/stereo kernel timings.

These are bounded technical measurements, not real-game, multi-hour, physical
4K60, Owl3D/binocular or other-GPU acceptance. Source GUI restart is required;
portable bundles have not been rebuilt.
