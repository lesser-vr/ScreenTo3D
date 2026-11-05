# DepthSBS product

Current product intent and local user behavior, 2026-09-10. Implemented limits
below describe the current build, not permanent restrictions on future designs.

## Goal

Give games and video viewing better depth and simpler operation than the user's
DA2 Small + Lossless Scaling FG baseline. Preserve 3840x2160 input and per-eye
image, producing 7680x2160 Full SBS at final 60 fps. Frame generation is allowed;
fresh model inference at 60 Hz is not required. The complete model, postprocessing,
FG and presentation path determines perceived quality and latency.

The user's comparison setup is iw3 with 3840x2160 60 fps input, Lossless
Scaling FG x2, and OpenVR / Desktop+ viewing on Quest 3. These identify the
baseline components, not verified routing order, actual output rates or headset
transport. Measure those rather than deriving them from the configured x2 factor.

This is a target, not certified support. Exact 59.94/60.00 cadence, model/base/FG
rates and output geometry must be declared in comparisons. A combined 4K SBS
image or a 4K model input is not equivalent to 4K per eye.

## Desktop experience

The Qt/QML desktop opens a compact 420x260 logical-pixel control window (minimum
380x260). Its primary controls are an explicit source picker and SBS start/stop.
A small menu opens 화질과 입체감, 파일 변환, or 설정과 진단 in a separate utility
window, and allows switching to whole-monitor capture. There is no sidebar,
original preview, in-app SBS preview, output-style picker or output-monitor picker.
Mode/strength/cursor controls live in the quality window; technical paths and
target cadence live in Settings. Shared controls retain keyboard focus and
long-label tooltips. Existing mode IDs and model defaults are unchanged.
The visual direction is a restrained, macOS-inspired light utility: warm light
gray, white input surfaces, blue primary action, thin borders and compact type.
Windows title-bar controls remain native and in their usual positions. The menu
uses a labeled, keyboard-accessible ellipsis button. The selected source shows
its application icon when available, otherwise a neutral window symbol. Icon
lookup reads only OS icon metadata, is bounded and never captures a thumbnail.
The quality, file, settings and separate error windows share the light treatment;
the SBS video surface itself remains black. QML color tokens live in Theme.qml.
Display names are 빠른 처리 / 균형 / 영상 품질 / 오프라인 품질. These are model
class choices, not certified performance or perceptual rankings.

The sole SBS result window can be moved normally and toggled fullscreen with F11
or its context menu; Escape exits fullscreen. Last normal output geometry and
screen identity are remembered locally, with bounds clamped to an available
screen on restart. No source titles or captured pixels enter that preference.
Main, utility, error and SBS windows remain excluded from capture. There is no
external-3D capture-permission option or input/output monitor-separation rule.
Capture-only and legacy output APIs remain for explicit diagnostic callers.

The prepared source launcher is `Run-DepthSBS.cmd`. Source-local features do not
automatically appear in old portable packages. The present app uses one exclusive
processing lease for live/file/installation work and snapshots settings at start.
The prepared checkout also offers a local RowFlow symmetric trial through
`powershell -File scripts/run-desktop.ps1 -RowFlow`. It requires Balanced/Base,
GPU processing and strength at most 1.92; unsupported settings fail visibly.
It changes stereo synthesis only, retaining Base TensorRT and depth processing.
No new primary UI option is exposed. First use of a screen size can require
compiler preparation; status explains the wait and Cancel remains available.
Ordinary launch retains the CUDA renderer. This trial is not in portable packages.
Utility navigation remains available during work; closing a utility does not
cancel a job. Closing the main app during live SBS stops and waits for owned
worker cleanup before exit. File-work cancellation still asks before quitting.

## Live capture and output

1. Select an explicit window or monitor; there is no initial automatic selection.
   Opening the picker refreshes the list without capturing. Refresh
   preserves the selected HWND/PID or monitor device identity across reordering.
   A disappeared selection requires explicit reselection, even after subsequent
   refreshes; it does not silently select another source. Cursor
   inclusion remains on by default and is adjustable in the quality window.
