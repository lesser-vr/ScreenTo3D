# Quality score

## 2026-09-04 visual correctness update

The table below is the historical pre-implementation baseline, not a fresh audit.
Current implementation evidence lives in execution plans. User-reported stereo
contour duplication led to a forward/visibility-aware CPU correction; see
`exec-plans/active/v1-1-stereo-ghosting.md`. The supplied clip is improved in
inspected frames, but user motion/VR review, complex-background goldens and a
material CPU performance regression remain open. Do not label visual quality
accepted based on frame-count/media-contract tests.

Status: Initial baseline  
Scale: 0 absent, 1 ad hoc, 2 defined, 3 implemented, 4 verified and enforced  
Last reviewed: 2026-09-03

| Domain | Score | Evidence | Next gate |
|---|---:|---|---|
| Product mode contracts | 2 | `product-specs/processing-modes.md` | Validate fallback UX and support thresholds |
| Architecture boundaries | 2 | `ARCHITECTURE.md` | Encode boundaries in source layout and structural tests |
| Build reproducibility | 0 | No build system | Complete V1 M0 |
| Media correctness | 1 | Invariants documented | Complete timestamp/audio/atomic-output tests |
| Depth correctness | 1 | Backend contract documented | Reference tensors and deterministic engine tests |
| SBS visual correctness | 1 | Artifact categories documented | CPU/reference oracle plus golden corpus |
| Temporal stability | 1 | Cut-reset and evaluation rules documented | Implement temporal corpus and metrics |
| Performance evidence | 1 | Benchmark protocol documented | Reproducibility audit with raw results |
| Memory/resource safety | 1 | Ownership/backpressure rules documented | Pool, cancellation, leak, and OOM tests |
| Observability | 1 | Required signals documented | Structured metrics and trace export |
| Reliability | 2 | Failure policy documented | Fault-injection and recovery tests |
| Security/licensing | 2 | Threat and license gates documented | Dependency/model inventory and automated checks |
| CI enforcement | 0 | No CI | Canonical non-GPU CI and GPU benchmark runner |

## Current interpretation

The initial table captured a pre-implementation state. A score of 2 meant the
expected behavior was documented, not that the product supported it. Refer to
current execution-plan evidence before interpreting these historical scores.

V1 is not complete until build reproducibility, media correctness, depth/SBS
correctness, performance evidence, memory safety, and CI enforcement each reach
at least 3, with benchmark claims reaching 4 for the exact supported envelope.
