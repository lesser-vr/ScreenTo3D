# DepthSBS product

Current product intent and local user behavior, 2026-09-07. Implemented limits
below describe the current build, not permanent restrictions on future designs.

## Goal

Give games and video viewing better depth and simpler operation than the user's
DA2 Small + Lossless Scaling FG baseline. Preserve 3840x2160 input and per-eye
image, producing 7680x2160 Full SBS at final 60 fps. Frame generation is allowed;
fresh model inference at 60 Hz is not required. The complete model, postprocessing,
FG and presentation path determines perceived quality and latency.

This is a target, not certified support. Exact 59.94/60.00 cadence, model/base/FG
rates and output geometry must be declared in comparisons. A combined 4K SBS
image or a 4K model input is not equivalent to 4K per eye.

## Desktop experience

One Korean desktop app provides Live, Files and Settings. Game/video intent and
clear source/output choices should lead the UX; model/profile details can remain
advanced settings. Existing mode IDs need not dictate a future interface.

The prepared source launcher is `Run-DepthSBS.cmd`. Source-local features do not
automatically appear in old portable packages. The present app uses one exclusive
processing lease for live/file/installation work and snapshots settings at start.
Navigation remains available during work; it does not silently cancel a job.

## Live capture and output

1. Select an explicit window or monitor, Original preview or DA2 Small SBS, and
   cursor inclusion (currently on by default). Refresh enumerates sources only.
2. Select a live policy, depth strength and output target. Stop before changing
   source/session settings. Original preview performs no depth inference.
3. Start and view the preview or separate fullscreen output. Escape exits
   fullscreen; output closure/hiding follows the implemented window behavior.
4. Stop releases the owned session and clears stale pixels. Source loss, incompatible
   color/topology changes and errors are visible; there is no silent source fallback.

Current live profiles are Performance, Balanced and Video Quality, all DA2 Small.
They vary temporal/stereo policy, not model identity. Offline Quality is file-only.
Moving content may force fresh depth even in Performance. The exact policy values
are owned by `v1/depthsbs_app/live_policy.py` and shared configuration, not a second
numeric table here. Model changes and other sampling/FG designs are valid experiments.

Current capture supports SDR BGRA8, source dimensions 16..4096 by 16..2160 and
Full SBS at twice source width. Unsupported shapes/HDR fail rather than crop or
stretch silently. Preview fitting does not change source geometry. The OS capture
border and own-app capture exclusion prevent unintended capture/feedback.
Recording/audio capture and OpenXR output are not implemented live features.

Prepared-local GPU processing and explicit reference selection are distinct from
host vs experimental native-texture delivery. A 30/60 Hz target is not achieved
fps. Show capture, processing and output health without presenting callback counts
as physical display latency. See [current paths and limits](implementation-status.md).

## Files and models

The current file picker/drop list accepts supported MP4/MKV/MOV/M4V inputs, up to
32 entries, with one selected job at a time. Input is never overwritten. Existing
destinations are confirmed; successful finalization publishes the result, while
failure/cancellation preserves the previous output. Native calls can delay
cooperative cancellation; file workers do not inherit the capture watchdog.

H.264/HEVC input uses the current FFmpeg path and source frame/cadence/audio policy.
Full SBS doubles width. Eye-4K file output requires explicit HEVC in the current
implementation because H.264 output is width-limited. Short 4K fixtures establish
compatibility only. Live overload replacement is not offline frame dropping.

Four existing file modes resolve a processing policy; explicit model selection
is separate. DA2 Small is the default. VDA/oVDA stateful file bindings currently
reject the skipped-frame Performance policy. Offline Quality with those bindings
still uses their streaming algorithms, not a separate offline-windowed model.

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