2. No output setup is needed before starting. Prepared-local defaults are
   Balanced/DA2 Base, GPU native-texture output, unlimited output FPS and strength 1.0.
   Native output loads when SBS starts; opening the app alone does not load its
   DLL. A preparation failure is visible and does not silently change paths.
   Settings retains explicit GPU host-output and reference diagnostic choices;
   the legacy reference environment override remains available.
   Settings and diagnostics also offers an output FPS limit: unlimited (default),
   30 or 60, changeable while stopped. The same publication limit applies to
   native and host output; missed deadlines do not trigger catch-up bursts.
   Resource release, retirement and failure checks continue while waiting for
   output. Unlimited removes app pacing and requests Qt vsync off; source,
   processing, driver and display constraints can still limit achieved FPS.
   Small and Base window GPU sessions use GPU capture and preprocessing internally.
   There is no new user-facing option. Whole-monitor capture and other models
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
| Balanced | DA2 Base | Stronger spatial depth and practical default; end-to-end 60 fps where hardware allows |
| Video Quality | oVDA or VDA, selected explicitly | Stateful temporal depth, cut-aware reset and low flicker; 60 fps goal with 30–60 fps as the test range |
| Offline Quality | VDA Small with centered five-frame processing; later validated models may replace it | File/offline-only, scene-local two-frame lookahead and color/depth-gated fusion; quality first with no realtime guarantee |

Backend availability, conversion correctness, license scope and complete-pipeline
evidence still determine whether a contract entry is supported on a given build.
There is no silent fallback to DA2 Small or another model. Moving content may force
fresh depth in Performance. Exact temporal/stereo values remain owned by
`v1/depthsbs_app/live_policy.py` and shared configuration; those values refine a
mode but do not redefine its model identity.

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
Full SBS at twice source width. Unsupported shapes/HDR fail rather than crop or
stretch silently. Preview fitting does not change source geometry. The OS capture
border and own-app capture exclusion prevent unintended capture/feedback.
Recording/audio capture and OpenXR output are not implemented live features.

Prepared-local GPU processing and explicit reference selection are distinct from
host vs native-texture delivery. An output limit is not guaranteed achieved
FPS or a physical monitor refresh setting. Show capture, processing and output health without presenting callback counts
as physical display latency. See [current paths and limits](implementation-status.md).

## Files and models

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
Automatic codec selection, persistent preferences and batch execution are not
introduced by this UI revision.

H.264/HEVC input uses the current FFmpeg path and source frame/cadence/audio policy.
Full SBS doubles width. Eye-4K file output requires explicit HEVC in the current
implementation because H.264 output is width-limited. Short 4K fixtures establish
compatibility only. Live overload replacement is not offline frame dropping.

The source desktop resolves Performance to DA2 Small and Balanced to DA2 Base.
Both use FP16 TensorRT model computation with FP32 input/output; Base preserves
sensitive Resize/LayerNormalization/Softmax operations in FP32. Base's FP16
default is an intentional precision/speed tradeoff, with no extra precision
selector or automatic FP32 fallback. File and live Base sessions use the same
trusted FP16 profiles; numerical and physical acceptance limits are in current status.
Balanced fits non-native source ratios inside the validated Base model canvas;
padding is internal to depth inference, not added to the source or SBS eyes.
Video Quality permits only an explicit oVDA/VDA choice. Offline Quality resolves
to VDA Small plus its dedicated centered five-frame processor: it buffers at most
two prior and two future depth observations within a scene, emits every source
frame in order, and flushes at cuts without crossing the boundary. Moving pixels
are gated rather than warped because this path has no trusted motion-vector input.
Missing artifacts and incompatible combinations fail before conversion. VDA/oVDA
stateful bindings still reject skipped-frame policies.

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
