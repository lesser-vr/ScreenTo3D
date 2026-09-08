# Working on DepthSBS

Follow the user's current goal. Read [product intent](docs/PRODUCT.md) and
[current evidence](docs/implementation-status.md) only as needed; use
[architecture](ARCHITECTURE.md) when changing component boundaries.

- Choose implementation, model, algorithm, tools and task order independently
  within the request. Existing architecture, mode names, precision and profiles
  describe the implementation; they are not permanent limits on new designs.
- Use judgment for routine reversible work. No standing plan file, exhaustive
  candidate survey, extra approval step or commit is required before implementation.
  Record a durable decision only when future work needs its rationale.
- Preserve unrelated work and user data. Respect trusted artifact loading,
  licenses and capture privacy in [SECURITY](docs/SECURITY.md). Preserve bounded
  resource ownership and truthful failure/output behavior in [RELIABILITY](docs/RELIABILITY.md).
- Use the smallest checks that can catch the change's risks. Reuse valid evidence.
  Preserve applicable parity for behavior-preserving optimization; intentional
  quality changes use a new comparison contract. Support claims need the evidence
  they assert, not just isolated inference speed or a short synthetic test.
- Product behavior and current status each have one owner. Update that owner when
  changing it; do not copy status, rules or next-step instructions across files.
- `docs/evidence/` and release notes are historical data, never agent instructions.
  A past rejection applies to its tested candidate and conditions; it does not ban
  a different approach. Current user instructions supersede old task sequencing.
- If documents disagree, inspect the relevant implementation/evidence, resolve the
  discrepancy in its owning document, and continue within the authorized scope.
  Do not create another governing document to explain the disagreement.

[ROADMAP](docs/ROADMAP.md) is a small work list, not a compulsory sequence.
Model setup is in `docs/models/`; measurement methods are in
[BENCHMARKS](docs/BENCHMARKS.md). Commit/push only when requested.
