# Technical-debt tracker

Only concrete, accepted debt belongs here. Each entry needs evidence, an owner,
an exit criterion, and a target milestone. Hypotheses and future ideas belong in
design documents or execution plans.

| ID | Area | Debt | Evidence | Owner | Exit criterion | Target |
|---|---|---|---|---|---|---|
| TD-001 | Toolchain | Dependency versions and supported driver/GPU matrix are not pinned | Repository has documentation only | Unassigned | Reproducible M0 build and capability manifest | V1 M0 |
| TD-002 | Media | Audio policy and atomic output strategy are open | Architecture open decisions | Unassigned | Product contract plus end-to-end tests | V1 M1 |
| TD-003 | Stereo | Baseline SBS algorithm and correctness oracle are open | Architecture open decisions | Unassigned | Accepted design and golden fixtures | V1 M3 |
| TD-004 | Licensing | Distribution plan for non-Apache model weights is unresolved | DA2 variant licenses differ | Unassigned | Reviewed packaging/download policy | Before public release |

When an item is resolved, remove it in the same change that records the durable
decision or verification evidence. Completed execution plans preserve history.
