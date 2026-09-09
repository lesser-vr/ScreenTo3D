# P1 one-frame motion-aligned history, 2026-09-09

## Decision

CPU prototype not selected for live integration: temporal processing alone exceeds
the 16.67 ms budget. Retained as a bounded reference for a possible GPU experiment,
not a deployed fix. No application defaults, mode routing or stereo policy changed.

## Contract

`v1/temporal_depth_experiment.py` owns only the preceding **raw**, normalized depth
and grayscale image. There is no recursively filtered history. Forward/backward
OpenCV DIS FAST flow aligns the history at the model grid. Bounds, one-pixel
forward/backward residual, photometric error .06, depth disagreement .08 and a
dilated depth-edge mask reject unreliable history. Confidence scales a maximum
.35 blend weight. Rejected pixels use current depth exactly. This is one common
monocular output, not separate left/right histories; no SBS renderer was integrated.

Start, source/grid resize, nonconsecutive sequence, nonpositive or over-50ms time
delta, explicit cut and coarse photometric cut reset to current depth. The general
prototype permits one preceding frame up to 50ms old; the tested 60Hz run's maximum
was 16,666,667ns. This is not proof of motion-compensated lower-rate depth support.

Comparison baseline is a model-grid same-coordinate EMA proxy: current weight .55,
RGB change .04 dilated 7x7 and depth disagreement .08 reject history. It is **not**
the full-resolution native implementation. Fresh depth is available every frame.
No assertion of bitwise parity or exact deployed-baseline quality is made.

## Executed evidence

`v1/evaluate_temporal_depth.py`, OpenCV one CPU thread, existing RTX 5090 setup.
Synthetic 180x320 textured camera pan at two pixels/frame, 90 frames, explicit cut
at 45, Gaussian depth noise sigma .005, seed 4931. Predeclared gate: at least 5%
ground-truth MAE reduction, exact cut fallback and at most one 60Hz-frame history.
Baseline MAE .003992177, candidate .003146767: **21.17% reduction**, gate passed.
This controlled planar/noisy case does not establish real-world depth accuracy.

Three checksum-pinned original 3840x2160 UVG-VCM public clips, 180 frames (three
seconds) each, 540 total. Distill FP32 at 518x518 supplies every current depth;
2/98-percentile bounds are independently smoothed with current weight .55.
Timing covers RGB-to-grid grayscale, CPU flow, rejection, blend and owned copies,
not inference, upscaling, stereo or presentation. Excluding the first reset frame:

| Scene | Temporal P50 ms | P95 ms | Mean history-accepted fraction |
|---|---:|---:|---:|
| FloorballGame | 25.996 | 29.658 | .9186 |
| OfficeWalk | 25.837 | 29.952 | .7731 |
| ParkingGarage | 26.165 | 31.518 | .9279 |

Mean consecutive-depth-change MAE baseline/candidate was .003273/.003447,
.011781/.011623 and .001336/.001485 respectively. This unsigned unaligned proxy
has no consistent win and is not a ghosting, temporal accuracy or comfort score.
The last-frame four-panel image of each clip was inspected: subject boundaries
remain recognizable, but differences are too small to establish a quality winner.
No full motion playback, real occlusion ground truth, games/HUD or HMD review.

Seven CPU tests pass: bounded static blending, flow/photometric rejection, depth
disagreement, identity/time/cut reset and owned copies, invalid input preserving
state, translated-object revealed-background exact fallback, resize/automatic cut.
The moving-object test supplies exact flow; it does not validate DIS on all objects.

## Reproduction and provenance

Run `v1/evaluate_temporal_depth.py --output <fresh-directory>` in the prepared
environment documented by the Distill experiment. Controlled local engine loading
uses the same pinned FP32 engine; no external serialized engine is accepted.
Source attribution and artifact trust are in [Distill evidence](p1-distill-small.md).
Completed output: `out/p1-temporal-depth-20260909/report.json`, SHA256
`31445ef2735de5bd784af288c5423db14097629769e70e5622e60a3122d15317`.
The report stores all per-frame rows and the measured evaluator/prototype hashes.
Twelve four-panel PNGs were generated; only three last-frame panels were inspected.
GPU engine and captures closed before final report publication. This is bounded
experimental closure, not a sustained/live/stereo/VR support result.
