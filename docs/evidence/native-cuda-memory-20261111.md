# Native CUDA memory and Torch-free desktop, 2026-11-11

Local unreleased work based on dirty revision
`71b9216419fbdf5ddef6ad17db011a625d6910b4`. The original 1.0.0 release and the
previous slimming candidates were retained. Only owned generated media/window
inputs and isolated workspace caches were used for actual execution tests.

## Implementation

`cuda_memory.py` owns CUDA streams, bounded device/pinned-host buffers and a
single-stream reuse pool capped at 512 MiB of idle storage. Individual allocations
are checked with Python integer arithmetic before cudaMalloc (1 GiB limit).
Buffers validate owner thread, device, arena state and pointer lifetime. Closing
an arena drains its stream, invalidates buffers and attempts every recorded free.
Cleanup failure poisons further access rather than silently continuing.

`native_small.py` borrows Small's existing TensorRT-owned stream and retains its
original preprocessing and FP16 model. `native_engines.py` loads Base/VDA through
the existing trusted plan/DPAPI/artifact validation, checks exact tensor names,
shapes and FP32 I/O, and keeps the current model canvases/precision. Base's GPU
and CPU preprocessing remain distinct and unchanged. VDA retains warmup followed
by first-two/latest-29 cache sampling, the 42-entry bound and explicit reset
semantics. Cache packing copies FP32 values; every depth/cache output is checked
for nonfinite values. GPU input and existing stereo kernels remain unchanged.

