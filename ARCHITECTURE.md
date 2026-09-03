# DepthSBS architecture

Status: Proposed for V1  
Last reviewed: 2026-09-03

## System goal

DepthSBS is a native, NVIDIA-GPU-first 2D-to-SBS video pipeline. V1 is an
instrumented CLI that establishes whether an end-to-end GPU path can meet the
targets in `docs/product-specs/processing-modes.md`. A GUI, broad model gallery,
and non-NVIDIA backends are outside the first milestone.

## Context

```text
compressed video
      |
      v
input probe -> decode -> preprocess -> depth -> temporal policy -> SBS -> encode
                  |          |           |             |          |        |
                  +----------+-----------+-------------+----------+--------+
                                      telemetry
```

The intended V1 technology set is C++20, CUDA, TensorRT, FFmpeg demux/mux, and
NVIDIA Video Codec SDK (NVDEC/NVENC). This is a proposed baseline: dependency
versions and supported driver/GPU ranges are selected only after a compatibility
spike records a reproducible matrix.

## Components and dependency direction

Dependencies flow downward only.

```text
app / CLI
   -> pipeline
      -> mode policy
      -> media I/O
      -> temporal
      -> stereo
      -> depth backend interface
   -> observability interface

platform adapters
   -> FFmpeg / NVDEC / NVENC / CUDA / TensorRT

foundation
   -> validated value types, status/error types, resource ownership
```

- `foundation`: codec-independent descriptors, time base, frame ID, dimensions,
  pixel/depth formats, errors, and RAII GPU-resource wrappers.
- `mode policy`: resolves one named mode plus probed device capabilities into an
  immutable processing plan. It never processes pixels.
- `media I/O`: demuxes, decodes, encodes, and muxes while preserving timestamps,
  color metadata, and audio policy.
- `depth backend`: consumes a validated GPU frame view and produces normalized
  depth plus metadata. DA2, oVDA, and future engines implement one contract.
- `temporal`: owns caches, propagation cadence, cut resets, and confidence. It is
  optional per processing plan.
- `stereo`: applies depth mapping, divergence/convergence, occlusion handling,
  edge treatment, and SBS layout.
- `pipeline`: schedules bounded work, owns cancellation, and reports progress.
- `observability`: emits structured stage timings, counters, environment data,
  and benchmark artifacts without becoming a stage dependency.

Platform headers must not leak into product policy. CUDA/TensorRT/NVCodec types
are contained in adapters or opaque resource handles.

## Frame and resource contract

Each frame has a monotonically increasing frame ID, input PTS, time base, color
description, dimensions, and a resource whose owner is explicit. Stages may
retain a frame only through an ownership-bearing handle.

The steady-state pipeline uses preallocated pools and bounded queues. Crossing a
GPU/CPU boundary must be observable. The intended hot path keeps decoded frames,
model tensors, depth, SBS surfaces, and encoder inputs in device-visible memory;
profiling must prove whether copies remain.

Queue saturation applies backpressure. It must not allocate an unbounded backlog
or drop frames in offline conversion. A future playback mode may define an
explicit drop policy, but that is a separate product contract.

## Processing-plan contract

The four user-facing modes resolve to a `ProcessingPlan` containing at least:

- depth backend and engine precision;
- inference resolution;
- full-rate inference or propagation cadence;
- temporal cache/reset policy;
- stereo algorithm and quality parameters;
- encode codec, pixel format, rate-control profile, and latency preference;
- memory budget and queue depth;
- capability requirements and permitted fallback behavior.

Resolution happens once before processing. If requirements are not met, startup
fails with an actionable message or uses a user-approved fallback. Individual
stages do not reinterpret the selected mode.

## Concurrency

V1 begins with an asynchronous bounded pipeline and measures before adding more
streams. Decode/encode hardware can operate independently from CUDA compute, but
overlap is accepted only when traces show a gain and ordering remains correct.

Every asynchronous unit carries frame ID and PTS. Completion order may differ
internally; mux order may not. Cancellation drains or releases every outstanding
resource and leaves no partially published output file.

## Extension points

- Depth backends are plugins behind a stable in-process interface, not runtime
  arbitrary shared-library loading in V1.
- Temporal policies are independent of the selected depth model where possible.
- Stereo kernels may evolve from a baseline symmetric warp to occlusion-aware
  forward warp/inpainting without changing media I/O.
- An orchestration UI may call the same validated application service later; it
  must not own pipeline logic.

## Architectural invariants

1. External metadata is validated before allocation or GPU submission.
2. No unbounded queues or implicit global GPU state.
3. No silent CPU/model/precision fallback.
4. Timestamps, color metadata, and eye order are preserved or deliberately
   transformed and reported.
5. Scene cuts invalidate temporal caches.
6. Stage timing is available in every build intended for benchmarking.
7. Model and engine provenance is recorded with every benchmark result.
8. Distribution must comply with each model's license; DA2 Base is not assumed
   distributable for commercial use.

## Open decisions

- Direct NVCodec APIs versus FFmpeg hwaccel wrappers for the first vertical slice.
- Exact CUDA surface format between decoder, preprocessing, and encoder.
- Baseline stereo algorithm used for the first correctness oracle.
- Audio copy/transcode policy and container support beyond the H.264/H.265 V1 set.
- Engine artifact format, cache location, and compatibility invalidation scheme.
