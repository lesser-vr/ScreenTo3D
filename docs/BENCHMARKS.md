# Measuring DepthSBS

Use a bounded experiment sufficient for the question. Development probes may be
short; stronger performance/support claims need repeatable representative evidence.
No whole matrix, restart, full survey or benchmark is required for every change.

## Comparable runs

Record revision/dirty state, relevant compiler/runtime/GPU/driver configuration,
model/engine hashes and shapes, resolved policy, source checksum/metadata, output
geometry, warmup, measurement interval and instrumentation. Control competing GPU
workloads and display/power conditions. Do not terminate unrelated applications
or compare changed background conditions as an optimization A/B.

Warm up engine/pools and report startup separately. For repeatable performance
claims use at least five measured repetitions, median and range, after discarded
warmup; choose longer runs when sustained behavior is the claim. Retain raw JSON/CSV
and failures. A short exploratory result is useful when labeled with its scope.

Separate capture, selected model input, fresh depth, base SBS and FG output rates.
Record input/per-eye/combined dimensions and distinct IDs. Compare end-to-end time
with end-to-end time, not inference alone. Model/profile differences in a quality
comparison are deliberate variables to disclose, not something to hide.

P50/P95/P99 latency, queue occupancy, copy/sync counts, process memory and GPU-wide
load answer different questions. Qt callbacks/clock readback are not physical
scanout or motion-to-photon; sampled memory is not leak proof. Report denominators
and instrumentation overhead. Detailed hashes/readbacks belong outside timed
windows when they materially change work.

## Correctness and quality

Use generated fixtures for geometry, polarity/eye order, timestamps/cuts and
deterministic regressions; public/licensed natural content for visual behavior.
Choose motion, text, thin structures, occlusion, low texture/darkness and cuts
relevant to the change. Test codec/resolution cases affected by it. User footage
is not the implicit default; current public live fixtures are UVG-VCM.

Behavior-preserving changes use the appropriate parity oracle. Intentional model,
precision or quality changes compare against the previous baseline with declared
tolerances and temporal/binocular criteria. Spatial detail and stable but wrong
depth must not be confused. Full decoding is media verification, not playback
review; stills and flow proxies do not establish VR comfort.

Support claims require valid output/A-V policy, the stated throughput/latency,
quality and resource bounds on the named hardware/runtime envelope. Release,
long-session and real device-loss claims require those specific checks. Missing
evidence limits the claim; it does not block unrelated experimentation.

## Existing tools

| Question | Existing entry points |
|---|---|
| Portable/reference media and motion | `scripts/media-smoke.ps1`, `scripts/test-v1.ps1`, `scripts/test-v1-motion.ps1` |
| Lifecycle and long-run observation | `scripts/test-v1-motion-stability.ps1`, `scripts/soak-v1.ps1` |
| Matched file renderers | `v1/compare_packaged_renderers.py`, `v1/validate_packaged_comparison.py` |
| Model comparisons | `v1/evaluate_live_action.py`, `v1/evaluate_live_supplement.py`, `v1/evaluate_ovda_expansion.py` |
| Matched native SBS quality dashboard | `scripts/run-sbs-quality.ps1`, `v1/evaluate_sbs_quality.py`; methods below |
| Held-out known-truth Spring disparity/temporal quality | `scripts/run-spring-quality.ps1`, `v1/evaluate_spring_quality.py`; methods below |
| Final RGB / independent target camera views | `scripts/run-sbs-rgb-quality.ps1`, `v1/evaluate_spring_rgb.py`; methods below |
| Offline/VDA temporal proxy | `v1/evaluate_offline_depth.py` on the pinned public corpus |
| oVDA actual reset/cache lifecycle | `v1/validate_ovda_lifecycle.py --noncommercial` |
| Live/native/capture attribution | `v1/benchmark_live_modes.py`, `v1/probe_capture_only.py`, `v1/summarize_guarded_baseline.py`, `v1/analyze_live_gpu_boundary.py` |
| Host live-input alternatives | `v1/benchmark_live_input_layout.py` |
| Exact isolated guided-filter CUDA candidates | `v1/benchmark_live_guide_candidate.py` |
| Non-exact rolling guide quality/performance | `v1/evaluate_live_guide_rolling.py`, `v1/benchmark_live_guide_rolling.py`, `v1/benchmark_live_guide_rolling_native.py` |
| Current guided-filter subkernel attribution | `v1/profile_live_guide_kernels.py` |
| Uniform-background FPS-collapse regression | `scripts/run-uniform-background-tc.ps1`; clip/contract in `tests/media/uniform-background.json` |
| GPU flat-background masks / bounded depth error | `v1/check_flat_background_gpu.py` |
| Matched-model flat-background native output | `v1/check_flat_background_native.py`; Small/Base/oVDA, default and explicit strength |
| Installed Small + LSFG baseline settings | `scripts/snapshot-lossless-scaling.ps1` |

