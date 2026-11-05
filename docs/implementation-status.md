# Current implementation status

Reviewed 2026-11-05. Small/Base window GPU sessions now use owned WGC/D3D11/CUDA capture
and exact GPU preprocessing. VDA/oVDA and monitor paths retain mapped capture;
the hybrid guided filter remains. Native output is now the prepared-local default;
host output is an explicit diagnostic choice. Native mixed-size restart is fixed.
Base now defaults to user-selected mixed-FP16 TensorRT plans with FP32 I/O;
Small was already FP16. Precision promotion and its checks are recorded below.
Output now defaults to unlimited; settings offers unlimited/30/60 FPS. Native
publication obeys the selected cap while release/error/retirement servicing stays
active. The verification record is linked below.
Additional Base profiling and the iw3 renderer comparison retain TensorRT and
CUDA stereo as defaults. Scoped regression coverage and
measurements below do not establish general 4K60 support.

This page owns current path status and measured-envelope summaries. Product goals
are in [the live specification](PRODUCT.md); work areas are
in [ROADMAP](ROADMAP.md). Unpassed acceptance is recorded below.

| Path | Delivered scope | Limits and evidence |
|---|---|---|
| C++ bootstrap | CMake/MSVC core, capability probe and mode contracts; CI/dev entry point exists | Not a complete native NVDEC-to-NVENC media pipeline; `CMakeLists.txt`, `.github/workflows/ci.yml`, `scripts/dev.ps1` |
| Python file conversion | Mode-owned routing now enforces Performance/DA2 Small, Balanced/DA2 Base, Video Quality/explicit oVDA or VDA, and Offline Quality/VDA with a dedicated centered five-frame processor; SBS, FFmpeg/NVENC, audio/publication and cancellation remain shared | Offline is bounded, future-aware and file-only; it is not motion-warped or a new trained model. Artifact/shape/license-specific local use; [model specifications](PRODUCT.md#files-and-models) |
| Capture-only diagnostic | Explicit WGC window/monitor capture, source transitions and isolated worker retained for diagnostic callers | Removed from user-facing mode selection; GUI defaults to SBS, with no automatic capture; [desktop behavior](PRODUCT.md#live-capture-and-output) |
| Live depth modes / host output | Immutable session routing selects Performance/DA2 Small, Balanced/DA2 Base, or Video Quality/explicit oVDA or VDA; Base/VDA/oVDA live GPU depth remains on its owner CUDA stream through GPU SBS | Explicit reference and file paths retain host depth. Offline Quality is file-only; correct artifacts, shapes and oVDA confirmation are required with no fallback |
| Live native texture output | Prepared-local default `gpu-texture` transport into Qt/D3D11 windows supports DA2 Small plus Base/VDA/oVDA device-depth live sessions with worker-owned bounded textures | Small/Base window input stays on GPU; VDA/oVDA and monitor inputs retain host capture. Native dependencies load at Start; failure is visible without automatic fallback. Broad display/game/VR acceptance remains separate; [default validation](evidence/native-default-20261105.md) |
| Temporal/model GPU experiments | Device boundaries and selected NVOF components have bounded evidence | Components are not general live model integration; fixed 1:2 NVOF cadence is rejected; [actual skip](evidence/nvof.md#record-result-ovda-nvof-actual-skip-2026-09-07) |
| Post-SBS Streamline DLSSG proposal | Feasibility review completed | Current adapter rejected at input-contract boundary; not a rejection of all external RGB FG; [feasibility](evidence/frame-generation.md#record-result-dlssg-feasibility-2026-09-07) |

## Measured envelope, not general support

DA2 Base window GPU sessions now keep captured RGB, exact preprocessing and
source-resolution FP32 depth on the owned CUDA path (2026-11-05). The capture
optimization preserved then-current FP32 plans; the subsequent authorized FP16
promotion changes model precision while preserving preprocessing arithmetic,
model-only padding/unpadding, geometry, stereo policy and file host-depth I/O. Whole-monitor
and VDA/oVDA capture still use the existing mapped path; Small's later GPU input
promotion is recorded below. Native delivery is
the prepared-local default; host and reference output remain explicit choices.
The [default validation](evidence/native-default-20261105.md) separates default
startup/lifecycle, bounded continuous playback and outstanding physical acceptance.
The earlier FP32 default-path public 4K run completed 603.59 measured seconds in one session
with median native output 23.65fps (23.59–23.80 range), about 1.45MiB worker
private-memory growth, and zero pools/nodes after shutdown. This is bounded local
playback evidence, not real-game, multi-hour, device-loss or physical VR acceptance.
The follow-up default-path Small run also passed movement across both connected
screens and preparation cancellation with no stale resources. 97 scoped unit/
measurement tests and actual Qt interaction checks pass; the Qt run has zero
warnings. Normal launch needs no output-path selection; old packages need rebuilding.

66 preprocessing/thumbnail cases, including pitched BGRA, match the CPU reference
exactly. A 24-case real-engine comparison across 1080p, ultrawide, portrait and
4K passes exact raw-depth, GPU-input/CPU-input SBS and host/native SBS checks,
including cuts and background refinement. 39 scoped unit tests pass. Thirty
repeated static-window captures cover resize/restart. Actual GUI tests cover
start/stop, fullscreen/Escape, cancellation, hidden/restored output, input resize,
source loss and worker-crash cleanup; native shutdown leaves zero pools/nodes.

Matched RTX 5090 / driver 621.14 measurements use the public FloorballGame source
process, 6s discarded warmup then five 6s windows, target 60Hz and unchanged
model/policy. Median output submissions:

| Input / per eye | Previous input + host output | GPU input + host output | Previous input + native output | GPU input + native output (now local default) |
|---|---:|---:|---:|---:|
| 1920x1080 | 18.21 fps | 26.69 fps | 21.20 fps | 32.33 fps |
| 3840x2160 | 6.78 fps | 12.56 fps | 9.27 fps | 23.87 fps |

At 4K/native, the aggregate depth stage falls from 90.80 to 31.97ms and sampled
worker total is 42.87ms. This stage includes preprocessing, inference, resizing
and validation; it is not pure-model time. Normal-background input avoids full
RGB host transfers, with exact scene/border samples read back; conditional CPU
background refinement remains counted. Host output still reads full SBS back.

Host output is a callback proxy; native counts distinct Qt afterFrameEnd IDs.
The 4K fixture is an upscaled 1080p excerpt, with 7680x2160 Full SBS processing in
a fitted window, not 1:1 scanout. The earlier input-comparison native benchmarks
used separate processes per size after a texture-wrapping failure. That restart
issue is now fixed by retiring output graphics with the scene graph. Six mixed
1080p/4K/portrait sessions and desktop hide/restore/resize/source-loss/crash checks
pass, including zero pools/nodes after stop. The TensorRT device-plan warning
remains. These are not sustained 4K30/60, physical-display or Owl3D/HMD acceptance
results.

Detailed copies, build pins, failed attempts and scoped evidence are in the
[GPU input record](evidence/base-gpu-input-20261105.md). The earlier device-depth
optimization is recorded [separately](evidence/da2-base-device-20261105.md).

The follow-up [restart/profile/iw3 record](evidence/native-restart-base-profile-iw3-20261105.md)
separates isolated Base preprocessing (~0.39ms), model GPU execution (~23ms),
upscale (~0.05–0.19ms) and native stereo cost. An opt-in CUDA graph candidate
passes 24 exact-depth/input/native parity cases and cleanup/lifecycle checks, but
matched native output changes only 32.15→32.51 fps at 1080p and 23.86→24.00 fps at
4K with overlapping ranges. It stays off by default; no practical additional
speedup is established.

RowFlow v3 symmetric, RowFlow v3 and MLBW small were run on the same final Base
depth/RGB for 180 public-video frames plus a ground-truth synthetic scene. After
calibrating opposite eye naming, learned warps smooth some diagonals but introduce
thin-structure/edge tradeoffs. That initial cost comparison was eager-only.
The [torch.compile follow-up](evidence/iw3-torch-compile-20261105.md) measures
1.39–1.52x renderer speedup at 1080p and 1.82–1.96x at 4K when compiling separately
for each fixed resolution. Default automatic shape generalization after 1080p→4K
instead regresses 4K performance. Compilation has startup cost and small nonzero
pixel differences; these are renderer-only timings, not application FPS or exact
parity. The current CUDA renderer remains. Reduced stereo-field resolution,
optimized model export and continuous binocular review were not tested; no iw3
weights or compiler dependency are part of the normal runtime or distribution.

The [app integration review](references/2026-11-05-torch-compile-app-review.md)
also tests Base directly: on the same FP32 518x924 GPU input, model-only median
times are TensorRT 25.00ms, PyTorch eager 44.13ms and compiled PyTorch 37.77ms.
Three public stills produce finite, close but non-identical raw depth; full SBS
parity and app throughput for that replacement are not established. The tested
compile candidate does not justify replacing Base TensorRT. The subsequent
[RowFlow symmetric app trial](evidence/rowflow-live-20261105.md) now connects only
that learned renderer to the existing Base TensorRT/depth path through an
explicit local launcher flag. Ordinary launch and portable packages retain CUDA.
Twelve real-engine cases across 1080p, 4K, portrait and ultrawide match compiled
host/native pixels exactly; compiled/eager results are not identical. Actual
native lifecycle tests cover resize, restart, hide/restore, source loss and worker
crash. Native output median is 29.36 fps at 1080p and 16.25 fps at 4K, below the
same-condition CUDA baseline of 32.15 and 23.86 fps. This is a quality trial,
not a speed improvement or physical binocular-display acceptance. Matched
host output changes 26.96→26.83 and 12.55→12.41 fps, with overlapping ranges.
Preparation cancellation followed by host-output restart passes without an error
dialog; owned compiler-descendant cleanup and 49 scoped unit tests pass.
The user deferred direct RowFlow quality/binocular comparison to the backlog on
2026-11-05. The local trial remains available; CUDA stereo stays the default.

The [precision/quantization review](references/2026-11-05-base-precision-review.md)
initially retained Base FP32. A bounded same-input model-only probe measured TensorRT FP32
23.37ms, PyTorch FP32 42.70ms, AMP FP16 24.28ms and AMP BF16 25.10ms. Thirty-six
public frames plus three constants are finite for each path; TensorRT passes
39/39 historical raw-depth checks, while both AMP paths pass 0/39. This is not
a visual ranking or a test of FP16/BF16 TensorRT plans. The follow-up
[actual TensorRT FP16 experiment](evidence/base-trt-fp16-20261105.md) built two
isolated 518x924 plans: mixed FP16 measured 4.20ms and selective FP16 5.35ms,
against a matched FP32 control of 25.32ms (model-only, not app FPS). Each produced
186/186 finite outputs but passed 0/186 historical raw-depth parity checks;
FP32 passed 186/186. Selective FP16 improves public-frame maximum errors but is
worse on the portrait and some constant cases.

The follow-up [native SBS/temporal comparison](evidence/base-fp16-native-20261105.md)
measures actual Qt native output at a diagnostic 60Hz target: FP32/mixed/selective
medians are 30.00/59.63/59.79fps at 1080p and 20.52/54.78/48.88fps at 4K, five 6s
windows per configuration. All six sessions stop with zero native pools/nodes.
Separately, 392 matched inputs produce 1176 full native texture outputs through
independent live postprocessing histories. At 4K, mixed/selective mean RGB errors
are 0.08045/0.05583 on the 0–255 scale, mean left-right disparity differences
0.02989/0.01910px, and within-clip temporal RGB error changes 0.10727/0.08607.
Maximum pointwise disparity differences reach 3.25/3.56px; lower averages do not
establish pointwise parity. Static tails are unchanged and four synthetic cuts
match the control at each size. These are measured proxies, not binocular quality
acceptance, sustained 4K60, 518x896-profile, real-game or broad lifecycle support.
Three trial-loader integrity tests pass. INT8/FP8 remain unbuilt/unmeasured.

After reviewing that comparison, the user selected mixed FP16 as the Base default.
The [promotion and Small review](evidence/base-fp16-default-20261105.md) records
installed 518x896/518x924 FP16 pins, correct precision telemetry and preserved
FP32 controls. Both live and file Base paths now use FP16 with FP32 I/O, without
a new precision option or automatic fallback. 35 scoped unit tests, 24 real-engine
input/host/native parity cases, ordinary native startup/resize/restart/source-loss/
crash/cancel checks, and two fully decoded file conversions pass. Long-session,
real-game and physical binocular acceptance for these engines remain unestablished;
the then-default 30Hz target and CUDA renderer were unchanged. Portable packages need
rebuilding; running source GUI instances should restart.

Small's existing model is already FP16 (334 FLOAT16 initializers and FP16 Conv/
MatMul/Softmax inputs), with FP32 I/O. Its current model GPU median is 1.359ms
for the fixed-input diagnostic. Before GPU input, Native Performance output measured 58.34fps at
1080p and 49.35fps at 4K under the same five-window/60Hz benchmark method; its
input path and mode differ from Base, so this is not a model-quality ranking.
At 4K, sampled stereo submit/wait is 12.74ms versus 2.66ms depth submission;
Small's asynchronous inference can charge GPU wait to the stereo interval, so
these are not isolated GPU kernel times.

Small window GPU sessions now use owned WGC/D3D11/CUDA capture, CUDA uint8 cubic
resize/normalization and device RGB postprocessing. The existing FP16 model,
Performance policy, source geometry and output defaults are unchanged. The
[Small GPU input record](evidence/small-gpu-input-20261105.md) covers 27 preprocessing
cases and 72 public-image cases across 1080p, ultrawide, portrait and 4K: model
input, raw depth, postprocessing and native/host SBS are bit-exact against the
existing path on this corpus. Coefficients are bounded shape-only setup; captured
pixels do not enter CPU model preprocessing. Monitor/file/reference paths retain
their existing input. Runtime and native-layout checks reject unsupported local
artifacts rather than falling back. Running source GUIs should restart; portable
packages have not been rebuilt. Matched Performance/native runs at a 60Hz target
measure 59.96→60.14fps at 1080p and 50.90→59.92fps at 4K per eye (five six-second
windows after warmup); the final pinned DLL confirms the 4K result. Native
startup/resize/restart/source-loss/crash/cancel checks, 27 scoped unit tests and
six actual Base regression cases pass. These are fitted-window/public-video
measurements, not physical 4K60, real-game or long-session acceptance.

The [common live GPU refactor](evidence/gpu-modular-refactor-20261105.md) now
shares explicit stream access, owner/image checks, pinned input-library loading
and thumbnail generation across Small/Base. A live model adapter registry owns
capture/renderer wiring and capabilities; the worker no longer repeats model-name
branches for these choices. Model preprocessing, native DLLs, precision and
resource ownership remain unchanged. 53 unit tests, 66 Base and 27 Small input
cases, 24 Base and 72 Small real-engine parity cases, and both default native
lifecycle runs pass. Current 4K/60Hz-target native medians are 59.92fps for Small
and 57.36fps for Base. No regression was observed against reused baseline runs;
the Base difference is not a demonstrated refactor speedup. Runtime coverage
for VDA/oVDA was not repeated; their adapter matrix is unit-tested.

The [uncapped diagnostic](evidence/uncapped-native-20261105.md) removes the
benchmark deadline and source timer limit and requests Qt vsync off, without
changing ordinary app settings. Five six-second live-capture windows on RTX 5090
measure median Small/Base native output at 140.96/92.42fps for 1080p per eye and
76.24/54.13fps for 4K per eye. Small reaches the public test window's supply rate;
these are observed fitted-window output submissions, not the model ceiling or
physical display refresh. All processed frames use fresh inference, and native
pools/nodes return to zero after stop. Broader content and sustained acceptance
remain separate.
The supplementary GPU public-frame replay excludes WGC/decode/window painting;
its completed rerun measures Small/Base medians 230.71/127.43fps at 1080p and
127.27/77.43fps at 4K. This is processing/delivery headroom, not live-capture FPS.
An initial replay attempt stopped during the next session's warmup with an
unrecorded underlying reason; the record retains it and the improved failure
diagnostics. The successful rerun does not establish long-session reliability.

The subsequent [output control change](evidence/output-limit-controls-20261105.md)
promotes unlimited to the app default and applies 30/60 FPS publication caps to
native delivery as well as host output. Sixty-one scoped tests, actual settings
keyboard interaction with no Qt warnings, and Base/30 plus Small/unlimited native
lifecycle checks pass. Five-window 1080p medians are 29.53/57.79/135.94fps for
30/60/unlimited; the 4K unlimited check reaches 75.81fps with the earlier, coarser
benchmark pump. All capped windows remain below their selected limit, and native
pools/nodes return to zero after stop. Limits are upper bounds, not guaranteed
achieved FPS. Running source apps need restarting; portable packages are not rebuilt.

The 2026-11-05 minimal Qt/QML redesign replaces the sidebar and live settings
dashboard with a 420x260 control window: explicit source selection and start/stop,
plus a secondary menu. File conversion, quality controls and diagnostics open in
a separate utility window. There is no in-app preview consumer or output-location
picker. The sole output window supports normal movement, remembered placement,
F11/Escape and X-to-stop. Model, strength, resolution and processing defaults are
unchanged. Source selection starts empty and refresh cannot silently replace it.

48 controller/placement tests passed. Actual Qt input checks passed at measured
DPR 1.0, 1.5 and 2.0; final 1.0/2.0 runs additionally cover minimized utility
reopening and injected error-exclusion failure. The runs had no Qt warnings and
cover selection refresh/identity loss, keyboard focus, long titles, preparation/
running captions, cancellation and native error Close/Escape/Ctrl+C. Real generated
source WGC + DA2 Base tests passed host and native output, F11/Escape, minimizing,
X-to-stop, restored geometry, restart and preparation cancellation. Native lifecycle
coverage also passed input resize/pool retirement, hidden output restoration,
source loss and worker crash, with zero remaining native pools/nodes after cleanup.
The first native lifecycle run caught retained scene-graph nodes after hiding;
disabling persistent output scene graphs fixed the regression and the rerun passed.
The separate file window also completed an actual fixture conversion with no Qt
warnings (`out/minimal-file-gui-20261105`). Independent finish review scored its
material findings resolved; physical-device and user acceptance remain separate.
Evidence and precise limitations: [minimal UI record](evidence/minimal-qt-ux-20261105.md).

The subsequent 2026-11-05 visual pass applies the user-approved macOS-inspired
light utility style without changing the minimal flow or model/presentation
defaults. A bounded selected-window icon provider adds OS application icons,
with identity checking and no client-pixel capture. 51 controller/placement/icon
tests passed, including real owned-window HICON conversion. Actual Qt checks
passed at measured DPR ~1.0, 1.5 and 2.0 with zero warnings; the final 1.0/2.0 runs
include checked-checkbox keyboard focus and Space toggling. A generated-source
Base host-output run passed start, stop, preparation cancellation, F11/Escape,
minimize and placement restore. Independent finish review scored its focus-ring
finding resolved. [Visual-pass evidence](evidence/macos-light-ui-20261105.md)

External-3D capture permission remains removed. Historical external-mode and
in-app-preview results under `out/` describe earlier layouts, not current controls.
Existing TensorRT device-plan compatibility warnings remain; the short real
tests do not certify sustained playback, monitor unplug/device loss or Owl3D/HMD
acceptance.

The corrected 2026-11-05 error UI uses a separate native QDialog with its own
HWND and the main window as transient owner. It replaces the earlier QML layer
and copy button. One explicit 닫기 button, title-bar close and Escape dismiss it;
Ctrl+C copies the entire error without requiring selection, with either text or
button focus. The non-blocking modal window preserves worker cleanup and the
status text; repeated errors reuse it. The native error window is capture-excluded.
Actual Qt tests clicked the visible close button, checked separate HWND identity,
Escape/close behavior, exact Ctrl+C clipboard content from both controls, and
absence of a copy button or QML overlay, with no warnings
(`out/native-error-window-verified-20261105`). Original clipboard formats were
restored after testing. Controller tests cover worker
failure notification, cleanup ordering, normal stop and output reopen failure.
Capture/inference behavior is unchanged by this presentation update.

The 2026-11-05 SBS-start regression check reproduced a first-frame failure with
an actual generated WGC window: `ndarray is not C-contiguous`. Retained D3D
capture views can have padded rows; both fused RGB conversion and the reference
BGRA copy now preserve their NumPy strides instead of flattening the buffer.
Exact-pixel tests cover padded rows and owned conversion results. The start
action also explains missing/stale selections and another job's lease instead
of silently ignoring or disabling the request. The user's original no-text-change
state was not reproduced in the fresh GUI, so these are confirmed defects and
tested fixes, not a confirmed diagnosis of that running instance.

63 scoped controller/capture/bridge/guard tests passed, and actual Qt clicks
verified normal/external startup rejection text, missing-source and busy
messages without QML warnings (`out/start-click-ux-fixed-20261105`).
`v1/test_sbs_start.py` exercised real QML clicks, WGC capture of a generated
window in a separate process, DA2 Base inference and 1440x480 Full SBS output:
four frames in-app and three frames on a separate fullscreen monitor, with
same-monitor rejection and stop/lease cleanup passing
(`out/sbs-start-real-fixed-20261105/report.json`). This is a bounded startup
check, not sustained playback or Owl3D activation acceptance. Running GUI
processes must be restarted to load the source changes.

Balanced/DA2 Base supports model-only padding and depth unpadding in the shared
file/live binding. RTX 5090 two-frame HEVC conversions at 3440x1440, 1080x1920,
1920x1200, 1024x768 and 1920x1080 decoded at exactly twice source width and
unchanged height. Live binding plus CUDA paired projection also produced the
expected SBS dimensions on ultrawide and portrait fixture frames, without desktop
capture. These are geometry/execution checks, not new VR or sustained FPS evidence.

The [2026-09-19 MoGe-2 Small tests](evidence/moge-small.md) remain **not promoted**.
The initial probe measured 13.585 ms median for PyTorch autocast FP16/1200-token
inference, postprocessing and host-depth return versus 5.294 ms for DA2 Small
TensorRT FP32 (different runtimes/preprocessing, not architecture parity).
The follow-up processed 1,080 unique public RGB frames into 2,160 eye-4K SBS pairs
and six fully decoded six-second 60fps videos. Flow-aligned depth residuals were
2.52x/1.79x/1.44x DA2 in sports/office/parking; these are proxies, not perceptual
flicker ratios. Sampled sheets retained thin-object concerns and did not establish
consistent quality superiority. The slow host reference renderer is not a live
performance measurement. Defaults/loaders are unchanged; continuous playback,
headset, live/FG and MoGe TensorRT integration remain unverified.

The 2026-09-10 source GUI revision removes the Original mode selector, groups
source/output/mode/strength, adds one start/stop action with explicit output
selection, collapsible SBS result demand and advanced/diagnostic sections.
File model selection is local to the file page; both action footers stay visible
at minimum window size. Model/processing/codec defaults, artifact checks, capture
exclusion, mode identity and job leases are retained. An output-open failure now
stops the newly owned live job without releasing its lease before cleanup.

34 no-capture controller tests and 13 desktop-job tests passed. The actual Qt
D3D11 `v1/test_desktop_ux.py` run passed page navigation, hidden advanced options,
SBS-only start dispatch, slider initial value, collapsed preview demand and
footer-bound checks at 1180x900 and 980x700 logical sizes. Six screenshots and
the report are in `out/ux-simplification-reviewed-20260910`; no model/capture was
run. This UI check is not new live performance, native-output or VR evidence.
Packaged copies require rebuilding; automatic codec selection, persistence and
batch processing remain outside this first UX revision.

The bounded P1 candidate experiments are concluded **without a default change**.
The [Distill Small comparison](evidence/p1-distill-small.md) passed 12/12 FP32
numerical checks; the longer GPU-postprocessor comparison produced 2,160 eye-4K
SBS pairs from 1,080 unique public source frames and six six-second videos.
DA2/Distill FP32 processing wall medians were 35.94–37.18 ms with host SBS readback
and concurrent recording, not native presentation or a live FPS measurement.
Distill remains an experimental reference, not a selected replacement: consistent
quality superiority is unestablished. Both tested FP16 recipes failed all 18
scoped FP32-preservation checks. No application model allowlist or package changed.

The [P1 motion-aligned history prototype](evidence/p1-temporal-depth.md) passed
a bounded synthetic ground-truth gate (21.17% MAE reduction), exact rejection/reset
tests and a 540-frame real-depth diagnostic. CPU optical flow/filtering alone
cost 25.84–26.17 ms P50, so this implementation is not selected for live integration.
It uses a common monocular result and one previous raw depth frame, but has no
stereo-renderer integration or natural-scene ground truth. Motion playback,
games/HUD, actual matched iw3 + LSFG and fused headset quality remain unpassed;
P1 experimental closure is not product quality or VR acceptance.

The [P1 Small 392x700 experiment](evidence/p1-small-aspect.md) is **not selected
for integration**: bounded native-4K-source depth tests showed no speed win,
limited still review found a thin-object tradeoff, and numerical checks did not
all pass. The original 518x518 product path is retained.

The [P0 baseline intake and model-stage diagnostic](evidence/p0-depth-attribution.md)
records installed iw3/LSFG settings and isolated VDA/oVDA timing. Continuous 4K
depth wall medians are 49.94/60.38 ms, with CPU preprocessing accounting for about
69%/64% of traced wall time. Earlier live run counters show near-per-frame history
resets under those conditions. Product behavior is unchanged; actual matched
iw3 + LSFG recordings, stereo attribution and Quest 3 review remain pending.
The source worker now appends start/resize/gap/cut reset counters to its bounded
processing metrics (indices 30–33), preserving existing stage indices and reset
precedence. They count the selected reason after successful reset, not simultaneous
events; live reads are asynchronous. This instrumentation has CPU regression
coverage, not a new measured live reset distribution or a changed history policy.

The [guarded native baseline](evidence/live-performance.md#record-result-live-guarded-baseline) records DA2
Small on RTX 5090, 1920x1080 input / 1920x1080 per eye / 3840x1080 Full SBS,
with native distinct-output rates of 59.70–59.99 fps across three legacy policy
labels. It is DA2 Small transport/policy evidence, not model-specific Balanced or
Video Quality evidence under the product contract.
These were warmup plus five ten-second windows per policy under the documented
Premiere-closed, monitor-off condition. They do not establish physical scanout,
VR latency or long-run stability; their conditions are not used to infer 4K behavior.

A separate [monitor-on eye-4K run](evidence/live-performance.md#record-result-eye-4k60-monitor-on)
used DA2 Small with the legacy Balanced policy at 3840x2160 input/per eye and
7680x2160 Full SBS. It did not run the Balanced mode's required DA2 Base model.
After ten seconds of warmup, five ten-second windows recorded median fresh/base
SBS 59.127 fps and final distinct native IDs 59.028 fps (58.789-59.482 range).
This is bounded application submission with a scaled public source and 1400x650
logical output window, not 1:1 fullscreen scanout, native-4K detail quality, FG,
VR acceptance, another mode/content/GPU or long-session support.

Boundary attribution over all 200 retained stage samples confirms the native path
already reduces output readback to a four-byte validity flag per frame. The remaining
explicit input traffic is 25,688,172 bytes per processed frame (about 1.495 GB/s in
that session), while the largest sampled P50 stage is the guided filter at 4.122 ms.
A direct owned-BGRA input alternative was rejected before integration: its exact
518x518 RGB result still took 4.169 ms versus 1.651 ms for the current host path and
would add 8,294,400 H2D bytes per 4K frame. No runtime/default changed from this
attribution; see the linked eye-4K evidence record.

An exact-order shared-memory guided-filter candidate also remains unselected. It
passed 27/27 exact depth/SBS comparisons, but its isolated 4K guide P50 improved
only 0.147%, below the predeclared 3% gate. That candidate remains rejected and
isolated for evidence; the product now uses the separately validated hybrid
described below.

Valid diagnostic decomposition attributes about two thirds of the 4K guided-stage
P50 to `coefficients_y` (1.407 ms, 34.2%) and `moments_x` (1.311 ms, 31.9%).
Instrumentation preserved 27/27 exact comparisons, added 0.182% to the enclosing
guide event and closed its event sum within 0.0059 ms. This is component timing,
not another application throughput claim.

A subsequent isolated chunked rolling-window candidate reduces the separable box
sum work while intentionally changing floating-point addition order. Its declared
bounded quality gate passed all 99 current-versus-candidate cases: maximum aligned
depth MAE/max were `8.49e-24`/`3.89e-19`, with exact final SBS RGB and exact
consecutive-frame RGB-change values. The corpus covered minimum/odd synthetic
motion and cuts plus six contiguous frames from each of three licensed public
clips, under all three legacy policy/radius combinations. A saved OfficeWalk
DA2 Small review pair using the legacy Balanced policy and
16x difference image were visually checked and matched the exact-RGB result.

Only after that pass, five order-alternated 20-frame 3840x2160 DA2 Small repeats
using the legacy Balanced policy
measured guide-event P50 at 4.1186 ms current versus 2.7945 ms candidate, a 32.15%
reduction above the declared 3% gate. Whole host-output FPS medians were 29.88 and
29.66 and do not show an end-to-end gain because this isolated harness retains
full SBS readback. The candidate supports an integrated validation step, not a
4K60 or visual/VR claim.

A no-readback native-publication boundary A/B then measured guide P50 4.1175 ms
current versus 2.7684 ms candidate (32.77% lower) and unpaced processing medians
90.95 versus 102.43 fps (12.62% higher). The first harness attempt correctly timed
out after two slots because it omitted the consumer's keyed-mutex acknowledgement;
the final isolated runtime adds a no-copy acquire/release consumer and passed equal
transfer/synchronization counters.

Finally, sequential actual-app WGC-to-Qt runs used the same scaled public
FloorballGame source at about 62.5 fps, DA2 Small with the legacy Balanced policy,
3840x2160 input/per eye,
7680x2160 Full SBS, ten-second warmup and five ten-second windows. Final distinct
output-ID median/range was 52.45 (51.54-53.01) fps current versus 58.83
(57.79-59.45) fps candidate, 12.17% higher. Sampled guide P50 was 5.2024 versus
3.5666 ms (31.44% lower), and exact transfer formulas stayed valid. The candidate
did not reach 60 fps in any measured window. These sequential single-content runs
support broader validation but not physical scanout, native-detail/VR quality,
sustained or general support.

The raw rolling implementation remains isolated and rejected as a global
replacement. See the
[rolling guide record](evidence/live-performance.md#record-result-guide-rolling-isolated).

Broader rolling-candidate actual-app coverage now spans FloorballGame, OfficeWalk
and ParkingGarage: all three improved processed, output and sampled-guide medians,
but no candidate output median reached 60 fps. The raw rolling implementation was
rejected as a global replacement after its radius-4 legacy Performance-policy guide regressed
2.03%. A hash-pinned hybrid instead keeps the exact current radius-4 kernels and
uses rolling chunks at radii 8/12. Its 99/99 quality matrix passed, including exact
final RGB; native-boundary gates passed with 0.00%/-0.42% guide/throughput change
in Performance, +31.20%/+13.08% in Balanced and +39.46%/+22.60% in Video Quality.
A fresh Balanced Floorball actual-app pair measured +3.59% processed, +0.78%
output and 27.98% lower sampled-guide P50. These labels describe DA2 Small policy
tests, not the product mode models. Five real-GPU native failure/cleanup
cycles also passed.

The hybrid has now been promoted into the canonical production source: the legacy
Performance policy keeps exact direct radius-4 sums, while the legacy Balanced and
Video Quality policies use 64-pixel rolling chunks at radii 8/12. This promotion
changes postprocessing only; it does not implement their required model routing.
The final candidate DLL SHA-256
`f67fc53ccaa37a29474ba90bac80d3cb2bff12e8c685a24df9f7382db0c00fa7`
repeated the 99/99 quality pass and all native gates. A separately linked product
DLL, SHA-256
`ad0871cce22011926b0948a59368ae1f71d9727962160110bdea7974f5e296eb`,
matched that candidate exactly in all 99 depth, RGB and temporal comparisons and
passed five real-GPU failure/cleanup cycles. A default-path Floorball 4K DA2 Small
using the legacy Balanced policy loaded that exact product hash and produced 52.43
distinct output IDs/s; its
8% device-wide GPU preflight makes it a functional smoke, not a performance claim.
Fifteen separately captured OfficeWalk output frames were all distinct and sampled
stills showed advancing motion, plausible eye order/letterbox and no black/frozen
output. This is sampled-still review, not continuous playback or headset acceptance.
See the
[hybrid record](evidence/live-performance.md#record-result-guide-hybrid-isolated).

An opt-in page-locked full-RGB staging candidate was evaluated after guide
promotion. It owns one bounded 24,883,200-byte host allocation at 3840x2160 and
copies the existing RGB frame into it before the unchanged product DLL. Its
261/261 quality matrix and five real-GPU failure/cleanup cycles passed. In a
matched Floorball 4K DA2 Small using the legacy Balanced policy, the sum
of sampled host input
conversion/staging P50 and GPU RGB-transfer/depth-resize P50 fell 4.3686 ->
3.5228 ms (19.36%), while processed/output medians changed only +0.10%/+0.05%
and output remained 59.93 fps. A first unpaced native-boundary trial narrowly
passed its 3% throughput gate, but the final source-hash repeat measured 38.51%
lower RGB-transfer P50 and only 2.71% higher native throughput, below that
predeclared gate. The candidate is therefore rejected for product promotion;
the normal native path and product DLL remain unchanged. See the
[pinned-input record](evidence/live-performance.md#record-result-pinned-input-rejected).

The next selected input-boundary change removes the 33,177,600-byte 4K WGC
callback memcpy. Because WGC's array view retains its owned mapped-frame exporter,
the same SBS worker now holds that view in a single latest-frame slot until RGB
conversion completes, then releases the last view before native capture stop.
The original preview keeps its bounded shared BGRA copy. In matched 4K DA2 Small
using the legacy Balanced policy, callback P50 fell 1.8641 -> 0.0402 ms
(97.84%) and owned-worker
CPU fell 9.99%; capture/processed/output changed -0.02%/+0.43%/-0.06% and worker
private-memory P95 rose 32.39 MiB, passing all declared gates. A final default-path
DA2 Small using the legacy Balanced policy at 0% GPU preflight recorded 62.48
capture, 62.14 processed and
59.83 distinct output IDs/s, a 0.0373 ms callback P50, zero shared capture-pixel
allocation and zero native pools/nodes after stop. These are short application
submission and lifecycle results, not sustained 4K60, scanout, continuous visual
or headset acceptance. See the
[retained-capture record](evidence/live-performance.md#record-result-retained-capture-promoted).

The source desktop now enforces the model-defined mapping for file and live
sessions. A sequential 1280x720 actual-GPU smoke loaded DA2 Base for Balanced,
then VDA for Video Quality, and both emitted matching model/policy provenance.
The one-second windows observed 12.94/13.93 and 17.89/16.90 processed/output
submission fps. This establishes routing and execution only, not comparative or
sustained performance, visual quality, 4K, oVDA or Offline Quality acceptance.
See the
[model-routing record](evidence/live-performance.md#record-result-model-defined-live-routing).

Clean-worktree repeated live measurements now cover all three non-Small live
choices on the public FloorballGame source. At 1920x1080 per eye, median
processed/output submission rates were 7.94/7.94 fps for DA2 Base, 8.43/8.43 for
VDA and 7.77/7.78 for oVDA. At 3840x2160 per eye with 7680x2160 Full SBS, they
were 2.48/2.48, 2.64/2.64 and 2.48/2.48 fps. Capture remained above 62 fps. The
4K sampled latest-stage medians put depth at 93-117 ms and SBS at about 288-290
ms, selecting the host-depth/SBS/output boundary for the next optimization
experiment. These are five short six-second windows on one resized public source,
not sustained 60 fps or a quality comparison. See the
[model performance record](evidence/live-performance.md#record-result-model-defined-live-performance).

The source desktop now keeps explicitly selected oVDA live depth on the model's
owned CUDA stream through temporal/guided postprocessing and stereo. Public
component parity was exact on 12/12 frames and the integrated wrapper completed
12/12 owned tokens without a pending result. A clean-commit actual-GUI run raised
1920x1080-per-eye median
processed/output submission from 7.77/7.78 to 21.35/21.49 fps. At 3840x2160 per
eye and 7680x2160 Full SBS it raised both from about 2.48 to 7.27/7.28 fps.
Explicit native delivery now raises output further to 22.54 and 9.44 fps at those
geometries. The path still has host capture/model input and is `zero_copy=false`;
60 fps, sustained performance and continuous visual/VR acceptance remain open.
See the [native-live record](evidence/live-performance.md#record-result-ovda-native-live-promoted).

VDA Small live sessions now use the same owned source-resolution device-depth
contract while file and Offline sessions retain the host-depth engine. The public
component rerun was exact for 12/12 raw-depth, host-SBS and shared-texture frames;
the integrated product wrapper also matched 12/12 final SBS frames, completed
every token and recorded no depth download. A clean actual-GUI run raised
1920x1080-per-eye processed/output from 8.43/8.43 to 23.99/23.99 fps. At
3840x2160 per eye and 7680x2160 Full SBS it raised 2.64/2.64 to 8.61/8.75 fps.
Explicit native delivery now raises output further to 28.15 and 11.92 fps at
those geometries. The path still has host capture/model input, is `zero_copy=false`,
and is not 60 fps. See
the [VDA native-live record](evidence/vda.md#record-result-vda-native-live-2026-09-09).

The file-only Offline Quality path now uses VDA Small inference plus a scene-local
centered five-frame processor. A final-code public 1080p60 FloorballGame conversion
emitted and decoded all 360 frames as 3840x1080 H.264 at 5.37 processing fps. The bounded
window held at most five samples / 47,174,400 bytes and used future context on
359 frames. On its first 120 public frames, a flow-aligned normalized-depth-change
proxy was 0.765x raw VDA overall and 0.819x at detected edges. A separate public
OfficeWalk-to-ParkingGarage hard cut was detected at annotated frame 60, flushed
once, produced two scenes and preserved 120/120 frames. These are temporal-stability
proxies and a short media/lifecycle run, not ground-truth depth, ghosting, visual,
VR comfort or sustained-performance acceptance. See the
[Offline record](evidence/vda.md#record-result-offline-centered-window-2026-09-08).

The optional oVDA Video Quality path also completed a license-confirmed public
1080p60 FloorballGame file run: 360/360 frames, 3840x1080 H.264, 6.997 processing
fps, full decode. A separate actual-engine public-frame check retained two
sequential cache positions, cleared the cache at a scene cut, accepted geometry
changes only after discontinuity/source-change reset, and rejected a skipped-frame
policy. This establishes the named local path and lifecycle contract, not quality,
long-run, public-release or commercial-use suitability. See the
[oVDA record](evidence/ovda.md#record-result-ovda-public-file-lifecycle-2026-09-08).

Older 720p30 / 1080p18 / 4K3 guidance belongs to the
[earlier generated-window reference-path experiment](evidence/live-performance.md#record-result-live-mode-performance-results).
It is not a current limit for all paths, and the separate runs are not a matched
optimization A/B. Native output must not be confused with zero-copy input.

Short 4K file fixtures establish only the codec/geometry scope recorded in the
model results. 7680x2160 allocation/encode compatibility is not a final 4K-per-eye
60 fps viewing result. Record input, per-eye, combined SBS, fresh-depth, base-SBS
and generated-output rates separately in future results.

## Build and evidence navigation

Use [README build/test commands](../README.md#build-and-test-on-windows), shared
with the C++ CI entry point. Model-specific setup and diagnostic commands remain
in `docs/models/`. No claim here certifies another GPU or a clean
machine.

## Regression coverage

The [scoped regression entry points](BENCHMARKS.md#scoped-regression-entry-points)
connect CPU contracts, current profiles, synthetic quality/protocol checks,
real FFmpeg fixtures and explicit local GPU/Qt checks. CI configuration includes
CPU, Qt and media jobs. The [CI repair record](evidence/ci-contract-registration-20261105.md)
records the previous classification failure and local checks; remote run status
is tracked in GitHub Actions. Worker error privacy, path alias protection and cleanup
before final publication are implemented in the source app. Existing packages
require a rebuild to inherit these changes. The comparison harness records
predeclared thresholds and review frames while keeping visual acceptance pending.
Its optional product-baseline contract records and validates the workload,
environment, exact path descriptions, geometry, five distinct pipeline rates,
latency state and product review decisions. No matched Small + LSFG capture has
yet been supplied, so this closes comparison setup ambiguity, not the quality gate.
The 2026-09-09 native-output extension also passed 258 discovery tests, 27 live
controller tests, scoped Ruff checks and Python bytecode compilation; its actual
GPU/GUI evidence is recorded in the linked VDA/oVDA native-live records.

## Unpassed acceptance

| Claim | Evidence still needed |
|---|---|
| Product mode contract | Mode routing, mismatch rejection, a license-confirmed public oVDA file/lifecycle run, the dedicated bounded Offline/VDA processor and short repeated actual-GUI live runs for all three non-Small choices are implemented. Offline is intentionally file-only; matched visual quality, broader content and sustained performance remain open |
| Better depth than the user's baseline | Matched spatial/temporal/binocular review against Small + LSFG, including games and video |
| Eye-4K final 60 fps | Short uncapped fitted-window live runs measure about 54.1fps for Base FP16 and 76.2fps for Small FP16/GPU input at 3840x2160 per eye; Small reaches the test source's supply rate. GPU replay headroom is separate from capture. Earlier VDA/oVDA runs reached 11.92/9.44fps. These are not physical high-quality 4K60 acceptance. 1:1 fullscreen/display behavior, applicable FG, broader content and sustained acceptance remain |
| Broad native-texture suitability | Native transport is the prepared-local default after scoped default-start/lifecycle and continuous-playback validation. Real games, multi-hour use, monitor unplug/device loss and physical 3D/VR acceptance remain unestablished |
| Broad content and VR comfort | Continuous playback and the applicable display/headset evaluation; scalar parity or stills alone are insufficient |
| Long-session reliability / real device loss | Actual long-duration/device scenarios for that claim; short or injected tests do not establish it |
| Public/other-GPU support | Declared hardware/runtime envelope, clean-machine and packaging/license evidence |

These gaps qualify claims. They do not add an approval or prerequisite to
independent experiments. The recorded resize/default-processing gate passed;
earlier failed processing-default attempts are not current blocks. Fixed 1:2 NVOF
and the tested DLSSG adapter remain rejected in their tested scope, not global bans.
