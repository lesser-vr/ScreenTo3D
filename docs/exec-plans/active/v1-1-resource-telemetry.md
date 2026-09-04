# V1.1 resource telemetry

Status: Resource telemetry slice verified; V1.1 remains active

## Plan

1. Count successful explicit CUDA copy submissions and stream synchronizations
   at their backend call sites, not by multiplying presumed inference cadence.
2. Sample cudaMemGetInfo after engine initialization, at most once per second
   during inference, and at finalization; retain aggregates only.
3. Expose resource statistics in completion telemetry and existing benchmark
   artifacts. Record CPU pipe byte counts and the synchronous worker contract.
4. Test counters with mocked CUDA, unavailable memory observations, and a
   packaged warmup plus five measured runs.

## Measurement contract

CUDA copy bytes are submitted payload bytes, not profiled bus traffic. Counters
exclude TensorRT internal copies and FFmpeg/NVENC internal transfers. Pipeline
pipe bytes are host payload bytes, not GPU transfers. Zero-copy is false.

VRAM is device-wide used/total bytes from cudaMemGetInfo, potentially influenced
by other processes. Its sampled maximum is NOT an exact process peak, does not
capture engine-build transients, and is not a leak test. Explicit input/output
buffer allocation size is reported separately; it excludes TensorRT workspace.
Memory probe failure is visible as an error count, never a false zero reading,
and must not fail an otherwise valid conversion. No additional CUDA synchronize
is introduced for memory sampling.

The Python worker processes one frame at a time without an application work
queue. That is a declared scheduling contract, NOT a measurement of FFmpeg,
CUDA, OS pipe or encoder internal buffering.

Remaining after this slice: startup/drain/mux timing and long-video resource
stability tests; whole-pipeline GPU profiling and native queue instrumentation.

## Verification (2026-09-04)

- 12 Python unit tests passed, including CUDA submission/synchronization
  failures, VRAM probe failure/recovery, throttling and 10000 constant-space
  observations. C++ regression suite and git diff --check passed.
- Portable package rebuilt. Performance warmup plus five measured 720p/60-frame
  runs passed output and resource-counter contracts. Each run completed 30
  inferences, 30 H2D and 30 D2H submissions, and 30 stream synchronizations.
  Payloads: H2D 96596640 bytes, D2H 32198880 bytes; host decode pipe 165888000
  bytes and host encode pipe 331776000 bytes. VRAM probes had no errors.
- Balanced, Video Quality and Offline Quality each passed a single packaged
  smoke run with cadence-derived counters. These are not performance baselines.
- Performance raw evidence: `out/benchmarks/v1-performance-20260904T012732Z.json`.
  Other mode artifacts end in `20260904T012738Z`, `20260904T012742Z`, and
  `20260904T012745Z`, respectively. Artifacts are local and excluded from Git.
- Last measured Performance run sampled device-wide used VRAM at 1920401408
  bytes; explicit backend I/O buffers are 4293184 bytes. Do not interpret the
  difference as TensorRT usage or infer absence of leaks from three samples.