The new `native_memory.dll` supplies only RGB conversion, equality, finite checks,
depth crop/resize and cache packing. Its pinned SHA-256 is
`0e88e2737b34793d12977ffbbb75e811c6dbafacbb728d1a730edb6eaf3e1708`.
Portable compilation includes compute_75 PTX and SM120 code. The resize uses the
align-corners FP32 scale, coordinate and fused evaluation order of the installed
PyTorch 2.7.1 kernel; separately rounding each multiply/add initially differed by
up to 4.77e-7 and was corrected before promotion. The final resize is bit-exact on
the tested random inputs/shapes. Source: [PyTorch 2.7.1 bilinear CUDA kernel](https://github.com/pytorch/pytorch/blob/v2.7.1/aten/src/ATen/native/cuda/UpSampleBilinear2d.cu).
The package retains the PyTorch license and attribution for this arithmetic.

Live VFG borrows the engine arena/stream; file VFG owns a separate CUDA stream and
three persistent pinned-host/device RGBA pairs. The NVIDIA bridge, weights,
original/midpoint/cut/tail cadence and output packing are unchanged. Installer
reference validation now uses CUDA-owned tensors, preserving the seed, tensor
signatures, reference samples/tolerances and warmup-to-cached transition before
publishing DPAPI-protected plans.

The normal desktop excludes Torch, torchgen, functorch and Torch-only Python
dependencies. It includes the pinned CUDA 13.1 `cudart64_13.dll` (540,784 bytes,
SHA-256 `352ba4ebe61e9a3b171f357a3daf5dd15b6af4a9857673ff893bd6fd2964c075`).
TensorRT builder resource selection and per-user GPU engine creation remain.
Source-only oVDA/RowFlow and explicit old comparison classes retain their Torch
development dependency. The old Base graph/stage diagnostic environment switches
are explicitly rejected on the native engine; no GUI option or ordinary mode is
removed and no alternate backend is selected implicitly.

## Numerical and lifecycle evidence

- `out/native-memory-pairs/comparison.json`: same generated RGB, default strength
  0.5, detail policy where applicable, fixed 60 Hz fixture clock and Half TB.
  Small: 16 frames, maximum RGBA difference zero. Base: 48 frames, maximum depth
  and RGBA differences zero. VDA: 70 frames, maximum depth and RGBA differences
  zero; both paths share the same 32→42 history counts, eviction and cut reset.
  Native runs reject importing Torch and record `torch_imported: false`.
- Portrait pairs use 518x896 rather than 518x924, with 180x320 input; these cover
  model-only padding removal and non-square depth restoration separately. All 12
  depth/output frames match exactly (`portrait-comparison.json`). Separate 4K
  pairs use 3840x2160 inputs, four frames per model; all final output hashes and
  Base/VDA depth hashes match (`4k-comparison.json`). This is numerical/geometry
  parity, not a sustained 4K throughput test.
- `out/native-vfg-paired.json`: six identical owned RGB frame pairs through the
  same NVIDIA Medium2x SDK/bridge, original Torch buffers versus native buffers;
  maximum output difference zero.
- `out/native-memory-owned-check.json`: actual CUDA tests reject an expired
  pointer after pool reuse, a foreign thread, nonfinite results, invalid/oversized
  allocations and access after close. Allocation counts plateau over 100 reuses.
  Reproducible hardware regression: `v1/test_native_memory.py --output <json>`.
- `out/native-memory-cpu-complete.json`: 471 CPU/Qt contracts pass, including new
  allocation overflow/shape guards. The native engine factory remains lazy and
  CPU profile-selection tests do not import CUDA/TensorRT.
- `out/native-desktop-qa/report.json`: actual embedded Python, no Torch package,
  Windows-only PATH and no CUDA/Python development environment. Native Small
  Half TB, live Korean/English switching, texture-pool cleanup and two real
  sequential file conversions with decoded geometry/frame counts/audio pass.
- `out/native-model-first-use/report.json`: another empty isolated cache installs
  SM120 and builds/verifies Base's two and VDA's four engines using the Torch-free
  embedded interpreter. Both complete real 12-frame conversions with audio.
- `out/native-install-vfg.log`: the same app installs/verifies the pinned original
  NVIDIA wheel locally, without importing Torch. No SDK/model is newly bundled.
- `out/native-live-models-qa/report.json`: the Torch-free desktop shows native
  Small/Base/VDA output for an owned 640x360 logical-pixel moving window. Small
  and Base each survive ON/OFF/ON/OFF VFG switches. Small subsequently runs for
  120.09 seconds and submits 6,962 frames. This count is texture submission on
  this workload, not physical monitor refresh or latency. All three stop with
  zero live texture pools and no QML warnings. A temporary static interval also
  exercises the exact-RGB equality path; this report does not assert a reuse count.
- `out/native-file-matrix/report.json`: actual worker, NVENC and SDK conversion
  for Small, Base, VDA and centered five-frame VDA with VFG on. Every owned input
  yields fully decoded 320x180 Half TB, 24 frames at 48 FPS, 0.5-second duration
  and audio; the original 24 FPS source has 12 frames. All use embedded Python
  with Windows-only PATH and an isolated model cache.
- `out/native-desktop-delivery/report.json`: the final one-part application ZIP
  and selected SM120 resource pass the distributed extractor's checksums. All
  4,793 app entries satisfy the pruning policy, and extracted representative
  native/application/media files match the prepared app. No other architecture
  resources are needed to extract this host's bundle.
- `out/native-delivery-launcher.json`: that extracted EXE shows its owned main
  window and closes normally with an isolated PATH. `out/native-delivery-qa/`
  repeats real native output, language switching and queued conversions from
  the extracted embedded interpreter.

## Package size

Decimal byte counts, excluding generated engine caches and optional models:

| Scope | Previous slimming candidate | Torch-free candidate |
|---|---:|---:|
| App files | 6,563,125,196 | 1,648,735,237 |
| App file count | 9,388 | 4,793 |
| App ZIPs | 3,944,459,156 (3 parts) | 788,372,541 (1 part) |
| App + selected SM120 ZIP | 4,216,476,017 | 1,060,389,402 |

The app shrinks a further 74.9%; download including SM120 shrinks 74.9%. Against
the original 1.0.0 app (9,730,850,006 bytes), the app shrinks 83.1%. A user's
architecture selects its resource; SM120 is only this host's example, not a
required 5090-only pack. Optional Base/VDA/VFG model policy is unchanged.
Candidate: `out/native-desktop/ScreenTo3D-1.0.0/`; assets:
`out/native-desktop/assets/`. The native launcher/version remains 1.0.0 with dirty
source metadata, and the build manifest hashes each bundled application source.

## Scope

Actual GPU tests use RTX 5090. Equality and reuse tests, generated media and short
native presentation checks establish their named contracts, not universal GPU
support, physical display/VR acceptance, indefinite soak or device-loss recovery.
No FPS improvement is claimed from package reduction. Existing model weights,
precision, licenses and VFG default-off policy are preserved. The published release
is unchanged; this candidate is not committed or pushed by this work.
