# V1.1 process-tree memory observations

Status: Synthetic and user short-clip smoke verified; long-media gate remains open

Plan: extend the packaged soak harness to sample worker descendants, test
process-tree selection with deterministic snapshots, and validate with existing
synthetic media. Real representative media requires a user-specified path.

Use Win32_Process PID, parent PID and creation time to select only the launched
worker and descendants present in each snapshot. Never select by name alone.
Reject a reused root PID or a child older than its apparent parent. A missing
parent can make a short-lived/orphan process unobservable; do not claim complete
coverage. Do not retain unbounded PID history or raw snapshots in memory.

Root creation timestamps are compared within one microsecond to accommodate
CIM precision, not a broad time window. Shared sample IDs tie process rows to
the totals CSV; disregard partial detail rows whose totals state is not
observed. Query failures and missing roots leave memory values blank, and an
entirely unavailable run reports null aggregate memory rather than zero.

Record per-process private bytes and working set in CSV, aggregate instantaneous
private-byte sums for the tree, and keep observation errors distinct from zero.
Working sets may share pages and are not a physical-memory total. Sampling can
miss brief subprocesses, especially probe/mux. No leak-free verdict follows
from one synthetic run. Existing worker-only fields remain backward compatible.

Reproduce with `scripts/test-v1.ps1` and `scripts/soak-v1.ps1 -SourcePath <video>`.
The soak JSON schema is now 2; conversion-worker telemetry is unchanged. The
sampler waits one second after each observation, so actual cadence also includes
CIM/query overhead. This overhead is not excluded from benchmark runtime.

## Verification (2026-09-04)

- Seven deterministic selection cases passed: descendants, missing root,
  reused root PID, rapid PID reuse, CIM precision, missing parent, and missing
  creation time. Integrated into scripts/test-v1.ps1; 21 Python tests and the
  C++ regression suite also passed. git diff --check passed.
- Short packaged conversion observed both FFmpeg processes and their console
  descendants. Root-only statistics omit substantial host-side memory.
- Five-minute synthetic 720p30 input: 9000 frames, output contract passed,
  219.788 seconds. This is one instrumented run, not a performance baseline.
- 202 tree observations, zero query errors or missing-root snapshots. Peak
  observed process count 5 (worker, two FFmpeg and two console processes).
  All 202 per-process CSV sums matched their aggregate rows.
- Sampled max private memory: tree 2175004672 bytes; descendants 929230848 bytes.
  Early tree mean (10-40 s) 1893.57 MiB; late (170-200 s) 1893.44 MiB.
  Descendant means 879.81 and 881.33 MiB respectively. The small changes do not
  establish leak freedom, and the final lower sample includes teardown.
- Evidence: `out/soak/0dd5099ace4d4ea481321d070b5e6170/result.json`, with adjacent
  process-tree-memory.csv and process-tree-totals.csv (local, excluded from Git).
- Injected query failure and empty snapshot integration tests passed with real
  short packaged conversions. Aggregates were null with unavailable coverage;
  totals CSV used blank memory values. Reproduce separately with
  `scripts/test-process-tree-observation-failure.ps1` (requires package/fixture).
  Evidence runs: `543c5e9098f04921b97530818582b469` and
  `fb4386b0a45d432ba843af61d5662804` under out/soak.
- No production pipeline or package binary changed in this slice.

## Remaining

A user-supplied 5.17-second clip passed four-mode smoke validation; see
`v1-1-user-clip-validation.md`. Longer representative footage is still needed.
Do not search unrelated user folders or substitute synthetic results for
real-media coverage.
Hour-long runs, physical device loss, unsampled/orphaned processes and concurrent
destination safety remain open. V1.1 is not declared complete.
