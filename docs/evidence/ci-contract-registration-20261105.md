# Contract registration repair — 2026-11-05

Historical repair record. Current implementation state belongs to
implementation-status.md; test commands are in BENCHMARKS.md.

## Observed failure

[Run 41968026978](https://github.com/lesser-vr/DepthSBS/actions/runs/41968026978)
at commit `40735a663557b2e45b3db4e1fa8386aacf91f1a5` failed all four Python
contract matrix jobs before executing tests. Every log reports the same 14
unclassified modules, including DA2 device-depth, model comparison, output
placement and window-icon tests. C++ build/test and real media contracts passed.
This was a test inventory failure, not evidence of a CUDA/runtime failure.
Original job logs are retained locally as `out/ci-job-127049486*.log`.

## Repair

The explicit test classification now includes all existing modules and the new
GPU interface/precision/renderer tests. The fail-closed inventory check remains;
unclassified, duplicate, missing, empty, failed or skipped required tests still
fail rather than silently disappearing from CI.

CPU-compatible tests run in the existing core/platform/profiles/quality groups.
Output placement and actual owned-window icon checks use a separate GPU-free Qt
matrix job with pinned PySide6 6.10.2. Tests importing TensorRT/CUDA/Torch remain
in the explicit prepared-local runtime group. The CPU runtime-import blocker is
unchanged. RowFlow's corrupted-library test now supplies fixture bytes instead
of depending on an untracked locally built DLL; the before-load rejection is
still asserted.

## Local verification before push

- `out/ci-cpu-contracts-20261105.json`: 309 CPU/Qt tests, no failures/errors/skips.
- `out/ci-runtime-contracts-20261105.json`: 24 prepared-local runtime tests,
  no failures/errors/skips. These are unit/ownership checks, not a new performance
  or broad hardware acceptance run.
- `out/ci-cpp-check-20261105.log`: Release configure/build and CTest pass.
- Changed Python files pass scoped Ruff E9/F with Python 3.12 as the target;
  `git diff --check` passes. An exploratory repository-wide lint also encountered
  two pre-existing unused imports outside the changed files; those are unrelated
  to the Actions failure and are not reported as repaired here.

Recent native runtime, pixel parity, throughput, UI and FPS limit evidence is
retained in the individual 2026-11-05 records rather than rerunning unrelated GPU
experiments for this test-inventory fix. No model weights, built native binaries,
private captures or local `out/` artifacts are added to Git. Final remote job
results are reported against the pushed commit in GitHub Actions.

## Clean-runner follow-up

[Run 42024853127](https://github.com/lesser-vr/DepthSBS/actions/runs/42024853127)
cleared the inventory failure and passed core/platform/quality/Qt and C++ checks.
The profiles job then exposed three previously hidden fixture problems: DA2/VDA
expected temporary paths were not normalized when the runner supplied a Windows
8.3 user alias, and the FP16 trial test relied on the developer's local Base model
directory existing. The expected fixture paths now resolve canonically, and the
trial test creates its own isolated checkout/model directory and checks both
accepted and rejected directories. Production path validation remains unchanged.
