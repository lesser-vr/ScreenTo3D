# Matched model and content comparisons

Historical evidence by recorded checkpoint. Current support is in
[implementation status](../implementation-status.md).

## Records

- [explicit-backend-performance-2026-09-06](#record-result-explicit-backend-performance-2026-09-06)
- [live-action-model-decision-2026-09-05](#record-result-live-action-model-decision-2026-09-05)
- [model-evaluation-2026-09-05](#record-result-model-evaluation-2026-09-05)
- [public-video-corpus](#record-plan-public-video-corpus)
- [da2-vda-review](#record-plan-da2-vda-review)
- [live-action-model-decision](#record-plan-live-action-model-decision)

<a id="record-result-explicit-backend-performance-2026-09-06"></a>
## explicit-backend-performance-2026-09-06

Checkpoint date recorded in source: 2026-09-06.

> 2026-09-06. Actual backend identities, not mode-label proxies.

### Method

> `v1/benchmark_explicit_backends.py` runs isolated fresh worker processes,
> interleaved by round, with one discarded warmup and three measured runs per
> backend. All use the same prepared 1920x1080 60fps/60-frame HEVC input with audio,
> Video Quality policy, CUDA SBS projection and H.264 Full SBS output. Every output
> is fully decoded and checked for 60 frames, 3840x1080 geometry and matching audio
> policy. Runtime telemetry must resolve the expected backend identity.

> The current system condition is Premiere Pro closed and monitor off after a
> monitor on/off transition. The DA2 control stayed above the 10-fps recurrence
> guard; no unexplained system collapse occurred. VDA/oVDA are not subject to that
> threshold because their expected current throughput is lower.

> Evidence: `out/explicit-backend-comparison/current-v2/report.json` and its 12
> MP4/JSON/log groups. `passed=true`. A first preserved attempt under `current/`
> stopped after one valid Small warmup because the harness expected the descriptive
> string `tensorrt-fp16` while the backend contract reports `tensorrt`; no model or
> runtime behavior changed for the clean rerun.

### Results

> | Explicit backend | Runtime | Median whole-pipeline fps | Range |
> | --- | --- | ---: | ---: |
> | DA2 Small | TensorRT (FP16 model artifact) | 15.109 | 14.987–15.116 |
> | VDA Small | TensorRT FP32 | 10.403 | 10.384–10.438 |
> | oVDA Small c16 | TensorRT FP32 | 10.898 | 10.894–10.946 |

> Mean stage times across the three measured jobs:

> | Backend | Depth inference | CUDA temporal/SBS | Frame total |
> | --- | ---: | ---: | ---: |
> | DA2 Small | 2.53 ms | 44.00 ms | 58.18 ms |
> | VDA Small | 33.21 ms | 40.17 ms | 81.56 ms |
> | oVDA Small c16 | 34.89 ms | 39.56 ms | 82.48 ms |

> oVDA's median whole-job rate is about 4.8% above VDA in this small sample, but
> its depth stage is slower and its frame-total mean is higher. Startup, drain and
> other job costs affect whole-pipeline FPS, so this is not evidence that oVDA
> inference is faster. Both temporal backends are roughly 28–31% below Small in
> whole-pipeline FPS; neither currently provides the hoped-for speed improvement.

> This file path uses the older host-returning backend and local CUDA projection.
> It is not the newer DA2-only live native-texture path that reached ~60 output fps.
> Therefore 15.1 fps here does not contradict the live result, and these numbers
> must not be presented as predicted integrated-live output rates.

### What streaming does and does not buy today

> Both temporal backends process every input frame and reset state on cuts. oVDA
> keeps a fixed 16-slot feature cache (190,857,216 bytes at this profile), so its
> state remains bounded for arbitrarily long sequential input. VDA reports a
> 42-entry bounded cache in this adapter. This supplies online temporal context
> without waiting for future frames; it is a temporal consistency/memory property,
> not an automatic throughput advantage.

> Current oVDA inference allocates output tensors per frame, synchronizes its CUDA
> stream, updates or occasionally concatenates cache tensors, resizes depth and
> returns an owned CPU NumPy result. It reports `zero_copy=false`. VDA likewise
> assembles cache inputs/outputs and returns depth to CPU. These paths do not use
> the live candidate's device-resident depth/native output contracts.

### Device-depth follow-up

> The isolated oVDA token retained source-resolution depth on its owning CUDA
> stream and rejected reuse before completion and use after completion. It matched
> the host depth bit-for-bit on 12/12 frames. Pure depth throughput improved from
> 31.17 to 32.43 fps (+4.1%); this alone did not prove a useful consumer.

> A second separate DLL then fed host or device depth into the identical CUDA
> temporal, guided-filter and SBS path. Final left/right output matched bit-for-bit
> on 12/12 frames. Three measured runs with alternating execution order yielded
> median 27.61 fps for host depth and 29.21 fps for device depth (+5.8%). Evidence:
> `out/ovda-device-depth/current-v3/report.json` and
> `out/ovda-device-post/current-v2/report.json`.

> This validates a real but modest benefit from removing the full-resolution
> depth D2H/re-upload pair. It does not establish integrated live FPS: decoded RGB
> is still uploaded, final SBS is still read to host, synchronization remains, and
> the flat-background CPU refinement was outside this non-flat-source spike.

> An allocation follow-up preallocated model outputs and all 16 schedule tensors,
> and replaced saturated-cache concatenation with alternating fixed cache banks.
> It also preserved exact final SBS pixels, but changed median throughput only
> from 29.28 to 29.42 fps (+0.47%) while reserving 381.7 MB for two cache banks,
> plus 13.8 MB of output buffers. It is rejected for product promotion on this
> evidence. The clean three-path result is
> `out/ovda-device-post/current-v3/report.json` (`passed=true`).

> The remaining performance work should therefore target larger boundaries:
> native device input/output and bounded presentation decoupling with correct
> frame IDs, epochs and resource leases. Integrating oVDA into live selection
> before those gates would add license and lifecycle surface while remaining well
> below fresh 60 Hz depth, so it is not justified by this result alone.

> The next isolated output-boundary test reused the proven two-slot D3D11 external
> memory/keyed-mutex transport. Its 12-frame diagnostic readback matched host SBS
> RGB exactly and kept alpha opaque. Timed runs replaced readback with a consumer
> acquire/release only: device-depth plus host SBS measured 29.26 fps, while
> device-depth plus shared texture measured 30.06 fps (+2.75%). Together with the
> depth handoff, that is about +8.6% over the matched 27.68-fps host-depth/host-SBS
> path. The 60-frame accounting removes 497,664,000 depth-readback bytes and
> 746,496,000 host-SBS-readback bytes. Evidence:
> `out/ovda-device-texture/current/report.json` (`passed=true`).

> This is a component result, not live output FPS. It still starts from decoded
> host RGB, performs CPU-driven model preprocessing and submission, synchronizes
> each frame, and uses a same-process diagnostic texture consumer. Since fresh
> oVDA depth remains near 30 fps, presentation decoupling cannot honestly be
> called fresh 60-Hz processing without a separately approved sampling/repetition
> policy and corresponding motion/cut/VR quality gates.

### VDA device-boundary follow-up

> VDA was then tested independently rather than inheriting the oVDA conclusion.
> Its owned device token matched raw depth and final host SBS bit-for-bit on 12/12
> frames, rejected pending reuse and expired tokens 12/12, and produced exact
> shared-texture RGB/alpha on 12/12. Three rotating-order component runs measured
> 27.544 fps for host depth/host SBS, 29.486 fps for device depth/host SBS, and
> 30.270 fps for device depth/shared texture: +7.05%, then +2.66%, or +9.89%
> combined. Evidence and remaining gates are in
> [vda.md](vda.md#record-result-vda-device-boundary-2026-09-06) and
> `out/vda-device-pipeline/current-v2/report.json`.

> This makes VDA's boundary candidate marginally faster than oVDA's comparable
> 30.063-fps texture spike, but the difference is too small and the runs are not a
> single isolated cross-backend benchmark. It is not a winner decision. Both
> remain near 30-fps fresh depth and below the DA2 live default's established
> behavior.


<a id="record-result-live-action-model-decision-2026-09-05"></a>
## live-action-model-decision-2026-09-05

Checkpoint date recorded in source: 2026-09-05.

> Status: Accepted current-delivery default decision; bounded evaluation complete.
> Owner: Model integration and quality. Date: 2026-09-05.

### Scope and provenance

> The official [UVG-VCM dataset](https://tie-ultravideo.rd.tuni.fi/UVG-VCM/index.html)
> provides CC BY 4.0 sequences. This experiment uses its compressed, unannotated
> MP4 previews, not raw YUV or the dataset's depth ground truth. Attribution:
> Ultra Video Group, Tampere University; T. Partanen, M. Anttila, R. Kortelahti,
> G. Gautier, A. Mercat and J. Vanne, *UVG-VCM: Benchmarking dataset for
> machine-oriented visual data compression*, QoMEX 2026.

> All four downloaded previews are H.264 3840x2160, 60fps, without audio. Excerpts
> at 1–3 seconds are explicitly downsampled to 1280x720 with Lanczos, H.264 CRF18,
> 120 frames, original cadence and no crop/padding/audio invention. OfficeWalk is
> an indoor **moving-camera** shot, not a person close-up despite its name.
> HighwayDrive supplies camera/vehicle motion; FloorballGame supplies people,
> thin sticks and fast articulation; ParkingGarage supplies an approaching car,
> backlighting, dark foreground and exposure change, not a calibrated noise test.
> KnownCut concatenates the first 60 excerpt frames of OfficeWalk and ParkingGarage;
> the second shot starts at zero-based frame 60. It is a derived cut fixture, not
> a fifth independent source. Source URL/hash pins are in `v1/evaluate_live_action.py`.

> [UVG Beauty](https://tie-ultravideo.rd.tuni.fi/dataset.html) separately supplies
> hair/face close-up coverage: copyright Digiturk, distributed by UVG, **CC BY-NC
> 3.0**. Citation: A. Mercat, M. Viitanen and J. Vanne, *UVG dataset: 50/120fps 4K
> sequences for video codec analysis and development*, MMSys 2020. This is local
> non-commercial evaluation material; do not bundle it into a commercial product.
> The official 3840x2160 HEVC elementary stream lacks reliable container timing;
> its published 120fps is explicitly applied. Frames 0–119 form a one-second
> 1280x720 H.264 excerpt. No cadence reduction, crop, padding or audio addition.
> Source SHA256: `88af90a616635b1a8b726d0260d724da9f662aaf321e5c376eab9ed8ce1eed7f`.
> Every result directory includes the relevant attribution and transformation note.

### Diagnostic method and limitations

> `temporal_diagnostics.py` operates only in the diagnostic worker; production
> conversion/model/render defaults are untouched. Each model receives exactly the
> same decoded input, Video Quality rendering/encoding policy and output geometry.
> Small keeps its square input; Base/VDA use validated 518x924 FP32 profiles. These
> are end-to-end backend comparisons, not equal architecture/resolution ablations.

> Raw depth is independently 5th/95th-percentile normalized per frame before
> renderer EMA and reduced with RGB to 480px width. OpenCV Farneback forward and
> backward source-image flow maps old depth into the current image grid. Valid
> pixels require in-bounds coordinates, forward/backward residual <=1 pixel,
> maximum RGB residual <=12/255 and a 3x3 erosion. Image-edge neighborhoods use
> Canny 60/120 dilated 5x5. Report valid coverage and aligned absolute depth change
> both globally and near edges. Null means no valid pixels, never zero error.
> Frame means are averaged, not pooled pixels. Production-detected cut pairs are
> excluded and re-prime the diagnostic's previous frame.

> Four unit tests cover analytic translation, injected depth error, inconsistent
> flow, photometric occlusion, actual static Farneback, cut exclusion/re-priming,
> non-finite data and the 124-frame cap. Only one previous reduced RGB/depth pair
> and <=124 scalar records are retained. The optical-flow method follows
> [OpenCV's primary documentation](https://docs.opencv.org/4.x/d4/dee/tutorial_optical_flow.html).

> These are **temporal proxies, not depth accuracy, ghosting or VR comfort scores**.
> Per-frame normalization hides global scale drift; smooth or incorrect depth can
> score well. Flow may fail on blur, low texture, occlusions or lighting changes,
> and masks may omit the hardest boundaries. No statistical significance or
> cross-scene aggregate winner is claimed. The 120fps Beauty metric must not be
> ranked against 60fps scenes without accounting for time interval.

> Every detected cut additionally compares the current SBS RGB against a fresh
> renderer with identical current depth: exact equality is required. A separate
> actual VDA test compares post-reset depth after eight prior frames with a newly
> created engine on the same decoded post-cut frame (atol=rtol=.001). This separates
> renderer EMA reset from model cache reset; neither proves all possible cuts.

### Initial completed live-action results

> Main report: `out/live-action-evaluation/eab25eb5c4b948b2a11b5ce3dad79a2f/report.json`.
> All 15 conversions pass, 120 frames each, 2560x720 SBS, matching source hashes,
> full-frame decode and preserved absence of audio. KnownCut is detected at frame
> 60 in every model; fresh-renderer maximum absolute RGB difference is zero.

> | Scene | Small aligned MAE | Base aligned MAE | VDA aligned MAE | Valid coverage |
> |---|---:|---:|---:|---:|
> | OfficeWalk | .008963 | .006765 | .006373 | 73.26% |
> | HighwayDrive | .003778 | .003086 | .002840 | 91.84% |
> | FloorballGame | .001778 | .001151 | .001053 | 88.16% |
> | ParkingGarage | .001754 | .001273 | .001053 | 92.69% |
> | KnownCut, cut pair excluded | .005364 | .004111 | .003902 | 83.01% |

> Corresponding edge MAEs (Small/Base/VDA): Office .010918/.008523/.008160;
> Highway .005473/.004769/.004496; Floorball .002363/.001623/.001619;
> Parking .001576/.001118/.000874. Identical coverage across models confirms the
> mask is source-derived rather than model-selected. VDA has lower proxy changes
> than Small on these clips; Base is intermediate. This does not establish spatial
> correctness or visibly eliminated ghosting.

> Source contact sheets and Floorball left-boundary frames 0/30/60/90/119 were
> visually inspected. Thin sticks/limbs remain recognizable; contour differences
> are visible and source motion blur is present. No perceptual winner is assigned
> from sampled stills. Labeled central-boundary review videos and both-eye stills
> are generated; a full blinded playback/VR review has not been performed.

### Decision criteria

> Supplement report: `out/live-action-supplement/475182585c664d51977a3a68ad421951/report.json`.
> Beauty adds three passing 120-frame conversions (2560x720, 120fps, no audio,
> matched decoded-input hashes), for **18 conversions / 2160 output frames** total.
> Beauty aligned MAE Small/Base/VDA: .007640/.006140/.003036; edge MAE:
> .011483/.008595/.006630; valid coverage 91.01%, edge-valid coverage 18.25%.
> Its five-time-point left face/hair timeline was inspected; source motion blur
> and model-dependent contour changes remain, without establishing a visual winner.
> VDA's actual post-reset depth versus fresh-engine depth has **max absolute error
> 0.0** on the selected frame after eight prior history frames.

> The canonical V1 gate passes **112 Python tests, seven process-tree cases and
> C++ CTest**. Diagnostic additions do not modify the production renderer or model
> code. Current machine snapshot: RTX 5090, driver 616.56, Windows; accepted local
> TensorRT 11.2.1.2 plans. Source hashes, model/plan identity, full policy and raw
> per-frame diagnostics are retained in reports. CPU test/build work overlapped
> some diagnostic runs; GPU model conversions were sequential. No new timing claim.

> Default promotion requires more than one favorable proxy: installation envelope,
> license, quality beyond smoothing, and end-to-end cost all matter. Existing
> [repeated timing/memory evidence](model-comparisons.md#record-result-model-evaluation-2026-09-05) on the original
> avatar reports median whole-conversion fps Small 18.289, Base 11.582, VDA 12.706;
> sampled active device-memory deltas approximately 254MB/1076MB/2001MB. Those are
> old short-clip measurements, not current real-content throughput or peak VRAM.
> Current diagnostic timings include flow, hashes and extra cut rendering and must
> not be used as a benchmark. Base weights remain CC-BY-NC-4.0; two FP16 candidates
> remain rejected. VDA is streaming Small, not oVDA or offline-windowed VDA.

### Accepted current-delivery defaults

> | Mode | Default | Decision and next promotion requirement |
> |---|---|---|
> | Performance | DA2 Small | Retain low-cost backend and adaptive cadence. VDA requires every frame and is incompatible with this mode's cadence contract. |
> | Balanced | DA2 Small | Base FP32 remains explicit NC selection. Temporal proxies improved, but spatial/perceptual benefit sufficient to justify extra cost and NC restrictions is not established. |
> | Video Quality | DA2 Small | VDA is the leading optional temporal candidate on this expanded corpus; retain explicit opt-in until broader perceptual/spatial quality and distributable installation support are established. |
> | Offline Quality | DA2 Small | Retain existing implementation, without calling it a dedicated offline model. Explicit VDA still means streaming inference. A native offline backend remains a separate implementation milestone. |

> This is a concrete decision to **retain** defaults for the current local delivery,
> not a claim that Small wins quality or that all four proposed model assignments
> are implemented. Do not silently switch to VDA/Base, relax FP16 acceptance, or
> bundle NC assets. Model-choice overrides remain visible. Rejected alternatives:
> promote Base from its name/size, promote VDA from temporal MAE alone, and label
> streaming VDA as offline quality implementation. Revisit on spatial/occlusion
> evidence and blinded playback, not just a smoother depth field.

> Release, one-hour soak and VR playback remain deferred by user direction. Broader
> 4K/low-fps/dark-noisy scenes, fades and sustained performance remain outside this
> bounded 1–3 task; the benchmark's full support matrix is not declared complete.

### Reproduce

> Obtain exact pinned sources from their official URLs, then use the prepared
> local model engines and Python environment:

> ```powershell
> $env:PYTHONPATH = 'v1;out/v1-python-deps'
> out/vda-oracle-env/Scripts/python.exe v1/evaluate_live_action.py
> out/vda-oracle-env/Scripts/python.exe v1/evaluate_live_supplement.py --live-root <new-live-result-directory>
> ./scripts/test-v1.ps1
> ```

> Both runners create unique result directories and retain partial reports on
> conversion failure. Never run GPU experiments concurrently. The optional
> `--prepare-only` followed by `--prepared <directory>` allows visual selection
> before conversion and rejects existing result videos instead of overwriting.


<a id="record-result-model-evaluation-2026-09-05"></a>
## model-evaluation-2026-09-05

Checkpoint date recorded in source: 2026-09-05.

> Decision: retain existing DA2 Small mode defaults. DA2 Base FP32 and VDA remain
> explicit selections. Base now supports the original aspect ratio and standard
> 16:9. Neither tested FP16 candidate passes the specified numerical acceptance
> gate, so no public FP16 option is enabled.

### Comparison conditions

> RTX 5090, driver 616.56, TensorRT 11.2.1.2, torch 2.7.1+cu128, Windows, dirty
> development worktree. The supplied original is 1056x608, 24fps, 124 frames with
> audio. All variants use Video Quality stereo/temporal/encode policy, H.264 Full
> SBS 2112x608, CPU stereo and native model preprocessing. Small uses its existing
> square model input; Base/VDA use the aspect-preserving 518x896 profile. VDA has
> native temporal state, unlike Small/Base. These differences are intentional.

> `v1/evaluate_depth_models.py` runs separate processes, one discarded warmup plus
> five measured conversions per variant, interleaved by repetition. Reported FPS
> uses frames divided by the conversion-call wall time, including engine startup
> inside conversion and audio mux, excluding Python imports and prior binding
> validation. All measured media pass full decode/count/geometry/audio checks.
> Separate quality runs enable source hashes and depth diagnostics. No competing
> agent GPU workloads were started during these timed runs. GPU state snapshots
> are retained, not a continuous clock/power trace. This short clip does not satisfy
> the sustained workload/corpus gates in the current
> [benchmark contracts](../BENCHMARKS.md).

> Evidence root: `out/model-evaluation/1086d3d9ede94afc8a3740f9177aeeee/`.
> Raw per-run JSON/logs, videos and `report.json` remain under that root.

> | Variant | Median whole-conversion fps | Range, five runs | Numerical status |
> |---|---:|---:|---|
> | DA2 Small existing backend | 18.289 | 18.016–18.366 | Existing accepted local backend |
> | DA2 Base FP32 | 11.582 | 11.562–11.606 | Pass |
> | VDA Small FP32 | 12.706 | 12.684–12.719 | Existing accepted local backend |
> | Base mixed FP16 candidate | 14.959 | 14.833–14.988 | Rejected |
> | Base FP32 encoder / FP16 head candidate | 14.721 | 14.612–14.727 | Rejected |

### FP16 decision

> ONNX Runtime's converter keeps FP32 I/O, Resize, LayerNormalization and Softmax;
> the second candidate additionally blocks encoder nodes from conversion. The
> graph is topologically sorted after conversion and checked before TensorRT build.
> The original FP32 reference is restored after fixed-position export, TF32 is off,
> and tolerance remains atol=rtol=0.001 for every comparison. All outputs are finite,
> but both candidates fail all 68 comparisons (64 real frames, first-frame repeat,
> black/gray/green synthetic inputs). The second graph was inspected: encoder qkv
> bias initializers remain FP32, and blocked encoder MatMul nodes remain present.

> | Candidate | Maximum absolute model-grid depth error | Plan bytes |
> |---|---:|---:|
> | Mixed FP16 | 0.176432610 | 200647284 |
> | FP16 head | 0.091629028 | 205872564 |
> | Original-profile FP32 reference engine | 0.000189781 | 402367692 |

> FP16 reduces plan storage by roughly half and improves short-clip throughput,
> but those benefits do not override the failed accuracy gate. Failed candidates
> are executed only through an explicitly labeled diagnostic path, never registered
> in GUI/defaults. Reports: `out/da2-base-trt/c2fab6ca37cc4d1ab5c4f3458b3e2127/`
> and `out/da2-base-trt/a8e14fb567f243029c101091043e18b1/`. An earlier converter
> node-order failure is retained at `f7451fff6ed449daab0757829f2eca9d`.

### Temporal and edge observations

> Separate memory probes (`*-memory-isolated.json`) observed device-free-memory
> deltas from a CUDA-initialized baseline to the end of frame processing while the
> engine remained alive: Small 253755392 bytes, Base FP32 1075838976, VDA 2000683008,
> mixed FP16 505413632, FP16 head 505413632. These include native TensorRT and
> allocator reservations, unlike the PyTorch-only peak field in timed reports.
> They are device-wide snapshots, not process-isolated peaks or leak measurements.
> An initial probe overlapped a diagnostic and was superseded by this isolated
> sequence; use only `*-memory-isolated.json` for this comparison.

> Reproduce a separate memory probe by adding `--one base --output <new.mp4>
> --memory` to the evaluation command. Repeat per variant with no other GPU job.
> Never mix these observations into the five-run timing table.

> Quality-run decoded source hashes match. Every input/output frame is decoded.
> `hands-20.png`, `hands-62.png`, `hands-100.png`, `left-hand-timeline.png` and
> `hand-motion.mp4` align source/model/eye/time labels. The motion artifact has
> inspection headers and no audio; the separate model output videos retain audio.
> Frame 62 and the five-time-point left-eye hand timeline were visually inspected.
> All three retain recognizable single hand contours in these inspected samples;
> small contour/position differences do not establish a perceptual winner.

> | Proxy | Small | Base FP32 | VDA |
> |---|---:|---:|---:|
> | Raw-depth static-pixel temporal MAE, normalized 0–1 | 0.00693039 | 0.00745474 | 0.00241823 |
> | Encoded stable-green-background temporal MAE, 0–255 | 0.28287949 | 0.28272461 | 0.27995713 |
> | Far-green-background contamination fraction | 0 | 0 | 0 |

> Raw depth is independently normalized by each frame's 5th/95th percentiles before
> renderer EMA. The eroded color-static mask averages 79.786% coverage and uses no
> optical flow; matching colors can miss motion. Green-background checks deliberately
> exclude a 20-pixel boundary neighborhood. They do not quantify subtle hand-edge
> ghosting or depth accuracy. VDA is more stable on this proxy; encoded background
> differences are small. No ground-truth depth, blinded playback review, broad
> natural-content corpus or headset comfort test is available in this result.

> Small is fastest here, Base does not demonstrate a quality advantage on this clip,
> and VDA's temporal proxy supports keeping it available for explicit evaluation.
> This evidence supports retaining defaults, not assigning all modes to Base/VDA.

### Reproduction

> ```powershell
> $env:PYTHONPATH = 'v1;out/v1-python-deps'
> out/vda-oracle-env/Scripts/python.exe v1/evaluate_depth_models.py --input 'samples/input.mp4'
> ```

> This command intentionally includes rejected local FP16 artifacts for diagnostic
> comparison. Their original local-build report and hashes must remain available.
> User conversion should use `scripts/run-da2-base.ps1` or `scripts/run-vda.ps1`.


<a id="record-plan-public-video-corpus"></a>
## public-video-corpus

Checkpoint date recorded in source: 2026-09-05.

> License/source: https://peach.blender.org/about/ (CC BY 3.0).
> Required excerpt attribution: (c) copyright 2008, Blender Foundation /
> www.bigbuckbunny.org. Downloads: https://peach.blender.org/download/ and
> https://download.blender.org/peach/bigbuckbunny_movies/.
> Results are local tests; this does not authorize publishing the user's media.

### Acquired source and reproducibility

> Official archive: `big_buck_bunny_720p_h264.mov.zip`, SHA256
> `b0c9ade80b086179feee41514929de583966eec87c703575d97f051f88b33b67`.
> Extracted MOV SHA256:
> `45c8bafeb9a53df7f491198d2e71529701bcf1cd51805782089fac1d32869f9b`.
> Source is H.264 1280x720 at 24fps with AAC. Stored under
> `out/public-video-source/bbb720/`; the test runner rejects another source hash.
> The archive was obtained from the official Blender download directory linked
> above. No account/login or restricted media downloader was used.

> `v1/test_public_video_corpus.py` extracts these native-aspect-ratio four-second
> excerpts with libx264 CRF18/YUV420P and AAC, then runs the accepted Small, Base
> FP32 and VDA models using the same Video Quality stereo/encode policy:

> | Name | Source interval | Observed content / intended stress |
> |---|---|---|
> | bird-branches | 00:20–00:24 | Bird takeoff, thin branch, foliage, title text appearing after takeoff |
> | dark-fur-grass | 00:40–00:44 | Dark cave, shadowed fur, grass/rock boundary |
> | moving-foreground | 03:00–03:04 | Moving foreground followed by character group/tree/grass shot; occlusion and transition |

> This is a first animation pilot, not a live-action or full benchmark corpus.
> Future source selection should add real people/hair, camera motion and dark/noisy
> footage with separately verified rights and compatible aspect ratio. Existing
> green-screen contamination metrics are intentionally not applied to this corpus.

### Results

> Report: `out/public-video-tests/34fd85fccd77471a8fe9a1149b7e598e/report.json`.
> All nine conversions pass: 96 frames each, all output frames decode, 2560x720 SBS,
> audio retained and identical decoded-input hashes across models. Reported scene
> reset counts agree across models: 1, 0, 1 for the three excerpts respectively;
> these are detector observations, not manually annotated scene-cut ground truth.
> Source/left/right inspection sheets are saved at frames 0/48/95. Midpoint sheets
> for bird-branches and moving-foreground were visually inspected; model quality
> is not ranked from these stills. Original source and derived clips retain their
> own hashes, timestamps, transformation description and ATTRIBUTION.txt.

> Reproduce after obtaining the exact official source:

> ```powershell
> $env:PYTHONPATH = 'v1;out/v1-python-deps'
> out/vda-oracle-env/Scripts/python.exe v1/test_public_video_corpus.py
> ```

> Diagnostic depth-static-pixel metrics are retained in per-model JSON but are not
> a ground-truth depth score, ghosting score or sustained FPS comparison. No
> model defaults or production inference code changed in this corpus addition.


<a id="record-plan-da2-vda-review"></a>
## da2-vda-review

Checkpoint date recorded in source: 2026-09-05.

> Implemented `v1/compare_depth_models.py`, accepting an explicit trusted DA2
> model path (default `out/models/da2-small/model_fp16.onnx`) and VDA profile root.
> Production model lookup is unchanged. Six reused comparison-helper tests pass;
> compileall and diff whitespace checks pass.

> Passing evidence: `out/depth-model-comparison/146729fe49dc40de8108001189e2ede7/`.
> Both runs use the original 1056x608 input, produce 2112x608 H.264 with audio,
> decode all 124 frames, and match decoded-input hashes. Model fingerprints and
> runtime telemetry are recorded in `report.json`. Source, both eyes and lower
> frame inspection sheets are retained at frames 20/62/100. The frame-62 sheet
> was inspected at reduced display size; it is not temporal ghosting acceptance
> or a quality ranking. Separate full videos support subsequent playback review.

> An earlier diagnostic run failed output validation because input preflight was
> incorrectly used on already-SBS media; output inspection now reads ffprobe
> streams directly without a second width doubling. Its failed report remains
> under `26e8ad6b6f40446f93b53247c55081a3` and is not acceptance evidence.

> ```powershell
> $env:PYTHONPATH = 'v1;out/v1-python-deps'
> out/vda-oracle-env/Scripts/python.exe v1/compare_depth_models.py --input 'samples/input.mp4'
> ```


<a id="record-plan-live-action-model-decision"></a>
## live-action-model-decision

Checkpoint date recorded in source: 2026-09-05.

### Completed evidence

> - Four CC BY 4.0 UVG-VCM live-action excerpts, one derived known-cut fixture,
>   and separately attributed NC UVG Beauty hair close-up; no crop/padding.
> - 18 matched conversions / 2160 fully decoded SBS frames. Main result:
>   `out/live-action-evaluation/eab25eb5c4b948b2a11b5ce3dad79a2f/report.json`;
>   supplement: `out/live-action-supplement/475182585c664d51977a3a68ad421951/report.json`.
> - Motion-compensated depth/edge diagnostics, ambiguity masks and coverage;
>   four new unit tests. Known cut frame 60 produces exact fresh-renderer parity
>   in all models, and actual VDA reset/fresh-engine depth maximum error is zero.
> - Labeled boundary review videos, both-eye stills and left-eye time sequences;
>   source contact, sports and face/hair time sequences visually inspected.
> - 112 Python tests, seven process-tree cases and C++ CTest pass.
> - Accepted current-delivery decision: retain Small in all modes, with Base/VDA
>   explicit; VDA is the leading temporal candidate, not a proven quality winner.

> Owning result/decision: [model-comparisons.md](model-comparisons.md#record-result-live-action-model-decision-2026-09-05).
> This closes the bounded evaluation/default decision, not release or all future
> mode-backend/quality acceptance work. Existing release/soak/VR deferrals stand.
