# Base FP16 native SBS throughput and matched-frame error

2026-11-05. Follow-up to the [isolated TensorRT FP16 test](base-trt-fp16-20261105.md).
The user requested actual native SBS FPS plus spatial and temporal error.
The production default remains FP32. All substitutions exist only inside explicit
diagnostic processes; the application allowlist and installed engines are unchanged.

## Actual application throughput

RTX 5090 / driver 621.14, TensorRT 11.2.1.2. Same pinned 518x924 plans as the
isolated test, Balanced policy, strength 1.0, GPU window capture/preprocessing,
CUDA stereo, native Qt/D3D11 output, CUDA graph off, target **60 Hz**. This target
is an experimental benchmark setting; the ordinary app's 30 Hz default is unchanged.

Public FloorballGame playback runs in an owned source process. Each engine/size
uses a separate app process, six seconds discarded warmup then five measured
six-second windows. Measurement order: 1080p FP32/mixed/selective, then 4K
selective/mixed/FP32. No quality readback workload runs during these windows.
The source timer painted 62.29–62.39 fps on average across sessions, similar for
all candidates; this timer is not a precisely paced 60.000 fps video reference.
GPU utilization before each session was 0–2%; unrelated applications were retained.

FPS counts distinct native **Qt afterFrameEnd IDs**, not worker loops or duplicate
Qt callbacks. Full SBS textures are 3840x1080 or 7680x2160 respectively. The
output window is fitted to 1400x650 logical pixels; this is not 1:1 physical 8K
scanout. The 4K source is the existing 1080p public preview enlarged by the source
window, not a new native-4K media-quality claim.

| Input / per eye | FP32 | Mixed FP16 | Selective FP16 |
|---|---:|---:|---:|
| 1920x1080 | **30.00 fps** (29.98–30.17) | **59.63 fps** (59.34–59.79) | **59.79 fps** (59.33–59.87) |
| 3840x2160 | **20.52 fps** (20.36–20.70) | **54.78 fps** (54.20–55.49) | **48.88 fps** (48.42–49.01) |

Values are medians and five-window ranges. Relative to this run's control, mixed
FP16 is 1.99x at 1080p and 2.67x at 4K; selective is 1.99x and 2.38x. Both 1080p
candidates reach the configured presentation ceiling; their small FPS difference
does not establish a speed winner there. Neither establishes sustained 4K60.
Earlier controls measured different FPS; they are not used as this comparison's
denominator. This test is bounded, not a long-session or general support claim.

Sampled worker intervals (median milliseconds; depth includes GPU preprocessing,
inference, source-size resize and validation; total excludes GUI presentation):

| Input | Engine | Depth | Stereo | Worker total |
|---|---|---:|---:|---:|
| 1080p | FP32 | 30.47 | 2.14 | 33.40 |
| 1080p | Mixed FP16 | 4.81 | 2.11 | 7.91 |
| 1080p | Selective FP16 | 6.33 | 2.09 | 9.09 |
| 4K | FP32 | 35.69 | 12.49 | 49.24 |
| 4K | Mixed FP16 | 5.30 | 9.76 | 17.82 |
| 4K | Selective FP16 | 9.07 | 10.37 | 20.18 |

The existing timestamp readback probe decoded 15/15 outputs per session outside
the throughput windows. Median source-paint-to-readback ages were 82.78/45.85/46.41
ms at 1080p and 105.79/57.27/76.07 ms at 4K (FP32/mixed/selective). This probe
includes readback overhead and clock-marker decoding; it is not motion-to-photon
or physical display latency. All six sessions stopped with zero live native
pools and nodes; the harness's bounded overload/backpressure checks completed.

## Spatial and temporal comparison method

Independent histories process identical ordered frames for all three engines;
this avoids comparing different frames merely because the engines run at different
speeds. The full live GPU preprocessing, depth normalization, temporal filtering,
guided filtering, flat-background refinement and native texture projection run.
Each native output texture is read back at full SBS resolution. The diagnostic
readback is not included in the throughput results above. Input staging is owned
GPU RGB prepared from known decoded frames, not real WGC capture in this phase.

Per resolution: 60 consecutive frames from each of FloorballGame, OfficeWalk and
ParkingGarage, then 12 identical OfficeWalk frames from reset histories, then
four alternating black/white cuts. Total 196 matched inputs per resolution,
392 across both resolutions, 1176 native outputs across three engines. The two
candidate comparisons therefore produce 784 metric rows. Frames from different
clips retain histories to exercise transitions; static history is reset explicitly.

The metric contract is written to `report.json` before processing:

- RGB MAE uses 0–255 channel code values, with left/right and edge-region MAE.
  Edges are reference SBS grayscale Sobel `abs(dx)+abs(dy) >= 128`.
- Changed-pixel fractions count any channel differing by more than 8 or 32.
- Effective postprocessed depth difference times `width * divergence` gives
  **left-right disparity difference in pixels**. Per-eye shift difference is half.
- Temporal RGB discrepancy is `mean(abs(E[t] - E[t-1]))`, where
  `E = candidate SBS - FP32 SBS`. Temporal disparity uses the analogous quantity.
  Ordinary-motion summaries exclude detected cuts and clip-group transitions.
  Fixed pixel coordinates are used: this includes motion/occlusion differences
  and is not an optical-flow-warped flicker score or a perceptual acceptance test.
