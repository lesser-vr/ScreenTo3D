# Reliability

Status: Proposed V1 contract  
Last reviewed: 2026-09-03

## Reliability objectives

- Never publish a truncated or corrupt output as a successful final file.
- Preserve frame order, timestamps, declared cadence, and the chosen audio policy.
- Keep memory and queue occupancy bounded for inputs of arbitrary duration.
- Fail early on incompatible GPU, driver, codec, model, or engine artifacts.
- Make cancellation prompt and deterministic, releasing all CPU/GPU resources.
- Produce actionable diagnostics without exposing sensitive paths or media data.

## Job state model

```text
created -> probed -> planned -> warming -> processing -> finalizing -> succeeded
    |         |         |          |            |            |
    +---------+---------+----------+------------+------------+-> failed
                                      |
                                      +------------------------> cancelled
```

Only `succeeded` publishes the final output path. Processing writes to a unique
temporary sibling and atomically promotes it after encoder flush, mux finalization,
and validation. Cleanup must be idempotent.

## Error policy

- Input and capability errors are reported before expensive engine work where
  possible.
- Frame-processing errors include stage, frame ID, PTS, backend, and stable error
  code; they do not include raw frame content.
- V1 aborts on unrecoverable decode, inference, stereo, encode, mux, OOM, or device
  loss. Skipping corrupt frames is not a silent default.
- No automatic model, precision, device, codec, or CPU fallback occurs.
- A scene cut or timestamp discontinuity resets temporal state and is counted.

## Resource guarantees

The Python V1 backend now closes partially initialized allocations if startup
fails, retains runtime/context ownership until explicit close, and attempts
every owned release even if one fails. Pending work is synchronized before
release on an inference error; normal completed inference adds no cleanup sync.
Release failures are surfaced and handles are not blindly retried because
driver-side ownership may be uncertain. This is not device-loss recovery.

Pipeline cleanup explicitly closes process pipes and preserves the primary
exception with cleanup notes. Completion is emitted only after cleanup succeeds.
Cancellation checks run before engine startup, around drain/mux, and before
publication; blocking native calls remain cooperative cancellation boundaries.
Atomic replacement no longer unlinks the prior output first, so a failed
replacement preserves it. See `exec-plans/active/v1-1-cleanup.md` for evidence.

All long-lived GPU resources use explicit ownership and bounded pools. Queue
capacity is fixed by the processing plan. Cancellation stops new submissions,
waits or aborts outstanding work through documented APIs, flushes only when safe,
and releases resources in dependency order.

Repeated job execution, cancellation at every stage, failed engine load, malformed
input, encoder initialization failure, and simulated OOM are required test cases.

## Observability

Each job gets a random correlation ID. Structured events include state changes,
resolved plan, capability summary, stage errors, copy/sync counters, queue
high-water marks, memory high-water marks, scene-cut resets, and final outcome.

Performance traces are opt-in artifacts with retention under user control. Logs
must not include video frames, model weights, full local paths by default, or
codec extradata beyond what is needed for diagnosis.

## Recovery and resume

V1 provides restart-from-beginning only. Offline Quality resume/checkpoint support
is an explicit future product feature; partial containers, depth caches, or engine
state must not be presented as resumable until their compatibility and integrity
format is specified and tested.
