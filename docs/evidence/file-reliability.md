# File lifecycle and telemetry

Historical evidence by recorded checkpoint. Current support is in
[implementation status](../implementation-status.md).

## Records

- [v1-1-cleanup](#record-plan-v1-1-cleanup)
- [v1-1-cuda-job-failures](#record-plan-v1-1-cuda-job-failures)
- [v1-1-cuda-lifecycle](#record-plan-v1-1-cuda-lifecycle)
- [v1-1-lifecycle-soak](#record-plan-v1-1-lifecycle-soak)
- [v1-1-process-tree-memory](#record-plan-v1-1-process-tree-memory)
- [v1-1-resource-telemetry](#record-plan-v1-1-resource-telemetry)
- [v1-1-stage-telemetry](#record-plan-v1-1-stage-telemetry)
- [v1-1-user-clip-validation](#record-plan-v1-1-user-clip-validation)

<a id="record-plan-v1-1-cleanup"></a>
## v1-1-cleanup

Checkpoint date recorded in source: 2026-09-04.

> Recorded outcome: Cleanup slice verified; physical device-loss and longer stress tests open

> Inspection found that a constructor failure after the first cudaMalloc could
> leak that allocation, and a failed cudaFree could skip remaining cleanup.
> Pipeline pipes also lacked explicit finally-close and cancellation was checked
> only inside the frame loop.

> Do not claim CUDA device-loss recovery from mocks or leak freedom from sampled
> global VRAM. Failed CUDA release attempts are surfaced, not silently retried.
> Cancel remains cooperative: blocking native calls finish before the next check.

### Changes and verification (2026-09-04)

> - Partial backend initialization now invokes cleanup. Runtime/context references
>   are owned explicitly and dropped on close. A failed release does not skip
>   the other resources, and repeated close does not retry uncertain handles.
> - Pending submissions are synchronized before error-path teardown. Normal
>   completed inference incurs no extra teardown synchronization. Original errors
>   retain cleanup details in notes; worker error events include these notes.
> - Process handles/pipes and temporary files are cleaned in finally. Completion
>   is emitted after successful cleanup, not before it. Cancellation is checked
>   before startup, after frame processing and before/after mux.
> - Publishing uses replacement without first deleting the old output.
> - Python unit tests: 21 passed, including seven pipeline-failure subcases;
>   C++ regression suite and git diff --check passed.
> - Real GPU/source-path smoke: three cycles of success, mid-frame-loop cancel,
>   injected inference error and invalid input (12 jobs in one process). All
>   children exited, pipes closed, temporaries removed and previous outputs
>   preserved on failure. Device-global used VRAM after each job was 1800863744
>   bytes; this is not proof of zero leaks or physical device-loss recovery.
> - Source smoke uses the packaged model/FFmpeg assets with current source code.
>   Its artifact is `out/cleanup/repeat-q7sqacvt/result.json`.
> - Portable package rebuilt. Warmup plus five measured successful conversions
>   passed media/resource contracts: `out/benchmarks/v1-performance-20260904T015733Z.json`.
> - Packaged cancellation passed after three frames: exit 2, cancelled event,
>   no complete event or temporary output, prior output hash unchanged.
>   Evidence: `out/cleanup/package-4cefe9ae5ff24385b71f5796ad298f3a/events.jsonl`.

### Reproduction

> ```powershell
> powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test-v1.ps1
> powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test-v1-cleanup.ps1
> powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test-v1-cancel.ps1
> ```

> The packaged cancellation test defaults to the five-minute fixture from
> [file-reliability.md](file-reliability.md#record-plan-v1-1-lifecycle-soak); use SourcePath to choose another sufficiently long
> input. Artifacts are retained under out/cleanup. Timeout stops only the test's
> launched worker tree. Do not run the GPU smoke with Python optimization enabled
> because it uses assertions for test gates.


<a id="record-plan-v1-1-cuda-job-failures"></a>
## v1-1-cuda-job-failures

> Recorded outcome: Job failure gate and dependency audit passed; CPU remains the default

> The diagnostic previously closed its GPU owner after convert_video returned,
> which was too late to prevent publication if GPU cleanup failed. Move optional
> projection ownership inside the pipeline's backend scope so close precedes mux
> and publication. Default CPU behavior stays unchanged; no implicit GPU fallback.
> Exercise success, cancel, projection-run failure, inference failure after GPU
> use, creation failure and close failure with prior-output sentinels. Audit native
> DLL dependencies and a PATH-isolated load/run. This is not a release licensing
> or clean-machine certification; package and GPU architecture support stay gated.

### Implementation and verification

> `convert_video` accepts an explicit internal projection_factory. The owner is
> entered inside the backend ExitStack and closes before depth-engine teardown,
> mux and publication. StereoSynthesizer uses the supplied projector; omitted
> factory retains CPU. Experimental adapter exposes separate completed-call copy
> and buffer counters. No GUI/worker argument enables CUDA yet.

> - Three cycles x six scenarios pass: success, cancel after actual GPU work,
>   injected projection status failure, depth inference failure after GPU work,
>   creation failure, and close failure. Sentinels survive every failure; no false
>   completion or temporary files remain; child processes/pipes and handles close.
>   Close failure is injected AFTER a real free, not a real driver free failure.
>   Report: out/cuda-job-cleanup/ee70d1328a9c4cf3a032f47974c99ae4/report.json.
>   Device-global used bytes are 1802960896 after all 18 scenarios. This is sampled
>   single-device evidence, not proof of device-loss recovery or leak freedom.
> - 57 Python tests plus process-tree and C++ suite pass. Three new non-GPU unit
>   tests enforce close-before-mux/publication and prior-output preservation.
> - Full clip through new ownership API: 248 CPU/GPU eye comparisons pass, and
>   decoded complete-video SHA256 is a04f86c2e6169bf36eb6603c7f7dc08ce4fb33da39ad84877df4ec4b3b7547c7
>   for both CPU and CUDA. Evidence: out/cuda-video-experiment/
>   45dca6e9394f4bac96e94953117307f0/report.json and adjacent videos.
>   Projection telemetry: 14125056 persistent device bytes, 1751506944 H2D bytes,
>   477683712 D2H bytes, 248 stream synchronizations. These are explicit completed
>   projection calls only; depth/FFmpeg counters remain separate. Not zero-copy.


<a id="record-plan-v1-1-cuda-lifecycle"></a>
## v1-1-cuda-lifecycle

> Recorded outcome: Persistent diagnostic connected and verified; release stays on CPU

### Implementation and evidence

> - Context owns five fixed-size GPU buffers and a private stream. Calls perform
>   no device allocation. The creating CUDA device is recorded; run rejects a
>   changed active device, cleanup selects the owning device then restores the
>   caller's device. Python enforces one owner thread and explicit close/context
>   management. Cross-device execution is not validated on this single-GPU host.
> - Pending transfers are drained before a failed native run returns to Python.
>   Wrapper errors close the context, preserve the original failure and attach
>   cleanup errors. No silent CPU fallback. Repeated close does not double-free.
> - 54 Python tests, process-tree and C++ suite pass. Five new fake-library owner
>   tests cover closed handles, invalid arrays, run/cleanup failures, exception
>   priority and wrong-thread rejection.
> - Real GPU: 20 create/use/close cycles and 60 injected partial-allocation
>   failures (ten at each of six stages) pass. Observed device-global memory
>   after cleanup is 1666646016 bytes throughout. Report:
>   out/cuda-projection-spike/lifecycle-ac420a310a29493fa5e271a5ed0f9dc9.json.
>   Actual device loss/failed CUDA free is not simulated; no leak-free guarantee.
> - Existing 114 spatial exact-pixel checks pass on the final DLL:
>   out/cuda-projection-spike/validation-5aed57c11f124d4abea47e09eacd57d4.json.
> - Full user clip via explicit diagnostic adapter: 248 exact eye checks over
>   124 frames. Output CPU and CUDA decoded-video SHA256 both equal
>   a04f86c2e6169bf36eb6603c7f7dc08ce4fb33da39ad84877df4ec4b3b7547c7.
>   Report and videos: out/cuda-video-experiment/d0d9482664014e53825339a2b48b0697/.
>   Each CUDA eye is compared to CPU during conversion, so total job time includes
>   oracle overhead and is not a speed benchmark. GPU call totals include initial
>   creation/validation/transfers/sync; other pipeline stages remain CPU/reference.

> Reproduce build-cuda-projection-spike.ps1, test_cuda_projection_lifecycle.py,
> test_cuda_projection_spike.py, then run_cuda_video_experiment.py --input <clip>.
> Development Python/TensorRT paths are required, using bundled model/media assets.
> Experimental logs explicitly mark the override; standard depth counters do not
> include projection copies. No zero-copy or complete GPU telemetry claim.


<a id="record-plan-v1-1-lifecycle-soak"></a>
## v1-1-lifecycle-soak

Checkpoint date recorded in source: 2026-09-04.

> Recorded outcome: Lifecycle slice and five-minute smoke verified; longer soak gates remain

### Reproduction

> Generate an exact-CFR extended fixture (do not stream-copy loop A/V clips,
> because container/audio padding can introduce timestamp gaps):

> ```powershell
> ffmpeg -n -v error -f lavfi -i testsrc2=size=1280x720:rate=30 -f lavfi -i sine=frequency=440:sample_rate=48000 -t 300 -c:v h264_nvenc -preset p1 -b:v 2M -pix_fmt yuv420p -c:a aac out/media-smoke/soak-cfr-720p30-300s.mp4
> powershell -NoProfile -ExecutionPolicy Bypass -File scripts/soak-v1.ps1 -SourcePath out/media-smoke/soak-cfr-720p30-300s.mp4
> ```

> Artifacts are isolated per run under `out/soak/<random-id>/`: output video,
> worker memory CSV, event JSONL and a final result with input hash, media probes,
> source revision and package manifest. Failed/timeout runs retain diagnostic
> artifacts; no success result is produced. Retention is manual.

### Results (2026-09-04)

> - Python tests: 15 passed (including fake-backend full conversion lifecycle);
>   C++ regression tests and git diff --check passed. Portable package rebuilt.
> - Initial stream-copy-loop fixture contained 8908 input frames due to timestamp
>   gaps; that exploratory run was stopped and is not accepted evidence.
> - Exact-CFR testsrc2 input: 1280x720, 30 fps, 300 seconds, 9000 frames, AAC.
>   Output: 2560x720, 9000 frames, video and audio each 300.000 seconds.
> - One Performance run: 243.436 seconds, 36.97 fps including engine startup,
>   draining and mux. This is synthetic single-run evidence, not a performance
>   baseline or a guarantee for arbitrary content.
> - Lifecycle: startup 0.301 s; setup 0.008 s; frame loop 237.299 s;
>   encode drain 0.065 s; audio mux 5.761 s. Other checkpoints under 1 ms.
> - Frame statistics retained 2048 of 9000 observations as designed.
> - Worker private-memory CSV: 242 samples. Early mean (10-40 s) 1009.23 MiB;
>   late mean (190-220 s) 1011.45 MiB, a 2.23 MiB increase. Last sample minus
>   first post-10-second sample: -11083776 bytes. Sampled maximum 1265180672
>   bytes includes startup/transients. These observations do not prove leak freedom.
> - Device-wide VRAM: 232 observations, zero probe errors; first/last/sampled max
>   all 1920401408 bytes. This excludes unsampled peaks and is not process VRAM.
> - Accepted artifact: `out/soak/b288101181a54858bc1d26764e52fae3/result.json`.
> - Short-run harness regression also passed; post-10-second memory baseline and
>   delta correctly remain null when the process ends earlier.


<a id="record-plan-v1-1-process-tree-memory"></a>
## v1-1-process-tree-memory

Checkpoint date recorded in source: 2026-09-04.

> Recorded outcome: Synthetic and user short-clip smoke verified; long-media gate remains open

> Root creation timestamps are compared within one microsecond to accommodate
> CIM precision, not a broad time window. Shared sample IDs tie process rows to
> the totals CSV; disregard partial detail rows whose totals state is not
> observed. Query failures and missing roots leave memory values blank, and an
> entirely unavailable run reports null aggregate memory rather than zero.

### Verification (2026-09-04)

> - Seven deterministic selection cases passed: descendants, missing root,
>   reused root PID, rapid PID reuse, CIM precision, missing parent, and missing
>   creation time. Integrated into scripts/test-v1.ps1; 21 Python tests and the
>   C++ regression suite also passed. git diff --check passed.
> - Short packaged conversion observed both FFmpeg processes and their console
>   descendants. Root-only statistics omit substantial host-side memory.
> - Five-minute synthetic 720p30 input: 9000 frames, output contract passed,
>   219.788 seconds. This is one instrumented run, not a performance baseline.
> - 202 tree observations, zero query errors or missing-root snapshots. Peak
>   observed process count 5 (worker, two FFmpeg and two console processes).
>   All 202 per-process CSV sums matched their aggregate rows.
> - Sampled max private memory: tree 2175004672 bytes; descendants 929230848 bytes.
>   Early tree mean (10-40 s) 1893.57 MiB; late (170-200 s) 1893.44 MiB.
>   Descendant means 879.81 and 881.33 MiB respectively. The small changes do not
>   establish leak freedom, and the final lower sample includes teardown.
> - Evidence: `out/soak/0dd5099ace4d4ea481321d070b5e6170/result.json`, with adjacent
>   process-tree-memory.csv and process-tree-totals.csv (local, excluded from Git).
> - Injected query failure and empty snapshot integration tests passed with real
>   short packaged conversions. Aggregates were null with unavailable coverage;
>   totals CSV used blank memory values. Reproduce separately with
>   `scripts/test-process-tree-observation-failure.ps1` (requires package/fixture).
>   Evidence runs: `543c5e9098f04921b97530818582b469` and
>   `fb4386b0a45d432ba843af61d5662804` under out/soak.
> - No production pipeline or package binary changed in this slice.


<a id="record-plan-v1-1-resource-telemetry"></a>
## v1-1-resource-telemetry

Checkpoint date recorded in source: 2026-09-04.

> Recorded outcome: Resource telemetry slice verified; V1.1 remains active

### Measurement contract

> CUDA copy bytes are submitted payload bytes, not profiled bus traffic. Counters
> exclude TensorRT internal copies and FFmpeg/NVENC internal transfers. Pipeline
> pipe bytes are host payload bytes, not GPU transfers. Zero-copy is false.

> VRAM is device-wide used/total bytes from cudaMemGetInfo, potentially influenced
> by other processes. Its sampled maximum is NOT an exact process peak, does not
> capture engine-build transients, and is not a leak test. Explicit input/output
> buffer allocation size is reported separately; it excludes TensorRT workspace.
> Memory probe failure is visible as an error count, never a false zero reading,
> and must not fail an otherwise valid conversion. No additional CUDA synchronize
> is introduced for memory sampling.

> The Python worker processes one frame at a time without an application work
> queue. That is a declared scheduling contract, NOT a measurement of FFmpeg,
> CUDA, OS pipe or encoder internal buffering.

> Startup/drain/mux timing and a five-minute resource smoke test are now verified
> in [file-reliability.md](file-reliability.md#record-plan-v1-1-lifecycle-soak). Longer resource stability tests, whole-pipeline GPU
> profiling and native queue instrumentation remain open.

### Verification (2026-09-04)

> - 12 Python unit tests passed, including CUDA submission/synchronization
>   failures, VRAM probe failure/recovery, throttling and 10000 constant-space
>   observations. C++ regression suite and git diff --check passed.
> - Portable package rebuilt. Performance warmup plus five measured 720p/60-frame
>   runs passed output and resource-counter contracts. Each run completed 30
>   inferences, 30 H2D and 30 D2H submissions, and 30 stream synchronizations.
>   Payloads: H2D 96596640 bytes, D2H 32198880 bytes; host decode pipe 165888000
>   bytes and host encode pipe 331776000 bytes. VRAM probes had no errors.
> - Balanced, Video Quality and Offline Quality each passed a single packaged
>   smoke run with cadence-derived counters. These are not performance baselines.
> - Performance raw evidence: `out/benchmarks/v1-performance-20260904T012732Z.json`.
>   Other mode artifacts end in `20260904T012738Z`, `20260904T012742Z`, and
>   `20260904T012745Z`, respectively. Artifacts are local and excluded from Git.
> - Last measured Performance run sampled device-wide used VRAM at 1920401408
>   bytes; explicit backend I/O buffers are 4293184 bytes. Do not interpret the
>   difference as TensorRT usage or infer absence of leaks from three samples.


<a id="record-plan-v1-1-stage-telemetry"></a>
## v1-1-stage-telemetry

Checkpoint date recorded in source: 2026-09-04.

> Recorded outcome: Stage timing slice verified; broader V1.1 remains active

> Each stage retains its latest 2048 samples. Count, mean and maximum cover the
> whole conversion; percentiles describe only that trailing window. All times
> are wall-clock milliseconds. Decode-read and encode-write include pipe waiting,
> not isolated codec timings. Depth includes transfers and synchronization.
> Temporal and stereo currently share one method and are measured together.
> Frame total excludes startup, encoder drain and audio mux; existing end-to-end
> elapsed time remains the throughput denominator. This does not establish
> zero-copy or a product frame-rate target.

> Resource counters and sampled device-memory observations are now implemented;
> see [file-reliability.md](file-reliability.md#record-plan-v1-1-resource-telemetry). Startup/drain/mux breakdown and an initial
> five-minute run are verified in [file-reliability.md](file-reliability.md#record-plan-v1-1-lifecycle-soak). Internal queue
> profiling, repeated cleanup and longer resource validation remain open.

### Verification (2026-09-04)

> - Python unit tests: 6 passed; C++ regression suite: passed.
> - Portable package rebuilt with telemetry.
> - Performance mode, 720p/60 frames: one warmup and five measured runs passed
>   existing output geometry/frame/audio gates. Every run reported 60 frame
>   samples and 30 inference samples, consistent with cadence two.
> - End-to-end median 33.816 fps, range 33.009-33.953 fps. This short fixture
>   validates instrumentation, not sustained product performance.
> - Raw evidence: `out/benchmarks/v1-performance-20260904T011708Z.json`
>   (local artifact, excluded from Git).


<a id="record-plan-v1-1-user-clip-validation"></a>
## v1-1-user-clip-validation

Checkpoint date recorded in source: 2026-09-04.

> Recorded outcome: Four-mode smoke passed; long-media and visual quality gates remain open
> Date: 2026-09-04

> Performance, Balanced, Video Quality and Offline Quality each completed using
> the packaged application and process-tree soak harness. All outputs contained
> 2112x608 video, 124 frames at 24 fps, and one audio stream. Process-tree probes
> reported no errors (3-4 samples per run). The clip is too short to establish
> memory stability, and single-run timings are not performance baselines.

> Output audio duration was 5.152000 seconds in every mode, approximately 15 ms
> shorter than the input audio and 14.7 ms shorter than output video. Audio
> presence is verified, not sample-exact audio preservation or perceptual sync.
> Visual stereo comfort/depth quality has not been accepted by this smoke test.

> Local result directories under out/soak (each has result.json and output.mp4):

> - Performance: 560b5ec271d048819bd0fa804f00fcae
> - Balanced: 4d54d712314645f5b5d99776ec1dceed
> - Video Quality: e416e268d3a242a2a71bb54b91334857
> - Offline Quality: 2e10a2f7ce4a4e8cb0bd3826dd229ea1
