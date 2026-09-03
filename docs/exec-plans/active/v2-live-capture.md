# V2: Real-time screen capture and SBS conversion

Status: Planned; starts after V1 instrumentation contracts are stable
Owner: Unassigned
Created: 2026-09-03

## Outcome

Deliver a Windows application mode that captures a selected monitor or window,
processes frames through the validated DepthSBS GPU stages, and presents a
bounded low-latency SBS preview with explicit cadence, latency, and drop metrics.

## Dependencies

- V1.1 structured stage telemetry and error taxonomy.
- A model-independent depth interface and data-driven mode resolver.
- V1.2 CUDA preprocess/stereo kernels and owned GPU frame contract.
- A benchmark harness capable of timestamping capture and presentation.

Capture API exploration may start earlier, but production integration waits for
these shared contracts to avoid a separate live-only pipeline.

## Non-goals for V2.0

- Direct OpenXR/SteamVR compositor injection.
- Virtual camera/display driver installation.
- Network streaming or cloud processing.
- Non-NVIDIA inference.
- Offline Quality as a live promise.
- Guaranteed capture of protected content or applications that block capture.

## M0 — Capture API and latency spike

- Prototype Windows Graphics Capture, DXGI Desktop Duplication, and FFmpeg
  `ddagrab` reference paths.
- Record format, D3D device ownership, cross-adapter behavior, cursor support,
  HDR metadata, resize behavior, permissions, and CPU/GPU copies.
- Measure capture-only P50/P95/P99 latency and stability for monitor/window,
  SDR/HDR, and multi-monitor DPI scenarios.
- Select the production API with an Accepted design decision; retain one simple
  reference oracle.

Exit: selected API and frame ownership contract are backed by traces and a
documented compatibility table.

## M1 — Deterministic live capture oracle

- Implement `CaptureSource` with explicit start, frame, resize, lost, stop, and
  failure states.
- Add monotonic sequence numbers and high-resolution capture timestamps.
- Render generated moving geometry and clocks to a test window for automated
  timestamp, orientation, crop, color, and cursor checks.
- Handle source closure, resize, DPI change, monitor removal, lock/unlock, and
  repeated start/stop.

Exit: the oracle captures a 30-minute generated session with bounded memory,
correct timestamps, and no leaked capture objects.

## M2 — Bounded real-time scheduler

- Connect capture to the existing preprocess, depth, temporal, and stereo stage
  interfaces.
- Use fixed-capacity pools and a latest-useful-frame queue for live processing.
- Separate captured, processed, presented, replaced, and dropped counters.
- Reset temporal state on source change, discontinuity, and a declared scene-cut
  signal.
- Resolve Performance, Balanced, and Video Quality once at session start.

Exit: overload increases the recorded drop count instead of queue latency or
memory, while stop/cancel drains or aborts resources deterministically.

## M3 — GPU interop and SBS preview

- Keep captured D3D frames GPU-visible through color conversion, resize,
  TensorRT input, depth, stereo, and preview where the selected APIs permit.
- Implement an in-app SBS preview sink with presentation timestamps and bounded
  buffering.
- Compare every GPU kernel/output against the file-pipeline reference oracle.
- Profile interop synchronization and prove copy counts rather than asserting
  zero-copy.

Exit: traces account for every device/host crossing, visual golden tests pass,
and preview latency is measured end to end.

## M4 — Live UX, controls, and diagnostics

- Add source selection, mode selection, start/stop, cursor option, preview, and
  clear active-capture indication.
- Show actual capture/processing/presentation fps, P95 latency, drop count, and
  recoverable errors.
- Prevent Offline Quality selection for live use with an explanation.
- Add privacy-safe export of environment, plan, counters, and timings.

Exit: a user can complete the full live flow and understand degraded cadence,
drops, and failures without consulting logs.

## M5 — Reliability, quality, and support decision

- Run 30-minute soak and repeated start/stop tests.
- Inject source loss, resize, display removal, permission loss, encoder/preview
  closure, device loss, OOM, and cancellation.
- Evaluate static UI, scrolling, video playback, rapid motion, games where
  permitted, scene cuts, thin text, occlusion, SDR, and supported HDR behavior.
- Benchmark 1080p30/60 and 4K30 hypotheses using the repository protocol.
- Publish exact supported GPU/driver/display/mode envelopes and reject failures
  explicitly.

Exit: V2.0 ships only when reliability, privacy, visual-quality, bounded-memory,
and end-to-end latency gates pass for at least one declared live envelope.

## Required benchmark record

Each run records commit, dirty state, OS, driver, GPU, display topology, capture
API, source type, resolution/refresh, color/HDR, model/engine checksum, mode plan,
queue capacities, copies/synchronizations, stage latency distributions, capture
fps, processed fps, presented fps, drop/replacement counts, VRAM, utilization,
power, and session duration.

## Risks and decisions still open

- Windows Graphics Capture may have different window/monitor, permission, and
  cursor behavior from Desktop Duplication.
- Cross-adapter displays can force copies or prevent direct interop.
- HDR capture and SDR preview require an explicit color-management decision.
- TensorRT engine time plus stereo/presentation may miss the latency hypothesis;
  cadence reduction must be disclosed by the resolved plan.
- Protected-content capture behavior cannot be bypassed and must produce an
  actionable user message.
- Direct headset presentation is a separate product/driver boundary and remains
  outside V2.0 until the preview pipeline is stable.

## Progress

- [x] Register real-time screen capture as a formal product goal.
- [x] Define initial user contract, non-goals, milestones, and acceptance gates.
- [ ] Complete M0 capture API and latency spike.
- [ ] Complete M1 deterministic capture oracle.
- [ ] Complete M2 bounded real-time scheduler.
- [ ] Complete M3 GPU interop and SBS preview.
- [ ] Complete M4 live UX and diagnostics.
- [ ] Complete M5 release audit and support decision.
