# DepthSBS product

Current product intent and local user behavior, 2026-09-10. Implemented limits
below describe the current build, not permanent restrictions on future designs.

## Goal

Give games and video viewing better depth and simpler operation than the user's
DA2 Small + Lossless Scaling FG baseline. Preserve 3840x2160 input and per-eye
image, producing 7680x2160 Full SBS at final 60 fps. Frame generation is allowed;
fresh model inference at 60 Hz is not required. The complete model, postprocessing,
FG and presentation path determines perceived quality and latency.

Full SBS uses standard left-eye/right-eye packing. With the backend's
larger-is-nearer depth contract, points in front of the screen plane have a
rightward offset in the left-eye image and a leftward offset in the right-eye
image. This physical sign is tested independently of CPU/GPU pixel parity.

The user's comparison setup is iw3 with 3840x2160 60 fps input, Lossless
Scaling FG x2, and OpenVR / Desktop+ viewing on Quest 3. These identify the
baseline components, not verified routing order, actual output rates or headset
transport. Measure those rather than deriving them from the configured x2 factor.

This is a target, not certified support. Exact 59.94/60.00 cadence, model/base/FG
rates and output geometry must be declared in comparisons. A combined 4K SBS
image or a 4K model input is not equivalent to 4K per eye.

## Desktop experience

The desktop supports Korean and English. **Settings and diagnostics → Language**
offers System default, 한국어 and English; the default follows the system UI
language, with English for unsupported languages. The selection is saved in the
existing user settings. Changes apply immediately to app text, stored progress,
model help, errors, output menus and notices without restarting the active SBS
session or changing its source, model, layout or VFG selection. An active VFG
notice keeps its existing hold/fade timing. File states use stable internal codes.
External window titles, filenames, original licenses and unknown diagnostic text
are preserved. Windows-owned file-dialog buttons can follow the OS language.
The first languages use left-to-right UI; packed eye order is never mirrored.
Error windows show a stable error ID, localized explanation and available original
diagnostics. Ctrl+C copies the whole displayed document; Close, Esc and the title
bar close button remain available. An unknown error uses a generic explanation
and keeps its original diagnostic details. Pre-GUI launcher failures use the
same language selection and stable IDs. Default file-worker logs omit private
diagnostics; detailed file errors require the explicit diagnostic option.

The Qt/QML desktop opens a compact 420x260 logical-pixel control window (minimum
380x260). Its primary controls are an explicit source picker and SBS start/stop.
The main window switches between 실시간 SBS and 파일 변환. Opening the capture
picker offers 창 and 모니터 전체 before source selection. The file workspace
expands the window and shows the queue and conversion action. Navigation
preserves the current job and the shared processing lease.
The live settings button opens 실시간 출력 설정 for depth model, strength, cursor,
frame interpolation and output FPS limit. Diagnostics are accessible from
that window. File settings expose the depth model, codec and file-specific
processing controls in the file workspace.
The visual direction is a restrained, macOS-inspired light utility: warm light
gray, white input surfaces, blue primary action, thin borders and compact type.
Windows title-bar controls remain native and in their usual positions. The selected source shows
its application icon when available, otherwise a neutral window symbol. Icon
lookup reads only OS icon metadata, is bounded and never captures a thumbnail.
The quality, file, settings and separate error windows share the light treatment;
the SBS video surface itself remains black. QML color tokens live in Theme.qml.
The single **깊이 모델** picker names DA2 Small (default), DA2 Base and VDA Small,
with computation precision beside each name. Base is marked **FP16 혼합**;
VDA shows **FP16 혼합** for the managed mixed-precision pack or **FP32** for an
installed legacy engine. Uninstalled VDA shows the downloadable pack's precision,
identified as an install target in help. Source-only oVDA remains an explicit
mixed-FP16 choice, and file conversion includes VDA Small · 5프레임. The adjacent ?
popup explains each model's purpose and FP32/FP16 boundaries. There is no second
model picker or implied quality ladder. Internal mode keys and their processing
policies remain stable, preserving existing saved mode/model selections.

