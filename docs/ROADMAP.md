# DepthSBS product roadmap

Status: Accepted sequencing; performance targets remain hypotheses until audited
Last reviewed: 2026-09-03

## Product direction

DepthSBS evolves in two deliberate steps:

1. make file conversion measurable, fast, reliable, and supportable;
2. reuse the proven GPU stages in a bounded low-latency live capture pipeline.

The existence of a user-launchable V1 does not by itself establish a supported
resolution or frame-rate envelope. Those claims require the benchmark and
quality gates below.

## Release sequence

| Release | Outcome | Required evidence |
|---|---|---|
| V1.0 | Portable Windows file converter using DA2 Small TensorRT | Completed H.264 fixture, four modes, audio, cancellation, isolated package run |
| V1.1 | Instrumented and reliability-hardened converter | Per-stage telemetry, H.264/H.265 corpus, repeated-run and fault-path results |
| V1.2 | GPU-optimized conversion path | CUDA stereo path, copy/sync accounting, bounded scheduling, profiler evidence |
| V1.3 | Published support and quality envelope | 1080p/4K benchmark matrix, real-image quality corpus, exact GPU/driver matrix |
| V2.0 | Real-time desktop capture and SBS preview/output | Bounded capture pipeline, latency/drop metrics, device-loss recovery, live quality gates |

## V1 hardening before V2

### V1.1 — Observability and media reliability

- Emit job IDs, resolved plans, stage timings, errors, frame counts, and final
  outcomes as structured artifacts.
- Measure decode, preprocess, inference, temporal, stereo, encode, mux, and
  end-to-end time separately.
- Add H.264 and H.265 fixtures with cuts, fades, variable timestamps, audio, and
  malformed/error cases.
- Test repeated conversion, cancellation at each stage, engine rebuild, encoder
  failure, device loss, and out-of-space behavior.
- Reconcile `QUALITY_SCORE.md`, active plans, and technical debt with current
  implementation evidence.

Exit: media correctness, reliability, observability, and CI enforcement reach
implemented status with reproducible commands.

### V1.2 — Native GPU performance path

- Replace CPU RGB decode transfer with NVDEC/D3D11 or an explicitly measured
  FFmpeg hardware-frame path.
- Implement CUDA preprocessing and symmetric SBS synthesis against the CPU
  golden oracle.
- Introduce bounded frame pools and queues with backpressure.
- Overlap decode, TensorRT, stereo, and NVENC only after serial equivalence.
- Record copy bytes/count, synchronization count, queue high-water marks, VRAM,
  and stage P50/P95/P99 latency.

Exit: the complete pipeline has bounded memory, profiler-confirmed ownership,
and materially better end-to-end throughput without quality regression.

### V1.3 — Quality and support matrix

- Run generated and approved real-image/video corpora covering motion, cuts,
  thin structures, occlusion, darkness, noise, and texture extremes.
- Validate depth polarity, eye order, convergence, borders, holes, temporal
  flicker, and visual comfort.
- Benchmark 1080p30/60 and 4K30/60 H.264/H.265 workloads with at least five
  measured repetitions on available reference GPUs.
- Publish supported, exploratory, and rejected hardware/workload envelopes.
- Reduce portable-package size and complete public redistribution review before
  a public binary release.

Exit: every advertised mode and workload is backed by raw benchmark and quality
evidence.

## V2.0 — Real-time screen capture and conversion

V2 explicitly adds live Windows desktop capture as a product goal. It converts
captured frames continuously into SBS output with bounded latency and memory.

Initial V2 sources and sinks:

- source: selected Windows monitor or window;
- source options under evaluation: Windows Graphics Capture and DXGI Desktop
  Duplication, with FFmpeg `ddagrab` retained as a reference path;
- output: in-app SBS preview and a reusable low-latency frame-output interface;
- audio: optional system-audio capture after video latency is stable.

Direct SteamVR/OpenXR injection, headset-specific drivers, network streaming,
and non-NVIDIA backends are not required for the first V2 release. The output
interface must avoid preventing those later integrations.

V2 milestones and acceptance gates are defined in
`docs/exec-plans/active/v2-live-capture.md`. User behavior is defined in
`docs/product-specs/v2-live-capture.md`.

## Sequencing rule

V2 capture prototyping may begin while V1.2 optimization is active, but V2 may
not duplicate or fork depth/stereo policy. It consumes the same validated stage
contracts. A live frame-drop mechanism is new scheduler policy, not a change to
offline conversion semantics.

## Unscheduled future work

- Direct OpenXR/SteamVR compositor integration.
- Virtual camera or virtual display output.
- Network/remote SBS streaming.
- Cross-vendor inference backends.
- User-installable model marketplace.
- Offline resume/checkpoint support.
