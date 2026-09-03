# V1.1: Reproducible end-to-end benchmark harness

Status: Active
Owner: Unassigned
Created: 2026-09-03

## Outcome

Produce one machine-readable benchmark artifact that ties repeated packaged
DepthSBS runs to their source revision, environment, model, resolved mode,
input/output media contract, and measured end-to-end throughput.

This is the first V1.1 observability slice. It establishes the outer benchmark
envelope before per-stage timing is added to the worker.

## Protocol

- Use the built portable `DepthSBS.exe`, not an in-process function call.
- Discard one warm-up run.
- Execute at least five measured runs.
- Use a unique output and status file for every run.
- Reject any run that does not end with `complete` or whose output contract
  differs from the input cadence, expected full-SBS geometry, or audio policy.
- Retain individual elapsed time, processing fps, output bytes, and final status.
- Report median and range; do not select the fastest run as the result.

## Recorded environment

- timestamp, commit, branch, and dirty-worktree flag;
- Windows version;
- GPU, driver, VRAM, and compute capability;
- package build manifest including model checksum, TensorRT, and FFmpeg;
- input checksum and FFprobe media description;
- selected mode and resolved policy;
- every raw measured run and aggregate median/min/max.

## Reproduction

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/benchmark-v1.ps1 `
  -Input out/media-smoke/fixture-720p30.mp4 `
  -Mode performance `
  -Runs 5
```

Artifacts are written under `out/benchmarks/` and remain outside Git by
default. Reviewed summaries and corpus manifests may be committed separately.

## Next gate

Add bounded per-stage samples for decode, preprocess, TensorRT, temporal,
stereo, encode write, mux, and total frame time. The worker must emit copy,
queue, synchronization, and VRAM counters before V1.1 is complete.
