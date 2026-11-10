# Final native SBS RGB evaluation — 2026-11-10

## What was measured

Completed two complementary full-reference RGB experiments with current
Small/Base/VDA/oVDA GPU preprocessing, causal inference, model-specific
postprocessing and actual native Full SBS / Half TB texture publication:

1. **True binocular reference:** four project-authored analytic 3D scenes
   (`room`, `thin_edges`, `dark_objects`, `depth_layers`). An independent ray
   tracer renders center input and both target cameras, including hidden colors.
   1280x720, focal 1152px, 30mm baseline and 4.5m convergence. Each model/scene
   receives 32 static warmup updates, 16 static calibration updates and 16 new
   moving poses. Both eyes are scored. Total: 1024 scored model eye images
   across two formats, in addition to native known-depth controls.
2. **Spring camera hold-out:** existing `0001`, `0011`, `0021`, `0047` left-camera
   sequences plus the independently rendered original right-camera RGB. Model
   input is left camera only; only the generated right native eye has an original
   camera reference and is scored. This is not a true central-input binocular
   reference. Frames 1–32 warm up, 33–48 calibrate and 49–80 score. Total: 1024
   scored model right-eye images across both formats, plus known-depth controls.

The Spring extension extracts only 256 required right RGB/disparity members
from the official V2 archives: 633,834,525 compressed / 1,043,629,353 extracted
bytes, without downloading whole archives. CRC/size and SHA256 checks pass.
Source and attribution remain under `out/spring-source/right-manifest.json`,
alongside the original left-camera subset. Source: Mehl et al. (2023),
[Spring, DaRUS V2](https://doi.org/10.18419/DARUS-3376), CC BY 4.0. Analytic
fixtures are project-authored procedural surfaces, with no external media.

Prepared RTX 5090, Torch 2.7.1+cu128, current trusted Small FP16, Base FP16,
VDA mixed FP16 and oVDA mixed FP16/c16 bindings. Both source shapes select
518x924 for Base/VDA/oVDA; Small retains 518x518. Engine/native DLL hashes,
ordinary policies and actual per-scene projection calibration are in each
report. Revision `c743214f889e84a2a43ce46273b054ac3d0c6446` plus working changes.

## Camera and metric contract

The app deliberately compresses disparity and masks problematic window edges;
those choices do not correspond to a fixed physical reference camera. The
comparison therefore disables only nonlinear disparity compression and window
masking in the diagnostic, calibrates projection scale/convergence on preparation
frames and freezes them for scoring. Range/temporal/edge/fill policies otherwise
remain model-specific and active. No evaluation-frame RGB alignment or fitting
is allowed. This measures calibrated final rendering, not unchanged-default
geometry or the value of a comfort policy. App settings/preferences are unchanged.

Analytic calibration fits postprocessed projection depth to inverse Z. Spring
fits it to source GT disparity, then sets native right-eye displacement to the
negative GT disparity. Spring UHD storage is sampled `[::2,::2]` without dividing
vector values by two. Native slots are read and retired before reuse. One
inference/post update produces Full SBS followed by Half TB of the same depth.
This sequential instrumented process is not an FPS or physical latency test.

Scores use per-eye RGB PSNR (0–255), Gaussian RGB SSIM (11x11, sigma 1.5), and
[LPIPS-Alex v0.1](https://github.com/richzhang/PerceptualSimilarity) in FP32 with
RGB normalized to [-1,1]. No metric-image downscale is used. A common outer
8-row/16-column rim is excluded. Half TB reference eyes are independently box-
reduced and bilinearly restored to the logical eye size before comparison.
Full/Half scores are each relative to their own sampling reference; they are
not a direct ranking of the output formats. Scores average eyes/frames, then
weight each scene equally. GT-only boundary and disocclusion RGB MAE/counts
accompany global metrics; prediction-dependent masks cannot hide bad pixels.

The official AlexNet checkpoint and LPIPS linear weights have full SHA256 pins
in the tool and report; provenance is in `out/sbs-metric-weights/provenance.json`.
The task initially prepared official weights through torchvision/LPIPS and
verified the full identities during finalization. Future runs enforce those
pins before loading. `lpips==0.1.4` / `scipy==1.16.3` are isolated under
`out/sbs-quality-python-deps`; normal app dependencies were not replaced.
Reproduction methods belong to
[BENCHMARKS](../BENCHMARKS.md#full-reference-native-sbs-rgb).

## Spring right-camera results

Half TB, 1920x1080 logical eye. Higher PSNR/SSIM is better; lower LPIPS/MAE
is better. Regional MAE uses RGB byte/channel values.

| Model | PSNR, dB | SSIM | LPIPS | Boundary MAE | Disocclusion MAE |
|---|---:|---:|---:|---:|---:|
| Known-depth native control | 34.026 | .9487 | .05572 | 6.791 | 11.953 |
| Small | 25.745 | .7706 | .10546 | 15.185 | 17.488 |
| Base | **27.091** | .7948 | .09836 | **14.224** | **16.244** |
| VDA | 26.676 | .8022 | .09938 | 14.635 | 16.833 |
| oVDA | 26.738 | **.8032** | **.09751** | 14.585 | 16.595 |

All three alternatives improve PSNR, SSIM and LPIPS over Small in every Spring
Half TB scene. Base gains 1.346dB mean PSNR versus Small; oVDA reduces mean
LPIPS from .10546 to .09751. These observations support an RGB improvement over
Small for this camera-matched sample. They do not make one alternative uniformly
best: Base leads mean pixel/region errors, oVDA mean structure/perceptual scores.
Base/oVDA PSNR wins split 2–2; VDA/oVDA LPIPS wins also split 2–2. Exploratory
scene-bootstrap difference intervals among Base/VDA/oVDA include zero for the
three global metrics. Four scenes do not establish a general ranking.

Full SBS is also measured, scoring the same right camera:

| Model | PSNR, dB | SSIM | LPIPS |
|---|---:|---:|---:|
| Known-depth native control | 31.877 | .9211 | .07158 |
| Small | 24.842 | .7294 | .11730 |
| Base | **26.117** | .7556 | **.11090** |
| VDA | 25.680 | .7616 | .11275 |
| oVDA | 25.722 | **.7626** | .11096 |

All three alternatives improve the mean scores, but not every Full-SBS per-scene
metric wins: for example, VDA's PSNR improves in three of four scenes and Base's
LPIPS improves in three. Do not extend the Half-TB 4/4 observation to all formats.

## True binocular procedural results

Half TB, 1280x720 logical eyes, both eyes scored:

| Model | PSNR, dB | SSIM | LPIPS | Boundary MAE | Disocclusion MAE |
|---|---:|---:|---:|---:|---:|
| Known-depth native control | 43.530 | .9960 | .00659 | 2.022 | 5.933 |
| Small | **39.068** | **.9842** | .01691 | **4.471** | **14.131** |
| Base | 38.684 | .9835 | .01675 | 4.643 | 15.315 |
| VDA | 37.118 | .9816 | **.01647** | 4.730 | 16.560 |
| oVDA | 36.256 | .9761 | .01964 | 6.173 | 21.737 |

Small has higher PSNR than VDA/oVDA in all four primitive scenes, unlike the
Spring sample. VDA has the lowest mean LPIPS but wins only one scene versus
Small; that small mean difference is driven by scene effects and its exploratory
interval includes zero. These low-texture analytic scenes test camera geometry,
thin structures and occlusion, but are not representative enough to override
the cinematic reference with a universal model recommendation.

Full-SBS binocular results:

| Model | PSNR, dB | SSIM | LPIPS |
|---|---:|---:|---:|
| Known-depth native control | 44.306 | .9958 | .00438 |
| Small | **38.315** | **.9833** | .01516 |
| Base | 37.800 | .9826 | .01504 |
| VDA | 36.894 | .9811 | **.01267** |
| oVDA | 35.927 | .9755 | .01597 |

Depth accuracy and final RGB fidelity therefore should not be collapsed into
one ranking. Scene appearance, occlusions, range/filter behavior, disparity
mapping and sampling all influence the final image. The current measurements
compare final content at fixed reference cameras; a causal stage A/B would be
needed to attribute an RGB difference to a particular postprocessing step.

## Controls and validation

- The analytic renderer computes each camera independently by ray/surface
  intersections. It never uses a tested model's warp to generate target RGB.
  Native known-depth controls pass visible-interior MAE <3 and boundary errors
  below both zero stereo and swapped-eye controls in all eight scene/format cases.
- Spring known-source-disparity controls improve PSNR, SSIM and LPIPS versus
  zero-stereo source duplication in all eight scene/format cases. Only known-GT
  control NaNs are locally inpainted for finite native submission; model output
  is never repaired or given a prediction-dependent validity mask. Independent
  right-camera GT still contains unknown background/view-dependent effects, so
  known-depth rendering is a control, not a mathematical perceptual upper bound.
- All source/weight identities and model-independent scoring masks pass final
  checks. Every model/scene has only the initial reset; no scored-frame cut/gap
  changes the comparison. Each prepared model/scene calibration remains frozen.
- All 102 quality contracts pass. Metric identity/offset, stereo-camera sign,
  packing and known-truth geometry checks are included.
- All 12 comparisons (three frames per model) are exact for native Full output
  and projection depth with additional Half TB publication enabled versus disabled.
  This checks that dual-format instrumentation does not perturb later output.
- Fixed GT-defined boundary crops from both datasets were inspected as 2D images.
  They reveal geometric/background deviations but are not normal-speed playback,
  physical scanout or Owl3D comfort acceptance.

Retained artifacts:

- `out/sbs-rgb-quality-20261110/`: completed true-binocular `report.json`,
  `summary.md`, `cases.csv`, `protocol.json`, native sample PNGs and
  `boundary-comparison.png` / `boundary-crops.json`.
- `out/spring-rgb-quality-20261110/`: completed right-camera counterparts;
  per-frame/per-eye errors and scene-paired exploratory intervals are in JSON.
- `out/sbs-rgb-fixture-20261110/`: three-view RGB, inverse-depth/masks and
  integrity manifest. `v1/sbs_rgb_fixture.py` is the independent generator.
- `out/sbs-rgb-contracts-final.json`, `out/sbs-rgb-final-validation.log`,
  `out/sbs-rgb-publication-parity.json`: checks and exact instrumentation parity.
- `out/sbs-rgb-oracle-20261110/` is the preliminary integer-raster oracle probe,
  not the final known-depth baseline. Final reports explicitly enable subpixel
  and continuous coverage for those controls.

Post-run finalization adds scene-paired statistics, clarifies calibration units
and report captions, and verifies weight pins without replacing measured frames.
These bounded experiments do not establish unchanged-default SBS quality,
sustained performance, real-game generalization or viewing comfort. No model,
renderer default, app preference, release archive or executable was changed.
