# DepthSBS agent guide

This file is a map, not the project encyclopedia. Read only the documents that
apply to the task, and keep durable decisions in the repository.

## Mission

Build a NVIDIA-GPU-first converter that turns 2D H.264/H.265 video into
VR-ready side-by-side (SBS) video. The product exposes four explicit operating
modes: Performance, Balanced, Video Quality, and Offline Quality.

The first milestone proves performance with a small end-to-end pipeline. Do not
add broad UI or model-selection work before the benchmark harness is credible.

## Start here

- Product behavior and mode contracts: `docs/product-specs/processing-modes.md`
- System boundaries and dependency direction: `ARCHITECTURE.md`
- GPU pipeline design: `docs/design-docs/gpu-pipeline.md`
- Benchmark protocol and acceptance gates: `docs/design-docs/benchmark-methodology.md`
- Current implementation plan: `docs/exec-plans/active/v1-foundation.md`
- Reliability and failure behavior: `docs/RELIABILITY.md`
- Security and model-license constraints: `docs/SECURITY.md`
- Current quality gaps: `docs/QUALITY_SCORE.md`

Indexes live in `docs/README.md`, `docs/product-specs/index.md`, and
`docs/design-docs/index.md`.

## Working rules

1. Verify the repository state before changing it. Preserve unrelated work.
2. For non-trivial changes, update or add an execution plan before implementation.
3. Keep mode policy data-driven. Do not scatter mode-name conditionals through
   decode, inference, stereo, or encode code.
4. Preserve the pipeline boundary types. Parse external input at the boundary;
   internal stages operate on validated descriptors and owned GPU resources.
5. Prefer bounded queues, explicit ownership, and deterministic cleanup. A
   faster pipeline that can grow memory without bound is not acceptable.
6. Instrument every stage: decode, preprocess, depth, temporal propagation,
   stereo synthesis, encode, and end-to-end latency.
7. Never claim a frame-rate target from isolated model inference timings.
   Measure the complete pipeline using the benchmark protocol.
8. Treat GPU zero-copy as an objective verified by profiling, not as a label.
9. A scene cut invalidates temporal state. Reset or re-prime cached depth before
   emitting propagated results.
10. Keep CPU fallback behavior explicit. Silent fallback that changes speed or
    output quality is forbidden.
11. New model backends require a license note, reproducible engine-build path,
    capability probe, and golden-output coverage.
12. Update the relevant product/design/reliability document in the same change
    when behavior or an invariant changes.

## Verification expectations

Use the smallest relevant checks during development and the complete V1 gate
before declaring the milestone complete:

- format, lint, and unit tests;
- deterministic synthetic-frame tests for preprocessing and SBS geometry;
- backend contract tests with a fake depth engine;
- short H.264 and H.265 end-to-end fixtures;
- visual/golden checks for depth polarity, eye order, convergence, and cuts;
- benchmark runs with raw JSON/CSV results and environment metadata;
- leak/error-path tests for repeated open, cancel, and device failure.

Commands are not defined yet. When the build system is introduced, document the
canonical commands here and make CI use the same entry points.

## Decision discipline

- `Accepted`: backed by a checked-in decision record or product specification.
- `Proposed`: useful initial direction, not yet proven by implementation.
- `Hypothesis`: must be validated by a named benchmark or experiment.
- `Open`: requires a product or engineering decision before dependent work.

Do not silently promote a hypothesis to an accepted constraint. Record benchmark
evidence and update the owning document.
