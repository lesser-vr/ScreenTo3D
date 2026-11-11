# Current implementation status

File depth strength and NVIDIA VFG added (2026-11-11). Independent file controls
use strength 0.25–2.0 (default/reset 0.5) and default-off VFG 2x; queue snapshots
carry both and busy work locks them. A bounded post-synthesis interpolator doubles
output FPS while keeping duration/audio, repeats rather than blends detected
cuts, then packs into the selected layout. The same pinned Medium VFG bridge is
used without live texture delivery. 456 CPU/Qt and 31 additional controller/
preference checks pass. Actual Small/Base/VDA and five-frame VDA workers convert
24fps inputs to decoded 48fps outputs with matching duration/audio; Base telemetry
confirms real SDK calls. Bilingual 150%/200% GUI checks pass. VFG-off real CPU media
contracts also pass. See [file VFG evidence](evidence/file-vfg-20261111.md).

Empty-tooltip guards added throughout the desktop (2026-11-11). Output-path,
shared help, choice-picker and settings-icon tooltips now require meaningful
content and visible owners; disabled help/select/settings owners close them.
41 Qt contracts pass, including six rendered production-component regressions.
Actual bilingual file-screen hover checks at 150%/200% scaling cover no file,
valid destination, whitespace and removal of the last file; real path tooltips
and normal help remain available. Reports: `out/tooltip-qt-final.json` and
`out/tooltip-ui-{150,200}/`. No conversion or shutdown behavior changed.

File workspace and sequential conversion updated (2026-11-11). All file settings
are expanded, the file settings icon is hidden, and fresh file selection defaults
to DA2 Base while live still defaults to Small and explicit saved selections stay
valid. Automatic names reflect Full/Half SBS or TB. A preflighted immutable queue
retains its processing lease across workers and stops on error/cancel. Optional,
unsaved Windows shutdown stays off by default, with a cancelable 30-second
countdown only after full queue success. 439 CPU/Qt contracts and 31 additional
controller/preference checks pass. Actual Base/Half TB workers convert two owned
videos in sequence with decoded frames/audio verified; actual cancellation and
invalid-media failure stop before the second file. Bilingual 150%/200% rendered
checks cover settings and countdown/cancel; real OS shutdown was never executed.
See [evidence and reproduction](evidence/file-queue-20261111.md).

File black-bar refinement label and help clarified (2026-11-11). Actual rendered
Korean/English checks at 150%/200% scaling verify the requested label, adjacent
layered help on mouse hover and keyboard focus, dismissal, and unchanged default
off/checkbox binding. The 29 Qt contracts, translation validation and QML/qmllint
review pass. Local rendered reports are `out/letterbox-help-{150,200}/`.
Only UI text/help changed; no image-processing behavior or performance was altered.

Korean/English localization with shared language registration and stable error
IDs implemented (2026-11-10). One bundled registry drives language choices,
locale/catalog loading, catalog builds and native launcher tables. A synthetic
third-language fixture verifies extension without per-language source changes.
142 semantic error IDs map to translated descriptions and parameter-free public
worker guidance; original diagnostics remain separate. Error windows retain ID,
Ctrl+C, Close/Esc and live retranslation. 765 Korean entries validate; 431 CPU/Qt,
26 runtime and 24 additional desktop/preference checks pass, as do real CPU media
publication/cancel/failure checks. The Qt-free CI core subset passes independently
(97 tests). Rendered 125%/150%/200% checks cover both languages and error copying.
An owned generated-window Small/Half TB native session retains its PID/session
through four language changes while output advances. Native core/launcher builds
pass; the new launcher is applied locally with its prior EXE backed up. Existing
portable folders are not replaced. This is bounded local runtime evidence, not
new GPU compatibility, long-session performance or stereo comfort acceptance.
See [initial scope](evidence/localization-20261110.md),
[registry/error evidence](evidence/localization-error-ids-20261110.md) and
[maintenance procedure](LOCALIZATION.md).

Full-reference native SBS RGB evaluation completed (2026-11-10). Four
project-authored three-view scenes test both native eyes; the same four Spring
scenes additionally test left-input to original right-camera RGB. Both Full SBS
and Half TB are measured with PSNR, Gaussian RGB SSIM, LPIPS-Alex v0.1 and
GT-defined edge/disocclusion errors. Camera calibration is fixed before scoring;
nonlinear disparity compression and window masks are disabled only in this
diagnostic to match physical target views. Ordinary application defaults are
unchanged. In Spring Half TB, Base/VDA/oVDA beat Small on all three global RGB
metrics in all four scenes; Base has highest mean PSNR, oVDA highest SSIM/lowest
LPIPS. Their small-sample pairwise intervals overlap; procedural-scene rankings
differ and do not support a universal winner. All 102 quality contracts and 12
exact Full-output/depth comparisons with secondary Half TB publication pass.
Numerical tests and inspected boundary crops do not establish physical comfort.
See [references, results and scope](evidence/sbs-rgb-quality-20261110.md).

Known-truth Spring subset evaluated (2026-11-10). Current Small/Base/VDA/oVDA
GPU/native bindings complete four preselected public training scenes, 80 ordered
frames each: 32 warmup, 16 fixed affine calibration, 32 held-out scoring frames.
Both backend inverse depth and final application disparity are measured against
GT disparity; temporal errors subtract GT depth changes using supplied flow.
All three alternatives beat Small in final-disparity spatial MAE and temporal
RMSE in all four scenes. Equal-scene mean final MAE/temporal RMSE are Small
3.922/.761, Base 2.930/.544, VDA 3.050/.444 and oVDA 2.693/.425 in 1080p px.
oVDA has the lowest mean final errors, Base the lowest boundary MAE, and VDA
the lowest raw-depth MAE. oVDA is not uniformly better than VDA/Base; the small
paired scene sample does not settle their overall ranking. All 99 quality
contracts pass, as do 12 exact native/disparity comparisons with diagnostic raw
readback on/off. Defaults are unchanged. These are locally calibrated numerical
quality results, not official stereo scores, performance or physical comfort
acceptance. See [data, results and limits](evidence/spring-quality-20261110.md).

