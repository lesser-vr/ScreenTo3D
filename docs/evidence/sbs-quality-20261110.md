# Native SBS quantitative quality baseline — 2026-11-10

## Scope and artifacts

The new `scripts/run-sbs-quality.ps1` / `v1/evaluate_sbs_quality.py` diagnostic
measures temporal disparity change, boundary preservation/error and response to
a controlled input change. No production rendering, model policy or preferences
were changed. The measurement definitions and repeat command belong to
[BENCHMARKS](../BENCHMARKS.md#matched-sbs-quality-dashboard).

Final local artifacts:

- `out/sbs-quality-20261110-final/report.json`: completed, all four models,
  raw frame metrics, response traces, resolved policies and artifact identities.
- `out/sbs-quality-20261110-final/summary.md`, `natural.csv`, `response.csv`:
  readable results and reusable tables.
- `out/sbs-quality-20261110-contracts-verified.json`: all 94 quality contracts pass.

The earlier `out/sbs-quality-20261110/` is a pilot with different sampling/warmup
and response definitions; it is not the baseline. Formatting, unavailable-data
handling and metadata were refined after the final model execution without
replacing measured frames. Small's model/plan identity was collected afterward
from the same unchanged configured local model/cache; this provenance is explicit
in the report. The synthetic Half TB calibration was also run separately and
included in the final report.

Prepared RTX 5090, Torch 2.7.1+cu128, revision
`c743214f889e84a2a43ce46273b054ac3d0c6446` with working changes. Small FP16,
Base FP16 engine, installed VDA mixed FP16 and oVDA 518x924 mixed FP16/c16 use
the ordinary trusted GPU preprocessing/inference/native renderer bindings.
Model-specific defaults remain variables; this is a current application-policy
comparison, not an isolated neural-network benchmark.

All models receive identical pinned public UVG-VCM FloorballGame, OfficeWalk and
ParkingGarage previews (CC BY 4.0; exact preparation and attribution retained in
the report). Input is 1920x1080, fixed 60 Hz source timestamps, 120 frames per
clip, strength .5, Half TB and VFG off. After 32 warmup frames, each model/clip
has 88 measured temporal pairs; no later cut/gap/resize reset occurs. RGB and
flow analysis use 480x270. Disparity values alone are converted to logical
restored-eye 3840-wide pixel units; this was not 4K input or 4K inference.
Native output readback retires every slot before reuse. Instrumentation and
sequential input feeding make these quality measurements unsuitable as FPS tests.

## Natural temporal and boundary proxies

OfficeWalk has the highest temporal RMS for each model in this short sample:

| Model | Temporal RMS, logical 4K px | Edge temporal RMS, logical 4K px | Absolute disparity P95, logical 4K px | Visible-source edge RGB MAE, 0–255 |
|---|---:|---:|---:|---:|
| Small | .382 | .480 | 14.831 | 3.778 |
| Base | .355 | .478 | 18.516 | 3.523 |
| VDA | .514 | .653 | 27.134 | 4.508 |
| oVDA | .543 | .667 | 24.901 | 4.495 |

OfficeWalk flow validity is 69.6% overall and 50.5% on edges; spatial edge
visibility coverage is 96.4–97.2%. Coverage is reported for every clip/model.
These metrics quantify temporal/output preservation, with contributions from
real depth changes, model response, postprocessing and correspondence error.
They are not depth-accuracy measurements. Natural edge reprojection has no
ground truth for hidden background and intentionally excludes occluded regions.

Equal strength .5 does not produce equal disparity: Small has much less parallax
than VDA/oVDA here. Lower absolute temporal/RGB error therefore does not establish
that Small has better stereo quality. The CSV also exposes signed P5–P95 span
and case-level temporal RMS/span (unavailable for near-flat depth); this does not
remove the need for scene-depth truth or replace the raw amplitude and coverage.

## Controlled tracking response

A constant-size card relocates after 96 source updates, then remains still for
96 updates. The old/new composite changes at most 12.5% of pixels and does not
cause a scene reset. Median disparity is measured in a fixed region at the new
card location. Each model's stable tail is its own target, not known true depth.

| Model | First 90% crossing, source ms | Settling within +/-10%, source ms | Signed amplitude, logical 4K px |
|---|---:|---:|---:|
| Small | 0 | 0 | 2.117 |
| Base | 0 | 0 | 5.370 |
| VDA | 0 | 1216.667 | 1.225 |
| oVDA | 33.333 | 500 | 4.915 |

VDA's immediate first crossing is followed by excursions, hence its longer
settling time. This is one composite stimulus and its amplitude differs across
models. It does not establish a general model-latency ranking. Zero means the
first processed changed source frame meets the criterion, not zero processing
or monitor latency. All four targets meet the stable-tail checks in this run.
Frozen output or insufficient target change is unavailable, never a perfect
tracking score. Full before/after samples are retained in `response.csv`.

## Known-truth renderer controls and checks

The independent layered oracle uses known RGB/depth and 1920-wide eyes, with
foreground widths 1/2/8/96 px, strengths .25/.5/1 and 21 phases per case.
Current fill-enabled rendering passes its declared boundary RGB and temporal
error budgets against fill-disabled controls in all 12 cases. This evaluates a
renderer component with known depth, excluding model inference. At strength .5,
boundary RGB MAE changes from .430 to .327 (1 px) and .649 to .554 (8 px).
Native Half TB output at zero disparity exactly matches independent CPU packing,
including opaque alpha. This guards against packing/sampling errors contaminating
the natural RGB proxy.

Six new CPU metric contracts cover empty-region handling, analytic movement and
un-normalized drift, edge RGB errors, frozen/overshooting response, Half TB
sampling and actual RGB flow on a known translation. The complete quality group
passes 94 tests. These checks and bounded measurements provide a numerical
baseline for future changes; physical Owl3D viewing/comfort, long sessions,
hidden-surface correctness and real-time throughput were not accepted here.