- The comparison is observational. No relaxed pass threshold or quality promotion
  is invented after looking at these results.

## Spatial and temporal results

All 392 matched inputs completed for all three engines: effective depths finite,
opaque native output, no pending depth token after render, matching RGB scene-cut
decisions, and engine/pool cleanup without an exception. Natural-video rows below
use 180 frames per resolution/candidate; temporal averages use 177 within-clip,
non-cut consecutive pairs. Static and deliberate cuts are excluded from averages.

| Resolution | Candidate | RGB MAE, 0–255 | Pixels with any channel error >8 | Edge RGB MAE | Disparity MAE, px | Temporal RGB discrepancy | Temporal disparity discrepancy, px |
|---|---|---:|---:|---:|---:|---:|---:|
| 1080p | Mixed FP16 | 0.08981 | 0.30893% | 0.25474 | 0.01398 | 0.12590 | 0.00522 |
| 1080p | Selective FP16 | 0.06331 | 0.21433% | 0.17936 | 0.00865 | 0.10150 | 0.00485 |
| 4K | Mixed FP16 | 0.08045 | 0.29828% | 0.29020 | 0.02989 | 0.10727 | 0.01137 |
| 4K | Selective FP16 | 0.05583 | 0.19535% | 0.19573 | 0.01910 | 0.08607 | 0.00990 |

These are mean frame metrics. Selective FP16 lowers average spatial and temporal
discrepancies in this sample, including all three clips' average RGB error. It is
not uniformly better at every point. At 4K, worst single-pixel left-right disparity
differences are **3.25246px mixed / 3.55936px selective** (per-eye shift differences
1.62623 / 1.77968px). The largest per-frame pixel p99 values are 0.56195 / 0.50929px.
At 1080p, maximum disparity differences are 1.13635 / 1.45647px. Thus small averages
do not establish pointwise parity or remove local outliers.

At 4K, maximum channel errors reach 243 / 242 code values, while mean fractions
of pixels exceeding 32 in any channel are 0.01542% / 0.01020%. Small geometric
differences can produce large local RGB differences near edges/occlusions; these
tails should not be hidden by a whole-frame mean. Left/right average RGB errors
are similar (mixed 0.08035/0.08055; selective 0.05579/0.05586). ParkingGarage has
the largest clip-average RGB discrepancy: 0.14978 / 0.09627 at 4K, versus
FloorballGame's 0.02373 / 0.01908 and OfficeWalk's 0.06784 / 0.05213.

For each resolution and candidate, the final four frames of the 12-frame static
sequence had **zero** inter-frame pixel change, as did FP32. All four black/white
cuts were detected identically and their candidate RGB matched FP32 exactly.
These bounded checks do not establish stability for all moving content or prove
motion-compensated flicker/physical binocular comfort. A saved 1080p OfficeWalk
FP32/candidate still pair was inspected for valid two-eye image content; no
normal-speed playback or headset quality acceptance was performed.

## Interpretation

There is a substantial **actual native application** speed benefit, beyond the
earlier model-only measurement. Mixed FP16 leads at 4K; selective trades about
5.90 fps for lower average spatial/temporal error on this corpus. Both remain
credible experimental candidates. The existing strict raw-depth parity failure
is not erased by these averages, and no new perceptual pass threshold was adopted.
The 518x896 profile, long sessions, broad resize/crash/device-loss lifecycle,
real games and physical binocular evaluation remain open for these new engines.
The ordinary app retains FP32; RowFlow's deferred viewing is unaffected.

## Reproduction and artifacts

Test-only scripts: `v1/base_trt_fp16_trial.py`,
`v1/benchmark_base_trt_fp16_live.py`, `v1/compare_base_trt_fp16_sbs.py`.
The adapter verifies hardcoded plan hashes/sizes and allows only its pinned
518x924 artifact. Three unit tests cover integrity rechecking, invalid shape/path,
restoration on failure, and an untouched FP32 path. No dependency install is needed.

```powershell
$env:PYTHONPATH='v1;out/gui-python-deps;out/capture-python-deps;out/v1-python-deps'
& out/vda-oracle-env/Scripts/python.exe v1/benchmark_base_trt_fp16_live.py --candidate mixed --output out/fp16-live-NEW --sizes 3840x2160 --modes balanced --hz 60 --path gpu-texture --source FloorballGame --source-process --seconds 6 --repeats 5
& out/vda-oracle-env/Scripts/python.exe v1/compare_base_trt_fp16_sbs.py --output out/fp16-errors-NEW --frames 60
```

Observed artifacts: `out/base-fp16-native-20261105/<size>-<candidate>/` contains
raw run windows, environment, CSV and explicit `precision-trial.json` provenance;
`out/base-fp16-native-20261105/summary.json` summarizes performance.
`out/base-fp16-sbs-errors-20261105/report.json` contains the numerical contract,
per-frame results and engine telemetry. Its per-size/candidate folders retain the
largest-MAE comparison's source, FP32 and candidate PNGs, with `case.json`.

The normal app was not promoted to FP16 and no commit/push was requested.
Both complete GPU runs exited zero; three adapter integrity tests and Ruff E9/F
checks passed, with a clean whitespace check. The existing control plan portability
warning and coexisting TensorRT logger warnings were retained in run output.