Unified native SBS quality dashboard added (2026-11-10). Small, Base, VDA and
oVDA now have a reproducible three-part diagnostic: motion-aligned temporal
disparity change, boundary preservation/error, and within-model tracking response.
The initial public baseline covers three clips x 120 input frames per model,
with 32-frame post-reset warmup excluded, plus controlled composite relocation
and independent layered renderer fixtures. All 94 quality contracts and the
native Half TB zero-disparity calibration pass. Input is 1080p; disparity alone
is expressed in logical 3840-wide eye pixels. Natural metrics have no depth truth,
and different parallax magnitudes prevent a simple cross-model quality ranking.
The relocation response is source-time settling, not physical latency. Production
defaults are unchanged; viewing comfort and sustained performance remain separate.
See [measurements and interpretation](evidence/sbs-quality-20261110.md) and
[reproduction methods](BENCHMARKS.md#matched-sbs-quality-dashboard).

Bounded VDA live history retention adopted (2026-11-10). Ordinary VDA now retains
model/renderer history across one missing capture with increasing source time
<=50 ms; consecutive captures keep their <=100 ms pause bound. Larger skips,
invalid/reversed indices or clocks, cuts and source/size changes reset. File
cadence and other models' policies remain separate. Seven repeated-drop native
comparisons against full-rate VDA pass: moving-edge depth-change residual falls
88.7–97.0% versus reset-on-skips; all 448 no-drop and 28 first-cut comparisons
are exact. The actual 4K default path records zero gap resets in 18 measured ON
seconds, passes the unchanged 4K performance-TC subset, and confirms 12 retained
single skips in the available ON traces. 203 platform/profile and five model
contracts pass. These are bounded numerical/runtime checks, not physical 3D,
multi-hour or FPS-gain acceptance. See
[policy, quality comparison and runtime limits](evidence/vda-single-skip-adoption-20261110.md).

VDA uniform-background TC added (2026-11-10). The secured TC-UBG-01 now accepts
`-Model vda-small` through the ordinary Video Quality / GPU capture / native Half
TB path. Installed mixed-FP16 v3, 518x924 passes both initial and repeated runs
against the unchanged throughput/frame-budget limits. The six-window repeat gives
1080p ON/OFF 54.67/56.57 FPS with 1.93 ms background processing, and 4K
41.70/45.38 FPS with 4.33 ms. Seven TC unit checks pass. The 4K repeat also records
39 gap-induced history resets with correction versus one without over 18 measured
seconds per condition. Follow-up instrumented reproduction identifies the default
VDA strict capture-index continuity check: all 14 traced post-warmup resets have
one skipped capture, 25–33 ms source intervals and no cut. ON processing takes
17.80 ms median versus 12.42 ms OFF; added work increases latest-frame replacement.
The existing opt-in single-skip setting retains all identical traced events and
records zero gap resets in a separate live comparison. That investigation retained
the then-strict production default; the subsequent adoption and repeated-drop
quality comparison are recorded above.
See [reset cause and scope](evidence/vda-background-history-20261110.md) and
[VDA methods, artifacts and both runs](evidence/uniform-background-gpu-20261110.md#vda-follow-up-tc).

Shared GPU uniform-background correction adopted (2026-11-10). Live CUDA
correction keeps full-resolution border-connected masks and component means on
the GPU, replacing the full RGB/depth CPU roundtrip with small coverage reads.
The bounded median/distance replacement retains correction and history-reset
semantics. Performance/DA2 Small now enables the same conditional correction;
its former skip was a CPU-cost policy, not a model requirement. At 4K it owns
about 238.3 MiB of reused workspace, released before the renderer/engine stream.
The independently secured 1.5-second TC-UBG-01 flower excerpt now passes actual
WGC/native Half TB checks for Small, Base and oVDA at both 1080p and 4K. Paired
ON/OFF ratios are .914–1.057 and background wall intervals 1.79–4.79 ms.
The secured oVDA 4K case rises from 3.16 to 42.52 submitted FPS (current OFF
control 46.54); these fixture rates are not maximum FPS or a 4K60 guarantee.
Thirty-seven mask/depth cases, 204 matched-model native comparisons including
strength 2, and 290 affected CPU contracts pass. The first Small boundary-error
candidate was corrected rather than exempted or given looser thresholds.
Physical Owl3D visual/comfort acceptance is separate; archived ZIPs were not
rebuilt. See [implementation, measurements and limits](evidence/uniform-background-gpu-20261110.md)
and [secured case origin](evidence/uniform-background-tc-20261110.md).

GPU utilization in output debug information (2026-11-10). The shared SBS title/
binocular fullscreen text now includes `GPU n%`, sampled once a second for the
actual CUDA GPU by UUID. It reports device-wide activity, not this process alone;
unavailable/stale/inactive readings show `GPU —`. Optional query failure does not
stop output. Sixty-one affected unit/controller checks pass, as do actual Small
Half TB and oVDA Half SBS GUI/fullscreen/stop/restart checks. Both eye labels match
the title and retain the existing font/packing compensation. Explicit NVML query
timing has 0.0007 ms median/0.1838 ms maximum over 50 calls; this is query overhead,
not an end-to-end FPS benchmark. See
[validation and screenshots](evidence/gpu-usage-display-20261110.md).

oVDA 518x924 mixed FP16 adopted (2026-11-09). Ordinary source live and file
loading now selects the previously validated encoder+spatial mixed-FP16 plan.
Temporal blocks/cache/depth head/floating I/O remain FP32. The canonical artifact
is installed at `out/ovda-local/518x924-fp16/model.plan`; UI/backend/CLI/engine
diagnostics identify mixed precision. All source ratios fit the single canvas;
normal loading does not silently substitute archived FP32 engines. Existing
quality/performance evidence remains applicable to these exact engine bytes.
Eight geometries/24 frames pass host/device depth parity, 15 affected unit checks
and actual normal GUI resize/movement/fullscreen/stop/restart/cancel pass.
The normal file CLI also completes and fully decodes a 360-frame/6-second
1920x1080 60 Hz Half TB public clip with matching frame count and duration. See
[adoption verification](evidence/ovda-fp16-adoption-20261109.md).

Prior oVDA resolution/mixed-FP16 evaluation (2026-11-09). With the current c16 history,
pixel EMA and range tracker, retained 518x924 mixed FP16 passes the declared
numerical budgets on nine public cases/1002 matched frames. The 392x700 FP32 and
mixed-FP16 candidates lower cost but fail edge/depth/native-image budgets and are
not selected as defaults. In short actual WGC/native Half TB tests, retained
resolution mixed FP16 improves 4K output 46.16->62.42 FPS and device-wide GPU
86.95->64.55%; optimized variants reach the ~62.5 Hz source ceiling. This is not
maximum FPS, ground-truth accuracy or comfort acceptance. Both mixed candidates
pass actual GUI resize/movement/fullscreen/stop/restart/cancel. Seven unit checks,
160 preprocessing combinations, 30 exact old/new GPU-input controls and six
padding restoration checks pass. At that evaluation stage the ordinary FP32 registry was unchanged;
an isolated-preference live comparison GUI is ready through
`scripts/run-ovda-resolution-trial.ps1`. See
[methods, pins, numerical tradeoffs and limits](evidence/ovda-resolution-fp16-20261109.md).

oVDA depth-range stabilization (2026-11-09). The source live adapter now uses a
causal raw-anchor range tracker, 2% endpoint deadband and source-time asymmetric
response, retaining pixel EMA 0.5, c16/FP32 and bounded short-skip history.
The optional bridge adds 4 KiB GPU state with no extra production readback or
per-frame allocation. Compatibility control is exact on 1890 synthetic/public
frames; product/native parity and anchor cleanup pass on 720 more. Low-motion
eye-shift RMS falls 1.9–30.6% in nine longer sampled public cases. A two-case
saturation audit finds no loss above 5% of the current P2/P98 normalized span;
small endpoint clipping can increase. These are stability proxies, not comfort
or ground-truth accuracy. Thirty-eight affected unit checks, error cleanup and
actual GUI resize/movement/fullscreen/stop/restart pass. Short native Half TB FPS
is essentially unchanged: 59.20->59.32 at 1080p and 46.32->46.23 at scaled 4K.
See [methods, native pins and limits](evidence/ovda-depth-range-20261109.md).

Prior oVDA independent pixel EMA tuning (2026-11-09; its range stage is superseded
above). The comparison selected pixel EMA 0.5 with range EMA 0.18, c16/FP32 and
bounded short-skip history.
The optional pinned bridge preserves the existing borrowed native layout; shared
production CUDA binaries are unchanged. Legacy/0.18 compatibility and range
identity pass on 468 synthetic/public native frames; product routing and error
cleanup pass on 48 more. Synthetic 90% step response improves 12->4 updates.
Weight 0.5 meets the declared subpixel variation budget in nine public cases;
0.75 and 1.0 exceed it. These are response/stability proxies, not comfort or
ground-truth accuracy acceptance. Thirty-four affected unit checks and actual
GUI resize/movement/stop/restart pass. Short native Half TB FPS is essentially
unchanged: 58.65->58.95 at 1080p and 46.12->46.40 at scaled 4K. See
[methods, bridge pins and limits](evidence/ovda-pixel-ema-20261109.md).

oVDA bounded short-skip history (2026-11-09). Source live oVDA retains model and
renderer history across one missing capture update with forward timestamps no
more than 50 ms apart; cuts, larger/longer gaps, invalid clocks and geometry
changes still reset. File cadence, model precision and postprocessing selection
are unchanged. Bounded metadata now measures actual pre-inference cache occupancy.
Thirty-two affected unit checks and actual GUI resize/movement/stop/restart pass.
No-drop depth/native output is exact on 72 comparisons. Nine sampled public-video
cases are closer to dense oVDA in raw/temporal/edge/native-SBS proxies; these are
not ground-truth accuracy or comfort measurements. In six short 4K timed windows,
gap resets fell 279->0 and full-context use rose 0->100%, with median native FPS
47.09->46.43; 1080p measured 59.98->59.53. See
[policy, comparison contract and limits](evidence/ovda-short-skip-20261109.md).

oVDA runtime allocation/validation cleanup (2026-11-09). The source live device
engine reuses input/output/schedule buffers and one retained cache bank, with
in-place temporal shifting and a single combined finite-output validation wait.
Completion/ownership fences and NaN/Inf failure behavior remain. Before/after
depth, sampled caches and native Half TB pixels match exactly on 330 public
frames. Persistent pointers, resets, nonfinite injections and host-input parity
pass; GUI resize, both-screen movement, stop/restart and cancellation pass, as do
17 affected unit checks. At 1280x720, steady inference's extra Torch allocation
peak fell from 208.26 to 3.52 MiB, with 18.68 MiB of retained inference buffers
and no second cache bank. Short final uncapped Half TB comparisons improved
median native FPS 58.20->60.05 at 1080p and 45.54->47.09 at scaled 4K; GPU use
rose slightly with throughput. Precision and user settings are unchanged. See
[scope, reference pins and limits](evidence/ovda-runtime-cleanup-20261109.md).

oVDA GPU input (2026-11-09). Source-only live window GPU sessions now use existing
WGC GPU capture and separately pinned, same-stream oVDA FP32 preprocessing. No
model precision, source geometry, CPU thread or history policy changed. Tensor,
depth/cache and actual native Half TB comparisons are exact on the checked public
fixtures; actual GUI input resizing, both-screen movement, stop/restart and
cancellation pass. Seventeen affected unit checks pass. In short reversed-order
uncapped Half TB runs, median native output rose 25.12->58.21 FPS at 1080p and
9.98->45.78 at scaled 4K; device-wide GPU use rose about 42->84% and 47->85% as
throughput increased. This is RTX 5090 source-local evidence, not other-GPU,
long-run or physical-display-quality acceptance. See
[methods, artifact pins and limits](evidence/ovda-gpu-input-20261109.md).

oVDA aspect-fit and mixed precision experiment (2026-11-09). The source c16 FP32
path now fits arbitrary ratios into its installed canvases, retaining native
transforms and source/SBS geometry. CPU native parity, padding restoration,
binding/installation contracts and actual host/device depth parity pass. Actual
ultrawide, portrait and square native GUI sessions passed fullscreen, both-screen
movement, stop/restart and preparation cancellation. Two isolated mixed-FP16
recipes were built and compared on 360 public frames. Encoder + spatial FP16
reduced 4K replay's TensorRT median from 16.28 to 6.18 ms; actual uncapped Full
SBS rose 25.08->29.97 FPS at 1080p and 9.20->10.62 at scaled 4K. Mean device-wide
GPU use fell 45.75->31.96% and 50.57->45.79%, respectively, in short reversed-order
runs. Both candidates exceed strict depth/cache parity; FP32 remains the normal
oVDA configuration. Physical comfort, long histories and other GPUs are not
established. See [methods, artifacts and precision/geometry limits](evidence/ovda-precision-aspect-20261109.md).

Model-oriented selection and precision (2026-11-09). Live/file settings now use
one depth-model picker instead of a quality-tier picker plus a conditional model
picker. Labels identify Small FP16 (default), Base mixed FP16 and VDA's installed
mixed FP16 or legacy FP32; missing VDA describes the mixed-precision download
target. Source-only oVDA remains an explicit FP32 entry, and file-only VDA
five-frame processing is named separately. Shared hover/focus help describes
model purpose and FP32 boundaries. Internal mode/model routing and saved keys
are retained; no inference or rendering policy changed. Ten preference/selection
tests, 52 controller/hotkey checks and four VFG contracts pass. Actual Qt choice,
precision help, file/live selection and fresh-process restoration passed without
QML warnings in source and portable code:
out/model-picker-fp-release-20261109/ and
out/model-picker-fp-portable-release-20261109/. Existing shell and D3D11/file
settings regressions passed at out/model-picker-fp-shell-20261109/ and
out/model-picker-fp-desktop-20261109/. Rendered help and choice lists were reviewed;
no new GPU-performance or physical-display-quality claim is made.

Defaults and compact VFG help (2026-11-09). Fresh source and portable desktops
now select Performance/DA2 Small and Half Top-and-Bottom. Each task restores its
last explicit user mode/model/layout through validated QSettings; programmatic
test/comparison changes do not save. VFG descriptions, shortcut registration
status and restrictions moved into the adjacent ? hover/focus popup. Transition
notice text is now 14 pixels; performance statistics retain their existing size.
Seven preference tests and 52 controller/hotkey regressions pass. Actual Qt
keyboard activation, hover/focus help, unsupported-mode explanations and a fresh
process readback passed in both source and portable code, with no QML warnings:
out/selection-defaults-help-20261109-r2/ and
out/selection-defaults-portable-20261109/. All four 14-pixel notice layouts,
receiver proportions, hold/fade timing and cancellation passed at
out/vfg-notice-14px-20261109/; the existing shell regression passed at
out/selection-help-shell-20261109-r2/. These checks do not remeasure GPU performance
or physical display quality.

VFG transition notices (2026-11-09). Windowed/fullscreen output now shows a
centered notice in each eye during preparation, followed by VFG ON or VFG OFF for
1.5 seconds and a 250 ms fade. Preparation is not subject to that timeout;
interruption restarts feedback, and cancellation/failure/hide clears it without
false success. The previous packed aspect is retained while worker metadata is
empty. Small/Half SBS and Base/Half Top-and-Bottom actual global-key transitions
passed on/off notices, expiry, cancellation and existing native lifecycle checks:
out/vfg-notice-live-small-half-sbs-20261109/ and
out/vfg-notice-live-base-half-tb-20261109/. Rendered tests passed all four layouts,
per-eye centering, Half receiver proportions, timing and interruption with no
QML warnings, including the updated portable code:
out/vfg-notice-render-20261109-r2/ and
out/vfg-notice-portable-render-20261109/. The 52 controller/hotkey regressions
also pass. These checks do not replace physical Owl3D visual acceptance.

Running VFG toggle (2026-11-09). The normal app now switches VFG through output
settings, the output context menu, or global Ctrl+Alt+S, including with another
process in the foreground. It keeps the selected source, output geometry and
fullscreen state while a bounded last-frame image covers the owned worker
restart. Missing-runtime preflight preserves the running session; repeated
requests cannot queue more workers. Stop cancels pending restart. Registration
conflicts are visible in settings, and fixed comparison launchers do not register
the shortcut. Defaults and existing compatibility requirements remain unchanged.
52 Qt controller/hotkey checks and four VFG contracts pass. Actual Small/Half SBS
and Base/Half Top-and-Bottom passed four on/off transitions each across windowed
and fullscreen output, generated-frame delivery, cancellation, restart placement,
and zero native pools/nodes after stop. Both display moves also passed. Artifacts:
out/vfg-switch-small-half-sbs-20261109-r4/ and
out/vfg-switch-base-half-tb-20261109-r2/. The updated portable code also passed
the same Full SBS/Small lifecycle at out/vfg-switch-portable-small-20261109-r2/,
with the checked SDK temporarily staged for QA and removed afterward; optional
VFG installation remains required. These are generated-input lifecycle
checks, not performance or physical Owl3D quality acceptance. The final Qt input,
settings, error-dialog and stop regression also passed without Qt warnings at
out/vfg-switch-shell-20261109/.

Half-format overlay playback proportions (2026-11-09). The earlier window-only
8×8-unit check did not account for the receiver expanding the compressed Half
axis. Half SBS now doubles the overlay's vertical axis; Half Top-and-Bottom
doubles its horizontal axis. The 8-pixel base font then becomes a proportional
16×16-unit glyph after the receiver's matching expansion, without the prior
overall text shrink. Base margins remain 6 pixels. Both Half formats passed
actual Small native output/fullscreen/restart tests and scene-coordinate checks
including the receiver transform. Captures are in
out/overlay-playback-final-half-sbs/ and out/overlay-playback-final-half-tb/.
Physical Owl3D visual acceptance remains unverified.

Taskbar icon correction (2026-11-09). The running source app was identified by
Windows as the Microsoft Store Python host despite the process AppID and Qt
window icon. Each main/utility/output/pattern/error native window now receives
an explicit ScreenTo3D AppID and relaunch command/name/icon via its Windows
property store, with reapplication on native surface recreation. The approved
multi-size ICO is shared by shell metadata and the launcher build.
Actual property-store reads passed for all four QML windows, including fullscreen
transitions. The two already-running app windows also received updated shell
properties without stopping SBS. Taskbar screenshots were unavailable through
the window-scoped UI inventory; visible user confirmation remains separate.

Half-height stereo synthesis (2026-11-09). Native CUDA Half Top-and-Bottom with
VFG off now reduces rows before projection, using guided-filter scratch after
full-resolution depth/history/disparity preparation. Half SBS, file/host, VFG
and RowFlow retain their existing synthesis paths. The
[quality contract and measurements](evidence/half-render-20261109.md) record
42 passing production comparisons with exact depth history, Small/Base/VDA GUI
checks and a sampled projection interval reduction from approximately 0.79 ms
to 0.38 ms. The production confirmation used approximately 40% device-wide GPU
versus 42.5% for the prior implementation, at approximately 62.4 FPS.
The source limited output cadence; no maximum-FPS improvement is established.
Reduced Half SBS failed the 1080p comparison and remains an explicit experiment.
Owl3D binocular playback and native-4K detail review remain unverified.

Stereo output formats (2026-11-09). Live and file settings support Full/Half SBS
and Full/Half Top-and-Bottom, with Full SBS retained as default. Native output
packs directly into final-sized shared textures, with the Half Top-and-Bottom
synthesis refinement described above.
The [packing validation and 4K measurements](evidence/stereo-layout-20261109.md)
record exact GPU/CPU comparisons, real output/file tests and five observation
windows per format. Half formats saved approximately 95 MiB of GPU memory.
All formats delivered approximately 62.4 FPS with approximately 62 FPS source
painting; a material GPU usage or FPS improvement was not demonstrated.
Physical stereo playback/comfort remains a device acceptance check.

ScreenTo3D rename (2026-11-09). App window titles, launcher product resources,
the CLI product label and desktop taskbar identity use ScreenTo3D.
Source and current portable `ScreenTo3D.exe` both opened the renamed QML window
and exited normally. The existing settings namespace and model/cache/log paths
remain compatible with DepthSBS installations. The GitHub repository is
`lesser-vr/ScreenTo3D`; the local origin URL was updated and remote HEAD access
verified after the repository rename.

Desktop EXE launcher (2026-11-09). The native Windows launcher is built by
`scripts/build-desktop-launcher.ps1` and included automatically by the portable
builder. Source and current portable EXEs opened the actual QML GUI from an
unrelated working directory and exited with zero after the GUI closed.
A Unicode/space-containing junction path to the portable also passed.
Isolated missing-runtime and injected Python-import failures produced Windows
error dialogs and exit code 1; the Python failure included a UTF-8 traceback.
Local QA is in `out/desktop-launcher/`. These checks cover launch and shutdown,
not a new SBS performance measurement.

The approved overlapping blue/mint screen icon is stored in
`v1/depthsbs_app/assets/depthsbs.png`. The launcher build embeds
16/20/24/32/40/48/64/128/256-pixel ICO entries derived from this artwork.
Qt uses the same artwork for app windows with Windows app ID
`DepthSBS.Desktop`. Main, utility and SBS window icon handles and the app ID
passed runtime checks; both updated EXEs opened and closed normally.

VDA Small aspect-fit (2026-11-08, RTX 5090). The portable file worker completed
24-frame moving test patterns in Video Quality and Offline Quality at 3440×1440,
1440×1080, 1080×1920 and 1920×1080. Each output contained 24 frames at twice
the source width and the source height. Both original profiles produced bit-exact
depth against the prior transform and resize on three consecutive frames each.
Native SBS continued through an owned window's ultrawide → portrait → 4:3 →
16:9 changes, with three resize resets and at least eight new output submissions
at each geometry. Wide and portrait FloorballGame excerpts also converted at
120 frames each; source and both eye images were inspected at three positions.
Physical stereo comfort and sustained playback performance remain unmeasured for these ratios.
The [short native VDA throughput and GPU measurements](evidence/vda-native-fps-gpu-20261108.md)
include 60 FPS and unlimited output, a playback baseline, and a slower-input history check.

The 2026-11-08 QML portable build includes Small and installs portable ONNX
packs for Base and VDA. On the RTX 5090, the packaged GUI fetched both over
loopback HTTPS, cancelled and retried a Base build, and built and numerically
checked two Base and four VDA engines on-device. All four file modes produced
12-frame, 2112×608 SBS files; all three depth models produced live native SBS
from an owned synthetic window. The seven release CUDA DLLs contain compute_75
PTX and SM120 machine code. Forcing PTX JIT on the projection DLL produced the
same output bytes on this GPU. Other GPU models remain untested. The official NVIDIA
VFG wheel passed a separate direct HTTPS download/install check; the same pinned
wheel's installed runtime produced generated live frames with both Small and Base.
The build and file/live tests also ran with the developer Toolkit removed from
PATH and CUDA_PATH unset. Public model hosting and a
separate clean-PC run remain unverified. [Distribution procedure](models/desktop-distribution.md)

Small, Base and VDA Small window GPU sessions use owned WGC/D3D11/CUDA capture.
For VDA, the [GPU input comparison](evidence/vda-gpu-input-20261108.md) covers
input and temporal depth parity, resize, and 1080p/4K native throughput.
The Windows desktop portable now ships the full-resolution fixed radius-12
guide. On an RTX 5090 it delivered 43.2 FPS in a short 4K native run at the
default 60 FPS limit. Aligned depth and native SBS bytes matched the previous
DLL on 120 paired frames. [Release verification](evidence/vda-radius12-review-20261108.md#portable-release-verification)
The subsequent VDA Small v2 model pack uses encoder mixed FP16. Against FP32
with the same renderer, median native throughput at the 60 FPS cap rose from
52.22 to 54.99 FPS at 1080p and from 43.08 to 45.58 FPS at 4K. The packaged
installer rebuilt both graph pairs on the RTX 5090 and the file and native
paths exercised the new engines. [Precision and output checks](evidence/vda-mixed-fp16-20261108.md)
An isolated [spatial attention trial](evidence/vda-spatial-fp16-20261108.md)
reached 58.06 FPS at 4K on the same GPU. Both original attention recipes and
the [two partial FP32 restorations](evidence/vda-spatial-fp16-20261108.md#streaming-with-blocks-restored)
exceeded the v2 depth reference tolerance. The v3 VDA pack adopts the all-fused
recipe following user comparison. Its local build check uses the pinned v3
depth and cache samples at the existing 0.001 absolute and relative tolerances.
An opt-in [single skipped-frame trial](evidence/vda-single-skip-20261108.md)
measured VDA depth continuity and 4K throughput on the installed v3 pack.
oVDA and default monitor paths retain mapped capture;
the hybrid guided filter remains. Native output is now the prepared-local default;
host output is an explicit diagnostic choice. Native mixed-size restart is fixed.
Base now defaults to user-selected mixed-FP16 TensorRT plans with FP32 I/O;
Small was already FP16. Precision promotion and its checks are recorded below.
Settings offers unlimited/30/60 FPS. Native
publication obeys the selected cap while release/error/retirement servicing stays
active. Non-VFG native workers also pace before acquiring fresh input, avoiding
precomputed results waiting behind occupied output slots. `Run-Compare-Small.cmd` prepares Small FP16 without VFG
for the same Owl3D-compatible output trial as Base A/B. All three actual Qt
paths pass startup/default/reset, native output, two-screen movement, fullscreen,
hide/restore, stop/restart/close and zero-pool/node cleanup. Nine comparison/timing
unit tests pass. A fast-Small timestamp-order failure is fixed by preserving raw
source and ready times and scheduling original output after both, with a bounded
100ms source lead. See [Small launcher validation](evidence/small-comparison-20261106.md).
Physical Small binocular quality and sustained performance remain unverified.
`Run-Compare-Small-VFG.cmd` now adds the shared Medium 2x VFG experiment to Small.
It retains Small's GPU preprocessing, FP16 inference and native output; the VFG
layer is shared with Base. Small/Base original-frame parity, actual GUI lifecycle
and Small cut/resize/cancel checks pass. The short public 1080p trial increases
output 70.73→102.92 fps while original SBS falls to 51.46 fps and median source
age rises 17.00→28.24ms. Repeated 4K results vary substantially: baseline
28.91/38.43 fps versus VFG 56.11/35.30 fps, with higher latency under VFG.
Consistent 4K benefit is not established. See [Small VFG validation](evidence/small-vfg-20261106.md).
Live Small/Base now default to source-time depth-range stabilization plus GPU
motion-aligned one-frame history plus a bounded left/right floating window and
fixed compression of large near/far disparities and selective contour/background
reconstruction (`detail`), including A/B and Small VFG. The prior same-depth
540-frame budget comparison at strength 0.5 reduces absolute disparity
P95 by 18.1–25.1% for Base and 6.9–14.0% for Small; central-third P50 is unchanged
in all six sequences. This is not a physical comfort result. Public
moving-region residuals improve 2.76–3.44% for Base and 3.76–5.79% for Small over
the prior range default; this is a temporal proxy, not physical viewing acceptance.
Details and limits are below.
The verification record is linked below.
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
| Live native texture output | Prepared-local default `gpu-texture` transport into Qt/D3D11 windows supports DA2 Small plus Base/VDA/oVDA device-depth live sessions with worker-owned bounded textures | Small/Base/VDA window input uses GPU capture; oVDA and default monitor inputs retain host capture. Native dependencies load at Start; failure is visible without automatic fallback. Broad display/game/VR acceptance remains separate; [default validation](evidence/native-default-20261105.md) |
| Temporal/model GPU experiments | Device boundaries and selected NVOF components have bounded evidence | Components are not general live model integration; fixed 1:2 NVOF cadence is rejected; [actual skip](evidence/nvof.md#record-result-ovda-nvof-actual-skip-2026-09-07) |
| Post-SBS Streamline DLSSG proposal | Feasibility review completed | Current adapter rejected at input-contract boundary; not a rejection of all external RGB FG; [feasibility](evidence/frame-generation.md#record-result-dlssg-feasibility-2026-09-07) |

## ZipDepth retired

ZipDepth was discarded at the user's request on 2026-11-07. Its desktop launchers
and dedicated checks in the shared runtime suites have been removed. It is not
an app model or a planned integration. Historical experiment code, downloaded
artifacts and [measurement evidence](evidence/zipdepth-20261106.md) remain for
traceability; shared Small/guide/pacing measurement tools remain usable.
Matched-frame temporal residuals worsened in all three tested clips, especially
OfficeWalk, and the complete-pipeline gain was limited. See the
[4K120 comparison](evidence/zipdepth-hfr-20261106.md).

## Shared GPU and delivery improvements

The normal app and all four Small/Base comparison launchers now start at 60 FPS
and strength 0.5; the strength reset also restores 0.5. VFG remains off by default
in the normal app. The measurements below predate this default change and retain
their original strength 0.25 conditions; they are not fresh performance claims
at strength 0.5.
The normal desktop and all four comparison entry points pass actual QML loading,
default/reset and 0/30/60 selection checks without capture or native model loading;
ten cadence/Qt-notification regression tests pass. Portable packages were not rebuilt.

A matched Jockey telemetry rerun shows about 83%/82% whole-GPU activity and
306W/299W for Small/ZipDepth, including player/desktop costs; these counters
do not establish peak-compute utilization or isolate a pipeline bottleneck.
A subsequent [GPU load audit](evidence/gpu-load-audit-20261106.md) isolates the
full-4K guided filter (47.6%) and stereo resolve (17.1%) in summed CUDA kernel
time. In its matched cap comparison, unlimited/60/30 output uses 80.3/46.4/31.1%
whole-GPU activity, but 60/30 caps deliver 55.9/29.1 FPS and increase software
frame age. The subsequent [shared GPU optimization](evidence/gpu-load-optimization-20261106.md)
promotes exact bitmap stereo resolve and early capped-input pacing. Five-window
paired Jockey runs improve unlimited output 83.60→94.59 FPS; at 60 cap, whole-GPU
activity falls 48.75→40.06%, power 221.21→184.16W and callback-to-Qt median age
43.11→16.31ms, with actual output 55.80→54.49 FPS. At 30 cap, age falls
77.16→17.58ms and power 142.58→128.66W, with output 29.10→28.60 FPS. These are
windowed software measurements, not physical display latency or sustained support.
Same-input depth/native pixels, Small GPU input/output, motion/RowFlow borrowed
layout, VFG compatibility, capped resize/restart and cleanup checks pass.
The later [radius-4 guide optimization](evidence/guide-compensated-20261106.md)
now uses two-component FP32 accumulation with FP64 final mean/conversion in the
prepared-local Small/ZipDepth path. Its guide kernels fall 3.60→0.85ms/frame.
All 792 synthetic/public matched frames have exact SBS RGB; Small's largest depth
difference is 5.96e-8. This includes genuine native-4K Jockey/Beauty checks.
Actual ZipDepth Jockey output improves 93.80→119.78 FPS, now source-limited near
120 FPS, with whole-GPU activity 79.62→66.45%. That change covered radius 4.
Native/Small/VFG/reuse/resize/restart checks pass.

On 2026-11-07 the two input adapters began sharing postprocessing after raw depth
reaches source resolution. In a paired RTX 5090 check with identical 4K Jockey
Base FP16 outputs, radius-8 guide GPU time (CUDA events 5–6) fell from 4.115 to
2.792 ms median over 30 order-alternated frame pairs after six warmups. This
measures the guide stage. At strength 0.5, twelve 4K frames per model had equal
old/new native SBS pixels; peak guided-depth difference was 1.78e-15 for Base
and zero for Small. Radius 8 and 12 also passed eight odd-sized synthetic frames
each. Five 60 FPS target live sessions covering Small/Base with VFG on/off passed
with zero retained native resources at cleanup. Local reports are under
`out/guide-common/{matched-output.json,guide-timing.json,runtime/result.json}`.

The user preferred radius 8 in the [4/8 quality comparison](evidence/guide-radius-ab-20261107.md)
and selected it for both live DA2 models. Performance/Small now shares Balanced/Base's
guide radius. The five-clip comparison records the guide-time cost and edge stability
for both radii.

The prepared DA2 desktop now runs the radius-8 filter on the same fixed-radius
kernel templates as radius 4. On the RTX 5090, the 4K Jockey Base guide fell
from 2.90 to 0.57 ms in a 30-pair isolated check. Native SBS output matched
byte for byte across 432 paired frames including motion, resets and odd edges.
See the [quality and native power measurements](evidence/guide-fixed8-20261107.md).

A separate [two-thirds guide experiment](evidence/guide-resolution-20261107.md)
builds the coefficients at 1440p for 4K input and applies them at full resolution.
Both DA2 modes still use the full-resolution radius-8 guide by default.

The prepared native DA2 detail path now [retains a settled SBS texture](evidence/static-sbs-20261108.md)
on exact repeat inputs. The session report counts held captures in
`reused_sbs_frames` separately from inference, rendered frames and new submissions.

The [native render notification fix](evidence/native-notification-20261106.md)
resolved the earlier missed-wakeup tail regression. The subsequent
[cadence implementation](evidence/cadence-product-20261106.md) now applies a
single non-VFG native work-rate owner, bounded publication guard, interruptible
deadline waits and frame-ready Qt delivery with bounded lease/health service.
In five-window actual Qt-loop 4K120 checks, ZipDepth 60-target output improves
54.70→60.00 FPS, callback-age P95 17.17→16.48ms, GUI polls 998→80/s and GUI-process
CPU time 13.91→9.06% of one logical CPU. Whole-GPU power is 169.24→177.83W while
processing more frames. ZipDepth 30/unlimited reaches 30.00/119.79 FPS and Small
60 reaches 59.90 FPS. These are windowed software rates, not physical refresh.
Host/VFG retain their full-period caps. Slow-source pause/resume, actual host
delivery, native resize/hide/fullscreen/source loss/restart, Base/Small VFG at
60/unlimited and notification/GPU cleanup pass; 52 scoped protocol and 13 Qt
tests pass. Timing contracts intentionally differ from strict per-frame spacing.
That scheduling change preserved stereo quality. Source-depth stage
timings now report unavailable rather than uninstrumented zeroes; CUDA events
for those stages remain future work.

## VFG experiment

The prepared normal desktop now offers an explicit VFG toggle, disabled on every
new app launch. Small/Base GPU window/native sessions use Medium 2x when selected;
off retains ordinary rendering. The worker owns the promoted renderer/producer
directly, and the GUI selects timed delivery without importing CUDA. The runtime
is the locally staged, pinned five-DLL official wheel candidate. Fixed A/B
launchers retain their separate measurement path and hide this toggle. This is a
local feature integration, not public packaging or license clearance. See
[VFG option validation](evidence/vfg-option-20261106.md).

Distribution clearance is not established. The 2026-11-06 review distinguishes
the permissive model license from the SDK runtime entitlement: Developer Program
Enterprise access does not authorize production distribution, and no applicable
customer-PC redistribution agreement has been verified. See the
[VFG license review](evidence/vfg-license-review-20261106.md) for checked terms and
the unresolved entitlement/Embedded licensing questions.
The [distribution case survey](evidence/vfg-distribution-cases-20261106.md) also
verified anonymous access to NVIDIA's public `nvidia-vfx` 0.2.0.0 wheel and that
its three core license PDFs match the NGC package. ComfyUI dependency installation
and Veyra's documented DLL bundle are distinct distribution examples; neither
settles DepthSBS's entitlement. NGC sign-in is not universally required, and the
public wheel's product classification remains unresolved rather than assumed to
inherit a Developer Program entitlement. No runtime or installer was changed.
The subsequent [bundling review](evidence/vfg-bundle-review-20261106.md) downloaded
and hash-verified that complete wheel and staged a local five-DLL candidate
(210,788,400 DLL bytes; 187,067,228-byte ZIP including notices). All five DLLs have
valid NVIDIA signatures but differ from the NGC file hashes. Four isolated probe
runs (640x180 Low/Medium/High, 7680x2160 Medium) pass; all 16 RGB results exactly
match preserved NGC outputs from the identical probe and verified fixtures.
This supports the proposed bundle's standalone feasibility, not application
coexistence, clean-machine qualification, broader GPU support or redistribution
clearance. That review did not change the app; the subsequent opt-in integration
above now uses the staged wheel runtime and its own pins.

The independent 2x Maxine VFG experiment now runs with official SDK/feature 1.3.0.0
on RTX 5090. All three modes accept 7680x2160 Full SBS. Three public Base FP16
native-SBS triplets measure approximately 1.00/2.71/11.42ms for Low/Medium/High
per generated frame, excluding transfers, depth rendering and presentation.
Medium beats frame hold/blend on the three held-out midframes; High's additional
error reduction is small in this bounded sample. Medium is an isolated prototype,
not a product default or perceptually accepted mode.

Manual cuts copy current exactly and resetting the flag restores the previous
non-cut result. Automatic Medium cuts instead hold previous in the tested
synthetic and cross-video cases. The native prototype disables SDK automatic cuts,
resets from the app cut/source timeline, and emits only the original at reset.
A one-triplet per-eye comparison reduces seam error but leaves overall error
nearly unchanged, with higher summed isolated cost.

The isolated Base FP16 native prototype now completes actual WGC/Qt measurement
under model contention: at 3840x2160 input / 7680x2160 Full SBS, five 4-second
windows give median native output 50.47 fps baseline versus 71.92 fps with Medium
(+42.50%). Fresh Base SBS falls from 50.23 to 35.94 fps; original capture-to-Qt
completion median rises from 23.51 to 41.58 ms. Worker private memory is about
2.96 versus 6.81 GiB (not VRAM). This is a short public-preview test with a fitted
output window, not physical scanout or general game performance.

Six original/native GPU parity cases, 31 scoped CPU tests, native hide/restore,
resize, stop/restart, preparation cancellation and injected cut-boundary handling
pass. Resource create/close counts balance and stopped native pools/nodes are zero.
Continuous motion/binocular review, natural-cut detector quality, long sessions
and physical display latency remain unmeasured. Normal GUI/default behavior is
unchanged at that experiment checkpoint; the normal desktop now also has the
explicit opt-in described above. A user-selected
window comparison is now prepared through `Run-Compare-A.cmd` and
`Run-Compare-B-VFG.cmd`. Both actual Qt paths pass start, measured original/generated
counts, restart and close cleanup using an owned public source; unsupported model
selection is rejected before capture. The expanded scoped suite has 33 passing
tests. The Owl3D follow-up permits external capture of the comparison output only
and adds cross-process output-source rejection. Both A/B pass movement across
the two connected screens, hide/restore and lifecycle with verified output affinity
0 and protected control/error windows; 34 scoped tests pass. A follow-up found
that the nested QML output was a native owned window rooted at the small control
window. Comparison output now clears its transient parent while retaining QObject
ownership and normal stop/close cleanup. Actual Owl3D 2.4.2 / screen 0.0.31 logs
recognize the revised fullscreen output, switch to whole-source localization,
confirm FullSBS and enable weaving; this is stronger integration evidence than
our own frame counters. On 2026-11-06 the user confirmed that stereo now works,
but reported uncomfortable near/far gaze changes compared with Owl3D Live SBS.
Reducing strength to 0.50x helped somewhat, but the user still found it
uncomfortable while Owl3D Live SBS appeared deeper and comfortable. Investigation
then reproduced a physical eye-order error: near inverse depth moved left in
the left eye, giving the opposite of standard LR stereo. CPU, CUDA host/native
and VFG projection now use the corrected sign; optional RowFlow no longer swaps
upstream eyes to match the erroneous baseline. A generated three-plane test
fails on the former implementation and passes after correction. Six actual GPU
geometry cases through 4K, real Base/native/VFG checks at 1080p and 4K, a pinned
RowFlow eager geometry check, and 143 scoped CPU tests pass. Old binary outputs
are retained separately; a full app restart loads the new pinned binaries.
That geometry correction left strength and convergence defaults unchanged; the
earlier user-requested strength default was 0.5; the current default is recorded above. The user subsequently
reported substantial improvement, but residual wobble/focus discomfort and lower
quality than Owl3D Live SBS; full comfort acceptance remains open. See
[stereo geometry correction](evidence/stereo-eye-order-20261106.md).
The [Owl3D Live SBS investigation](evidence/owl3d-live3d-analysis-20261106.md)
confirmed shipped content-weighted convergence, disparity budgeting/edge fade and
weighted subpixel reconstruction, with stored runtime logs corroborating the
view-synthesis family. Exact runtime flags and Owl3D temporal state remain unknown.
It also found that normal capture index skips reset DepthSBS depth history; an
earlier 1,040-original-frame VFG session had 784 gap resets. DA2 Small/Base now keep
history across timestamp-valid capture replacement and use bounded subpixel
reconstruction by default in live CUDA sessions. Actual discontinuities still
reset depth and VFG history. Three public 3-second clips show temporal depth-error
proxy changes of +2.2%, -14.6% and -25.1%; these are not ground-truth depth scores.
The independent fractional-shift oracle improves maximum marker error from 1 px
to 0.00197 px. Small's rebuilt input DLL passes 27 preprocessing fixtures and 72
public/adapted host/native cases; Base/native/VFG original parity passes six cases
through 4K, with generated-frame runtime checks at both sizes. 236 scoped CPU
contracts pass. The content-plane experiment is retained explicitly but not
promoted: its central disparity reduction increases whole-frame P95 disparity by
up to 33.4% in these clips. Defaults for strength/convergence remain unchanged.
See [stereo stability validation](evidence/stereo-stability-20261106.md) for
timing, live lifecycle evidence and remaining physical-viewing limits.
The user subsequently reports that strength 0.5 feels similar to Owl3D Live SBS;
this is the next comparison baseline, not a change to the global default or full
quality acceptance. A follow-up review reproduces a remaining 1 px silhouette
transition across a 0.1 px projected motion at both strengths 1.0 and 0.5, with
identical reference/subpixel output on the isolated layered-color fixture.
Current CUDA motion rejection bypasses temporal blending on 13.4–69.3% of pixels
in three public clips. A separate 480x270 CPU one-frame motion-history candidate
reduces an aligned full-image proxy by 4.0–5.6%, leaves edge error nearly unchanged,
and adds about 7 ms before full-resolution rendering. It is not integrated.
The subsequent coverage update remains part of the live DA2 CUDA default for Small/Base,
native/host and the VFG comparison. Partial foreground coverage combines with a
locally visible farther sample, retaining existing unresolved-hole filling. An
independent analytic oracle passes 16 strength/thickness configurations, including
one-pixel objects and near-integer shifts in both eyes. At strength 0.5 the isolated
coverage transition is at most 2/255 per tested small step rather than an opaque
on/off jump. Three public 90-frame comparisons preserve the old subpixel mode
exactly; the new mode changes more than one RGB level on 0.31–0.66% of pixels on
average. 236 CPU contracts, 72 Small host/native cases, six Base/native/VFG original
cases and both actual A/B lifecycle runs pass. The isolated 4K projection cost is
1.654 ms old binary versus 1.667 ms new coverage. Current full-path measurements
are about 24.26→24.22 fps for subpixel/coverage; B produces about 19.15 fresh plus
19.15 generated fps. These short runs are slower than earlier measurements even
in the control; the cause is not isolated, so they do not establish a new general
performance envelope. See [coverage validation](evidence/stereo-coverage-20261106.md).
The follow-up depth-range update is included in the default on these
same Small/Base CUDA paths, including A/B and Small comparison launchers. It
transports prior percentile bounds into current model units only when a bounded
stationary-anchor fit is reliable, then applies a separate source-time response.
Cut/discontinuity resets are exact, and motion/weak anchors fall back to the time
response. A simple slower-range candidate increased one public temporal error by
7.9% and was not promoted. The final candidate reduces motion-aligned mean depth
disparity residual by 0.34–18.8% for Base and 5.34–22.1% for Small across three
90-frame public clips at strength 0.5; edge residuals also decline in all six
model/clip combinations. Whole-image P95 absolute disparity changes by less than
1.5% on these samples; this is not a blanket depth-quality/comfort claim.
The final parallel kernel adds about 0.054/0.067ms to isolated 1080p/4K GPU source
postprocessing. The disabled path stays exact over all 540 paired public frames;
238 scoped CPU tests, 27 Small resize fixtures, 72 Small host/native cases, six
Base/native/VFG cases and actual Small/A/B lifecycle checks pass. See
[range stabilization validation](evidence/depth-range-20261106.md).
The subsequent motion stage adds bidirectional GPU optical-flow alignment of
one previous pre-motion depth observation, without inference skipping or future
frames. Reversible-flow/color/depth/edge gates and a source-age-weighted capped
contribution protect unreliable areas; rejected pixels, cuts and time resets stay
exact to current range-only depth. Across the same three 90-frame public clips,
mean residual falls 1.37–3.45% for Base and 1.53–5.76% for Small; moving-region
residual falls 2.76–3.44% / 3.76–5.79%, with edge residual also lower in all six
combinations. This is an intentional quality change, not baseline pixel parity.
Isolated added stream time is about 1.07ms at 1080p and 1.56ms at 4K, with measured
P95 1.85/2.57ms. Two depth buffers and one RGB history add about 87MiB at 4K plus
small flow buffers. CPU contracts (243), 27 Small resize fixtures, 72 Small
host/GPU/native comparisons and six original/native VFG cases per model pass.
Actual Base and Small VFG GUI checks pass source selection, output capture policy,
two-screen movement/fullscreen, stop/restart and zero-pool/node cleanup.
The short Small VFG 4K run also passes resize/hide/restart/preparation-cancel;
77.51–78.03 native fps there is an unpaired observation, not a demonstrated
speedup or sustained physical 4K cadence.
See [motion-history validation](evidence/motion-history-20261106.md).
The retained `window` stage adds narrow masks for left/right screen-edge
violations without altering depth or projection geometry. Masks are capped at
1.5% of one eye's width; public strength-0.5 samples use at most 13.73px for Base
and 9.50px for Small at 1920px. All pixels outside the masks remain exact in
180 paired public frames; 105 analytic cases also verify side/direction, width,
no-change cases, disabled-path parity and source-time release/reset. Scoped CPU
contracts (243), Small resize (27)/host-native (72), Base/Small VFG original/native
checks and actual Base/Small VFG GUI lifecycle pass. VFG initially revealed up to
20/255 RGB inside a protected border; post-interpolation remasking fixes the
tested 1080p/4K generated borders to exact black. A bounded native-projection
benchmark shows no resolved cost increase at its noise level (1080p medians
0.4310→0.4332ms, 4K 1.8467→1.8461ms); this is not a full-app FPS claim.
See [window validation](evidence/stereo-window-20261106.md). Actual Owl3D viewing,
edge-HUD visibility and sustained generated-frame quality remain open. Top/bottom
window violations are outside this correction. The subsequent `budget` default
adds an exact linear core and a smooth compression-only near/far disparity curve
before projection. It leaves depth/history and convergence unchanged, uses no
scene statistic or new temporal state, and calculates edge masks from the actual
compressed shift. At strength 0.5, the same three public 90-frame clips for each
model (540 frames) retain central-third P50 exactly; Base central P95 changes by
0.04–4.50%, while Small central P95 stays exact. Same-pixel temporal differences
never increase in the tested pairs, excluding resets; this is a pointwise curve
contract, not motion-aligned perceptual quality. A bounded alternating benchmark
measures native projection/publication medians of 0.4412→0.4343ms at 1080p and
1.8321→1.8349ms at 4K. It excludes capture, inference and VFG; no full-app FPS
improvement is claimed. See [disparity validation](evidence/disparity-budget-20261106.md).
The final budget binaries pass 21 synthetic shape/strength conditions, actual
RGB eye-direction checks, Small preprocessing/host-native parity, Base/Small
VFG original/native parity and generated-edge protection. Existing window and
motion regressions, 243 CPU and 12 VFG contracts also pass. Actual Base A and
Small VFG GUI sessions confirm the budget default, start/stop/restart, two-screen
fullscreen, capture policy and zero-pool/node cleanup. Physical comfort and
sustained binocular quality remain unverified.
The subsequent `detail` default adds selective subpixel contour correction and
bounded farther-surface reconstruction, with user-requested strength/reset 0.25.
Contour shifts stay inside the original splat cells and retain original depth
for visibility/surface classification, so they cannot change owners or holes.
The first candidate's large RGB transitions were rejected; final public contour
max RGB differences are 9–25 across the six sequences. Background sampling can
change individual pixels more substantially and remains a limited local correction.
At the same strength 0.25, 540 public frames preserve input depth/history exactly
and change 0.00135–0.00697% of output pixels on average per clip. Controlled
layered fixtures reduce background-region RGB MAE by 7.3–15.9% at 0.25 while
preserving sharp thin objects. This is not natural-video or physical comfort
acceptance. Final native projection/publication medians increase by about
0.054ms at 1080p and 0.217ms at 4K on a synthetic many-occlusion fixture;
capture/inference/VFG and sustained FPS are excluded. See
[detail validation](evidence/stereo-detail-20261106.md).
Final detail validation also passes Small preprocessing (27) and host/native
parity (72), Base/Small original/native VFG checks and generated-edge protection,
existing motion regression and RowFlow borrowed-layout-only checks. Actual Base A
and Small VFG GUI sessions confirm strength/reset 0.25, the detail default,
two-screen/fullscreen behavior, capture guards, start/stop/restart/close and
zero pool/node cleanup. Static crop inspection is separate from unperformed
normal-speed binocular/Owl3D viewing acceptance.
See [native window integration](evidence/vfg-owl3d-root-window-20261106.md). These establish
launcher operation, not real-game or user visual acceptance; see
[launcher validation](evidence/vfg-comparison-launcher-20261106.md) and
[Owl3D compatibility validation](evidence/vfg-owl3d-output-20261106.md). See the
[standalone evidence](evidence/vfg-experiment-20261105.md),
[native evidence](evidence/vfg-native-20261106.md) and
[isolated experiment](../experiments/vfg/README.md).

## Measured envelope, not general support

DA2 Base window GPU sessions now keep captured RGB, exact preprocessing and
source-resolution FP32 depth on the owned CUDA path (2026-11-05). The capture
optimization preserved then-current FP32 plans; the subsequent authorized FP16
promotion changes model precision while preserving preprocessing arithmetic,
model-only padding/unpadding, geometry, stereo policy and file host-depth I/O. Whole-monitor
and VDA/oVDA capture used the mapped path in that comparison. Native delivery is
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
matching eye order to the then-reversed CUDA baseline, learned warps smooth some diagonals but introduce
thin-structure/edge tradeoffs. That initial cost comparison was eager-only.
That eye-order matching was not physical stereo calibration; current rendering
and comparison scripts use standard LR order following the correction above.
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

The earlier [output control change](evidence/output-limit-controls-20261105.md)
made unlimited the app default at that time and applied 30/60 FPS publication caps to
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
This CPU prototype is distinct from the subsequent integrated fresh-frame GPU
correction described in [motion-history validation](evidence/motion-history-20261106.md).

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