The sole SBS result window can be moved normally and toggled fullscreen with F11
or its context menu; Escape exits fullscreen. Last normal output geometry and
screen identity are remembered locally, with bounds clamped to an available
screen on restart. No source titles or captured pixels enter that preference.
Live output settings and file conversion settings offer one stereo format picker:
Full SBS, Half SBS, Full Top-and-Bottom and Half Top-and-Bottom (default).
Live and file tasks each remember the user's mode/model and stereo format across
app launches. Fresh selections use DA2 Small and Half Top-and-Bottom. Only
explicit user selection writes these preferences; diagnostic/comparison setters
do not overwrite them. Stored values are validated against each task's choices.
The left eye is on the left or top. Half SBS averages adjacent horizontal pixels
after full-resolution stereo synthesis. Native CUDA Half Top-and-Bottom with VFG
off uses half-height stereo synthesis: RGB/depth/shift rows are reduced after
full-resolution depth history, selecting the nearer surface at depth boundaries.
Guided-filter scratch is reused on the same CUDA stream. File, host, RowFlow and
VFG output retain full-resolution synthesis followed by packing.
Odd dimensions replicate the final edge pixel. The playback device must use the matching format
to restore the original per-eye proportions. Live format changes apply on the
next session; file format and codec are independent job settings.
The SBS title updates each second with original, total output and interpolated
FPS over the last two seconds, plus median original capture-to-Qt latency and
`GPU n%` utilization. GPU usage is device-wide for the actual processing GPU,
including other applications, sampled at most once a second. Unsupported/failed,
not-yet-sampled or more-than-three-second-old readings show `GPU —` rather than
zero or a stale percentage. Optional utilization reporting never stops SBS.
The live output settings and output context menu share a saved, default-off
option to show these figures at matching positions in both eyes in fullscreen.
Overlay text uses an 8-pixel base font and 6-pixel base top/right margins per eye.
For stereo playback, Half SBS doubles the overlay's vertical axis and Half
Top-and-Bottom doubles its horizontal axis. The receiver's expansion of the
compressed video axis then restores balanced glyph proportions without shrinking
the text. The raw Half preview intentionally shows this compensation.
The main, utility and error windows use capture exclusion. For window input, the
independent SBS output allows external compositors to capture it. Monitor input
excludes the SBS output from capture to prevent feedback. There is no
external-3D capture-permission option or input/output monitor-separation rule.
Capture-only and legacy output APIs remain for explicit diagnostic callers.

