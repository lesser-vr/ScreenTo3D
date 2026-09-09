# VDA export, runtime and quality

Historical evidence by recorded checkpoint. Current support is in
[implementation status](../implementation-status.md).

## Records

- [offline-centered-window-2026-09-08](#record-result-offline-centered-window-2026-09-08)
- [vda-native-live-2026-09-09](#record-result-vda-native-live-2026-09-09)
- [vda-device-live-promoted-2026-09-08](#record-result-vda-device-live-promoted-2026-09-08)
- [streaming-model-candidate](#record-result-streaming-model-candidate)
- [vda-device-boundary-2026-09-06](#record-result-vda-device-boundary-2026-09-06)
- [vda-lifecycle](#record-plan-vda-lifecycle)
- [vda-quality-export](#record-plan-vda-quality-export)
- [vda-small-oracle](#record-plan-vda-small-oracle)
- [vda-attention-repro](#record-plan-vda-attention-repro)
- [vda-default-size](#record-plan-vda-default-size)
- [vda-feature-divergence](#record-plan-vda-feature-divergence)
- [vda-implementation](#record-plan-vda-implementation)
- [vda-letterbox-refinement](#record-plan-vda-letterbox-refinement)
- [vda-nan-diagnosis](#record-plan-vda-nan-diagnosis)
- [vda-onnx-spike](#record-plan-vda-onnx-spike)
- [vda-profile-comparison](#record-plan-vda-profile-comparison)
- [vda-public-reference](#record-plan-vda-public-reference)
- [vda-trt-parity](#record-plan-vda-trt-parity)
- [vda-trt-pipeline](#record-plan-vda-trt-pipeline)
- [vda-widescreen](#record-plan-vda-widescreen)
- [vda-local-preview](#record-reference-vda-local-preview)

<a id="record-result-offline-centered-window-2026-09-08"></a>
## offline-centered-window-2026-09-08

> Date: 2026-09-08. Current behavior is owned by
> [PRODUCT](../PRODUCT.md) and [implementation status](../implementation-status.md).

> Offline Quality now pairs the installed VDA Small TensorRT FP32 engine with
> `CenteredDepthWindow` (`centered-color-gated-depth-fusion-v1`). The file-only
> processor keeps two past and two future reduced observations, aligns neighbor
> depths to the target's robust range, and accepts contributions only where color
> and normalized depth are stable. It does not motion-warp. The queue is capped at
> five samples, emits in source order, drains a scene before cut reset, and verifies
> emitted count equals decoded count before publication. The pipeline rejects an
> Offline job without this processor and rejects the processor in other modes.

> Public source: prepared first six seconds of UVG-VCM FloorballGame, CC BY 4.0,
> 1920x1080 at 60 fps, no audio, SHA256
> `a0506f552047992498ea81c9ffb19269504d1d617a5bea89360f159a2842007b`.
> Source URL and complete attribution are pinned by `v1/public_test_media.py` and
> the adjacent JSON/ATTRIBUTION records under `out/public-live-default`.

> Actual application result:
>
> - `out/offline-window-public-final-20260908/FloorballGame-offline-sbs.mp4`
>   fully decodes as H.264, 3840x1080, 60/1 fps, 6.000 seconds, 360/360 frames.
>   SHA256 is `b978fe0f740c130228c4e8c5d1466a13054cc336582834386f37d3b347604285`.
> - Processing rate was 5.3744 fps in this final-code short run. The centered-window
>   stage averaged 45.8937 ms/frame; it used future context on 359 frames and
>   recorded a five-sample / 47,174,400-byte maximum. No cut occurred in this clip.
> - Two post-cache runs measured 44.1 and 45.9 ms/frame versus the initial 54.5
>   ms/frame (about 15.8–19.0% lower) while raising the bounded window maximum from
>   36.8 to 47.2 MB. Initial, optimized and final-code MP4 SHA256 values are all
>   identical, so these implementation optimizations preserved the complete encoded
>   result for this input. Whole processing rate moved from 5.2308 to 5.3755/5.3744
>   fps; these short observations are not a repeated performance claim.

> `out/offline-window-public-smoke-optimized-20260908/temporal-proxy-120.json`
> compares raw and centered depth over the first 120 public FloorballGame frames.
> The centered/raw Farneback-aligned normalized-depth-change ratio is 0.7654
> overall and 0.8193 at detected edges, with equal 0.8777 valid fraction. A second
> report, `temporal-proxy-public-hard-cut-120.json`, concatenates 60 public
> OfficeWalk frames and 60 public ParkingGarage frames in memory. Both raw and
> centered paths detect the annotated cut at frame 60; the window reports two
> scenes, one flush, five samples maximum and 120/120 emitted frames. Its aligned
> ratios are 0.8465 overall and 0.8585 at edges.

> Related unit/publication contracts pass ordering, owned-frame retention,
> future context, motion gating, invalid input/lifecycle, hard-cut isolation,
> count preservation and close-before-publication. The proxy shows lower temporal
> change on these bounded public samples. It does not establish ground-truth depth,
> spatial fidelity, absence of ghosting, continuous visual quality, VR comfort,
> other content/hardware, long-run stability or a model-quality winner.

> Reproduction uses a fresh output/report path:
>
> ```powershell
> .\scripts\run-vda.ps1 -InputVideo out\public-live-default\FloorballGame.mp4 `
>   -OutputVideo out\new-offline-sbs.mp4 -Mode offline-quality -StereoRenderer cuda
> .\scripts\evaluate-offline-vda.ps1 -OutputReport out\new-offline-proxy.json
> .\scripts\evaluate-offline-vda.ps1 -Clip OfficeWalk -CutClip ParkingGarage `
>   -OutputReport out\new-offline-cut-proxy.json
> ```

<a id="record-result-vda-native-live-2026-09-09"></a>
## vda-native-live-2026-09-09

> Date: 2026-09-09. Clean commit `e9b27f0` connects the existing VDA device-depth
> path to the explicitly selected `gpu-texture` delivery. The common texture-output
> mixin changes only publication; file/Offline VDA keeps the host engine, live host
> output remains available, and native delivery is still experimental.

> The product-class diagnostic used the pinned public FloorballGame source and
> matched the host reference's final SBS pixels exactly on 12/12 frames. All 12
> alpha planes were opaque, all device-depth tokens completed, no token remained
> pending and no depth download was recorded. Evidence:
> `out/vda-native-product/public-floorball-20260909/report.json`.

> The clean actual-GUI run used retained WGC input, both Qt/D3D11 consumers, a
> 60 Hz target, six-second warmup and five six-second windows per geometry:
>
> | Per-eye input / Full SBS | Capture | Processed | Distinct native output |
> |---|---:|---:|---:|
> | 1920x1080 / 3840x1080 | 62.47 | 28.15 | 28.15 fps |
> | 3840x2160 / 7680x2160 | 62.34 | 11.92 | 11.92 fps |
>
> Against the preceding clean device-depth/host-output medians, distinct output
> is 17.35% higher at 1080p and 36.24% higher at eye-4K. Every session ended with
> zero live pools/nodes. All 15 review captures per geometry had unique hashes;
> inspected first/middle/last samples advanced, retained plausible Full SBS layout
> and showed no black/frozen frame. These are downscaled output-window grabs, not
> 1:1 eye-4K, continuous playback, physical scanout, VR or long-session acceptance.
> Capture and model input remain host-mediated and `zero_copy=false`. Evidence:
> `out/model-native-vda-clean-20260909`.

<a id="record-result-vda-device-live-promoted-2026-09-08"></a>
## vda-device-live-promoted-2026-09-08

> Date: 2026-09-08. The prior isolated candidate below was rerun on the pinned
> public FloorballGame source before product integration. Raw depth, host SBS and
> shared-texture SBS were exact on 12/12 frames; pending reuse and completed-token
> expiry were rejected 12/12. Three-run medians were 26.795 fps for host depth /
> host SBS, 29.016 for device depth / host SBS (+8.29%), and 30.478 for device
> depth / shared texture (+5.04% from device host output, +13.75% combined).
> Evidence: `out/vda-device-pipeline/public-floorball-20260908/report.json`.

> The single-pending device token is now owned by `depthsbs_app.vda_device` and
> selected only for live VDA sessions. File and Offline bindings retain the host
> engine. The live worker uses the same source-resolution GPU post/SBS consumer
> as oVDA and retains host RGB input/host SBS output; native shared texture remains
> deferred. Trusted manifests, exact cache assembly, the 42-entry history bound,
> stateful every-frame policy and explicit reset/failure behavior are unchanged.

> The integrated product wrapper matched exact SBS on 12/12 public frames,
> completed all 12 owned device tokens, left no pending token and recorded zero
> depth downloads / 99,532,800 bytes avoided. Evidence:
> `out/vda-live-product/public-floorball-20260908/report.json`. The repository's
> discovery suite passed 257/257 tests in the prepared torch environment.

> The final actual-GUI run used clean commit `7434955`, five six-second windows
> per geometry, the retained WGC path and host output. It selected
> `model-device-depth-gpu-stereo-host-output` and recorded:
>
> | Per-eye input / Full SBS | Capture | Processed | Output | Sampled depth / SBS / total |
> |---|---:|---:|---:|---:|
> | 1920x1080 / 3840x1080 | 62.52 | 23.99 | 23.99 fps | 32.51 / 8.08 / 41.77 ms |
> | 3840x2160 / 7680x2160 | 62.57 | 8.61 | 8.75 fps | 70.57 / 37.85 / 115.10 ms |
>
> This is about 2.85x the preceding clean 8.43 fps 1080p host-depth path and
> 3.25x the 2.64 fps eye-4K path. Stage values are medians of 120 sampled
> latest-frame snapshots per geometry, not all-frame distributions or physical
> latency. All 30 review grabs had unique hashes. Sampled first/middle/last frames
> at both geometries showed advancing content, plausible eye order/aspect and no
> black or frozen output. The 2100x975 grabs are downscaled window captures, not
> 1:1 7680x2160 or continuous/VR review. The run stopped with no pending mailbox
> frame or FFmpeg process and GPU utilization returned to 0%; it is not a long
> soak. Evidence: `out/model-performance-vda-device-clean-20260908`.

<a id="record-result-streaming-model-candidate"></a>
## streaming-model-candidate

Checkpoint date recorded in source: 2026-09-04.

> Status: Development CUDA oracle validated, not a production backend; 2026-09-04

> Candidate: official Video-Depth-Anything-Small streaming path. This is NOT an
> assertion that the earlier roadmap name oVDA identifies the same implementation.
> Do not rename this candidate oVDA or change Video Quality's default yet.

> [Official project](https://github.com/DepthAnything/Video-Depth-Anything) labels
> streaming experimental and reports lower accuracy than its offline path. It
> lists Small as Apache-2.0 and Base/Large as non-commercial variants. Pin the
> exact checkpoint/revision and verify artifact provenance before acquisition;
> the pinned Small checkpoint has now been acquired for the isolated oracle.
> See [vda.md](vda.md#record-plan-vda-small-oracle) for provenance, reproduction,
> real-model cache/reset evidence and outstanding production gates.

> [Streaming implementation](https://github.com/DepthAnything/Video-Depth-Anything/blob/main/video_depth_anything/video_depth_stream.py)
> keeps attention-cache/frame-ID lists, initializes transforms on the first frame
> and requires subsequent dimensions to match. An adapter must clear those caches,
> transform and sequence state on cuts/source changes, normalize output shape and
> polarity, and record bounded cache memory. Keep the upstream preprocessing for
> the correctness oracle rather than substituting DA2's fixed square transform.

> The [reference runner](https://github.com/DepthAnything/Video-Depth-Anything/blob/main/run_streaming.py)
> stores all predicted frames and permits CPU fallback. Do not reuse that whole
> runner in the application: our adapter must emit one result at a time, require
> explicit CUDA capability and release GPU state on cancellation/failure.

> Next experiment gates:

> 1. Pin source, dependencies and Small checkpoint with licenses/checksums.
> 2. Run the official CUDA inference oracle in an isolated development environment.
> 3. Implement and test cache reset, owned output, repeated sessions and cut scenes.
> 4. Compare depth/output and characterize model-native smoothing versus current EMA.
> 5. Assess ONNX/TensorRT streaming-cache export and engine build reproducibility;
>    do not describe the PyTorch oracle as a production TensorRT backend.
> 6. Only after real-model contract evidence, proceed to V2 capture integration.


<a id="record-result-vda-device-boundary-2026-09-06"></a>
## vda-device-boundary-2026-09-06

Checkpoint date recorded in source: 2026-09-06.

> Status: Proposed component candidate, not integrated. Owner: DepthSBS. Date:
> 2026-09-06.

### Question and invariants

> Can the validated VDA Small TensorRT FP32 backend retain resized depth on its
> own CUDA stream through the existing temporal/guided/SBS consumer, and then
> publish SBS into the proven two-slot D3D11 shared-texture transport, without
> changing pixels or weakening ownership?

> The experiment preserves the checked warmup/cached engine choice, exact 31-cache
> input assembly, 42-entry history bound, model/profile/hash validation, reset
> reasons, owner thread and explicit failure. Only one device token may be pending;
> it expires after completion. Production `VdaEngine`, backend selection, pinned
> application DLLs and defaults are unchanged. There is no CPU or model fallback.

### Method

> `v1/test_vda_device_pipeline.py` uses the same prepared 1920x1080, 60-frame
> HEVC source and Video Quality policy as the explicit backend comparison. The
> experimental class is `experiments/vda/device_depth.py`; the separate native DLL
> is built from `vda_device_texture_spike.cu`.

> Correctness first uses 12 sequential frames. Host VDA supplies reference depth
> and host SBS. A fresh device-token engine is checked against both, including
> early-reuse rejection and expiry. A third fresh engine publishes to shared
> textures; diagnostic D3D readback checks RGB and alpha. This source contains no
> detected cut after the initial reset, so cut recovery is not established.

> Timing uses one discarded warmup and three measured 60-frame runs per path,
> rotating path order. Shared-texture timing uses keyed-mutex acquire/release but
> no pixel readback. Runs share one Python process, so process-global PyTorch
> allocator reservation accumulates across engine instances and is not leak or
> steady-state-memory evidence.

> Evidence: `out/vda-device-pipeline/current-v2/report.json` (`passed=true`).

### Results

> All raw depth comparisons were bit exact for 12/12 frames. Final host SBS and
> shared-texture SBS were also bit exact for 12/12; texture alpha was opaque for
> 12/12. Pending reuse and post-completion validation were rejected 12/12 each.

> | Explicit VDA path | Median fps | Three-run range |
> | --- | ---: | ---: |
> | Host depth -> host SBS | 27.544 | 27.436-27.561 |
> | Device depth -> host SBS | 29.486 | 29.433-29.526 |
> | Device depth -> shared texture | 30.270 | 30.217-30.334 |

> Device depth improves the matched host-output path by 7.05%. Shared texture adds
> 2.66% over device depth with host SBS. The combined component-boundary change is
> 9.89%. Per 60 frames, the two boundaries avoid 497,664,000 bytes of resized-depth
> D2H and 746,496,000 bytes of host-SBS D2H.

> This is not integrated live FPS or end-to-end zero-copy. Host RGB preprocessing
> and upload, per-frame synchronization, VDA cache concatenation and a CPU texture
> consumer command remain. Fresh depth is still about 30 fps, not 60 fps.

### Decision and remaining acceptance

> Retain the device token/native output as an experimental candidate; do not
> promote VDA to the default live backend yet. The result is slightly faster than
> the comparable oVDA component spike, but is too close for a cross-backend winner
> claim without an isolated matched process benchmark and quality comparison.

> Remaining work:

> 1. Profile and optimize the exact VDA preprocessing and 31-entry cache assembly;
>    accept only bit-exact output and bounded memory. Process-isolate A/B runs.
> 2. Add cut, discontinuity, geometry-change, cancellation and injected CUDA/
>    consumer failure coverage for the device token and texture lifecycle.
> 3. Design bounded frame-ID, epoch and dual-consumer leases before any asynchronous
>    presentation test. Repetition or model-input sampling requires an explicit
>    product/quality decision; it is not fresh 60-Hz processing.
> 4. Prototype native input only after matching the current OpenCV cubic/float64
>    normalization contract, color, adapter and resize behavior.
> 5. Run matched motion/thin-edge/temporal pumping tests, long memory/queue soak,
>    actual live 30/60 latency measurements and headset review.
> 6. Only then add immutable live backend selection, capability/license identity,
>    explicit no-fallback failure and packaging boundaries.

> Rejected now: integrating first and testing later; calling repeated presentation
> fresh 60-Hz depth; treating process-global allocator reservation as a leak; or
> claiming VR comfort from this short component run.


<a id="record-plan-vda-lifecycle"></a>
## vda-lifecycle

Checkpoint date recorded in source: 2026-09-04.

> Recorded outcome: Short default-size lifecycle checks passed

### Results (2026-09-04)

> Report: `out/vda-lifecycle/046c7d1e5ac5459a9cd02e2fa736a13a/report.json`.
> Original 1056x608 user clip: 124 frames at model input_size=518, no source
> downscaling by the test. Cache entries stay within 42; unique cache storage is
> constant in samples from frame 50 onward. Total allocator bytes fluctuate and
> are recorded, not treated as an exact model-memory count.

> Initial strict zero-allocation assertion exposed 8,519,680 bytes after close.
> A diagnostic-only PyTorch cuBLAS workspace clear reduced allocation to baseline
> zero. No private CUDA API was added to the application. Initial total-allocation
> stability gate was replaced with a direct unique-cache-storage check; this does
> not prove long-run allocator stability. Failed diagnostic reports are retained
> under `out/vda-lifecycle`.

> Cancellation after the first frame and injected second-inference failure both
> preserve the existing-output sentinel, close the engine, clear its model
> reference, remove temporary files and leave tracked subprocesses exited.
> A subsequent normal full pipeline succeeds and its output decodes 124 frames.
> Existing 76 Python tests, seven process-tree cases and C++ regression pass.

> Reproduce using the isolated environment prepared in [vda.md](vda.md#record-plan-vda-small-oracle):

> ```powershell
> out/vda-oracle-env/Scripts/python.exe v1/test_vda_lifecycle.py --input 'samples/input.mp4'
> ```

> Real device loss, hour soak and VR checks were not performed. Public defaults and portable packages remain unchanged.


<a id="record-plan-vda-quality-export"></a>
## vda-quality-export

### Evidence

> `out/vda-temporal-comparison/be928c36317f49d3bd4e3f07ce3bfb47/report.json`
> records two 124-frame conversions at input_size=518. Their complete depth hashes
> match, isolating the renderer policy change. alpha=1 disables both depth EMA
> and percentile-range EMA; this is not an isolated depth-EMA-only comparison.
> Other renderer refinements remain active, so native_only means native model
> temporal processing without renderer EMA, not unprocessed model output.

> Matching left-eye/source sheets are available at frames 20, 40, 60, 80 and 100.
> Frame 60 was visually inspected at reduced display size: the character and hands
> remain recognizable in both variants, but this is insufficient to judge subtle
> ghosting or prefer a mode. Temporal playback, full-scale hand crops, DA2 baseline,
> depth polarity and right-eye golden checks remain open. No quality improvement
> or visual acceptance is claimed.

### Observed export boundary (pinned source, this input only)

> ```powershell
> out/vda-oracle-env/Scripts/python.exe v1/compare_vda_temporal.py --input 'samples/input.mp4'
> ```


<a id="record-plan-vda-small-oracle"></a>
## vda-small-oracle

Checkpoint date recorded in source: 2026-09-04.

> Pinned upstream source: DepthAnything/Video-Depth-Anything commit
> 4f5ae23172ba60fd7bc11ef671cca678842c7072.
> Official Small weight repository revision: 256875362cff76724b920335dfb4b29dd611f66e.
> File video_depth_anything_vits.pth, 116440756 bytes; published LFS SHA256
> 13379300b739e659f076a59d52e9801bd8d38c541a7e71f73bbca4dcfb013609.
> Upstream model card declares Apache-2.0; keep source LICENSE and checkpoint
> provenance. Verify digest before weights_only loading. Never load arbitrary
> pickle objects or use an implicit CPU fallback.

> Install a dedicated out/vda-oracle-env, leaving DA2 dependencies untouched.
> Upstream torch 2.1.1 requirements are not used verbatim on this Python 3.13 /
> RTX 5090 host; pin CUDA 12.8 torch 2.7.1 / torchvision 0.22.1 and record the
> compatibility deviation. Review imported upstream code before executing it.

### Evidence (2026-09-04)

> `out/vda-oracle-checks/b822dee9af964773acc9c98258ad9210/report.json`:
> six direct-upstream/adapter depth arrays match exactly; 64 reduced-size frames
> retain at most 42 cache entries; owned output remains unchanged; cut reset
> matches fresh output; dimensions cannot change without reset; closed use fails.
> Default input size 518 passes one-frame CUDA smoke. A 48-frame HEVC fixture
> completes the real decode/depth/CPU-stereo/NVENC pipeline with one scene cut and
> 48 model calls. These sequence tests use input size 140, not a quality preset.
> PyTorch allocator statistics are process-global, not a leak proof.
> Existing 76 Python tests, seven process-tree checks and C++ regression pass.

### Reproduction

> Use Python 3.13 in a separate virtual environment. From the repository root:

> ```powershell
> python -m venv out/vda-oracle-env
> out/vda-oracle-env/Scripts/python.exe -m pip install torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cu128
> out/vda-oracle-env/Scripts/python.exe -m pip install opencv-python==4.11.0.86 einops==0.8.1 easydict==1.13 numpy==2.5.2 pillow==12.3.0
> git clone https://github.com/DepthAnything/Video-Depth-Anything.git out/vda-source
> git -C out/vda-source checkout --detach 4f5ae23172ba60fd7bc11ef671cca678842c7072
> New-Item -ItemType Directory -Force out/models/vda-small
> Invoke-WebRequest 'https://huggingface.co/depth-anything/Video-Depth-Anything-Small/resolve/256875362cff76724b920335dfb4b29dd611f66e/video_depth_anything_vits.pth' -OutFile out/models/vda-small/video_depth_anything_vits.pth
> out/vda-oracle-env/Scripts/python.exe v1/test_vda_oracle.py --input 'samples/input.mp4'
> ```

> The runner currently requires the existing local GPU-preview FFmpeg assets and
> motion fixture path recorded in its source. Full resolved dependency versions
> are recorded in the report. No xFormers is installed; native PyTorch CUDA
> attention is explicit and enforced. Source revision/cleanliness and checkpoint
> SHA256 are verified by the adapter before model execution.

> Follow-up: [vda.md](vda.md#record-plan-vda-lifecycle) records passing short default-size sequence/cache,
> cancellation and injected inference-failure checks on the 124-frame user clip.
> Remaining: long-run memory/device-failure validation;
> model-native temporal quality versus existing EMA; depth polarity/eye-order
> visual golden coverage; ONNX/TensorRT cache export/build feasibility. The oracle
> does not satisfy the production model-backend acceptance gate. All four public
> modes and existing portable executables remain DA2 Small and unchanged.


<a id="record-plan-vda-attention-repro"></a>
## vda-attention-repro

Checkpoint date recorded in source: 2026-09-04.

### Results (2026-09-04)

> Original minimal Q/K/V-to-attention-output graph reproduces 11,520 nonfinite
> TensorRT values from finite [180,1,64] Q/K/V inputs, while ORT is finite:
> `out/vda-attention-repro/de01faddeeaf49b299f671182690ecab/report.json`.
> Builder optimization level 0 does not resolve it:
> `out/vda-attention-repro/7179a3bd20f54fcaa136a5b5081a5538/report.json`.

> Stable Softmax decomposition was applied to eight temporal Softmax nodes per
> graph in separate copies (subtract max, Exp, ReduceSum, Div). The rewritten
> minimal graph STILL fails:
> `out/vda-attention-repro/57e1890846b64193892760cddcc1453f/report.json`.
> Therefore this is not a general attention fix or proof of a Softmax defect.

> However, the rewritten complete warmup/cached graphs, without extra diagnostic
> outputs, build and pass all 36 depth/cache comparisons:
> `out/vda-trt-parity/1bc98c1fa54447f4aa0fa9043de88e14/report.json`.
> Reusing those plans on 64 consecutive real frames plus fresh warmup passes all
> 585 tensor comparisons (65 depth and 520 cache), with independent PyTorch/TRT
> feedback histories bounded to 42 entries and unchanged rtol/atol 1e-3:
> `out/vda-trt-parity/15597b76f9864f1e8a075cbbb00c362b/report.json`.
> No NaN clamping, changed weights or tolerance relaxation was used.

> Treat this as an optimization-sensitive full-graph workaround candidate, not
> production acceptance. Next gates: fresh-build reproducibility, default input
> size/aspect ratio, FP32 versus autocast quality, full pipeline and error paths.
> The reduced test explicitly resizes the source to 252x140; it does not verify
> the upstream aspect-preserving preprocessing or production resolution.
> Original ONNX files and failed reports are retained. Public modes unchanged.

> ```powershell
> out/vda-oracle-env/Scripts/python.exe v1/reproduce_vda_attention.py --input 'samples/input.mp4'
> out/vda-oracle-env/Scripts/python.exe v1/rewrite_vda_softmax.py out/vda-onnx-spike/164ea87e20e54fba91149f398dc1f047
> # Use the directory printed by the rewrite command for a fresh engine build:
> out/vda-oracle-env/Scripts/python.exe v1/test_vda_trt.py --input 'samples/input.mp4' --frames 64 --onnx-dir out/vda-softmax-rewrite/8176ca68686749ec92386742ee6e49dd
> ```

> Regression: 76 Python tests, seven process-tree checks and C++ pass.


<a id="record-plan-vda-default-size"></a>
## vda-default-size

> Follow-up [vda.md](vda.md#record-plan-vda-feature-divergence) resolves this tested default-size failure:
> precomputing the input-independent positional Resize makes all 585 full-graph
> comparisons pass. Original unfurled graphs remain failed evidence.

### Results

> Fresh reduced-size build, without plan reuse, passes all 585 comparisons:
> `out/vda-trt-parity/3ca5af659972437e912b465821ee5f51/report.json`.
> The full-graph workaround is reproducible on this host at 140x252.

> Added explicit 140/518 size options to export and parity diagnostics. Default
> size uses the pinned model's own aspect-preserving transform (518x896 for the
> supplied clip); mismatched shapes are rejected, not silently resized.
> Default-size ONNX export/checker passes:
> `out/vda-onnx-spike/ad0c74eeb60e4c299acc744131f8bb6c/report.json`.
> Rewritten copies: `out/vda-softmax-rewrite/b2a2bf2379684e35ad298b8ba21f1943`.

> Fresh default-size engines both build and execute all 64 frames plus reset,
> with no nonfinite values in either backend, but all 585 elementwise comparisons
> fail the unchanged rtol/atol 1e-3 gate:
> `out/vda-trt-parity/78fe1a63da80421bb6b5242a296e9011/report.json`.
> First depth max absolute error 0.2168977, mean 0.0099383; first cache_0 max
> 0.3125463. Do not confuse finite output with correct output.

> Same-size warmup ORT/PyTorch diagnostic passes all nine outputs, max depth
> absolute error 0.00073719, with matched FP32/TF32-disabled settings:
> `out/vda-nan-diagnosis/bcaa261dc538468f82029f46e5570685/report.json`.
> No nonfinite graph constants. This narrows the remaining discrepancy to the
> TensorRT path at this shape, not proof of a specific operator defect.

> No tolerance relaxation. Cached-step ORT parity, autocast-quality equivalence and full SBS pipeline remain open.

> ```powershell
> out/vda-oracle-env/Scripts/python.exe v1/export_vda_spike.py --input-size 518
> out/vda-oracle-env/Scripts/python.exe v1/rewrite_vda_softmax.py out/vda-onnx-spike/ad0c74eeb60e4c299acc744131f8bb6c
> out/vda-oracle-env/Scripts/python.exe v1/test_vda_trt.py --input 'samples/input.mp4' --input-size 518 --frames 64 --onnx-dir out/vda-softmax-rewrite/b2a2bf2379684e35ad298b8ba21f1943
> ```

> Existing 76 Python, seven process-tree and C++ regression checks pass.


<a id="record-plan-vda-feature-divergence"></a>
## vda-feature-divergence

Checkpoint date recorded in source: 2026-09-04.

### Evidence (2026-09-04)

> Prefix probe `out/vda-feature-probe/e5109ca300564c0d8223b402da207cbd/report.json`:
> patch convolution passes (max absolute error 1.55e-6), positional Resize fails
> (max 0.00697938), followed by token addition and block-0 outputs. The positional
> Resize is the earliest observed failed boundary, before temporal attention.

> `v1/fold_vda_position.py` verifies the Resize dependency graph has no runtime
> input, evaluates the constant-only ONNX using ORT CPU, and writes separate
> fixed-shape graphs with the resulting initializer. Original weights/graphs are
> not overwritten. No image-time CPU fallback, clipping, or NaN replacement.
> Position shape [1,384,37,64] and SHA256 are recorded in
> `out/vda-position-fold/bf391b9ed2d242a282dfe9316d605ea6/fold.json`.
> This technique is specific to the exported fixed shape, not dynamic resolution.

> Fresh full-graph TensorRT engines (stable Softmax rewrite plus positional fold),
> without intermediate diagnostic outputs, now pass all 585 depth/cache checks
> at 518x896 on 64 real frames plus fresh warmup, unchanged rtol/atol 1e-3:
> `out/vda-trt-parity/87c1b4d53eae42ad9092960883c7fc23/report.json`.
> Maximum absolute error over all compared tensors is 0.000112772. This supports
> the positional interpolation workaround on this host; it is not a general
> TensorRT Resize defect claim or production readiness certification.

> Reproduction (after [vda.md](vda.md#record-plan-vda-default-size) exports):

> ```powershell
> out/vda-oracle-env/Scripts/python.exe v1/probe_vda_features.py --input 'samples/input.mp4'
> out/vda-oracle-env/Scripts/python.exe v1/fold_vda_position.py out/vda-softmax-rewrite/b2a2bf2379684e35ad298b8ba21f1943
> out/vda-oracle-env/Scripts/python.exe v1/test_vda_trt.py --input 'samples/input.mp4' --input-size 518 --frames 64 --onnx-dir out/vda-position-fold/bf391b9ed2d242a282dfe9316d605ea6
> ```

> Remaining: package-independent reproducible builder, real pipeline binding,
> cancel/error cleanup, complete output/visual comparison and additional aspect
> ratios. FP32 parity is not autocast quality/performance equivalence. Public
> mode defaults and packages unchanged. Existing 76 Python, seven process-tree
> and C++ regression tests pass.


<a id="record-plan-vda-implementation"></a>
## vda-implementation

Checkpoint date recorded in source: 2026-09-04.

> 1. Replace experiment-path runtime dependencies with a manifest-validated
>    application backend and self-contained, oracle-tested preprocessing.
> 2. Build a local artifact from pinned source/weights, stable Softmax export and
>    positional constant fold; require 64-frame depth/cache/reset parity before
>    publication, retain failed build evidence and model notices.
> 3. Expose opt-in backend/engine-path diagnostics and GUI/CLI selection without
>    changing mode defaults or silently enabling cadence-incompatible modes.
> 4. Verify artifact failures, tensor signatures, owner/cancel/cut/cleanup paths,
>    H.264/HEVC input and output, and actual public worker execution.
> 5. Compare matched TensorRT/PyTorch FP32 full pipeline, make left/right hand
>    inspection artifacts and characterize autocast differences. Quality
>    improvements over DA2 must not be inferred from model integration alone.
> 6. Record supported envelope, startup/runtime dependencies and reproducible
>    launch commands. Mark implementation done only when the opt-in path runs;
>    distinguish deferred portability and broader quality acceptance.

### Completion evidence

> - Application adapter: `vda_backend.py`, `vda_artifacts.py`, `vda_preprocess.py`.
>   Explicit CLI/GUI model and engine selection; `scripts/run-vda.ps1` launches
>   the prepared local environment. No upstream source imports at application runtime.
> - Builder: `build_vda_artifact.py` freshly built
>   `out/vda-local/518x896-fp32/`; 585 comparisons pass, max absolute error
>   0.000105262. Manifest publication follows parity and includes notices/provenance.
> - `test_vda_application.py`: report
>   `out/vda-application/6bb84a35a563447fa63a88a5a3047d88/report.json` passes exact
>   preprocessing, FP32 first-frame reference, reset/owner/double-close, real
>   cancellation and injected-failure output preservation/process cleanup,
>   124-frame H.264/audio conversion and public-worker HEVC 48-frame cut sequence.
> - `test_vda_gui.py` passes real Tk construction, worker arguments, invalid
>   Performance/VDA rejection and unchanged DA2 defaults.
> - `compare_vda_application.py`: report
>   `out/vda-application-comparison/b22c5885f26f4cde91e1043660d46bbb/report.json`.
>   All 124 full-size depth comparisons pass (max 0.000141621). Decoded SBS
>   differences are documented, not treated as a quality superiority score.
>   Static left/right hand crops at frames 20, 60 and 100 were visually inspected;
>   no conspicuous extra duplicated hand was seen in these stills, but fine moving
>   edges and VR comfort remain outside this acceptance.
> - Non-GPU regression: 82 Python tests, seven process-tree cases and C++ CTest pass.
>   No dedicated Python formatter/linter is configured; diff whitespace check passes.
> - User guide: [vda.md](../models/vda.md); product, architecture,
>   reliability, security and quality status updated in the same change.
> - Final rerun after partial-constructor ownership/close-order and preprocessing
>   telemetry changes also passes:
>   `out/vda-application/af85ff460d0d45399daaca10f8b7ca1a/report.json`.
>   The full 82-test/Python + process-tree + C++ regression was repeated successfully;
>   compileall and diff whitespace checks passed.


<a id="record-plan-vda-letterbox-refinement"></a>
## vda-letterbox-refinement

Checkpoint date recorded in source: 2026-09-05.

> Hypothesis: paired narrow black bars prevent the existing uniform-border guard
> from recognizing an otherwise flat backdrop, contributing to the observed hand
> halo. Test using identical decoded RGB and VDA depth, not another model/resize.

### Evidence and decision

> - Development-only `letterbox_refinement.py`: paired full near-black edge rows/
>   columns (RGB <=8), 2-pixel minimum, at most 10% per edge, symmetry tolerance
>   2 pixels, and a 2-pixel interior transition guard. At least 32 pixels of content
>   remain on each axis. The existing flat-backdrop threshold is unchanged.
> - `compare_letterbox.py` decodes each frame and runs VDA once, then renders two
>   independently owned temporal states using that exact RGB/depth. Source arrays
>   are verified unchanged. Both outputs use identical NVENC settings and copy the
>   source audio. OpenCV diagnostic decode differs from the application FFmpeg
>   path, so do not compare these raw hashes to earlier application runs.
> - Result: `out/vda-letterbox/c5886097b05f4ddfa63b89b82aa8e3b3/report.json`.
>   124 model inferences, 124 frames in each 3840x1080 SBS video, audio retained.
>   Original refinement applied 0/124; candidate applied 124/124. Detected content
>   rectangle remains [22,0,1898,1080]. Original padding pixels match exactly in
>   both eyes for all 124 frames **before** lossy video encoding. Depth outside the
>   inset content region is unchanged; source images are never cropped or stretched.
> - `hands-20.png`, `hands-62.png`, `hands-100.png` and `eyes-62.png` visually
>   inspected: dark hand/arm/tail edge trails are substantially reduced in these
>   stills, and the black bars stay straight. This supports the guard-interaction
>   hypothesis on this clip; it does not measure artifact reduction as a percentage
>   or certify every moving edge/VR playback.
> - 99 Python tests + seven process-tree cases + C++ CTest pass. New cases cover
>   both axes/windowboxing, no-padding identity, single/asymmetric/oversized bars,
>   a bar caption/noise pixel, dark/textured scenes, immutable input and exact
>   pre-encode padding restoration. Existing occlusion/projection tests pass.

> Decision: retain as a development-only candidate, not an automatic production
> policy. The sample is one synthetic letterboxed avatar clip. Changing captions,
> vignettes, artistic borders, detector eligibility across frames, and more natural
> content need testing before default promotion. No GUI/CLI model defaults, VDA
> engine artifact, portable executable or release changed. Soak/VR remain deferred.

> Reproduce from the prepared environment:

> ```powershell
> $env:PYTHONPATH = 'v1'
> out/vda-oracle-env/Scripts/python.exe v1/compare_letterbox.py --input '<supported-clip-up-to-124-frames.mp4>'
> ```

> The generated `baseline.mp4` and `candidate.mp4` are the review pair; development
> logs and raw inspection images stay with their report. A later source-app opt-in
> adds three-frame confirmation and explicit GUI/CLI selection; defaults remain
> off. See [file-quality.md](file-quality.md#record-plan-letterbox-opt-in) for its separate application evidence and limits.


<a id="record-plan-vda-nan-diagnosis"></a>
## vda-nan-diagnosis

> Inspect exported constants for nonfinite values and compare the same warmup
> real-image input in PyTorch FP32 and ONNX Runtime CPU (explicit diagnostic,
> not application CPU fallback). If ONNX reproduces the issue, locate its first
> nonfinite node before changing TensorRT settings. Do not hide NaNs or loosen
> parity tolerances. Preserve failed artifacts and keep public modes unchanged.

### Evidence

> ONNX Runtime CPU 1.22.1 installed only in the isolated development environment.
> Warmup graph has no nonfinite initializers/tensor constants. First comparison
> had finite outputs but depth max error 0.00770; its PyTorch cuDNN TF32 setting
> was not aligned. After explicitly disabling both matmul and cuDNN TF32, report
> `out/vda-nan-diagnosis/8805642eaba34c6e8589e7585ca316f8/report.json`
> passes all nine outputs at the unchanged rtol/atol 1e-3. Depth maximum absolute
> error is 0.00004054. This is one real warmup frame, not cached-step ORT acceptance.

> TensorRT diagnostic network outputs were added around motion_modules.2,
> transformer_blocks.0 attention and normalization. Exposing attention_blocks.0
> made cache_5 finite, but depth/cache_6/cache_7 remained nonfinite:
> `out/vda-trt-parity/e1ef0b63020f40299c884a6d5a540ea0/report.json`.
> Exposing attention_blocks.1 as well made cache_6 finite; warmup cache_7 and depth
> still fail, while cached steps fail only depth:
> `out/vda-trt-parity/488c2860439749ebb7795754cafcec4b/report.json`.
> All exposed internal attention outputs in the second probe are finite.

> Interpretation: adding observable outputs changes builder optimization/tactics and shifts the failure downstream. Attention fusion/tactic behavior is a hypothesis, not a proven specific kernel defect. Instrumented graphs are not a fix or a release candidate. Do not introduce NaN clamping or change public modes.

> Reproduce with `v1/diagnose_vda_onnx.py --input <video>` in the oracle environment;
> TensorRT probes use `v1/test_vda_trt.py --input <video> --probe`.
> Existing 76 Python tests, seven process-tree checks and C++ regression pass.


<a id="record-plan-vda-onnx-spike"></a>
## vda-onnx-spike

> Recorded outcome: Fixed-shape export, ONNX checker and TensorRT parser passed

### Results

> `out/vda-onnx-spike/164ea87e20e54fba91149f398dc1f047/report.json` records successful warmup/cached exports and ONNX checker validation. `tensorrt-parser.json` records TensorRT 11.2.1.2 accepting both without errors: warmup 1 input/9 outputs; cached 9 inputs/9 outputs. No engine build or inference parity was performed. Shape-dependent tracing warnings restrict these graphs to [1,1,3,140,252]; dynamic shapes and autocast-oracle parity are not established.

> Isolated dependencies added: onnx 1.18.0, protobuf 7.36.1. Initial builder DLL
> loading failed with PATH alone; explicit Python DLL-directory registration
> resolved it. This was a loader-path issue, not a graph parser error.

> ```powershell
> out/vda-oracle-env/Scripts/python.exe v1/export_vda_spike.py
> $env:PYTHONPATH='out/v1-python-deps'
> python v1/parse_vda_onnx.py out/vda-onnx-spike/164ea87e20e54fba91149f398dc1f047 --runtime-dir C:/TensorRT/TensorRT-11.2.1.2/bin
> ```

> Enlarged matching frame-60 source/left-eye hand crops show no obvious detached
> duplicate hand contour in either VDA condition. Small contour differences remain;
> one encoded frame cannot establish temporal ghosting improvement or a preferred
> EMA setting. Moving-sequence and DA2 comparison remain open. Public policies
> and portable packages remain unchanged.


<a id="record-plan-vda-profile-comparison"></a>
## vda-profile-comparison

Checkpoint date recorded in source: 2026-09-04.

### Results

> - `compare_vda_application.py` now accepts an engine/profile root, explicit runtime
>   path and actual-frame budget (1..124). Metadata/geometry preflight precedes
>   output creation. Underreported frame counts cannot run past the actual budget.
>   All three runs must agree on decoded RGB hash and frame count; postdecode
>   rejects missing/extra frames or changed geometry. Final source-file SHA256
>   protects container/audio changes as well as decoded-pixel changes.
> - Reference runs now report `pytorch-cuda-fp32` / `pytorch-cuda-autocast`, not
>   TensorRT. Frame budget, source/weight provenance and selected plan hashes are
>   recorded. Timings include paired reference inference and hashing, so these
>   are not benchmark results.
> - Lower-frame regions use normalized coordinates, separate labels and bounded
>   aspect-preserving preview images instead of original-resolution hardcoded crops.
> - 1080p report: `out/vda-application-comparison/041c9cf0d48d44da89904c6b000f739b/report.json`.
>   All 124 full-size depth comparisons pass; max absolute error 0.000106096.
>   All three decoded-source hashes agree. Decoded SBS versus source FP32 has
>   MAE 0.203546/255, max 163; versus autocast MAE 0.263716/255, max 236. This run
>   predates the final additional file-hash guard; decoded-hash agreement was checked.
> - Original-profile rerun with the final file-hash guard:
>   `out/vda-application-comparison/cc20289b687f420c85c86691a04deed6/report.json`.
>   124/124, max depth error 0.000141621, decoded FP32 SBS MAE 0.290933/255, max 108;
>   matches the earlier baseline. Correct distinct runtime descriptors verified.
> - 93 Python tests, seven process-tree cases and C++ CTest pass; compileall and
>   diff whitespace checks pass. No runtime mode default, portable or release changed.


<a id="record-plan-vda-public-reference"></a>
## vda-public-reference

Checkpoint date recorded in source: 2026-09-04.

> Recorded outcome: Source review complete; plain-matmul experiment rejected for TensorRT NaNs

> - MapMindAI/DepthAnythingOnnx, MIT, commit
>   693f8eda3caaf0c453bc96a3e4ef7a5e653f5d19: offline [B,T,3,H,W] converter uses
>   plain MatMul/Softmax attention for CPU-safe export. No external streaming
>   cache outputs or TensorRT-11 parity evidence found in the inspected converter.
> - nagadomi/nunif, MIT, d23721f1b5f0a4c92c3ee1be013180bf298730c5:
>   iw3 has separate online-window and streaming VDA wrappers, reset/EMA handling.
> - nagadomi/Video-Depth-Anything_iw3, Apache-2.0,
>   1758a70d841cef480bf1532e5707f0dab2e1401b: tensor-native streaming input and
>   explicit reset, same first-two-plus-last-29 cache selection and gap 41.
>   Temporal SDPA branch exists but use_sdpa is disabled by default in inspected
>   code. It is not evidence of TensorRT streaming support.

### Experiment result

> `v1/vda_plain_attention.py` implements an export-only, mask/upcast-preserving
> standard MatMul/Softmax path. `export_vda_spike.py --plain-attention` switches
> only the eight temporal attention modules on the experimental model instance.
> The production registry, pinned upstream source and default export stay intact.

> ONNX export/checker passes:
> `out/vda-onnx-spike/138edf1bee494ad88e54b24d8be602ec/report.json`.
> Both fresh TensorRT engines build, but 197 of 585 comparisons fail with
> nonfinite values across 64 real frames and fresh warmup:
> `out/vda-trt-parity/4f67bd6a43ab4c01852d546b4e0f5e63/report.json`.
> This does not demonstrate a defect in the public offline converter: our test
> uses a different streaming model, TensorRT version, GPU and export path.
> Do not adopt this candidate as a fix. Keep the previously passing full-graph
> stable-Softmax rewrite as the current candidate, pending default-size and
> fresh-build reproducibility. Public sources confirm useful design patterns but
> do not remove the need for our actual deployment-target parity gates.

> Source matrix, pinned paths and reuse constraints:
> [public-depth-integrations.md](../references/public-depth-integrations.md).


<a id="record-plan-vda-trt-parity"></a>
## vda-trt-parity

Checkpoint date recorded in source: 2026-09-04.

> Recorded outcome: Engines built; numerical acceptance failed (TensorRT-path nonfinite outputs)

### Evidence (2026-09-04)

> Initial build report: `out/vda-trt-parity/6d88b187d10544109622dc463ec77774/report.json`.
> Warmup and cached plans build successfully with TF32 disabled and 2 GiB workspace.
> All 36 comparisons ran (three frames plus fresh warmup, nine tensors each).
> Parity fails; no tolerances were relaxed and no default was changed.

> Diagnostic rerun with the same plans:
> `out/vda-trt-parity/3bbb88a3c97b460599f90ddde3fdb4f5/report.json`.
> PyTorch outputs are finite throughout. TensorRT-path depth contains 35,280
> nonfinite values on every checked step. Warmup cache_5 has 11,520 nonfinite
> values; cache_6 and cache_7 have 46,080 each. Other cache outputs pass the
> declared numerical gate. Repeated fresh warmup reproduces the issue, so cache
> feedback accumulation is not necessary to trigger it.

> This localizes the problem to the exported/TensorRT execution path, not yet to a specific operator or a TensorRT defect. Do not clamp/replace NaNs to hide the issue or ship these experimental plans.

> The initial failed report contains JSON NaN metrics; the diagnostic runner now
> records null error magnitudes and explicit per-backend nonfinite counts instead.
> TensorRT warns about default-stream synchronization; this experiment makes no
> speed claim. Normal-size export, autocast parity, long cache horizon and actual
> cut-reset streaming integration are still unverified.

> ```powershell
> out/vda-oracle-env/Scripts/python.exe v1/test_vda_trt.py --input 'samples/input.mp4'
> # Optional diagnostic reuse of this locally built experiment (not a production cache):
> out/vda-oracle-env/Scripts/python.exe v1/test_vda_trt.py --input 'samples/input.mp4' --plans out/vda-trt-parity/6d88b187d10544109622dc463ec77774
> ```


<a id="record-plan-vda-trt-pipeline"></a>
## vda-trt-pipeline

Checkpoint date recorded in source: 2026-09-04.

> Recorded outcome: Development pipeline and short lifecycle checks passed

### Evidence (2026-09-04)

> `out/vda-trt-pipeline/60fdd5ee3ecc4593b1b8bdf6581024eb/report.json`:
> 124-frame supplied clip completes with actual TensorRT depth inference, CPU
> stereo synthesis and NVENC encoding. Output decodes 124 frames at 2112x608;
> audio presence is retained (not a listening/sync quality certification).
> Cancellation after the first frame and injected second-inference failure
> preserve prior output bytes, remove temporary files, close the engine/cache
> and leave tracked subprocesses exited. A subsequent conversion succeeds.
> Direct cut reset reproduces the first depth array exactly. A 48-frame
> same-resolution synthetic cut fixture produces exactly one pipeline cut reset
> and two backend resets including start.

> `v1/vda_trt_experiment.py` requires exact hashes of locally validated plans,
> TensorRT 11.2.1.2, SM120, and a transform resolving to 518x896. Unsupported
> source dimensions/aspect ratios fail explicitly. It uses a dedicated CUDA
> stream, keeps bound inputs alive through synchronization, validates every depth
> and cache output as finite, and retains at most 42 cache entries. PyTorch is
> used for GPU buffers/interpolation, not a fallback depth model. Native copies
> remain explicit and zero-copy is not claimed.

> No production registry entry or new user mode was added; the four public modes still use DA2. This developer binding requires the isolated environment and existing local FFmpeg preview assets. No executable was rebuilt/distributed. Hardware failure, long-duration leaks, additional aspect ratios, visual quality and PyTorch-autocast comparison remain open.

> ```powershell
> out/vda-oracle-env/Scripts/python.exe v1/test_vda_trt_pipeline.py --input 'samples/input.mp4'
> ```

> Existing 76 Python tests, seven process-tree checks and C++ regression pass.


<a id="record-plan-vda-widescreen"></a>
## vda-widescreen

Checkpoint date recorded in source: 2026-09-04.

### Results

> - Fresh artifact `out/vda-local/518x924-fp32/`: 585/585 depth/cache/reset
>   comparisons, max absolute error 0.000128269. Old 518x896 plans untouched.
> - `out/vda-application/c74cf754a2c94f1ea2105a5bf14a6a69/report.json`: exact
>   upstream preprocessing, first-depth parity, reset/owner/double-close,
>   cancel/failure preservation and 124-frame 1080p H.264/audio conversion;
>   public worker 48-frame HEVC input/output with one cut and two resets.
> - `out/vda-widescreen/07afaccdee26490c8262cc61b90b646f/report.json`: public
>   launcher auto-selects original 518x896 for 124 frames and 518x924 for the short
>   4K HEVC fixture, preserving 12 frames, audio and hvc1 tag as 7680x2160 SBS.
>   Every output frame decodes. 4K preprocessing is exactly equal to pinned source,
>   first-frame depth max error 0.000048161. First SBS preview inspected for layout.
> - Input fixture `out/vda-widescreen-fixtures/e27e0df90d9949e885fc6c3e12aecacb/`
>   explicitly letterboxes/scales the original to 1080p; the 4K test upscales that
>   copy. Original user media is unmodified. These are compatibility fixtures,
>   not native-4K quality or general-content acceptance.
> - 87 Python tests, seven process-tree cases and C++ CTest pass. Actual Tk GUI
>   construction/worker profile-root propagation and mode rejection pass.
> - Product, architecture, security, reliability, quality and local usage documents
>   updated. No portable rebuild, release, commit or push performed.

> Still deferred: other aspect ratios/GPU/TRT versions, long-duration 4K throughput,
> native-content quality corpus, one-hour soak and VR validation. DA2 defaults,
> VDA streaming-only semantics and Performance rejection remain unchanged.


<a id="record-reference-vda-local-preview"></a>
## vda-local-preview

Checkpoint date recorded in source: 2026-09-04.

> Status: Implemented and locally verified, 2026-09-04. Not a public release.

### Run on the current development machine

> The launcher preselects VDA + Video Quality and supplies `out/vda-local` as the
> trusted profile root plus runtime/media-tool directories. Choose input/output
> and press Convert; input preflight matches the engine before output mutation.
> Do not launch the old portable executable expecting VDA: it has not been rebuilt.

> ```powershell
> .\scripts\run-vda.ps1 -Diagnostics
> .\scripts\run-vda.ps1 -InputVideo 'samples/input.mp4' `
>   -OutputVideo '.\out\avatar-vda-sbs.mp4' -Mode video-quality
> # Optional HEVC output:
> .\scripts\run-vda.ps1 -InputVideo '<supported-input.mp4>' `
>   -OutputVideo '<output.mp4>' -OutputCodec hevc
> ```

### Reproduce the developer build

> - Python: `out/vda-oracle-env/Scripts/python.exe` (3.13.14).
> - Source: `out/vda-source`, official revision
>   `4f5ae23172ba60fd7bc11ef671cca678842c7072`, clean worktree.
> - Small checkpoint: `out/models/vda-small/video_depth_anything_vits.pth`, SHA256
>   `13379300b739e659f076a59d52e9801bd8d38c541a7e71f73bbca4dcfb013609`.
> - Artifacts: `out/vda-local/518x896-fp32/manifest.json` and
>   `out/vda-local/518x924-fp32/manifest.json`, each with its own two `.plan` files.

> ```powershell
> out/vda-oracle-env/Scripts/python.exe -m pip install onnx==1.18.0 onnxruntime==1.22.1 protobuf==7.36.1
> out/vda-oracle-env/Scripts/python.exe -m pip install --no-deps `
>   'C:\TensorRT\TensorRT-11.2.1.2\python\tensorrt-11.2.1.2-cp313-none-win_amd64.whl'
> out/vda-oracle-env/Scripts/python.exe v1/build_vda_artifact.py `
>   --input '<supported-validation-clip-with-at-least-64-frames.mp4>' `
>   --output out/vda-local/new-518x896-fp32
> # Build the independent 16:9 profile (new folder only):
> out/vda-oracle-env/Scripts/python.exe v1/build_vda_artifact.py `
>   --input '<16-by-9-validation-clip-with-at-least-64-frames.mp4>' `
>   --profile 518x924 --output out/vda-local/new-518x924-fp32
> ```

### Verification commands and evidence

> ```powershell
> .\scripts\test-v1.ps1
> $env:PYTHONPATH = 'v1'
> out/vda-oracle-env/Scripts/python.exe v1/test_vda_application.py --input '<supported-clip.mp4>'
> # A profile root supports either accepted ratio:
> out/vda-oracle-env/Scripts/python.exe v1/test_vda_application.py --input '<1080p-clip.mp4>' --engine-dir out/vda-local
> out/vda-oracle-env/Scripts/python.exe v1/test_vda_gui.py --input '<supported-clip.mp4>'
> out/vda-oracle-env/Scripts/python.exe v1/compare_vda_application.py --input '<supported-clip-up-to-124-frames.mp4>'
> out/vda-oracle-env/Scripts/python.exe v1/test_vda_widescreen.py --widescreen '<1080p-clip.mp4>' --original '<1056x608-clip.mp4>'
> ```

### Full-sequence widescreen comparison and known visual gap

> The 1080p 124-frame source FP32/TRT comparison passes at max depth error
> 0.000106096; decoded SBS MAE is 0.203546/255 (max 163), not pixel-identical output.
> Report: `out/vda-application-comparison/041c9cf0d48d44da89904c6b000f739b/report.json`.
> The original-profile rerun also passes, retaining its previous depth and pixel
> comparison figures: `out/vda-application-comparison/cc20289b687f420c85c86691a04deed6/report.json`.
> 93 Python tests plus process-tree/C++ gates pass. These diagnostics include
> reference inference and hashing; their timing is not performance evidence.

> **Known quality gap:** the padded 1080p fixture shows dark hand-edge trails in TRT and source-reference SBS. Its 22-pixel side bars mix black and green border colors, disabling the existing flat-background refinement (0/124 frames versus 124/124 for the original). Numerical agreement is not a quality pass. This is specific observed content, not proof that all 16:9 inputs exhibit the artifact. See [vda.md](vda.md#record-plan-vda-profile-comparison).

> 2026-09-05 follow-up: the development-only letterbox-aware candidate now passes
> a same-inference 124-frame A/B. Baseline applied flat-backdrop refinement 0 times,
> candidate 124 times. At inspected frames 20/62/100, the dark hand-edge trail is
> visibly reduced; exact original black padding is restored in both eyes before
> encoding, without changing dimensions or source RGB/depth. The outputs retain
> audio. This supports the suspected guard interaction on this clip, not general
> quality/VR acceptance. Normal GUI/launcher defaults are **unchanged** pending
> broader content and review. Review artifacts:
> `out/vda-letterbox/c5886097b05f4ddfa63b89b82aa8e3b3/baseline.mp4` and `candidate.mp4`.
> Reproduction and limits: [vda.md](vda.md#record-plan-vda-letterbox-refinement).

### 16:9 extension evidence

> Evidence: `out/vda-local/518x924-fp32/`,
> `out/vda-application/c74cf754a2c94f1ea2105a5bf14a6a69/`, and
> `out/vda-widescreen/07afaccdee26490c8262cc61b90b646f/`.
> The 1080p diagnostic copy explicitly scales/letterboxes the supplied original;
> 4K is an upscaled compatibility fixture, not a native detail/quality sample.

### Original-profile evidence

> Build gate: all 585 comparisons passed; max absolute error 0.000105262.
> Application gate: 124-frame H.264 + audio conversion, reset determinism,
> owner-thread/double-close, cancel/injected failure preserving previous output and
> closing media processes, public worker HEVC input/output with 48 frames and one
> cut/two resets. GUI construction, command propagation and mode rejection passed.

> Matched source FP32 comparison: all 124 resized-depth frames passed, max absolute
> error 0.000141621. Encoded-and-decoded SBS differs (mean absolute 0.290933 / 255,
> maximum 108); floating-point edge decisions and encoding mean numerical depth
> agreement is **not pixel-identical SBS**. Against source autocast, mean difference
> is 0.314155 / 255, maximum 229. Neither comparison ranks quality against DA2.
> Static left/right hand inspection artifacts at frames 20/60/100 are retained;
> subtle moving-edge quality and headset comfort are not certified by this test.

> Evidence directories under ignored `out/`:

> - `vda-local/518x896-fp32/` (manifest, parity report, notices and build logs).
> - `vda-application/6bb84a35a563447fa63a88a5a3047d88/` (lifecycle/media report).
> - `vda-application/af85ff460d0d45399daaca10f8b7ca1a/` (passing final rerun after
>   constructor/close ownership and preprocessing telemetry changes).
> - `vda-application-comparison/b22c5885f26f4cde91e1043660d46bbb/` (three videos,
>   depth comparisons, full-eye and hand crops).
