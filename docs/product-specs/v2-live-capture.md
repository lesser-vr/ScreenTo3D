# V2 live capture product specification

Status: Proposed; implementation sequence accepted by `docs/ROADMAP.md`
Owner: Product and live pipeline
Last reviewed: 2026-09-03

## Product promise

V2 lets a user select a Windows monitor or capturable window and view a
continuously generated SBS representation without first recording a video file.
The product reports actual cadence and latency and never disguises frame drops,
fallbacks, or capture interruptions.

## User flow

1. Select a monitor or window.
2. Select Performance, Balanced, or Video Quality.
3. Review the resolved capture resolution, target cadence, depth cadence,
   expected latency class, and output sink.
4. Start capture and view SBS preview plus live health indicators.
5. Stop capture without leaving GPU resources, child processes, or partial
   recordings.

Offline Quality remains a file-conversion mode unless a later benchmark proves
that its resolved plan can satisfy an explicitly labeled live profile.

## Required behavior

- Capture one selected monitor or supported window on Windows 11.
- Handle display resize, DPI, orientation, minimized/occluded windows, and source
  closure through explicit state transitions.
- Preserve a monotonically increasing capture sequence and source timestamp.
- Keep capture, processing, and output queues bounded.
- Prefer the newest useful frame when live latency would otherwise grow without
  bound; record every dropped or replaced frame and its reason.
- Re-prime depth/temporal state after large discontinuities, source changes, or
  capture restart.
- Display capture fps, processed fps, displayed fps, end-to-end latency, drop
  count, GPU utilization, and current mode.
- Fail visibly when the required NVIDIA GPU/driver/runtime or capture permission
  is unavailable. No silent CPU inference fallback is permitted.

## Mode behavior

| Mode | Live promise | Initial scheduling policy |
|---|---|---|
| Performance | Lowest latency and best cadence | latest-frame bounded queue; depth cadence may be reduced explicitly |
| Balanced | Default quality/latency tradeoff | full-rate where supported, otherwise a disclosed fixed cadence |
| Video Quality | Greater temporal stability | bounded stateful smoothing with a higher allowed latency class |
| Offline Quality | File conversion only in initial V2 | unavailable in live selector with explanation |

Mode resolution is data-driven and produces one immutable live processing plan.
Capture, depth, stereo, and output components do not reinterpret the selected
mode.

## Latency and cadence hypotheses

The following are experiment targets, not support claims:

- 1080p60 capture and preview on the RTX 5090 reference machine;
- 1080p30 as the first compatibility envelope on a future minimum GPU;
- steady-state motion-to-preview P95 below 50 ms for Performance;
- no unbounded queue growth during a 30-minute session;
- 4K30 as a stretch workload after the 1080p path is stable.

Support is granted only for the exact GPU/driver/display/mode envelope that
passes the benchmark protocol.

## Capture and color contract

The capture descriptor includes source identity, dimensions, pixel format,
color space, HDR state, orientation, DPI scaling, capture timestamp, and frame
sequence. SDR and HDR behavior must not be conflated. Unsupported HDR input is
rejected or explicitly tone-mapped by a named policy.

Cursor capture is a user-visible option. The default and its performance cost
must be measured before acceptance.

## Output contract

The first sink is an in-app full-SBS preview. A sink receives ordered GPU frame
handles plus timestamps through a bounded interface. Later recording, OpenXR,
virtual-display, or network sinks must implement the same ownership and
backpressure contract.

## Reliability and privacy

- Capture starts only after explicit user action and shows an active indicator.
- Frames are processed locally and are not retained unless recording is
  explicitly enabled.
- Diagnostics never include captured pixels or window titles by default.
- Device removal, display reconfiguration, session lock, permission loss, and
  output closure transition to visible recoverable or terminal states.
- Stop and cancellation release capture sessions and GPU resources
  deterministically.

## V2 acceptance

- Generated desktop fixtures prove geometry, color, cursor, resize, and
  timestamp behavior.
- Real desktop workloads cover static UI, scrolling text, video playback,
  animation, games where capture is permitted, multi-monitor DPI, and HDR/SDR.
- Latency is measured from capture timestamp to preview presentation, not from
  isolated inference time.
- Drop counts, queue occupancy, copies, synchronization, VRAM, power, and stage
  P50/P95/P99 are retained with environment metadata.
- Thirty-minute soak, repeated start/stop, source loss, display change, device
  loss, and cancellation tests pass without leaks or stale capture indicators.
