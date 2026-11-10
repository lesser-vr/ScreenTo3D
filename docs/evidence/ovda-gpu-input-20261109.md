# oVDA GPU capture and preprocessing — 2026-11-09

## Delivered change

The optional source-only oVDA live device engine now accepts the same owned
`GpuFrame` used by Small/Base/VDA. Window GPU sessions select existing WGC
D3D11/CUDA capture by default. Source RGB stays on the engine stream through
model input preparation and stereo synthesis. Monitor/default host and file
paths retain their existing CPU input; this is explicit routing, not fallback.
No new GUI setting, CPU thread change, model precision change or history/reset
policy change was introduced.

The shared `GpuExecution`/`GpuInputSupport` boundary provides owner/device/thread
checks and the existing exact scene thumbnail. The oVDA-derived implementation
remains in `experiments/ovda`. Its separately pinned kernel performs FP32
half-pixel bicubic (-0.75), replicated-edge canvas padding and FP32 mean/std
normalization. A same-stream reduction checks whether any RGB value exceeds one,
preserving upstream's all-0/1 normalization behavior without host readback. BGRA
alpha is excluded. RGB and pitched BGRA use the same contract.

The scalar reduction scratch belongs to the input adapter. Engine shutdown
waits for the owned stream before dropping the adapter. Device tokens retain
their tensors through consumer completion; pending reset/re-inference, foreign
tokens, expired tokens and foreign-thread close are rejected. Model loading and
FP32/c16 cache behavior remain unchanged. Tiny scene/border observations still
cross to CPU; this is not an absolute zero-copy claim.

## Build and provenance

`scripts/build-ovda-input.ps1` builds only this optional kernel, outside the
portable build. CUDA 13.1.80, MSVC 2022, `-O2 --fmad=false`, SM120 plus compute_75
PTX. The current model loader remains validated for RTX 5090 only; embedding PTX
does not establish support on other GPUs.

- Source SHA256: `d70cb62c3c5e261d931d816ac72a0bdda8abcd42cdaf20b6ded10090d1e2e1c8`.
- DLL SHA256: `c8e46577269273be279458562d513aa2da60e3bc400f80d73717b1b53f6c1d29`.
- Manifest: `out/ovda-gpu-input/build-manifest.json`.
- The input runtime also verifies the existing trusted Base thumbnail DLL.
  Missing/corrupt oVDA binaries fail visibly. No NC runtime/weights were added
  to portable distributions.

## Correctness

`check_gpu_input.py` compares the GPU tensor with `FramePreprocessor` on all three
canvases, eight sizes per canvas, and public/zero/one/binary/random patterns:
120 comparisons. The checked sizes include 1080p, 4K, ultrawide, portrait,
square, 1056x608, a native-canvas size and 16x16. The initial and final tensor
tests found zero absolute error; the final run additionally exercises pitched
BGRA and DLL/dtype/canvas/size/thread/current-stream rejection.

Matched independent FP32 histories consume FloorballGame, OfficeWalk and
ParkingGarage for six source geometries, 330 frames total. Each clip has at
least 18 consecutive updates, crossing the 16-slot history eviction boundary.
Depth is read back only after its owner stream fence; cache comparisons include
initial state, frame 15 and the final frame. Both native Half TB textures are
read back for every compared frame. Measured maximum differences were zero for
source-sized depth, sampled caches and every packed output pixel. GPU inference
reported zero model-input upload and zero full-image readback. These matched
tests do not measure FPS, motion-to-photon latency or physical comfort.

Artifacts: `out/ovda-gpu-input-parity-20261109/report.json` and the final
`out/ovda-gpu-input-parity-20261109-r2/report.json`. The latter adds the negative
contracts and pitched input coverage. Public inputs come from the existing
local UVG-VCM corpus. No private capture was recorded.

Actual GUI validation at `out/ovda-gpu-capture-gui-20261109/report.json` passed
start, live input resize across 1080p/portrait/square/1056x608 and back, F11/Esc,
output minimization, output close, restart, preparation cancellation and movement
on PG32UCWM and Owl3D Shift. Windows DPI rounding produced a 1025x1025 square
fixture; Half TB correctly packs that as 1025x1026. This is display movement and
resource-lifecycle evidence, not Owl3D 3D-mode or comfort acceptance.

## Actual native throughput

RTX 5090, Windows, driver 621.14, Torch 2.7.1+cu128 and TensorRT 11.2.1.2. Both
conditions use the same pinned current-device FP32 518x924 control engine from
the [precision experiment](ovda-precision-aspect-20261109.md):
`7bd4916e0104a1306c99dd0bb5a37e8bf27aed0f8ac698b5f35f1076147b0e75`.
Production model/precision pins were not replaced. That control's comparison
against the installed FP32 engine is recorded in the precision evidence.

An owned FloorballGame preview advances on a 16 ms timer, observed about 62.6
advances/s. 4K scales this public source; it is not native 4K game rendering or a
4K decoder benchmark. Settings: native Half Top-and-Bottom, strength 0.5, VFG
off, no app FPS cap, unchanged stereo/history policy. CPU threads were unchanged.
For each source size, the session order is CPU/GPU/GPU/CPU. Each session discards
three seconds of warmup and measures three adjacent three-second windows:
six windows per condition and size. These are short repeated measurements,
not a sustained soak. All eight sessions stopped with zero live native pools
and nodes, enforced by the benchmark.

| Input/per-eye size | Input path | Median native FPS | Window min–max | Mean device GPU |
|---|---|---:|---:|---:|
| 1920x1080 | Existing CPU | 25.12 | 23.61–25.67 | 42.12% |
| 1920x1080 | GPU | 58.21 | 57.63–58.66 | 84.00% |
| 3840x2160 | Existing CPU | 9.98 | 9.95–10.28 | 47.38% |
| 3840x2160 | GPU | 45.78 | 44.60–45.96 | 84.88% |

Output FPS counts distinct native submissions, not physical scanout. The GPU
condition is approximately 2.32x/4.59x faster in these runs. Device-wide NVML
utilization is sampled every 0.5 s and includes the source, desktop and other
clients. Utilization increases as CPU starvation falls and more frames execute;
this is not a claim of lower GPU load or process-exclusive utilization.

The benchmark checks transfer counters in every timed window: CPU input must
upload bytes; GPU input must report zero model/RGB H2D. Small bounded CPU
observations remain in GPU D2H counts. Tiny mask/position schedule uploads are
unchanged and are not included in these model/RGB counters. Strict missed-frame resets are unchanged;
their observed frequency changes with throughput. These unmatched real-time
histories are throughput evidence, not an independent temporal-quality comparison.

Valid artifact: `out/ovda-gpu-capture-native-20261109-r2/report.json`.
Reproduce with `benchmark_precision_live.py --capture-comparison --windows 3
--layout half-tb --output <new-directory>` in the prepared source GUI environment.
The first run without `-r2` is invalid as an A/B: the controller overwrote a
partial keyword, so both conditions actually used GPU input. Its audit file
records that exclusion. The fixed child wrapper overrides the snapshot inside
the worker and verifies the observed transfer contract.

The affected model-selection, capture-selection and oVDA-binding unit checks
pass (17 tests). Longer sessions, other GPUs, Full SBS performance and physical
display comfort were not established by this change.
