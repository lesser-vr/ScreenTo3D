# Quality score

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

The repository has a defined intent but no implementation evidence. A score of 2
means the expected behavior is documented, not that the product supports it.

V1 is not complete until build reproducibility, media correctness, depth/SBS
correctness, performance evidence, memory safety, and CI enforcement each reach
at least 3, with benchmark claims reaching 4 for the exact supported envelope.
