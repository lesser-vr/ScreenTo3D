# Spring known-truth model and application comparison — 2026-11-10

## Execution and data

Completed all four current live model bindings on four Spring scenes selected
before any model result was available: `0001`, `0011`, `0021`, `0047`.
The deterministic selection takes evenly spaced eligible sorted training IDs
with at least 80 frames, and the first 80 left-eye RGB frames in each.
Only the left image is input to the monocular model. No model was retrained.
Public training-split GT is used; held-out means separation of calibration and
scoring frames, not a claim about the models' upstream training data.

Source: Mehl, Schmalfuss, Jahedi, Nalivayko and Bruhn (2023), *Spring: A
High-Resolution High-Detail Dataset and Benchmark for Scene Flow, Optical Flow
and Stereo*, [DaRUS V2](https://doi.org/10.18419/DARUS-3376), CC BY 4.0.
The [official FAQ](https://www.spring-benchmark.org/faq) explains the vector
units and HDF5 formats; the
[official utility loader](https://github.com/cv-stuttgart/spring_utils/blob/main/dataloader.py)
provides the `[::2,::2]` subsampling convention used here.
Data attribution and subset modifications are retained in the local manifest.

Exact HTTP ranges extract only needed RGB, disp1, forward flow and forward
disp2 from four official ZIP64 archives. 888 members total 2,797,841,289
compressed bytes / 3,828,620,713 extracted bytes (2.606 / 3.566 GiB).
Each member passes ZIP CRC/size checks; its SHA256 is checked again before
model evaluation. Whole-archive official MD5 values are recorded but were not
verified through a full archive download. There is no dependency on private
footage or a large original movie. Local source and metadata reside under
`out/spring-source/`; no dataset or model files are added to tracked source.

Prepared RTX 5090, Torch 2.7.1+cu128 and HDF5 reader h5py 3.15.1 (isolated
`out/spring-python-deps` install). Revision
`c743214f889e84a2a43ce46273b054ac3d0c6446` plus working changes. The ordinary
trusted GPU capture preprocessing, inference and native renderer are used:
Small FP16 518x518, Base FP16 518x924, installed VDA mixed FP16 518x924 and
oVDA mixed FP16 518x924 c16. Model/engine and resolved renderer hashes are
retained in the report. Source RGB is 1920x1080; output is native Half TB,
strength .5, VFG off, with fixed experimental 60Hz source timestamps and no
dropped frames. Those timestamps are not an assertion about original movie FPS.

Each scene has frames 1–32 for warmup, 33–48 for OLS affine calibration on a
fixed 8px grid, and 49–80 for scoring. Calibration is separate per scene,
model and track, then frozen. No scored frame is fitted or normalized by the
evaluator. Model raw output and final application disparity have separate
calibrations to compare geometry at common GT scale despite different strength
responses. All units below are original 1080p pixels; UHD GT storage does not
double the vector values. This is a local monocular evaluation, not an official
Spring stereo leaderboard submission or a metric-depth zero-shot benchmark.

Methods and reproduction belong to
[BENCHMARKS](../BENCHMARKS.md#known-truth-spring-subset).

## Final application disparity

Lower is better. Each row is the mean of four scene-level errors, with equal
weight per scene, each containing 32 scored frames and 31 temporal pairs.
Temporal RMSE measures error in actual disparity change along supplied GT flow,
after subtracting true disparity change. It does not count correct distance
changes as instability. It combines flicker, bias change and response mismatch;
it is not a separate physical delay measurement.

| Model | Spatial MAE, px | Boundary MAE, px | Temporal RMSE, px |
|---|---:|---:|---:|
| DA2 Small | 3.922 | 5.808 | .761 |
| DA2 Base | 2.930 | **5.030** | .544 |
| VDA Small | 3.050 | 5.590 | .444 |
| oVDA c16 | **2.693** | 5.085 | **.425** |

Base, VDA and oVDA each improve final spatial MAE and temporal RMSE over Small
in all four scenes. Against Small, oVDA lowers the equal-scene mean spatial MAE
by 31.3% and temporal RMSE by 44.2%. These reductions belong to this selected
sample and fixed calibration contract.

oVDA has the lowest aggregate spatial/temporal errors, but does not win every
scene against Base or VDA. Base/oVDA split spatial MAE wins 2–2. VDA has lower
temporal RMSE than oVDA in three scenes; oVDA's larger gain in `0047` yields
the lower overall mean. Their exploratory scene-bootstrap difference intervals
include zero for spatial MAE and temporal RMSE. Four scenes do not establish
a universal ranking among the three alternatives. Base has the lowest mean
boundary error, close to oVDA, with wins split 2–2 between them.

## Backend output before application postprocessing

Source-sized inverse depth uses the actual model binding and interpolation.
Small readback uses the renderer's existing CUDA resize probe; source-depth
models retain their normal source-resolution depth output. The measured
backend output precedes rendering normalization, temporal filtering, flat-
background/edge correction and disparity comfort/window policies.

| Model | Spatial MAE, px | Boundary MAE, px | Temporal RMSE, px |
|---|---:|---:|---:|
| DA2 Small | 3.182 | 5.127 | .825 |
| DA2 Base | 2.440 | **4.294** | .541 |
| VDA Small | **2.220** | 4.391 | **.469** |
| oVDA c16 | 2.355 | 4.535 | .492 |

VDA has the lowest raw mean spatial/temporal error. That spatial advantage
does not fully survive the current app pipeline. For example, `0047` VDA raw
MAE is 3.533 versus final-disparity 6.344; oVDA is 3.810 versus 4.693.
The two tracks use separately frozen fits and the application intentionally
changes depth/disparity geometry. This observation identifies postprocessing
as a useful comparison target, but does not isolate a specific filter or prove
that removing a comfort policy improves viewing quality. A targeted A/B would
be needed to attribute the difference to an individual stage.

## Controls, masks and retained artifacts

All scored frames have only the initial reset at frame 1; no evaluation-time
cut or discontinuity contaminates the response. Spatial/temporal pixel masks
are identical across models and depend only on GT, not prediction confidence.
Spatial scoring includes finite nonnegative disparity, including zero sky.
Boundary regions derive from GT disparity jumps, not model-specific edges.

Temporal eligibility uses in-frame GT flow and target visibility consistency
with a .5px tolerance, eroded by one pixel. Scene-average coverage is 96.31%,
94.80%, 93.43% and 80.93%, respectively. The GT-to-GT transport control has
RMSE .0209/.0306/.0218/.0541 px, quantifying subsampling/interpolation and GT
quantization effects. This is recorded as a control, not subtracted from model
errors. A constant disparity control and errors restricted to real depth-change
regions are retained, so a temporally flat output is not sufficient evidence
of correct tracking. Natural invalid GT values are excluded consistently;
invalid model predictions abort instead of shrinking a model's scoring mask.

Artifacts:

- `out/spring-quality-20261110/report.json`: completed 16 cases, 512 scored
  frames / 496 temporal pairs across four models; policies, calibration, raw
  per-frame metrics, scene wins and exploratory bootstrap intervals.
- `out/spring-quality-20261110/summary.md`, `cases.csv`, `frames.csv`: readable
  and reusable results. `protocol.json` was written before evaluation.
- `out/spring-source/manifest.json`, `plan.json`, `dataset.json`, archive indexes:
  source identity, attribution, selection and resumable subset extraction.
- `out/spring-quality-contracts-final.json`: 99 quality tests pass, including
  five added tests for fixed calibration/drift, known true depth movement,
  visibility/invalid data, bounded range handling and verified extraction/resume.
- `out/spring-instrumentation-parity.json`: native RGB pixels and final disparity
  are exact for all 12 comparisons (three frames per model) with diagnostic raw
  readback enabled versus disabled. Pools/engine streams close normally.

The initial runtime report recorded legacy renderer ABI identifiers as hashes.
Finalization corrects that metadata to the resolved pinned portable DLL bytes,
retaining the legacy identifiers separately and the post-run verification
provenance. The final parity check loads those same verified bytes. Table
formatting was finalized without rerunning or replacing measured frames.

Normal app behavior/preferences are unchanged. These data establish numerical
differences for the selected calibrated sample. They do not evaluate hidden-
background image reconstruction, final binocular RGB truth, sustained FPS,
physical scanout, or Owl3D viewing comfort, and do not imply general superiority
on real footage or games.
