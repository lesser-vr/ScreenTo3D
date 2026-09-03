# Core beliefs

Status: Accepted as initial project principles  
Last reviewed: 2026-09-03

1. **End-to-end performance is the product.** Model inference time alone does not
   determine whether video conversion is realtime.
2. **Temporal stability is part of quality.** A sharper per-frame depth map can
   be worse for video if it flickers or pumps.
3. **Modes are promises, not model names.** Models and kernels may change while
   the user-visible tradeoff remains stable.
4. **Copies are guilty until profiled innocent.** The design aims for a GPU-resident
   hot path, and traces must show where transfers and synchronization remain.
5. **Correctness precedes overlap.** Establish a deterministic serial oracle,
   then add bounded concurrency while comparing output and timestamps.
6. **Backpressure is a feature.** Offline conversion preserves frames and bounds
   memory instead of hiding overload through drops.
7. **Scene cuts are hard temporal boundaries.** No cached geometry crosses them.
8. **Observability ships with the pipeline.** Every stage is timed and every
   benchmark records enough provenance to reproduce the result.
9. **Fallbacks are product decisions.** Changing backend, precision, resolution,
   or cadence must be visible and testable.
10. **Licensing shapes architecture.** A technically superior model cannot be a
    default distributable backend if its terms do not permit the intended use.
11. **Simple, inspectable components beat opaque convenience.** Abstractions must
    expose ownership, synchronization, errors, and performance costs.
12. **Quality debt is collected continuously.** New artifacts or architectural
    exceptions are recorded with an owner and exit criterion, not normalized as
    precedent.
