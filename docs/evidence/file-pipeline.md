# File pipeline and engine foundations

Historical evidence by recorded checkpoint. Current support is in
[implementation status](../implementation-status.md).

## Records

- [on-device-engine-build](#record-result-on-device-engine-build)
- [m1-media-reference](#record-plan-m1-media-reference)
- [m2-da2-small-engine](#record-plan-m2-da2-small-engine)
- [m2-da2-small-inference](#record-plan-m2-da2-small-inference)
- [m2-da2-small-reference-oracle](#record-plan-m2-da2-small-reference-oracle)
- [m2-on-device-engine](#record-plan-m2-on-device-engine)
- [model-backend-boundary](#record-plan-model-backend-boundary)
- [v1-1-benchmark-harness](#record-plan-v1-1-benchmark-harness)
- [v1-1-cuda-projection-spike](#record-plan-v1-1-cuda-projection-spike)
- [v1-1-expanded-gpu-validation](#record-plan-v1-1-expanded-gpu-validation)
- [v1-1-gpu-preview](#record-plan-v1-1-gpu-preview)
- [v1-1-hevc-output](#record-plan-v1-1-hevc-output)
- [v1-user-release](#record-plan-v1-user-release)
- [m2-tensorrt11-smoke](#record-plan-m2-tensorrt11-smoke)
- [v1-foundation](#record-plan-v1-foundation)

<a id="record-result-on-device-engine-build"></a>
## on-device-engine-build

### Recorded design

> The V1 design selected target-GPU TensorRT compilation from trusted ONNX and a validated local cache. Cache identity covered model hash, runtime/device, shapes, precision and preprocessing contract. Atomic publication, corrupt-cache rejection and a bounded rebuild attempt protected partial/invalid entries. This was a design decision, not broad hardware or installer certification; engine implementation evidence is recorded below.


<a id="record-plan-m1-media-reference"></a>
## m1-media-reference

### Outcome

> Establish a deterministic, generated-media reference path before native FFmpeg,
> NVDEC, and NVENC integration. The oracle validates container finalization,
> dimensions, frame count, duration, audio preservation, and atomic publication.
> It is not a performance or zero-copy path.

### Current implementation

> `scripts/media-smoke.ps1`:

> 1. generates two one-second 1280x720@30 H.264 shots with a hard cut;
> 2. adds a two-second 48 kHz AAC tone;
> 3. creates a deterministic duplicate-eye 2560x720 SBS reference;
> 4. encodes video with NVENC and copies audio;
> 5. probes the temporary output with ffprobe;
> 6. validates one video stream, one audio stream, dimensions, 60 frames, and
>    approximately two seconds of duration;
> 7. writes a machine-readable report and only then publishes the final output.

> Canonical command:

> ```powershell
> powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\media-smoke.ps1
> ```

> Generated artifacts live under `out/media-smoke/` and are ignored by git.

### Limitations

> - FFmpeg is an executable dependency discovered on `PATH`; native headers and
>   libraries are not installed in the current environment.
> - The SBS image duplicates the source into both eyes and does not estimate depth.
> - Filtering is not GPU-zero-copy and cannot support performance claims.
> - The first implementation is Windows PowerShell-only.


<a id="record-plan-m2-da2-small-engine"></a>
## m2-da2-small-engine

### Outcome

> Build a TensorRT 11 engine from a pinned Depth Anything V2 Small FP16 ONNX on
> the user's GPU. The model and generated engine remain local cache artifacts and
> are not committed.

### Pinned artifact

> - Upstream: `depth-anything/Depth-Anything-V2-Small`
> - ONNX source: `onnx-community/depth-anything-v2-small`
> - Revision: `4472b7362082ad9968fee890ca0f1e5aca36b93d`
> - File: `onnx/model_fp16.onnx`
> - SHA-256: `2df6223f206b5164e21f664ace61dabeb9bb6a49b8b5a3e00510b4807d0f5b04`
> - License: Apache-2.0

> The community ONNX is an integration artifact, not the final provenance
> boundary. Before release, compare its output against the official checkpoint or
> replace it with an internally exported and validated ONNX.

### Validated result

> On TensorRT 11.2.1 and an RTX 5090 (SM 12.0), the model parsed and generated a
> strongly typed engine successfully. The observed engine size was about 51.1 MiB
> and engine generation took about 19.8 seconds.

> TensorRT warned that FP16 LayerNorm reductions after self-attention may
> overflow. Release acceptance therefore requires numerical comparison with the
> official model on a representative image corpus. An opset 17 export using a
> normalization operator is a candidate mitigation if the comparison fails.

### Reproduction

> Run:

> ```powershell
> powershell -NoProfile -ExecutionPolicy Bypass -File scripts/da2-small-engine-smoke.ps1
> ```

> The script verifies byte length and SHA-256 before building. It does not claim
> inference correctness; `inference_validated` remains false until the numerical
> oracle is implemented.


<a id="record-plan-m2-da2-small-inference"></a>
## m2-da2-small-inference

### Reproduction

> ```powershell
> powershell -NoProfile -ExecutionPolicy Bypass -File scripts/da2-small-inference-smoke.ps1
> ```


<a id="record-plan-m2-da2-small-reference-oracle"></a>
## m2-da2-small-reference-oracle

### Validated observation

> On the deterministic RGB gradient fixture:

> - MAE: 0.00350
> - RMSE: 0.00457
> - maximum absolute error: 0.01802
> - mean relative error: 0.200 percent
> - correlation: 0.9999867

> These results clear the current error budget. They cover one synthetic input,
> so a real-image corpus and direct official-checkpoint comparison are still
> required before release.

### Reproduction

> Install the local development dependency once:

> ```powershell
> python -m pip install --target out\python-deps -r tools\requirements-reference.txt
> ```

> Then run:

> ```powershell
> powershell -NoProfile -ExecutionPolicy Bypass -File scripts/da2-small-reference-check.ps1
> ```


<a id="record-plan-m2-on-device-engine"></a>
## m2-on-device-engine

Checkpoint date recorded in source: 2026-09-03.

### Outcome

> Build a trusted DA2 Small ONNX model into a GPU-specific TensorRT FP16 plan on
> first use, validate it, publish it atomically to the per-user cache, and reuse it
> on the next run.

> The governing design is [file-pipeline.md](file-pipeline.md#record-result-on-device-engine-build).

### Local prerequisite result

> Validated on 2026-09-03:

> - TensorRT 11.2.1.2 Windows SDK at `C:\TensorRT\TensorRT-11.2.1.2`;
> - `trtexec.exe`, `NvInfer.h`, `nvinfer_11.lib`, `nvonnxparser_11.lib` present;
> - `nvinfer_11.dll` and `nvonnxparser_11.dll` load when the SDK `bin` directory is
>   applied to the current process PATH;
> - RTX 5090 builder resource (`sm120`) present;
> - current Codex process predates the environment-variable change, so a process
>   restart or explicit script refresh is required.

> Canonical verification:

> ```powershell
> powershell -NoProfile -ExecutionPolicy Bypass `
>   -File .\scripts\tensorrt-check.ps1 -UpdateCurrentProcess
> ```


<a id="record-plan-model-backend-boundary"></a>
## model-backend-boundary

> Recorded outcome: First binding slice implemented and verified; second real model pending

### Results

> 76 Python tests, seven process-tree checks and C++ regression pass. Tests cover
> unavailable ID rejection, stateful full-rate guard, reset reasons, invalid depth,
> owned output buffers and start -> infer -> scene-cut reset -> infer ordering in
> the full fake pipeline. Model input preparation and engine ownership are supplied
> by the binding; DA2 keeps its existing preparation/engine. Actual output identity
> is reported separately from the mode. Stateful model output scheduling beyond
> one result per input frame remains unsupported.

> Real DA2 diagnostic on the supplied user clip completes CPU/GPU conversions and
> 248 exact pre-encode eye checks:
> `out/cuda-video-experiment/2b27c8e5306a44619d838b6ead2bfe47/report.json`.
> No speed comparison is claimed; the new owned-result copy has not been separately
> benchmarked. Existing portable executables were not rebuilt or distributed.

> Candidate intake: [vda.md](vda.md#record-result-streaming-model-candidate) identifies official VDA Small streaming as a proposed experiment, not a renamed/validated oVDA backend. The isolated real-model follow-up now passes CUDA oracle and cache/reset checks; see [vda.md](vda.md#record-plan-vda-small-oracle). No candidate is accepted as a production default.


<a id="record-plan-v1-1-benchmark-harness"></a>
## v1-1-benchmark-harness

Checkpoint date recorded in source: 2026-09-03.

### Outcome

> Produce one machine-readable benchmark artifact that ties repeated packaged
> DepthSBS runs to their source revision, environment, model, resolved mode,
> input/output media contract, and measured end-to-end throughput.

> This is the first V1.1 observability slice. It establishes the outer benchmark
> envelope before per-stage timing is added to the worker.

### Reproduction

> ```powershell
> powershell -NoProfile -ExecutionPolicy Bypass -File scripts/benchmark-v1.ps1 `
>   -Input out/media-smoke/fixture-720p30.mp4 `
>   -Mode performance `
>   -Runs 5
> ```

> Artifacts are written under `out/benchmarks/` and remain outside Git by
> default. Reviewed summaries and corpus manifests may be committed separately.


<a id="record-plan-v1-1-cuda-projection-spike"></a>
## v1-1-cuda-projection-spike

### Results

> - CUDA 13.1 rejected the default VS 2026 host compiler. Build now explicitly
>   selects installed VS 2022; no unsupported-compiler override was used.
> - Local GPU: RTX 5090, compute capability 12.0, driver 616.56. Binary targets
>   sm_120 only, with fused multiply-add disabled and round-to-nearest float32
>   quantization matching the reference. Not a general hardware support claim.
> - 114 exact-pixel checks pass: randomized dimensions and collisions, empty rows,
>   signed integer/half-pixel shifts, nearest/conservative paths and both eyes on
>   the saved real normalized/EMA depth sample. No production output changed.
> - Final 30-repeat one-eye medians at 1056x608: CPU 16.971 ms, GPU host-to-host
>   2.542 ms. GPU includes Python validation, five allocations, H2D/D2H, global
>   synchronization and frees. It does not include depth inference, temporal or
>   backdrop refinement, decoding, encoding, muxing or two-eye assembly.
> - Raw result: out/cuda-projection-spike/
>   validation-1fb9edd24f654aab91d5e1e26f4329d0.json. Includes DLL/source hashes,
>   compiler paths/version, GPU metadata and all samples. Build manifest adjacent.
> - Existing 49 Python tests, process-tree cases and C++ suite still pass.

> Reproduce with scripts/build-cuda-projection-spike.ps1 then
> v1/test_cuda_projection_spike.py using out/v1-python-deps and v1 on PYTHONPATH.
> This source is original project code, not copied SDK sample code. API reference:
> https://docs.nvidia.com/cuda/cuda-programming-guide/05-appendices/cpp-language-extensions.html


<a id="record-plan-v1-1-expanded-gpu-validation"></a>
## v1-1-expanded-gpu-validation

Checkpoint date recorded in source: 2026-09-04.

> Recorded outcome: Three-mode/1080p checks and five-minute GPU run verified; 4K conversion
> unsupported, explicit rejection implemented; broader release gates remain open

> 4K investigation: local FFmpeg/NVENC reports `Width 7680 exceeds 4096` for
> H.264 full SBS on RTX 5090. Add a conservative release boundary rejecting
> input widths above 2048 before GPU setup/output cleanup, with an actionable
> message. Do not silently resize, change codec or claim 4K support. Record the
> failed 4K gate; keep the separate 720p five-minute run moving. Rebuild preview
> only after the active soak completes and verify rejection and short regression.

> Preserve both packages. Run matched-package comparison and independent media
> validation for Balanced, Video Quality and Offline Quality on the supplied
> 124-frame clip: two diagnostics, one discarded warmup, five measured runs per
> renderer. GPU jobs run sequentially to avoid benchmark interference.

### Mode and resolution results (2026-09-04)

> The original matrix report remains failed because 4K conversion failed; do not
> rewrite that historical outcome. Completed cases and logs:
> `out/expanded-gpu-validation/9033f87fac0f47fea63b82104e7838b3/report.json`.

> Each mode below has 16 outputs (four diagnostics, two warmups, ten measured),
> exact CPU/GPU input/depth/pre-encode and decoded-output hashes, and independently
> validated media geometry/cadence/frame/audio contracts. CPU/GPU each have five
> measured repetitions after one discarded warmup; GPU work ran sequentially.

> | Mode | CPU process-wall median (range), s | GPU median (range), s | Ratio |
> |---|---|---|---|
> | Balanced | 13.572 (13.108-14.164) | 7.373 (7.210-7.592) | 1.84x |
> | Video Quality | 13.535 (13.495-13.712) | 7.469 (7.394-7.584) | 1.81x |
> | Offline Quality | 13.835 (13.685-14.454) | 7.590 (7.495-7.740) | 1.82x |

> Reports under `out/packaged-comparison/`:
> - Balanced: `832f1447b82b417c834b100dc7024342/report.json`.
> - Video Quality: `45ff4ad3372c4c73bf6facacf75852a4/report.json`.
> - Offline Quality: `77298ef9024d480789d17906af75a1f7/report.json`.

> Each has adjacent `media-validation.json`. These are short 1056x608 user-clip
> observations on RTX 5090/616.56, not sustained high-resolution performance.

> 1080p30 synthetic: four diagnostic conversions of 30 frames pass exact hashes
> and media validation, producing 3840x1080 Full SBS. Report:
> `out/packaged-comparison/8d647ebce4564f20ba0e1b9f637eee36/report.json`.

> 4K30 synthetic: first CPU-reference conversion failed with an unhelpful pipe
> OSError; original failed report:
> `out/packaged-comparison/bf910233224b43fda6051e04e744cdc1/report.json`.
> Isolated local NVENC initialization reports `Width 7680 exceeds 4096`.
> The application now applies a conservative H.264 release limit before engine
> creation; no resizing/codec substitution. The expanded script now tests 4K
> rejection explicitly instead of treating it as a supported conversion.
> Full 4K remains an open product/output-format gate.

### Extended GPU run and boundary fix

> After the original matrix stopped at 4K, the independent soak ran to completion:
> `out/soak/0b6d2597b7954a0098da49c714bb5c61/result.json`.
> Exact-CFR 1280x720/30 fps, 300 seconds, AAC: 9000 input/output frames,
> 2560x720 output, 9000 depth inferences and 18000 GPU eye calls. Elapsed 472.276 s,
> 19.057 pipeline fps; not real-time. This was one extended run, not five repeated
> sustained benchmarks. A brief failed NVENC capability probe and CPU regression
> tests ran during it; desktop workload and clocks were not controlled.

> This run used the pre-boundary-fix preview executable, whose hash is retained
> in its report. Afterward the preview alone was rebuilt with width rejection;
> the standard CPU package remains unchanged. 64 Python unit tests, seven
> process-tree tests and C++ regression tests pass.
> Packaged 4K rejection before start/progress preserves prior output:
> `out/gpu-output-limit/d48c751957034e5e951d98954eaaf04c/report.json`.
> The rebuilt preview also passes the user-clip four-mode conversion and packaged
> cancel/prior-output-preservation smoke:
> `out/gpu-preview-checks/27533a6df90246619c68a4e81ec56ad1/report.json`.


<a id="record-plan-v1-1-gpu-preview"></a>
## v1-1-gpu-preview

Checkpoint date recorded in source: 2026-09-04.

> Recorded outcome: Local preview packaged and smoke-verified; public release gates open

### Results (2026-09-04)

> - Build: `powershell -File scripts/build-v1-portable.ps1 -GpuPreview`.
>   Output: `out/gpu-preview/DepthSBS-GPU-Preview/DepthSBS-GPU-Preview.exe`.
>   CPU release was not rebuilt or replaced. Native export audit excludes
>   projection_create_injected; CUDA EULA and projection build hashes included.
> - 60 Python unit tests, seven process-tree cases and the C++ suite pass.
> - H.264 user clip: four packaged modes each emit 124 frames and 248 GPU eye
>   calls. Geometry, cadence, duration/audio presence and cancellation with prior
>   output preservation pass. Child PATH contains only Windows directories and
>   PYTHONPATH is removed. Report:
>   `out/gpu-preview-checks/2e6f7430485240029ea152e0f74637fc/report.json`.
>   One process-wall run each: Performance 8.506 s, Balanced 7.786 s,
>   Video Quality 8.028 s, Offline Quality 7.584 s. No CPU oracle runs inside
>   these workers. Not a repeated benchmark, speedup or real-time claim.
> - H.265 48-frame motion fixture: same four-mode and cancel gates pass.
>   `out/gpu-preview-checks/b1e865aecb824ff9a4240171fcd5e588/report.json`.
> - Fresh diagnostic using bundled preview DLL and dependencies: 248 CPU/GPU
>   pre-encode eye comparisons exact; both diagnostic encoded videos decode to
>   RGB24 SHA256 8f26dd3c8a3858a9a733af22d542c029d1b47bc86c3dcd14902bebcb60bc55ca.
>   `out/cuda-video-experiment/b0ccce9241f14eff95bdb2d8d5ccbddc/report.json`.
>   This diagnostic includes CPU oracle cost and is not timing evidence.

> GUI entry point is packaged and labeled; interactive GUI visual QA remains unverified in this slice. No screen capture is implemented here.

### Final-container parity limitation

> Follow-up: same-executable CPU/GPU parity now passes through final decoding in
> 16 runs; see [file-quality.md](file-quality.md#record-plan-v1-1-packaged-parity). The old discrepancy below remains
> historical evidence, not proof of a persistent CUDA projection error.

> The existing CPU package and new GPU package do NOT produce identical decoded
> video hashes on the user clip. Their Performance output PSNR is 50.233212 dB
> (FFmpeg psnr, 124 frames). GPU RGB24 hash is
> a9827ecc6a67a4fd106a99ea4422a226f0d35ca0f14ca154453f203fe31a22bc;
> CPU package hash is
> 8a9dd017d4ac554a02ed2b3777b6422fee463a3e628cf2d3f5c8d26d9321fa76.
> CPU comparison files are beside the H.264 report as cpu-package.mp4/jsonl.
> This is distinct from the exact pre-encode diagnostic oracle above. The cause
> of this packaged/development or encoding difference has not been isolated;
> do not claim packaged pixel identity or infer perceptual acceptance from PSNR.
> Matched-build pre-encode/encode parity isolation is a next gate before promoting
> this local preview to a default renderer.


<a id="record-plan-v1-1-hevc-output"></a>
## v1-1-hevc-output

Checkpoint date recorded in source: 2026-09-04.

> Recorded outcome: HEVC preview implementation and short 4K gates verified; hour-long and
> player/hardware acceptance remain open

### Reproduction

> ```powershell
> powershell -File scripts/build-v1-portable.ps1 -GpuPreview
> python v1/compare_packaged_renderers.py --input <4K clip> --output-codec hevc --diagnostics-only
> python v1/validate_packaged_comparison.py --input <4K clip> --report <comparison report>
> python v1/test_gpu_preview_package.py --input <4K clip> --output-codec hevc
> ```

> After short codec gates, an hour-long representative input can use:

> ```powershell
> powershell -File scripts/soak-v1.ps1 -SourcePath <one-hour clip> -GpuPreview -OutputCodec hevc -TimeoutSeconds 14400
> ```

> This command is a future gate, not a recorded run. A one-hour input is distinct
> from one hour of measured execution; record both, resolution and actual workload.
> Do not substitute a low-load repeated/static fixture for representative stress
> without explicitly narrowing the claim. Full 4K remains far from real-time in
> the current CPU/GPU hybrid path.

### Results (2026-09-04)

> - 68 Python tests plus seven process-tree cases and C++ regression tests pass.
>   Output-policy boundaries, invalid codec, unchanged H.264 default, HEVC encoder
>   and hvc1 tag selection, and publication are covered. GPU preview rebuilt;
>   existing CPU release not replaced. GUI now has an explicit codec selector;
>   interactive visual GUI QA is not certified by these worker tests.
> - 3840x2160/30 fps SDR synthetic input (30 frames, AAC), Performance CPU/GPU
>   two diagnostic runs each: all pre-encode hashes and decoded HEVC outputs match.
>   Output is 7680x2160, hevc/hvc1, same cadence/frame count and audio duration.
>   Decoded RGB24 hash ca8760408c087015e16c946b24981a05aa63438075d474f05ac3b05cef500d88.
>   `out/packaged-comparison/e5203074ee9348088bfc5a17397849a1/report.json`
>   and adjacent `media-validation.json`. Diagnostic timings include hashing and
>   are not a throughput benchmark.
> - Same 4K input: four GPU modes and packaged cancellation preserving prior
>   output pass: `out/gpu-preview-checks/cc0af9aa405f452893dc4412e2a7a266/report.json`.
> - H.264 user-clip four-mode and cancellation regression passes:
>   `out/gpu-preview-checks/cda621b5eeeb452884f0659222f673c2/report.json`.
> - Default H.264 still rejects 4K before work and preserves prior output:
>   `out/gpu-output-limit/6a96dd9dfe0442f2af50f8336ef452a5/report.json`.
> - HEVC soak-harness integration checked on the SHORT 30-frame 4K fixture:
>   `out/soak/c037f7102adb4ea19c3ef2d85ca168ae/result.json` (13 memory samples).
>   This checks argument/codec/resource plumbing only; it is NOT an hour-long
>   run or evidence of leak freedom. The hour-long gate has not been executed.


<a id="record-plan-v1-user-release"></a>
## v1-user-release

### Known V1 limitations

> - NVIDIA GPU and compatible driver are required.
> - Output is H.264 full SBS MP4.
> - Rotation/color HDR metadata handling is not release-complete.
> - Stereo synthesis is the deterministic CPU reference path, not zero-copy CUDA.
> - Model quality is DA2 Small for every mode; modes tune the end-to-end policy.


<a id="record-plan-m2-tensorrt11-smoke"></a>
## m2-tensorrt11-smoke

Checkpoint date recorded in source: 2026-09-03.

> Recorded outcome: Completed vertical slice on 2026-09-03

### Result

> The standalone TensorRT 11 C++ smoke path successfully:

> - generated a trusted ONNX 1.20 fixture with FP16 input/output tensors;
> - configured and built against TensorRT 11.2.1 and CUDA 13.1;
> - parsed the ONNX model through `nvonnxparser_11`;
> - built a serialized engine on an RTX 5090;
> - deserialized the in-memory engine immediately for validation;
> - verified two FP16 I/O tensors;
> - wrote a temporary plan and atomically published the final file.

> Measured local result:

> ```text
> engine size: 12,084 bytes
> build + validation: 3,471 ms
> I/O tensors: 2
> FP16 I/O: true
> deserialization validated: true
> atomic publication: true
> ```

> ```powershell
> powershell -NoProfile -ExecutionPolicy Bypass `
>   -File .\scripts\tensorrt11-engine-smoke.ps1
> ```

> Python package `onnx==1.20.0` is installed only under the ignored
> `out/python-deps` development directory to generate the fixture. It is not a
> runtime or end-user dependency.

### TensorRT 11 findings

> - TensorRT public headers require the CUDA Toolkit include directory.
> - MSVC builds on a Korean Windows code page require `/utf-8` so warnings in
>   NVIDIA headers do not fail a `/WX` build.
> - The historical `BuilderFlag::kFP16` is not available in TensorRT 11.2.1.
>   Precision must be represented by the network/tensor precision policy; this
>   smoke uses FP16 ONNX I/O explicitly.


<a id="record-plan-v1-foundation"></a>
## v1-foundation

Checkpoint date recorded in source: 2026-09-03.

### Outcome

> Deliver an instrumented CLI vertical slice that converts a short supported
> H.264/H.265 2D input into valid SBS H.264/H.265 output on an NVIDIA GPU, using a
> DA2 Small or Base TensorRT backend, and produces reproducible stage and end-to-end
> benchmark artifacts.

> This milestone proves architecture and performance. It does not promise a GUI,
> all four production-ready modes, live playback, or final visual parity with iw3.

### M0 — Reproducible toolchain and capability probe

> - Select CMake/toolchain/dependency strategy and pin versions.
> - Build a small executable that reports GPU, driver, CUDA, TensorRT, NVDEC/NVENC,
>   codec, and memory capabilities as structured JSON.
> - Add canonical configure/build/test commands and CI for non-GPU checks.
> - Record model-license and redistribution implications before downloading or
>   packaging weights.

> Exit: a clean checkout can build the probe using documented steps, and failure
> messages identify missing/incompatible components.

### M5 — Benchmark and V1 decision

> - Run the defined corpus on RTX 4090 and RTX 5090 where available.
> - Compare against an equivalently configured iw3 baseline.
> - Publish raw results, environment manifests, traces, and an interpreted summary.
> - Decide the supported Performance/Balanced envelope and prioritize the limiting
>   stage for V2.

> Exit: support claims are evidence-backed or explicitly rejected; the quality score,
> technical debt, and next execution plan are updated.

### Planned verification commands

> The build system does not exist yet. M0 must replace this section with exact
> copy-pasteable commands for configure, build, unit tests, fixture generation,
> end-to-end tests, benchmarks, and trace inspection. CI must call those entry points.

### Decisions

> - 2026-09-03: Start with an instrumented CLI and one vertical slice. This keeps
>   performance, ownership, and media correctness visible before UI work.
> - 2026-09-03: Treat four-mode throughput numbers as hypotheses until complete
>   pipeline benchmarks satisfy the current [benchmark contracts](../BENCHMARKS.md).
> - 2026-09-03: Use DA2 Small/Base as V1 candidates; defer oVDA/VDA/DA3 integration
>   until the backend contract and temporal-quality corpus exist.

### Progress

> - [x] Establish repository knowledge base and initial contracts.
> - [ ] Complete M0 toolchain and capability probe.
> - [ ] Complete M1 media correctness skeleton.
> - [ ] Complete M2 depth backend vertical slice.
> - [ ] Complete M3 SBS synthesis.
> - [ ] Complete M4 bounded GPU pipeline.
> - [ ] Complete M5 benchmark and V1 decision.

<a id="provenance-docs-design-docs-benchmark-methodology-md"></a>
### Additional provenance: benchmark-methodology

> `python v1/run_expanded_gpu_validation.py --input <clip>` runs remaining-mode
> comparisons sequentially, validates every output, generates one-second SDR
> 1080p30/4K30 synthetic fixtures with audio for 1080p hash diagnostics and explicit
> 4K rejection (current H.264 output width limit), then runs the
> five-minute 720p30 GPU soak. It preserves commands, logs and referenced raw
> reports under `out/expanded-gpu-validation`. Resolution smoke tests do not
> establish sustained frame-rate support. A failed comparison stops the sequence;
> its partial report and logs remain available for diagnosis.

> `scripts/test-v1-motion.ps1` generates two-second 640x360 H.264/H.265 inputs and
> runs all four modes in the built portable package. It requires 48 output frames,
> one cut, zero flat-background refinements and exact inference counts (48 in all
> modes; Performance adds 23 motion refreshes and one off-cadence cut to its 24
> scheduled inferences). Raw reports
> are linked by a unique validation JSON under out/quality-fixtures. These are
> media/cut regressions, not performance benchmarks, natural-video quality gates,
> audio checks or proof of motion-compensated propagation.
