# oVDA allocation and validation cleanup — 2026-11-09

## Change and ownership

The source-only live device runtime reuses one model input tensor, five model
output tensors and sixteen mask/position pairs. `OvdaBuffers` owns those buffers,
a device status scalar and a pinned host scalar on the engine's existing stream.
GPU preprocessing accepts the persistent input destination; host input copies
into that same destination. File-only `OvdaTrt` remains unchanged.

The existing single cache bank stays allocated across resets and is zeroed on
the owner stream. Once full, a native kernel shifts slots 1..14 to 0..13, writes
the new value to slot 14 and zeros slot 15. Each thread owns one feature across
all temporal slots, so this in-place update has no overlapping thread ownership.
It replaces four `cat` allocations and their zero tails without a second large
cache bank. Reset reasons, cache capacity, masks and model values are unchanged.

Normal inference previously waited for TensorRT, then separately read a finite
predicate for each of the five outputs: six validation-related host waits. The
new device reduction checks every depth/cache output, transfers one status int
to pinned memory and waits once before lending any depth token. Nonfinite output
still aborts before cache updates/publication. Pending-token exclusion, owner and
current-stream checks, consumer-completion fences and close fences remain.
This does not remove all synchronization or all per-frame allocation: restored
source-resolution depth and owned captured frames still have their lifetimes.

No precision, model/profile, input ratio, history-gap policy, stereo quality,
CPU thread setting, app FPS default or user-facing option changed. No oVDA code
or weights were added to a portable distribution.

## Provenance and comparison reference

The source app still validates its existing FP32 model artifacts. A pinned
pre-change device-runtime snapshot was saved before editing:
`out/ovda-runtime-cleanup-20261109/reference/device_depth.py`, SHA256
`e104fd8fc1e4763e50bd09d0afc83a60732c37239193997fd56a56f74be45af7`.
`runtime_trial.py` verifies that explicit local reference before loading it for
tests; it is never a runtime fallback.

The optional native runtime was rebuilt with CUDA 13.1.80, MSVC 2022, FP32,
`--fmad=false`, SM120 and compute_75 PTX using `scripts/build-ovda-input.ps1`.

- Native source SHA256: `349b1c8da8e0ff1ea578ad127465d611ba6ec40971b79666432fa52cdbd4ad74`.
- Native DLL SHA256: `89c5caea88cf1f074855fa0a97d833626f3b6666b11405313b8005a8d4b8375e`.
- Archived manifest and implementation hashes:
  `out/ovda-runtime-cleanup-20261109/build-manifest.json` and `source-hashes.json`.

Both comparison variants use the same input algorithm and trusted native library;
the reference uses its original per-frame allocations, cache concatenation and
Torch finite predicates. Model precision is FP32 in both conditions.

## Correctness and failure checks

`check_gpu_input.py --reference-runtime` compared independent before/after GPU
histories on FloorballGame, OfficeWalk and ParkingGarage, six geometries and all
three installed inference canvases: 330 frames, including full-cache eviction
and clip resets. Source depth, sampled recurrent cache tensors and actual native
Half TB texture pixels all had zero measured difference. The unchanged input
transform also passed 120 CPU/GPU comparisons, including zero/one/binary/random
patterns and pitched BGRA. Readbacks were explicitly fenced and excluded from
FPS measurement. Artifact: `out/ovda-runtime-cleanup-20261109/parity/report.json`.

`check_runtime_buffers.py` verified persistent input/output/schedule/cache
addresses, all four reset reasons with zeroed caches, pending/expired-token and
foreign-thread protection, and rejection of a foreign validation/cache stream.
NaN, positive infinity and negative infinity were injected into the final element
of every output (15 cases); all were rejected. A real inference followed by an
injected nonfinite cache output closed the engine without returning a token or
incrementing completed-inference count. Three host-input frames matched the
reference exactly. Artifact: `out/ovda-runtime-cleanup-20261109/buffers-final.json`.

Actual GUI start, input resizing across 1080p/portrait/square/1056x608 and back,
fullscreen, both-monitor movement, stop/restart and preparation cancellation pass
at `out/ovda-runtime-cleanup-20261109/gui/report.json`. Seventeen affected model,
capture-selection and oVDA-binding unit checks also pass. These are bounded
development checks, not device-loss, long-run or physical-comfort acceptance.

## Allocation measurement

After 18 warmup updates, six steady full-history 1280x720 inferences measured
Torch's peak *additional allocated bytes* relative to the start of each call.
Each token was completed and released before the next sample. No captured frame
upload or SBS output was part of this isolated measurement.

| Quantity | Before | After |
|---|---:|---:|
| Extra Torch allocation peak per sampled call | 218,374,144 B (208.26 MiB) | 3,686,400 B (3.52 MiB) |
| Retained cache bytes | 190,857,216 B | 190,857,216 B |
| Fixed inference/status/schedule buffers | none | 19,588,868 B (18.68 MiB) |

All six samples in each condition matched the listed peak. The remaining 3.52 MiB
is the source-sized FP32 depth tensor. These figures exclude TensorRT/native
allocations, CUDA allocator reservation and total device VRAM. They do not mean
that the entire model/session uses only 3.52 MiB.

## Actual native performance

The final comparison uses RTX 5090, driver 621.14, Torch 2.7.1+cu128 and TensorRT
11.2.1.2. Both conditions use the same current-device FP32 518x924 control plan
from the [precision evidence](ovda-precision-aspect-20261109.md), SHA256
`7bd4916e0104a1306c99dd0bb5a37e8bf27aed0f8ac698b5f35f1076147b0e75`.
GPU capture/preprocessing is enabled in both. An owned public FloorballGame
window advances on a 16 ms timer; 4K scales that source, rather than testing a
native game or decoder. Settings are native Half TB, strength 0.5, VFG off and
unlimited app output. The normal user's FPS setting remains unchanged.

At each resolution the session order is before/after/after/before. Each session
discards three warmup seconds then measures three adjacent three-second windows:
six windows per condition. Output FPS counts distinct native submissions, not
physical scanout. Device-wide NVML samples include public playback, desktop and
other clients. The benchmark requires zero model/RGB H2D counters in every window
and zero live native pools/nodes after each of eight sessions.

| Input/per-eye size | Runtime | Median native FPS | Window min–max | Mean device GPU |
|---|---|---:|---:|---:|
| 1920x1080 | Before | 58.20 | 57.94–58.65 | 83.29% |
| 1920x1080 | After | 60.05 | 59.84–60.26 | 86.19% |
| 3840x2160 | Before | 45.54 | 45.36–45.74 | 84.62% |
| 3840x2160 | After | 47.09 | 46.62–47.26 | 86.95% |

Median output increased about 3.18% and 3.40%, respectively. Source advance rates
averaged 62.49–62.65/s across the four conditions. The higher GPU utilization
reflects increased work throughput; this is not a lower-GPU-load claim. The
normal strict missed-frame reset policy was retained in both conditions.

The final numbers are recorded at
`out/ovda-runtime-cleanup-20261109/native-final/report.json`; the earlier exploratory
run is retained at `native/report.json`. Reproduce with
`benchmark_precision_live.py --runtime-comparison --windows 3 --layout half-tb
--output <new-directory>`. The result is a modest FPS improvement; the larger
effect is lower allocation churn and temporary memory peak. Short runs do not
establish sustained throughput, other-GPU support or physical display quality.