Check each tool's current arguments before use; reproduction commands and their
measured limitations are in [evidence](evidence/README.md). No command here is an
instruction to start a GPU job. Preserve the user's
[guarded-run condition](evidence/live-performance.md#guarded-run-condition)
when reproducing that specific recurrence test.

### Matched SBS quality dashboard

With the prepared public fixtures and existing trusted model/runtime installations,
run `scripts/run-sbs-quality.ps1 -Model da2-small,da2-base,vda-small` for the
three packaged models. Add `ovda-small-c16` and `-NonCommercial` only under its
existing license conditions. Omitting `-Model` selects all four, requiring that
confirmation. `-Frames` selects 32–360 frames per public clip (default 120);
32 contains warmup only and produces unavailable natural metrics. A new output
directory receives raw `report.json`, `natural.csv`, `response.csv` and a readable
`summary.md`. Missing models or mismatched fixture hashes fail explicitly.
This diagnostic does not download models or change application preferences.

The three metric families have different references:

- **Temporal disparity change:** independent RGB-only forward/backward Farneback
  correspondence at 480x270, consistency <=1 analysis pixel and gray residual
  <=12/255, eroded by one pixel. Report pixel-weighted RMS, maximum per-pair P95,
  all/edge coverage and signed disparity span. Disparity values retain logical
  restored-eye 3840-wide pixel units; they are not re-normalized each frame.
  Real depth changes and flow errors can contribute alongside instability.
- **Boundaries:** known layered RGB/depth fixtures compare the native fill
  component with an independently constructed target view. Natural footage instead
  measures visible-source edge RGB preservation by forward visibility and inverse
  sampling of both published eyes. That proxy excludes occluded/unreliable samples
  and cannot evaluate the correctness of hidden background or scene depth.
- **Tracking response:** a constant-size composite card relocates after 96 updates,
  followed by 96 updates of the new view. Track median signed disparity in a fixed
  region at the new location. Each model's final eight samples define its own
  target plateau; this is not known physical depth. Record first 90% crossing,
  eventual settling within +/-10% for all remaining samples (at least five),
  amplitude, overshoot and trace. Insufficient change, a step-time reset or an
  unstable tail yields unavailable timing rather than a perfect result.

Input is 1920x1080 at fixed 60 Hz source timestamps, Half TB, strength .5 and
VFG off; current model-specific precision, input canvas and postprocessing remain
disclosed variables. Skip the first 32 frames after each reset in natural summaries.
Every native slot is read and retired before reuse. RGB readbacks, flow analysis
and sequential feeding intentionally exclude live FPS/physical display latency
claims. Response times are source-time samples, not capture-to-display delay.
Smaller parallax can lower both temporal and RGB errors, so report disparity span
and coverage alongside errors; there is no combined quality score or automatic
model ranking. A frozen/flat depth map is not evidence of good quality.
See the [initial measured baseline](evidence/sbs-quality-20261110.md).

### Known-truth Spring subset

`scripts/run-spring-quality.ps1 -Prepare -NonCommercial` prepares and evaluates
the four selected scenes with the current Small/Base/VDA/oVDA bindings. `-Model`
can select packaged models without oVDA's existing noncommercial confirmation.
The existing GPU runtime/models are required. HDF5 reading additionally needs
`h5py==3.15.1` in `out/spring-python-deps`; install its binary wheel there with
the existing oracle environment's pip and `--no-deps --only-binary=:all:`.
No global environment or app preference changes are required.

Preparation uses exact HTTP ranges and ZIP64 member metadata from the official
[Spring V2 dataset](https://doi.org/10.18419/DARUS-3376), CC BY 4.0. It selects
four evenly spaced eligible sorted training scene IDs before model results are
available, and the first 80 left-eye frames per scene. Only required RGB, disp1,
forward flow and disp2 members are extracted; the full multi-GB archives are not
downloaded. ZIP CRC/size checks catch member corruption; per-member SHA256 and
the official file metadata are retained. Whole-archive MD5 is recorded, not
claimed verified by a partial download. Resume verifies existing member CRCs.
Public training-split labels are used locally. Held-out means calibration versus
scoring frames here, not proof that upstream model training excluded Spring.

Frames 1–32 warm up the actual causal model/renderer, 33–48 fit one OLS scale
and offset per scene/model/track on a fixed 8px grid, and 49–80 are held-out
scoring frames. There is no evaluation-frame refit, clamping or per-frame
normalization. Two separately calibrated tracks are reported: source-sized
backend inverse depth before rendering postprocessing, and actual native output
signed disparity after application postprocessing. This distinguishes model
fidelity from the app's range, temporal, boundary and comfort-budget policies.
Raw Small upsampling uses the actual CUDA resize probe; source-depth models
retain their ordinary source-resolution output interpolation.

GT is subsampled `[::2,::2]` like the official utility loader. Its vectors remain
1080p pixel values; do not divide them by two despite their UHD storage grid.
Positive disparity magnitude is used (closer means larger). Finite nonnegative
GT including sky is scored. Report spatial MAE, RMSE, >1px fraction and errors
around GT discontinuities (>1px neighbor jump, dilated one pixel). This local
monocular evaluation does not use the official leaderboard's four-candidate
subpixel error rule and must not be presented as an official stereo score.

For consecutive held-out frames, use supplied forward flow `F` and target
disparity `D2` on the reference grid:

`temporal error = [P(t+1, x+F) - P(t,x)] - [D2(t,x) - D1(t,x)]`.

`disp2` contains future disparity at the material point, not a disparity delta.
Use finite/in-frame points with next-frame GT disparity sampled at `x+F` within
.5px of `D2`, eroded by one pixel. That prediction-independent visibility mask
excludes occluded/unreliably sampled correspondences. Report all/edge RMSE,
coverage, changing-depth regions (absolute GT delta >=.1px), and a constant
disparity control. Lower jitter alone cannot win against true depth motion.
An oracle transport control also samples next-frame GT with the same flow/mask,
recording the residual from subsampling, interpolation and GT quantization.

Ordered source frames have fixed experimental 60Hz timestamps for all models;
this is neither an original-movie FPS assertion nor a real-time FPS test. Default
strength .5, Half TB and VFG off are used. Each scene has 32 scored frames and
31 temporal pairs; summaries give equal weight to scenes. Pairwise scene wins
and exploratory scene-bootstrap intervals disclose the very small sample rather
than treating millions of correlated pixels as independent trials. Model and
renderer hashes, settings, source manifest identity, per-frame statistics and
failure/partial results are retained. Final stereo image quality and physical
viewing comfort require their own reference/device evaluations.
See [measured four-scene results](evidence/spring-quality-20261110.md).

### Full-reference native SBS RGB

Two complementary RGB references are available:

- `scripts/run-sbs-rgb-quality.ps1 -Prepare -NonCommercial` compares both native
  eyes on four project-authored analytic 3D scenes. The independent ray tracer
  generates central input and left/right target images, including background
  invisible in the center. Fixtures are 1280x720, focal length 1152px,
  30mm baseline, 4.5m convergence. Frames 1–32 warm up on a static pose; updates
  33–48 calibrate on that pose, followed by 16 new moving poses for scoring.
- `v1/prepare_spring_rgb.py` adds only original right-camera RGB/disparity for
  frames 49–80 of the existing four Spring scenes; `v1/evaluate_spring_rgb.py
  --output <new-dir> --noncommercial` compares generated right native eyes with
  those independent camera images. Input remains left camera only. This is a
  one-eye target-view check, not a true central-input binocular reference.
  Original ordered frames 1–32/33–48/49–80 remain warmup/calibration/scoring.

Both use current trusted model/preprocessing/postprocessing and native texture
publication, reading and retiring every slot. One inference/post update produces
Full SBS followed by Half TB publication of the same depth. No framewise RGB
alignment or GT-driven pixel correction is allowed. For physical reference
matching, the diagnostic alone disables nonlinear disparity compression and
window-edge masks; an OLS scale/convergence fit on preparation frames is then
fixed throughout scoring. This deliberate camera calibration is not unchanged
application-default geometry or a comfort-policy change.

For the analytic scenes, fit postprocessed projection depth `q` to inverse
physical Z: `1/Z = a*q+b`. Set total disparity scale `f*B*a` and convergence
`(1/Z0-b)/a`. Spring uses source GT disparity `D=a*q+b`; a right eye must shift
by `-D`, so native paired scale is `2*a` and convergence `-b/a`. Projection-only
contour/fill and model-specific temporal/range policies otherwise remain active.
The output is scored directly against the fixed target camera, without an
evaluation-frame fit or a model-dependent scoring mask.

PSNR uses RGB squared error at range 0–255; SSIM uses an 11x11 Gaussian window,
sigma 1.5, population covariance and mean RGB score. LPIPS-Alex v0.1 uses
FP32, RGB tensors normalized to [-1,1], no metric image resizing, and the
official `lpips==0.1.4` calibrated network. Its official AlexNet and linear
weight hashes are checked before deserialization. Local metric dependencies
are `lpips==0.1.4` and `scipy==1.16.3` in `out/sbs-quality-python-deps`, alongside
the prepared runtime's torchvision; checkpoint cache is `out/sbs-metric-weights`.
With that local dependency path active, `v1/prepare_sbs_rgb_metrics.py` downloads
the official 244,408,911-byte AlexNet checkpoint if missing and verifies both
full SHA256 pins before any metric model is loaded. It never replaces a differing
existing checkpoint silently. The provenance receipt remains beside the cache.
See [LPIPS source and input convention](https://github.com/richzhang/PerceptualSimilarity).

Evaluate per eye, excluding a fixed 8-row/16-column outer rim. Half TB reference
eyes receive independent integer box reduction and bilinear logical-eye restore,
matching the declared delivered sampling contract. Do not compare Full and Half
numbers as a direct format ranking: each is compared against its own sampled
reference. PSNR/SSIM/LPIPS scores are means over eyes/frames, then equally
weighted scenes. Report GT-defined edge and disoccluded-region RGB MAE and
pixel counts beside global scores; hidden regions are not simply excluded.
Visibility masks derive from GT geometry/disparity, never model confidence.

Controls include native rendering with known source depth, zero-stereo central
duplication, analytic swapped-eye targets, metric identity/known RGB offsets,
camera sign/units and independent packing. The native known-depth result is a
renderer/control reference, not a mathematical perceptual upper bound: single-
view RGB lacks hidden colors and may differ in view-dependent effects. Analytic
camera controls require visible-interior RGB MAE <3 and edge MAE better than
both zero stereo and swapped eyes. Region-empty metrics are unavailable.
Retain source/weight hashes, resolved calibration, per-eye/per-frame data,
matched masks, scene wins and exploratory scene-bootstrap intervals. Four-scene
results do not establish general quality or physical stereo comfort rankings.

### Other native performance diagnostics

The uniform-background TC uses a secured 1.5-second local excerpt, independent
of the original large video or its external path. It checks input eligibility,
paired native output rate and background-stage budget; a decoder smoke alone
does not pass it. Its compact natural fixture and GPU execution are local;
public media-contract CI generates an owned synthetic counterpart. See
[fixture, commands and pass/fail contract](../tests/media/README.md).

For an uncapped native throughput diagnostic, use `benchmark_live_modes.py
--hz 0 --source-interval-ms 0 --source-process --path gpu-texture` with the
usual source, size, mode and output arguments. Zero selects the app's unlimited
default; `--hz 30` and `--hz 60` exercise its capped publication path. The legacy
`--uncapped` flag is an alias for unlimited and remains required for GPU replay.
The app polls at 1ms and requests Qt vsync off; this does not guarantee physical
scanout. The benchmark pumps events more frequently than that timer, so its own
sleep does not impose a coarser rate limit. Report source paint rate alongside
distinct native output IDs because the public source can become the bottleneck.
Adding `--gpu-replay` instead feeds a bounded cache of 60 public frames directly
from GPU memory into the ordinary Small/Base pipeline. It excludes decoding,
window painting and WGC, so label its result pipeline headroom, not live capture
FPS. Keep cache setup outside timed windows; verify fresh inference, no depth
reuse, bounded native delivery and zero pools/nodes after stop. See the
[uncapped measurement](evidence/uncapped-native-20261105.md).
The subsequent [output control verification](evidence/output-limit-controls-20261105.md)
covers app defaults, capped native publication, settings and cleanup.

`analyze_live_gpu_boundary.py --runs <runs.json> --output <new-json>` checks the
cumulative CUDA byte/synchronization formulas and summarizes all retained GPU and
host stage samples. CUDA event intervals can include host enqueue gaps, so their
percentiles rank observed work but are neither utilization nor an additive critical
path. `benchmark_live_input_layout.py --output <new-json>` is a CPU-only microbench
for full-resolution capture ownership/color alternatives. It cannot establish an
end-to-end speedup; increased transfer bytes or slower host work should reject a
candidate before integration.

`benchmark_live_guide_candidate.py --candidate-dll <dll> --output <new-directory>`
loads the pinned current DLL and an isolated candidate in the same process. It
requires exact aligned-depth bits and SBS RGB across odd/minimum dimensions and
all three live guide radii, then alternates 4K timing order. The guide CUDA-event
interval is the primary metric because the equal host-output path includes full
SBS readback. Declare `--minimum-guide-improvement-percent` before the run; exact
pixels without the required effect do not support promotion.

`profile_live_guide_kernels.py --profile-dll <diagnostic-dll> --output
<new-directory>` verifies the event-instrumented current algorithm against the
pinned DLL, bounds instrumentation overhead/event accounting, and reports the
four guide subkernels separately. Use the subkernel result only when exact parity
and both declared instrumentation gates pass. Whole-path host-output FPS is
supplementary because it includes allocations and full SBS readback.

The rolling-window candidate intentionally changes floating-point addition order,
so it uses two ordered gates instead of the exact-candidate command. First run
`evaluate_live_guide_rolling.py --candidate-dll <dll> --output <new-directory>`.
It compares the pinned and candidate DLLs over minimum/odd synthetic motion and
cuts plus contiguous licensed public frames at all three radii. Its declared
aligned-depth and final-RGB limits are gating; consecutive-frame RGB change is
reported as a non-gating proxy unless a temporal limit was declared before a
future run. Only a passing quality report may be supplied to
`benchmark_live_guide_rolling.py --quality-report <report> --candidate-dll <dll>
--output <new-directory>`. The benchmark verifies the artifact hash, then uses
five order-alternated 20-frame 4K Balanced repeats and a predeclared guide-event
improvement threshold. It does not establish integrated capture or 4K60.
`benchmark_live_guide_rolling_native.py` additionally includes native texture
publication and a test-only no-copy keyed-mutex consumer; pass its separately
built `live-texture-runtime-consume` DLL. Its predeclared minimum-improvement
arguments may be negative to express a bounded non-regression contract (for
example, `-1` means no more than 1% regression); values at or below `-100` are
rejected. It still excludes WGC, IPC and Qt.

The raw rolling implementation is not a global candidate because radius 4 failed
its measured non-regression check. The promoted production implementation retains
the exact direct radius-4 algorithm and selects 64-pixel rolling chunks only for
radii 8/12. `live-depth-guide-hybrid` and `live-depth-guide-promoted` remain
reproducible evidence builds; treat each as a distinct artifact and rerun quality
and each mode's native gate against its hash rather than inheriting another DLL's
results. The normal prepared-local product path is `live-depth-parallel`.

For a historical actual-app candidate run, `benchmark_live_modes.py --path
gpu-texture --guide-candidate rolling`, `hybrid` or `promoted` selects only that
fixed, hash-pinned artifact inside its owned worker. Arbitrary DLL paths are not
accepted. Omitting `--guide-candidate` exercises the normal prepared-local product
DLL. For an A/B, keep geometry, source, mode, warmup, windows, native/runtime
hashes, presentation target and output guard matched. Validate the pair with
`summarize_live_guide_rolling_app.py`; the observed effect is not a post-hoc 4K60
gate.

The current benchmark controller routes `--mode` through the model-defined product
mapping. Video Quality defaults to VDA for automation; use `--video-model` to name
VDA or oVDA, and oVDA additionally requires the explicit
`--ovda-noncommercial` confirmation. The report records the actual model ID.
Historical DA2 Small runs labeled Balanced or Video Quality remain legacy
policy/transport evidence only; they must not be relabeled as DA2 Base or
oVDA/VDA model performance.

`evaluate_offline_depth.py` defaults to the pinned public FloorballGame clip and
caps work at 124 frames. `--cut-clip ParkingGarage` builds an in-memory annotated
hard-cut sequence from two separately hash-verified public clips; it does not write
or silently substitute user media. The report compares raw and centered VDA using
the existing 480-pixel Farneback-aligned normalized-depth-change proxy. Lower
change can indicate steadier depth, but it is not ground truth, spatial fidelity,
ghosting or VR comfort. `validate_ovda_lifecycle.py` likewise defaults to public
frames and requires the explicit noncommercial confirmation; it is a lifecycle
check rather than a benchmark.

`benchmark_live_modes.py --path gpu-texture --input-candidate pinned` selects the
isolated page-locked full-RGB staging worker. It cannot be combined with a guide
candidate. Count its CPU staging inside `input_color`; the CUDA
`rgb_h2d_depth_resize` interval alone omits that cost, and CUDA stage intervals
are not an additive critical path. Use `test_live_gpu_quality.py --pinned-input`
for the normal numerical matrix and `test_live_gpu_failures.py --native
--pinned-input` for allocation/failure cleanup. Then run
`benchmark_live_pinned_input.py --runtime-dll <consume-runtime> --output
<new-directory>` for five order-alternated unpaced native repeats with declared
RGB-transfer, whole-throughput and guide-regression gates. The tested candidate
is rejected because its final source-hash run did not repeat the required 3%
whole-throughput gain.

For capture-ownership work, `benchmark_live_modes.py --capture-telemetry` retains
per-callback entry/exit observations. The historical `--capture-candidate
retained` switch selected a metadata-only, one-slot WGC mapped-frame owner inside
the SBS worker; that behavior is now the product default, so omitting the switch
is the current-path check. Evaluate matched five-window pairs with
`evaluate_live_retained_capture.py`: the declared gates are at least 80% lower
callback P50, at least 5% lower owned-worker CPU, no more than 1% regression in
capture/processed/output rate, and no more than 64 MiB worker-memory P95 growth.
The callback interval starts after native readback and Python/GIL entry, so it
isolates the removed host memcpy but does not measure WGC latency or scanout.
Always verify `native_after_stop.live_pools/live_nodes == 0` for sequential modes.

## Scoped regression entry points

Install `tools/requirements-contracts.txt` in a separate Python 3.12 environment.
The `qt` group also needs `tools/requirements-qt-contracts.txt` (pinned PySide6).
`python scripts/test-contracts.py --group cpu --report <json>` runs all GPU-free
groups including Qt; use `--group core`, `platform`, `profiles`, `quality` or `qt`
for affected work. CI runs these separately and installs Qt only for its own job.
Tests importing TensorRT/CUDA/Torch stay in the explicit local `runtime` group.
Missing/import-failed/empty/skipped required modules fail.
The runner owns classification; current-profile expectations can change with
intentional product changes and do not freeze future models or algorithms.

`python v1/test_media_contracts.py --media-tools <directory> --output <new-directory>`
checks real FFmpeg media, timestamps/audio, cancellation, failed encoder and owned
child cleanup with explicitly synthetic depth and CPU encoding. CI obtains a
checksum-pinned test-only FFmpeg through `scripts/prepare-contract-media.ps1`.
It does not replace or bundle the app's media tools. Add `--encoder nvenc` for the
prepared GPU path. These are short fixtures, not general codec support claims.

In the existing prepared GPU/Qt Python environment, run
`python scripts/test-hardware-contracts.py --output <new-directory> --fault-fixture <fixture-directory>`.
Prepare that test-only fixture once with
`scripts/build-cuda-projection-spike.ps1 -OutputDirectory <new-fixture-directory>`;
rebuild it when the CUDA source changes. Production exports remain free of fault
injection, while the separately built fixture tests six real allocation-failure
stages. Only the projection/all group needs this fixture.
Its optional `--group runtime|projection|transport|qt|media|jobs` scopes dependency
tests, real CUDA close/parity, NT-handle lifecycle, actual synthetic Qt pixels and
lease rejection, NVENC media, or repeated real depth/projection job cleanup.
The jobs-only group requires `--input <short-fixture>`; all uses its generated
media fixture. Model assets and the previously built engine must be prepared. Missing runtime/artifacts are failures, not passes.
Only owned test processes are used; each child has a timeout. GPU and Qt checks
are explicit local runs, not self-hosted jobs exposed to external PRs.

For a changed quality algorithm, run `v1/compare_quality_regression.py` with
`--source`, matched `--baseline`/`--candidate`, `--media-tools` and a new `--output`.
It bounds inspection to `--frames` (at most 240), records hashes/eye geometry/rate,
emits review frames and reports RGB/temporal proxies. Optional predeclared
`--max-rgb-mae` and `--max-temporal-change-increase` apply only to that comparison.
Without thresholds the result is measurement, not acceptance; visual review stays
pending in either case. Low change can mean frozen or wrong depth. Existing
natural-content evaluation and real playback/VR checks remain necessary for those
claims. Long soak and physical device loss keep their separate evidence scope.

For a product-baseline comparison, also pass `--contract` using
`docs/matched-quality-comparison.example.json` as the starting shape. The contract
records the workload identity, environment, input/per-eye/combined geometry,
capture/model/fresh-depth/base-SBS/generated-output rates, exact path descriptions,
latency evidence state and the seven review decisions named by the product. The
tool rejects inconsistent rate ordering or media geometry and hashes the contract
into the report. A valid contract can still remain pending; it never converts RGB
proxies or unreviewed motion into a depth-quality verdict.

Before recording the Small + LSFG side, run
`scripts/snapshot-lossless-scaling.ps1 -OutputDirectory <new-directory>`. It hashes
the installed executable, settings and renderer config and records only the
quality-relevant saved profile fields plus GPU/driver and active power scheme.
The snapshot is read-only and does not prove which profile was active during a
capture; pair its hash with the capture contract and confirm the visible profile.

For iw3 baseline intake, use `python v1/snapshot_iw3_baseline.py --help` to
snapshot a supplied installation into a fresh output directory. This read-only
tool uses a quality-setting allowlist and hashes relevant installed artifacts;
it does not start capture or prove the saved settings were active.

For isolated VDA/oVDA depth attribution in the prepared model environment, run
`python v1/profile_model_stages.py --output <new-directory> --models vda ovda
--noncommercial`. The oVDA flag requires the user's applicable personal-use
confirmation. Defaults use 1080p and upscaled-4K prepared FloorballGame frames,
continuous/reset-each-frame cases, 16 warmup frames and five ten-frame repeats.
The report records source hashes, exact three-frame diagnostic parity, exclusive
host regions, TRT stream intervals and instrumentation overhead. Model cleanup
precedes final publication; `partial.json` is not a completed result. This is
depth-only cost evidence, not native-4K quality, stereo/FG or complete-path FPS.

`v1/compare_small_aspect.py` compares locally built, pinned-ONNX Small engines at
518x518 and 392x700 using original checksum-pinned 4K public frames. It preserves
the square preprocessing values, alternates shape order, records ORT reference
checks and bounded timing samples, and exports paired depth stills. Its engine
files must come from the controlled local build; the CLI precision label is not
an artifact validator. See the [recorded build recipe and limits](evidence/p1-small-aspect.md).

For the isolated Distill Small model replacement, `v1/distill_small_experiment.py`
verifies the pinned source/weights and exports a fixed square oracle;
`v1/compare_distill_small.py` compares locally built FP32 engines using the same
public frames and reference stereo path. `v1/review_distill_small.py` creates
native-pixel eye crops from completed output. These are controlled diagnostics,
not application model installers. See [provenance, build flags and limitations](evidence/p1-distill-small.md).
