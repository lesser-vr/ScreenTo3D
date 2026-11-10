# Medium VFG native SBS experiment — 2026-11-06

## Scope and result

An isolated Base FP16 / Medium 2x VFG prototype completed actual window capture,
CUDA SBS and Qt native output. At 4K input / 7680x2160 Full SBS, native output
increased by 42.50%, with lower fresh-frame throughput, higher original-frame
age and higher private process memory. This is experimental evidence, not a
default promotion or continuous binocular-quality acceptance.

| Metric | Baseline | Medium VFG |
|---|---:|---:|
| Native output fps, median of five windows | 50.47 | 71.92 |
| Native output fps, window range | 49.66–50.58 | 71.12–72.98 |
| Fresh Base SBS fps, median | 50.23 | 35.94 |
| Observed generated fps, median | 0 | 35.96 |
| Original capture-to-Qt age, median of window p50 (ms) | 23.51 | 41.58 |
| Original age, median of window p95 (ms) | 32.04 | 47.24 |
| Generated midpoint age, median of window p50 (ms) | — | 40.77 |
| Generated oldest-input age, median of window p50 (ms) | — | 54.79 |
| First measured worker private memory (GiB) | 2.96 | 6.81 |
| Private-memory change across measured windows (MiB) | +0.289 | +0.102 |

The original-frame median age increases by 18.07 ms. Private memory is a Windows
process metric, not VRAM; its short-term stability does not prove absence of leaks.
VFG output intervals have roughly 13.75–13.97 ms window medians and 20.1–21.3 ms
p95: the measured output is not a perfectly even 72 Hz cadence.

## Measurement method

- RTX 5090, driver 621.14; CUDA 13.1.80 bridge, Python 3.13.14, Torch 2.7.1+cu128,
  TensorRT 11.2.1.2 Base FP16 and Qt 6.10.2. Official VFX SDK/feature 1.3.0.0
  loads its own CUDA 12 / TensorRT 10 dependencies in the same isolated worker.
  Archive provenance, SDK pins and terms are in the
  [standalone record](vfg-experiment-20261105.md).
- Public FloorballGame preview, decoded/painted without a requested frame cap in
  an owned source process, captured through the normal WGC GPU path. The existing
  compressed 1080p preview is upscaled to 3840x2160, not native 4K source detail.
  Source paint-rate medians were 75.75 and 77.61 fps respectively.
- Same Base FP16 inference, depth/stereo policy and native output; unlimited
  presentation. Full 7680x2160 textures are fitted into a 1400x650 output window.
  Baseline first, then VFG, each in one session with 4 seconds warmup and five
  consecutive 4-second windows. These are not five independent process repeats
  or randomized comparisons.
- Both runs use the same observer. Distinct native output IDs are collected
  after the native node's Qt `afterFrameEnd` metrics callback. Observed sample
  counts equal native completion counts in every measured window. Baseline:
  199/201/203/202/202; VFG: 285/288/288/292/292.
- Age is the source capture timestamp to Qt completion. Generated frames have
  midpoint and oldest-input timestamps, distinct from fresh inference IDs.
  This is neither physical scanout nor input-to-photon latency. Real games,
  display/Owl3D behavior and perceptual motion quality are outside this run.

## Implementation and ownership

`experiments/vfg/native_path.py` installs experiment-local renderer/mailbox/delivery
adapters. Base-only GPU window capture and timed native output are required.
No VFG entry is added to normal GUI settings or backend selection.

The renderer keeps previous/current/generated RGBA GPU frames on the borrowed
engine stream. It projects into its own GPU buffer before waiting for a shared
output slot. The only production hook is `requires_texture_slot` in `live_sbs.py`,
defaulting to true for every existing renderer. The deferred publisher still
acquires real metadata and keyed-mutex ownership immediately before writing.
It retains the existing two-slot shared pool and bounded timing records.
Three linear frames account for approximately 189.84 MiB at Full SBS 4K, apart
from SDK/model allocations and shared/native textures.

Medium uses explicit 2x midpoint generation, rebinding both input images each
pair. SDK automatic cuts are disabled; app cut/start/resize invalidates pair
history and emits an original only. Nonmonotonic or over-100ms source intervals
also skip interpolation. Capture index gaps alone are allowed if timestamps
form a valid pair. Generated then original output has separate IDs and due
times; per-output GUI notification ensures both frames can reach Qt. Retirement
drains leases regardless of presentation deadlines. Effect/postprocessing is
destroyed before the borrowed stream's engine owner.

Bridge SHA-256:
`236ab065e0baed1875ca89b1834ceb466cb32ccd415f96b54733a66d28bb1519`.
The pinned SDK and existing engine/native resource validations remain enforced.
Runtime/model binaries remain local ignored artifacts, with no distribution claim.

## Validation

- Six original-frame parity cases: three public frames at 1080p and 4K. Original
  CUDA renderer output equals the prototype's original RGBA exactly, and shared
  native publication/readback is exact. Medium generated output runs at both
  sizes with the mixed runtime. This is original-path parity, not a claim that
  generated images equal held-out true frames.
- 31 CPU tests pass: four experiment timing/mailbox cases, 12 existing native
  delivery protocol cases and 15 texture-mailbox cases. Ruff E9/F passes.
- 4K VFG hide/restore, input resize to 1280x720 with pool replacement,
  stop/restart, and cancellation during preparation pass. Stopped native pools
  and nodes are zero and stale output is cleared. Worker effect create/close
  counts are 2/2 for the resize session, 1/1 for restart and 0/0 for cancellation.
- Separate 1080p injected-cut run: two 3-second windows after 2 seconds warmup,
  forced reset every 30 Base frames. All observed forced-cut boundary outputs
  are original; none generated. A post-run assertion against the saved Qt samples
  verifies 17 boundary samples, all original (`cut-validation.json`). Lifecycle
  checks also pass with balanced
  resource counts. Approximately 120.40 native fps here is a functional-test
  observation, not a matched 1080p performance comparison.
- Natural-cut detector accuracy, continuous motion/binocular review, multi-hour
  stability, device loss and physical display latency remain untested.

## Local artifacts and excluded attempts

Final successful runs, each with `completed: true`:

- `out/vfg-native-baseline-4k-20261106/report.json`
- `out/vfg-native-medium-4k-20261106/report.json`
- `out/vfg-native-cut-lifecycle-1080-20261106/report.json`
- `out/vfg-native-cut-lifecycle-1080-20261106/cut-validation.json`
- Aggregation: `out/vfg-native-summary-20261106.json`
- Exact parity: `out/vfg-native-parity-20261105/result.json`
- Build: `out/vfg-native-bridge/build-manifest.json`

Early smoke found missing per-output GUI notification, which blocked slot return;
the prototype was corrected before the reported runs. Earlier acquisition before
projection also limited throughput; deferred publication produced the measured
candidate. The misleadingly named `out/vfg-native-medium-4k-20261105` was invoked
without `--vfg`; its report correctly records `vfg: false` and it is excluded.
Two subsequent attempts stopped safely when the source was hidden/minimized or
the desktop changed; the user confirmed these actions. Their incomplete samples
are excluded. The final retries completed with the source left visible, and all
test-owned source/output windows were closed afterward.

Reproduction commands are in the [experiment README](../../experiments/vfg/README.md).
