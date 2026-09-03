# V1 native pipeline foundation

Status: Active planning; implementation not started  
Owner: Unassigned  
Created: 2026-09-03

## Outcome

Deliver an instrumented CLI vertical slice that converts a short supported
H.264/H.265 2D input into valid SBS H.264/H.265 output on an NVIDIA GPU, using a
DA2 Small or Base TensorRT backend, and produces reproducible stage and end-to-end
benchmark artifacts.

This milestone proves architecture and performance. It does not promise a GUI,
all four production-ready modes, live playback, or final visual parity with iw3.

## Repository facts

- The repository began empty on 2026-09-03.
- Product, architecture, reliability, security, and benchmark documents exist.
- No build system, source code, fixtures, CI, or dependency lock is present yet.
- Exact dependency versions, minimum GPU, and media compatibility envelope remain
  open and must be established by the compatibility spike.

## Milestones

### M0 — Reproducible toolchain and capability probe

- Select CMake/toolchain/dependency strategy and pin versions.
- Build a small executable that reports GPU, driver, CUDA, TensorRT, NVDEC/NVENC,
  codec, and memory capabilities as structured JSON.
- Add canonical configure/build/test commands and CI for non-GPU checks.
- Record model-license and redistribution implications before downloading or
  packaging weights.

Exit: a clean checkout can build the probe using documented steps, and failure
messages identify missing/incompatible components.

### M1 — Media correctness skeleton

- Probe/demux input and define validated media descriptors.
- Implement timestamp-preserving decode/encode/mux with a synthetic passthrough or
  deterministic SBS test pattern.
- Decide and test audio policy and atomic output publication.
- Add generated 1080p fixtures with cuts and non-trivial PTS.

Exit: outputs decode, have correct duration/frame order, and cancel without leaving
a final-looking partial file.

### M2 — Depth backend vertical slice

- Define the model-independent backend and engine provenance contract.
- Implement reproducible DA2 Small TensorRT engine creation/loading.
- Add reference preprocessing/postprocessing tests and depth polarity/range checks.
- Measure startup, warmup, inference, memory, and copies independently.

Exit: identical inputs produce deterministic depth within declared tolerance, and
incompatible engines fail before frame processing.

### M3 — Baseline SBS synthesis

- Implement a deterministic symmetric SBS reference and one CUDA path.
- Cover eye order, convergence, divergence, borders, thin structures, holes, and
  output geometry with synthetic fixtures.
- Compare reference and CUDA outputs with documented tolerance.

Exit: the end-to-end CLI emits correct SBS video and attributes time to every stage.

### M4 — Bounded GPU pipeline

- Introduce resource pools, bounded queues, backpressure, and cancellation.
- Minimize and count CPU/GPU copies.
- Overlap decode, compute, and encode only after the serial oracle passes.
- Run leak, repeated-open, corruption, and out-of-memory error-path tests.

Exit: steady state has bounded memory, no unexpected per-frame allocation, and
pipeline output matches the oracle.

### M5 — Benchmark and V1 decision

- Run the defined corpus on RTX 4090 and RTX 5090 where available.
- Compare against an equivalently configured iw3 baseline.
- Publish raw results, environment manifests, traces, and an interpreted summary.
- Decide the supported Performance/Balanced envelope and prioritize the limiting
  stage for V2.

Exit: support claims are evidence-backed or explicitly rejected; the quality score,
technical debt, and next execution plan are updated.

## Planned verification commands

The build system does not exist yet. M0 must replace this section with exact
copy-pasteable commands for configure, build, unit tests, fixture generation,
end-to-end tests, benchmarks, and trace inspection. CI must call those entry points.

## Decisions

- 2026-09-03: Start with an instrumented CLI and one vertical slice. This keeps
  performance, ownership, and media correctness visible before UI work.
- 2026-09-03: Treat four-mode throughput numbers as hypotheses until complete
  pipeline benchmarks satisfy `benchmark-methodology.md`.
- 2026-09-03: Use DA2 Small/Base as V1 candidates; defer oVDA/VDA/DA3 integration
  until the backend contract and temporal-quality corpus exist.

## Risks

- Direct NVDEC/CUDA/TensorRT/NVENC interop may impose hidden format conversions or
  synchronization; preserve a correct reference path and instrument every copy.
- Model licensing may prevent redistribution or commercial defaults, especially
  DA2 Base/Large variants.
- 4K SBS output dimensions and encode format may exceed a GPU/codec/profile limit;
  capability resolution must use final output geometry.
- Temporal quality cannot be inferred from spatial metrics or throughput alone.
- Comparing with iw3 may be misleading unless model, stereo, and encoder settings
  are held equivalent and differences are disclosed.

## Progress

- [x] Establish repository knowledge base and initial contracts.
- [ ] Complete M0 toolchain and capability probe.
- [ ] Complete M1 media correctness skeleton.
- [ ] Complete M2 depth backend vertical slice.
- [ ] Complete M3 SBS synthesis.
- [ ] Complete M4 bounded GPU pipeline.
- [ ] Complete M5 benchmark and V1 decision.