The app is named ScreenTo3D. The prepared source and portable launcher is
`ScreenTo3D.exe`. It runs without a
console, resolves runtime paths relative to itself and reports launch failures
in a Windows error dialog. Per-launch logs are saved in
`%LOCALAPPDATA%\DepthSBS\logs`. Build it with
`scripts/build-desktop-launcher.ps1`; the portable builder does this automatically.
The source checkout also retains `Run-DepthSBS.cmd`. Source-local features do not
automatically appear in old portable packages. The present app uses one exclusive
processing lease for live/file/installation work and snapshots settings at start.
With ordinary native CUDA output and VFG off, DA2 Small and Base can keep the
last finished stereo image on screen while identical captures continue arriving.
The worker verifies all RGB pixels and waits for the displayed depth and border
mask to settle. Changed content resumes normal rendering on that capture.
The prepared checkout also offers a local RowFlow symmetric trial through
`powershell -File scripts/run-desktop.ps1 -RowFlow`. It requires Balanced/Base,
GPU processing and strength at most 1.92; unsupported settings fail visibly.
It changes stereo synthesis only, retaining Base TensorRT and depth processing.
No new primary UI option is exposed. First use of a screen size can require
compiler preparation; status explains the wait and Cancel remains available.
Ordinary launch retains the CUDA renderer. This trial is not in portable packages.
The normal prepared desktop exposes **프레임 보간 (VFG)** in **실시간 출력 설정**.
Its adjacent **?** icon opens a layered help popup on hover or keyboard focus,
with the explanation, global shortcut status and any compatibility restriction.
These descriptions are not permanently expanded below the checkbox.
It starts disabled on each app launch. Enabling it requests Medium 2x interpolation
for DA2 Small/Base GPU window capture with native output and the CUDA stereo
renderer. VFG can also be toggled during SBS from output settings, the output's
right-click menu, or the Windows global **Ctrl+Alt+S** shortcut (matching Lossless
Scaling's default). The app keeps the output window and its position/fullscreen
state, briefly displays its last frame, and restarts the owned processing session
on the same input. Repeated toggles are ignored during transition; Stop or closing
the output cancels it. The output displays a preparation notice at the center of
each eye during transition. Once the new output is ready, **VFG ON** or **VFG OFF**
uses a 14-pixel base font, stays visible for 1.5 seconds, then fades out over 250 ms. These notices appear in
both windowed and fullscreen output independently of the optional performance
overlay; Half formats compensate the compressed axis. Cancellation, errors and
hiding the output clear the notice without a success confirmation.
Enabling preflights the runtime before stopping existing
output, so a missing/corrupt installation leaves that session running. A failed
restart stops visibly rather than silently changing back. Shortcut conflicts with
another app are shown in its help popup; the controls remain available.
Unsupported selections explain the reason; a checked option can always be turned
off while idle. Starting an incompatible configuration or a missing/corrupt VFG
runtime reports an error rather than silently dropping interpolation. VFG adds
GPU/memory cost and latency; 2x interpolation does not promise twice the source
or displayed FPS. File conversion and capture privacy policy are unchanged.

The prepared checkout also retains an explicit VFG A/B trial: `Run-Compare-A.cmd`
opens the existing Base/CUDA SBS path and `Run-Compare-B-VFG.cmd` adds Medium 2x
VFG. `Run-Compare-Small.cmd` opens Performance/DA2 Small FP16 without VFG;
`Run-Compare-Small-VFG.cmd` adds the same Medium 2x VFG to Small. Both retain
the same output compatibility and current stereo reconstruction. All four use
the ordinary window picker and SBS start/stop; none starts capture automatically.
The comparison supports the launcher's selected Small or Base GPU window capture
with native output, initially limited to 60 FPS. Unsupported model, monitor or host-output
settings fail visibly before capture. Window titles identify model/A/B and show recent
original/generated output FPS and capture-to-Qt age. Numerical reports, without
source identities or captured frames, go under `out/vfg-comparison/`; comparison
output placement is separate from normal app preferences. For the user's Owl3D
3D-display comparison, these four launchers allow external capture of the SBS
result window; control and error windows stay protected. Its SBS output is an
independent native top-level window so external fullscreen detection resolves to
the SBS surface rather than the compact control window. F11/Escape and closing
the output to stop remain unchanged. DepthSBS output windows
are rejected as input across processes. No separate input/output monitor rule is
imposed. Stop and close one
comparison app before opening the other. These fixed A/B launchers hide the normal
VFG toggle to keep their measurement variants explicit. Existing portable packages
do not gain this new option automatically. See the [comparison instructions](../experiments/vfg/README.md#실사용-ab-비교).
Utility navigation remains available during work; closing a utility does not
cancel a job. Closing the main app during live SBS stops and waits for owned
worker cleanup before exit. File-work cancellation still asks before quitting.

File VFG processes completed Full SBS stereo frames before packing into any of
the four layouts. Original frames retain their source timestamps on the doubled
output timeline. A generated midpoint is inserted between ordinary adjacent
frames; a detected cut repeats the previous frame at that midpoint, and one final
repeat completes the original duration. Generated frames never enter depth-model
history. The file adapter uses the same pinned Medium 2x NVIDIA VFG bridge with
bounded host/device buffers; SDK/geometry errors stop the job and preserve any
previous output. Source-processing rate and output file FPS are distinct metrics.
The file API/CLI keep strength 1.0 and VFG off by default for existing diagnostics;
Desktop controls are integrated separately. This does not change live VFG policy.

## Live capture and output

1. Select an explicit window or monitor; there is no initial automatic selection.
   Opening the picker refreshes the list without capturing. Refresh
   preserves the selected HWND/PID or monitor device identity across reordering.
   A disappeared selection requires explicit reselection, even after subsequent
   refreshes; it does not silently select another source. Cursor
   inclusion remains on by default and is adjustable in the quality window.
2. No output setup is needed before starting. Fresh desktop defaults are
   Performance/DA2 Small, Half Top-and-Bottom, GPU native-texture output,
   60 FPS output and strength 0.5. Saved user mode/format choices take precedence.
   The strength reset button restores 0.5. Comparison launchers keep their
   explicitly selected model and do not save it to normal app preferences.
   Native output loads when SBS starts; opening the app alone does not load its
   DLL. A preparation failure is visible and does not silently change paths.
   Settings retains explicit GPU host-output and reference diagnostic choices;
   the legacy reference environment override remains available.
   Settings and diagnostics also offers an output FPS limit: unlimited,
   30 or 60 (default), changeable while stopped. With VFG off, native output targets that
   rate by scheduling work before taking the latest input. Small timing errors
   are recovered within a bounded interval; larger stalls reset the schedule
   without replaying missed work. A short spacing guard prevents closely grouped
   publications. This is a target rate, not an exact minimum gap between every
   pair of displayed frames. Host output and VFG retain their full-period
   publication caps; VFG's own scheduled frame times are also respected.
   Native delivery wakes when a frame/pool is ready or a pending deadline is due.
   Resource release, retirement and failure checks continue while waiting.
   Unlimited removes app pacing and requests Qt vsync off; source,
   processing, driver and display constraints can still limit achieved FPS.
   Small, Base, VDA Small and source-only oVDA window GPU sessions use GPU capture and preprocessing internally.
   There is no new user-facing option. Whole-monitor capture and reference paths
   retain their existing input path. This delivery change does not change the
   depth model, stereo renderer, source resolution or capture exclusion.
3. SBS 시작 starts conversion and opens the separate output. Invalid target
   selection rejects before capture; an output-open failure stops the owned job.
   Missing source selection or another owned job disables start with an adjacent
   explanation. Closing the output stops SBS; minimizing it keeps the session
   alive. Stop before changing session settings.
   Before the first available SBS frame, the status reports preparation and the
   action is 취소; after a frame arrives it becomes SBS 중지. It does not invent
   model-load progress or an estimated completion time.
4. Stop hides output, clears stale pixels and releases the owned session. Hidden
   Qt output scene graphs are not retained, so GPU nodes retire without waiting
   for another presentation. Source loss, incompatible
   color/topology changes and errors are visible; there is no silent source fallback.
   Live setup/start/output/runtime failures open a separate native SBS error
   window with a title-bar close control and an explicit 닫기 button. Escape also
   closes it. Ctrl+C copies the entire plain-text error without selecting text,
   whether the text or close button has focus. There is no copy button or QML
   overlay. The status line retains a short message; repeated notifications reuse
   one window. Error-window capture exclusion is rechecked before display; on
   failure the dialog remains hidden, live capture stops and status retains the
   original error plus the display failure.
   Normal progress and user-requested stop do not open it. The dialog does not
   block worker cleanup or release the processing lease early.
5. Display topology changes stop an active output session and restore a reachable
   control window. Restart validates capture again and fits saved output placement
   to the available screen. Automatic continuation across device/topology changes
   is not certified.

The four product modes are defined by their depth-model class and purpose, not only
by temporal/stereo policy labels:

| Mode | Depth-model contract | Processing and frame-rate intent |
|---|---|---|
| Performance | DA2 Small | Lowest latency and highest throughput; 1080p/4K 60–120 fps exploration |
| Balanced | DA2 Base | Stronger spatial depth; end-to-end 60 fps where hardware allows |
| Video Quality | oVDA or VDA, selected explicitly | Stateful temporal depth, cut-aware reset and low flicker; 60 fps goal with 30–60 fps as the test range |
| Offline Quality | VDA Small with centered five-frame processing; later validated models may replace it | File/offline-only, scene-local two-frame lookahead and color/depth-gated fusion; quality first with no realtime guarantee |

Backend availability, conversion correctness, license scope and complete-pipeline
evidence still determine whether a contract entry is supported on a given build.
There is no silent fallback to DA2 Small or another model. Moving content may force
fresh depth in Performance. Exact temporal/stereo values remain owned by
`v1/depthsbs_app/live_policy.py`, model-specific live adapters and shared configuration; those values refine a
mode but do not redefine its model identity.

Live DA2 Small and Base both use an eight-pixel radius for depth edge guidance.
Live Performance/DA2 Small, Balanced/DA2 Base and Video Quality retain conditional
uniform-background correction. A sufficiently uniform image border and a broad
border-connected backdrop trigger it; it is a color/geometry heuristic, not a
semantic subject mask. The live CUDA path keeps full-resolution classification
and correction on the GPU, with bounded approximations to median/distance weights.
It preserves interior depth and stabilizes the foreground rim and flat backdrop.
Its performance/quality comparisons are local evidence, not a 4K60 guarantee.
They keep depth postprocessing history across ordinary latest-frame
capture replacement when source timestamps remain increasing and at most 100 ms
apart. Cuts, source/size changes, replayed frames and longer pauses reset history.
Their prepared-local CUDA renderer reconstructs fractional-pixel shifts on the
same depth surface for both host and native output, including the VFG comparison.
At a locally separated foreground boundary, partial pixel coverage is combined
with a nearby visible farther surface instead of treating any coverage as opaque.
This is a bounded edge reconstruction; existing uncovered-hole filling remains.
The same live Small/Base CUDA paths stabilize their 2/98-percentile depth range
using source elapsed time separately from pixel-history filtering. Reliable
stationary depth anchors first compensate coherent model scale/offset drift;
weak or inconsistent anchors fall back to the time-based range response. Small
range changes settle slowly and larger changes respond faster; cuts and timestamp
discontinuities adopt the current range immediately. The same paths align one
previous depth observation to current motion on the GPU. Only reversible motion
with matching color, nearby depth and no strong depth boundary can contribute;
unreliable/newly visible areas keep current depth. The contribution decays with
source age, is capped per pixel and never feeds back into its own history. Cuts,
time discontinuities and applied flat-background refinement discard this history.
For foreground cut off by the left/right image boundaries, the prepared-local
Small/Base renderer adds a narrow floating-window mask on the left eye's left
edge and/or the right eye's right edge. Width follows the clipped foreground's
disparity, capped at 1.5% of one eye's width. Protection expands immediately and
releases with source time; cuts and time discontinuities reset it. The mask hides
a small edge strip without changing image dimensions, depth or projection geometry.
Pixels outside that strip remain unchanged. The VFG comparison also reapplies
the larger of its two source masks after interpolation, so generated frames do
not reveal the protected edge. Top/bottom boundaries are not addressed by this
left/right-window correction.
The same live Small/Base paths now compress large near/far disparities before
projection, including the comparison/VFG launchers. Small disparities remain
exact; beyond a smooth knee, magnitude approaches a fixed width-relative limit
without reversing depth order or amplifying disparity. Near and far limits are
separate. These are conservative rendering parameters, not physical comfort
guarantees. The curve does not depend on scene statistics, change convergence or
modify depth history. Edge masks follow the resulting actual disparity.
Increasing strength still increases disparity, with progressively smaller gains
in already compressed regions. The existing linear path is retained for diagnostics.
The prepared-local Small/Base renderer additionally adjusts only a narrow,
uncertain depth fringe where neighboring depth surfaces and RGB boundaries agree.
It changes projection position, preserving the original depth used to identify
surfaces and the model/history state. Its subpixel movement stays within existing
pixel coverage so it cannot switch the foreground/background visibility winner.
Sharp thin objects and flat surfaces are
left alone. For holes and partially covered foreground pixels, it samples the
farther surface continuously where visible; otherwise it can extend a locally
consistent background color gradient by at most four source pixels. Uncertain
texture/depth boundaries retain the previous fill. This is a bounded local
correction, not generation of unseen scene detail or a general inpainting model.
Base/Small VFG originals share these corrections before frame interpolation.
This adds no user setting or lookahead. Strength remains user-controlled (default 0.5) and convergence stays
fixed; content-driven automatic convergence is an explicit diagnostic experiment.
File/reference rendering and stateful VDA/oVDA history contracts remain separate.

The source desktop now snapshots and validates the model owned by the selected
mode. Performance uses the existing fused DA2 Small live path. Balanced uses DA2
Base, while Video Quality exposes only an explicit oVDA/VDA choice. Base, VDA and
oVDA live GPU sessions keep source-resolution depth on their owned CUDA stream and
use native-texture delivery by default in the prepared checkout; host output remains
available. Base's explicit reference path and file conversion keep host-depth
output. Offline Quality remains file-only. Missing, unlicensed or
shape-incompatible artifacts fail visibly without model fallback.
See [current paths and limits](implementation-status.md).

Current capture supports SDR BGRA8, source dimensions 16..4096 by 16..2160 and
the selected stereo arrangement within twice the source pixel count. Full SBS
doubles width; Full Top-and-Bottom doubles height; Half formats keep approximately
the source pixel count. Unsupported shapes/HDR fail rather than crop or
stretch silently. Preview fitting does not change source geometry. The OS capture
border and own-app capture exclusion prevent unintended capture/feedback.
Recording/audio capture and OpenXR output are not implemented live features.

Prepared-local GPU processing and explicit reference selection are distinct from
host vs native-texture delivery. An output limit is not guaranteed achieved
FPS or a physical monitor refresh setting. Show capture, processing and output health without presenting callback counts
as physical display latency. See [current paths and limits](implementation-status.md).

## Files and models

The current desktop portable opens live and file tasks in 빠른 처리 with DA2 Small
FP16 bundled. Small builds its local TensorRT engine on first use. Selecting
Balanced, VDA Small, or enabling VFG exposes the missing component beside that
selection, with its download size and terms. Installation starts on explicit
action, shares the processing lease, and supports cancel, retry and a verified
local file. The install never starts capture or conversion. Both tasks reuse
completed installations from the user's local DepthSBS model cache. The packaged
Base and VDA installers compile verified ONNX graphs on the user's current GPU
and check numerical depth output before making the new engines available.
VDA uses mixed FP16 for encoder projections and spatial attention in all twelve
encoder blocks, and FP32 for its temporal layers
and state. The installer also verifies its warmup-to-cached transition. The packaged
desktop offers VDA Small for Video Quality; oVDA is a source-only integration.
Source and portable desktops share the Small default even if Base is installed;
the saved selection can restore Base without downloading it again.
See the [portable build and optional pack procedure](models/desktop-distribution.md).

The current file picker/drop list accepts supported MP4/MKV/MOV/M4V inputs, up to
32 entries, with one selected job at a time. Input is never overwritten. Existing
destinations are confirmed; successful finalization publishes the result, while
failure/cancellation preserves the previous output. Native calls can delay
cooperative cancellation; file workers do not inherit the capture watchdog.
File-specific model choice and license confirmation are on the file page, next
to its processing settings. Conversion/progress actions remain outside the
scrolling settings area. Completed files offer video and parent-folder opening.
Settings contains environment checking and collapsed diagnostics/paths. The user
selects live SBS (initial choice) or file conversion as the installation-check
target; the check snapshots that task's model and paths and labels its result.
The existing no-argument diagnostic API still checks file conversion. Installation
inventory does not execute a model or certify GPU performance. Advanced model-path
editing continues to use the model selected on the file page.
Other processing controls and codec selections are not persisted by this change.
Automatic codec selection and batch execution are not introduced.

H.264/HEVC input uses the current FFmpeg path and source frame/cadence/audio policy.
Full SBS doubles width and Full Top-and-Bottom doubles height. Full-resolution
eye-4K files require explicit HEVC; Half formats can keep both packed axes within
the H.264 release limit. Short 4K fixtures establish
compatibility only. Live overload replacement is not offline frame dropping.

The source desktop resolves Performance to DA2 Small and Balanced to DA2 Base.
Both use FP16 TensorRT model computation with FP32 input/output; Base preserves
sensitive Resize/LayerNormalization/Softmax operations in FP32. Base's FP16
default is an intentional precision/speed tradeoff, with no extra precision
selector or automatic FP32 fallback. File and live Base sessions use the same
trusted FP16 profiles; numerical and physical acceptance limits are in current status.
Balanced fits non-native source ratios inside the validated Base model canvas;
padding is internal to depth inference, not added to the source or SBS eyes.
VDA Small also fits non-native ratios, including ultrawide, 4:3 and portrait,
inside the installed canvas with the highest fraction occupied by the image.
It replicates the edge pixels and crops the resulting depth to the content
before resizing it to the source. Inputs matching the original VDA profiles
retain their validated resize and profile selection.
Source-only oVDA uses the same aspect-fit principle over its installed
518x924 mixed-FP16 canvas, including 4:3, ultrawide, portrait and square sources.
The encoder and spatial attention use mixed FP16; temporal blocks, cache, depth
head and floating I/O remain FP32. Live and file jobs use the same verified
engine. The matching native profile keeps its existing transform; other cases
aspect-fit into that canvas. The source and SBS are never
stretched or cropped by model preprocessing. Source-size changes reset model
history even when the chosen canvas stays the same.
Video Quality permits only an explicit oVDA/VDA choice. Offline Quality resolves
to VDA Small plus its dedicated centered five-frame processor: it buffers at most
two prior and two future depth observations within a scene, emits every source
frame in order, and flushes at cuts without crossing the boundary. Moving pixels
are gated rather than warped because this path has no trusted motion-vector input.
Missing artifacts and incompatible combinations fail before conversion. VDA/oVDA
file bindings still require every decoded frame. Live VDA infers every accepted
capture update and retains model/rendering history across at most one missing
capture when source timestamps advance and the interval is at most 50 ms.
Consecutive captures retain the existing 100 ms maximum source interval. Larger
capture skips, invalid/reversed indices or clocks, cuts and source/size changes
reset both histories. Cache updates count accepted inputs; no artificial cache
frames are inserted. The strict legacy behavior remains a diagnostic override.
Live oVDA infers every accepted
capture update, but retains model and rendering history across at most one missing
capture update when timestamps advance and the interval is at most 50 ms.
Two or more missing updates, an interval above 50 ms (even without an index skip),
invalid/reversed clocks, cuts and source-size/source changes reset history.
No synthetic frames are inserted into its cache. Other models' history policies
and oVDA's model precision and output settings are unchanged.
Live oVDA uses lighter additional pixel-depth smoothing independently of depth-range
stabilization, retaining its model's temporal context and existing motion gates.
Its live depth range suppresses small endpoint changes and follows elapsed source
time: new near/far content expands the range quickly, while contraction recovers
more slowly. Reliable stationary raw-depth anchors carry the range across global
model scale/offset changes. Cuts and discontinuities adopt a fresh range; the
first frame's range is never permanently locked.
This does not alter the file defaults or add a user-facing setting.

- [DA2 Base local setup](models/da2-base.md)
- [VDA Small local setup](models/vda.md)
- [oVDA local setup and license scope](models/ovda.md)

The optional black-bar backdrop refinement is off by default. It neither crops
nor adds bars: three stable eligible regions activate restoration; captions,
changed bounds, ineligibility or cuts clear it. Zero applied frames is not job
failure. General-content/VR effectiveness remains unestablished.

## Presentation and validation

Keep a clear, keyboard-accessible Korean interface, readable contrast, responsive
layouts and actionable errors. Existing colors/window sizes are implementation
choices; they are not mandatory design tokens for a redesign.

Compare spatial depth, temporal stability, occlusion/edge artifacts, text, cuts,
binocular consistency and game latency on the actual path. Do not substitute
synthetic correctness for natural-content/VR acceptance. [Current acceptance](implementation-status.md#unpassed-acceptance)
is separate from [future work](ROADMAP.md).
