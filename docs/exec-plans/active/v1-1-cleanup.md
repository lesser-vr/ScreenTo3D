# V1.1 repeated cleanup and failure paths

Status: Cleanup slice verified; physical device-loss and longer stress tests open

Inspection found that a constructor failure after the first cudaMalloc could
leak that allocation, and a failed cudaFree could skip remaining cleanup.
Pipeline pipes also lacked explicit finally-close and cancellation was checked
only inside the frame loop.

Plan: make backend construction exception-safe, attempt all owned releases,
retain the primary error, and synchronize outstanding submitted work on error.
Close all process pipes and check cancellation around finalization; preserve
existing output if atomic replacement fails. Add fault-injection tests, then
repeat successful jobs and cancellation using the actual GPU/FFmpeg path.

Do not claim CUDA device-loss recovery from mocks or leak freedom from sampled
global VRAM. Failed CUDA release attempts are surfaced, not silently retried.
Cancel remains cooperative: blocking native calls finish before the next check.

## Changes and verification (2026-09-04)

- Partial backend initialization now invokes cleanup. Runtime/context references
  are owned explicitly and dropped on close. A failed release does not skip
  the other resources, and repeated close does not retry uncertain handles.
- Pending submissions are synchronized before error-path teardown. Normal
  completed inference incurs no extra teardown synchronization. Original errors
  retain cleanup details in notes; worker error events include these notes.
- Process handles/pipes and temporary files are cleaned in finally. Completion
  is emitted after successful cleanup, not before it. Cancellation is checked
  before startup, after frame processing and before/after mux.
- Publishing uses replacement without first deleting the old output.
- Python unit tests: 21 passed, including seven pipeline-failure subcases;
  C++ regression suite and git diff --check passed.
- Real GPU/source-path smoke: three cycles of success, mid-frame-loop cancel,
  injected inference error and invalid input (12 jobs in one process). All
  children exited, pipes closed, temporaries removed and previous outputs
  preserved on failure. Device-global used VRAM after each job was 1800863744
  bytes; this is not proof of zero leaks or physical device-loss recovery.
- Source smoke uses the packaged model/FFmpeg assets with current source code.
  Its artifact is `out/cleanup/repeat-q7sqacvt/result.json`.
- Portable package rebuilt. Warmup plus five measured successful conversions
  passed media/resource contracts: `out/benchmarks/v1-performance-20260904T015733Z.json`.
- Packaged cancellation passed after three frames: exit 2, cancelled event,
  no complete event or temporary output, prior output hash unchanged.
  Evidence: `out/cleanup/package-4cefe9ae5ff24385b71f5796ad298f3a/events.jsonl`.

## Reproduction

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test-v1.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test-v1-cleanup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test-v1-cancel.ps1
```

The packaged cancellation test defaults to the five-minute fixture from
`v1-1-lifecycle-soak.md`; use SourcePath to choose another sufficiently long
input. Artifacts are retained under out/cleanup. Timeout stops only the test's
launched worker tree. Do not run the GPU smoke with Python optimization enabled
because it uses assertions for test gates.

## Remaining

Physical device loss and CUDA OOM integration tests remain simulated/unverified.
Blocking FFmpeg/native calls do not yet have immediate cancellation. Hour-long
representative media and concurrent jobs need separate validation; fixed sibling
temporary names still preclude safe concurrent writes to one destination.
