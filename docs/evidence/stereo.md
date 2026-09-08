# Live stereo and numerical parity

Historical evidence by recorded checkpoint. Current support is in
[implementation status](../implementation-status.md).

## Records

- [live-parallel-projection](#record-result-live-parallel-projection)
- [live-parity-followup](#record-result-live-parity-followup)
- [live-resize-parity](#record-result-live-resize-parity)
- [live-sbs-results](#record-result-live-sbs-results)
- [public-live-tests](#record-result-public-live-tests)
- [live-parity-followup](#record-plan-live-parity-followup)
- [live-sbs-output](#record-plan-live-sbs-output)
- [live-parallel-projection](#record-plan-live-parallel-projection)

<a id="record-result-live-parallel-projection"></a>
## live-parallel-projection

Checkpoint date recorded in source: 2026-09-06.

### Contract and implementation

> Only the live CUDA hole resolver changes. The existing serial implementation in
> `experiments/cuda_projection/projection.cu` and file renderer stay unchanged.
> The new live build includes `resolve_parallel.cuh`: one 256-thread block per row
> uses prefix/suffix maximum scans to locate neighboring valid owners, then writes
> each pixel independently. Width dispatch uses 4/8/16 items per thread, covering
> the existing 16–4096 live input-width envelope without changing eye dimensions.

> The selected owner is exactly the old rule: use the pixel's owner if present;
> otherwise select the adjacent valid owner with smaller quantized depth; a tie
> chooses the left owner. Empty rows copy their own RGB. Leading/trailing holes
> and source-index tie behavior are preserved. There is no temporal approximation,
> inference skipping, resolution reduction or model/precision change.

> Block scratch is bounded (at most 4096 indices plus CUB scan storage per block),
> with no per-frame GPU allocation. Native owner/thread/stream/reset checks remain.
> Six fixed diagnostic events split left/right splat, resolve and D2H intervals;
> shared latest-value telemetry grows from 24 to 30 integers, not an event queue.
> Splat intervals also include owner clear (and right-side shift negation).
> Intervals include GPU scheduling/host enqueue gaps; do not sum sampled medians
> as a precise complete frame trace.

> `DEPTHSBS_LIVE_RESOLVE=serial|parallel` is an explicit A/B selection, checked
> before GPU allocation and fixed for a renderer instance. Unknown values fail.
> Parallel is the default after the gates below; no automatic algorithm fallback.
> The new pinned build is
> `out/live-depth-parallel/live_depth.dll`; the former artifact in
> `out/live-depth-candidate/` is preserved. Use `scripts/build-live-depth.ps1
> -OutputName live-depth-parallel`; rebuilding requires an explicit hash review.

### Standalone oracle

> `out/live-parallel-projection/probe/report.json` contains 140 passing exact
> cases: 22 widths from 1 to 4096 across empty/full/leading/trailing/tie/random
> owners, plus eight full-resolution patterns. Both CUDA paths match an independent
> CPU owner-selection oracle on the small-height cases and each other at full size.
> Three discarded warmups and 15 CUDA-event measurements per full-size path:

> | Dimensions | Serial resolve, ms | Parallel resolve, ms |
> | --- | --- | --- |
> | 1920x1080 | 0.810–1.021 | 0.074–0.090 |
> | 3840x2160 | 1.816–2.002 | 0.445–0.562 |

> Ranges above are pattern medians, not uncertainty intervals. These isolated
> synthetic results exclude projection, transfers, inference, capture and display.
> They cannot establish complete pipeline throughput or perceptual superiority.

### Integrated gates

> Full public/synthetic comparisons, real GPU failures, GUI lifecycle and normal
> two-window output measurements are required before default promotion. The full
> quality script has an optional `--compare-serial` gate requiring exact SBS output
> between serial/parallel contexts on the same borrowed TensorRT result for every
> case, in addition to unchanged CPU-reference numerical limits.

> `out/live-parallel-projection/quality/report.json`: all 3,447 cases pass unchanged
> limits, and all 3,447 have exact serial/parallel SBS pixels. Maximum depth error
> is 9.3847513e-5 and maximum changed-pixel fraction against the CPU reference is
> 0.00099054784. These unchanged reference differences are not relaxed thresholds.
> Preprocessing/host-color parity and ownership/reset/reuse checks also pass.
> The FloorballGame/Balanced frame-180 still was visually inspected; no new visual
> quality advantage or motion/VR acceptance is claimed.

> 198 automatic tests (161 unit +37 controller/worker) pass. Five real-GPU
> NaN/poisoned-context/close cycles pass. Actual 60-target GUI checks pass including
> distinct eyes, active settings lock, output exclusion, hidden demand/restore,
> fullscreen/Escape, resize, stop clearing, source loss and owned-worker crash.
> The GUI lifecycle fixture is 720x480 then 600x420, not a 1080p performance run.

> First matched normal-UI Balanced comparison: serial output 59.100 fps versus
> parallel 59.273 fps. Sampled worker ownership-to-publication median is
> 13.6478 -> 12.0137 ms; paired resolve 1.759039 -> 0.170848 ms; paired D2H
> 1.415167 -> 1.331742 ms. Resolve and D2H values are medians of per-sample paired
> sums, not sums of stage medians. These samples are latest values, not atomic
> complete-frame traces. The worker saving does not translate into a material
> output-fps increase on this ~60-fps source/display setup. Reverse-order repeat:
> parallel 59.289 fps, serial 59.320 fps. There is no consistent output-fps gain.
> Repeat paired-resolve medians are 1.753807 -> 0.172736 ms; paired D2H is
> 1.398959 -> 1.404655 ms; worker median 13.34895 -> 11.87445 ms (120 samples/path).
> Default 30-Hz GUI lifecycle also passes the same checks.
> Physical display/frame-ID proof, long soak and VR comfort remain separate gates.

### Following stage: GPU texture handoff

> `texture_handoff_probe.cu` is a standalone experiment, not an application path.
> It creates two fixed RGBA8 shared textures on a CUDA-LUID-matched D3D11 adapter,
> imports them once through CUDA external memory, maps persistent surface objects,
> and uses external keyed-mutex wait/signal ownership transfer to a second D3D11
> device. Legacy `cudaGraphicsD3D11RegisterResource` failed with invalid resource
> handle for these NT shared textures; the failure report is preserved separately.
> It validates pixels and clearing
> through diagnostic staging readback outside handoff timing. Reopen/size changes
> release the old slot pair before creating another.

> `out/live-texture-handoff/report.json` passes 192 exact frames across three sizes
> (3840x1080, 1200x420, 7680x2160), two cycles and 12 black clearing frames.
> Handoff medians range 0.136–0.183 ms, excluding diagnostic readback. This probe
> uses explicit stream waits, so further pipelining is not presumed.
> The final rebuilt source also passes all 192 cases at
> `out/live-texture-handoff/final/report.json` (0.148–0.177 ms pattern medians).
> It does not establish cross-process
> sharing, Qt adoption, WGC integration, physical latency or a zero-copy app.
> The matching Qt 6.10.2 base/declarative SDK is isolated under `out/qt-sdk` for a
> subsequent native scene-graph experiment; the Python runtime is unchanged.

> The standalone Qt experiment now renders native textures, checks sampled exact
> color/frame values, performs six screenshots including black clear, and covers
> resize/hide/recreate/restart. A separate variant moves CUDA to an owned child,
> duplicates unnamed NT handles only into its actual parent, validates the Qt
> adapter LUID/texture descriptor and requires explicit child cleanup on close.
> GPU completion is checked before returning a slot to the producer; screenshot
> leases lacking afterFrameEnd remain held until the next render or destruction.
> The existing app setting `QT_D3D_NO_VBLANK_THREAD=1` is required in this environment.
> These synchronous diagnostic tests are not throughput measurements.

### Actual SBS surface and public-video worker

> `out/live-texture-projection/quality/report.json` passes all 3,447 unchanged
> reference cases, exact serial comparisons and exact RGBA-surface-to-SBS RGB
> comparisons (alpha is 255). A separate pinned diagnostic DLL borrows the exact
> live layout/stream and reruns projection without changing its temporal state.
> Only its D3D oracle reads the surface back; the application DLL is unchanged.

> `live_texture_publish.cu` adds a separate publication API: GPU resolve and RGBA
> packing write the shared surface, followed by external semaphore publication.
> The public-video worker uses the same model, postprocess and refinement policy,
> then this API instead of returning CPU SBS pixels. It still performs CPU decode,
> input resize/RGB upload, a four-byte validity readback, and eligible flat-depth
> refinement readback/upload. Diagnostic staging and output allocations are still
> reserved by the prototype. It is not an end-to-end zero-copy pipeline.

> `out/live-texture-publish/quality/report.json` also passes all 3,447 cases with
> exact publisher-surface and serial RGB matches, unchanged reference limits and
> ownership/reset/reuse checks. This validates the separate publish/consume API,
> not just the earlier synchronous texture oracle.

> `out/live-texture-publish/worker-quality/report.json`: all 126 exact worker-wrapper
> comparisons pass across three public clips, flat/cut scenes and all three live
> policies, including reset and 12 exact black clears. This short wrapper gate is
> separate from the full projection gate. The standalone public GUI uses Balanced,
> preserves SBS display aspect ratio, resizes its test input explicitly when testing
> other texture sizes, and checks distinct eyes, clear, hidden demand and teardown.
> It is not desktop capture and has only one texture consumer. Public source
> provenance remains in `out/public-live-default/*.json` (UVG-VCM, CC BY 4.0).

> `out/qt-texture-probe/public-final/report.json` passes the real-video lifecycle:
> 653 raw Qt swap callbacks, five explicit source creations/closes, zero live
> sources, six screenshots, preserved SBS aspect, hidden demand pause and distinct
> eyes. `public-crash/report.json` detects an injected producer termination and
> leaves no tracked descendants. These are bounded lifecycle observations, not
> distinct-frame throughput, long-duration leak freedom or real device loss.
> `ipc-final/report.json` and `final/report.json` retain the synthetic exact-sample
> checks; each checks 8,181 screenshot samples plus a fully black clear image.
> Final source/DLL-fingerprinted reruns are `public-provenance/report.json` and
> `public-crash-latest/report.json` under `out/qt-texture-probe`; both pass with no
> remaining tracked descendants. Earlier raw results are preserved separately.

### Reproduction and remaining integration

> Build scripts are `build-resolve-probe.ps1`, `build-live-depth.ps1`,
> `build-texture-handoff-probe.ps1`, `build-qt-texture-probe.ps1` and
> `build-live-texture-projection.ps1` under `scripts/`. The last script takes
> `-OutputName live-texture-publish` for the separate publisher. All builds record
> local provenance; no existing portable artifact is replaced.

> With the prepared local Python dependency paths, the key gates are:

> ```text
> python v1/test_live_gpu_quality.py --output <new-directory> --compare-serial
> python v1/test_live_gpu_quality.py --output <new-directory> --compare-publish --compare-serial
> python v1/test_texture_public_worker.py --output <new-directory>
> python v1/test_qt_texture.py --ipc --public-video --output <new-directory>
> python v1/test_qt_texture.py --ipc --public-video --crash-worker --output <new-directory>
> ```

> The Qt runner additionally uses `out/qt-build-deps` for its isolated process
> inspection dependency, and the matching Qt 6.10.2 SDK. The public worker is
> launched through the explicit base interpreter to avoid a venv launcher becoming
> an extra parent; the actual-parent NT-handle check is not weakened.

> Still required before app integration: asynchronous publication with generation
> and frame IDs; coordinated bounded ownership for preview and output consumers;
> hide/restore/resize/stop privacy semantics matching the app; fail-visible worker
> and device errors; normal dual-window public latency/throughput measurements;
> profiling of remaining crossings and long-run/VR validation. Synchronous
> single-window prototype swaps cannot substitute for these gates. No AFW,
> model downgrade, inferred-frame skipping, commit, push or release is included.

> API basis: [CUDA/D3D interoperability](https://docs.nvidia.com/cuda/cuda-programming-guide/04-special-topics/graphics-interop.html)
> requires explicit mapping ownership and recommends registering once per resource;
> [Qt D3D11 textures](https://doc.qt.io/qt-6/qnativeinterface-qsgd3d11texture.html)
> wrap but do not own the native resource and require the scene-graph render thread.


<a id="record-result-live-parity-followup"></a>
## live-parity-followup

Checkpoint date recorded in source: 2026-09-06.

> Superseded status: the final resize/percentile failure is now fixed and all 3,447
> comparisons pass. See [current validation and local-default decision](stereo.md#record-result-live-resize-parity).
> The sections below retain the earlier diagnostic evidence, not current blockers.

> Status: substantial numerical improvement, promotion still blocked by one case.
> Normal GUI GPU selection remains experimental; reference remains default.

### Evidence and cause

> `out/live-parity-followup/stages-original/report.json` isolates inference,
> normalization, temporal output and guided filtering on public OfficeWalk.
> Raw TensorRT depth matches exactly. At Balanced frame 92, pixel (1356,966),
> depth deltas -0.0799999833 and -0.0800001025 fall on opposite sides of 0.08.
> The old hard switch turns that tiny difference into temporal error 0.0520000
> and final guided error 0.000214636. Guided-filter-only error is 8.34e-7.
> Frames 164 and 169 reproduce the same amplification.

### Deliberate live policy change, not relaxed tests

> `temporal_depth_transition=0.008` makes the current-depth weight continuous
> between deltas 0.072 and 0.08. Ordinary EMA is retained below that interval;
> color changes and deltas >=0.08 still use fresh depth immediately. Cuts/resizes/
> gaps still reset state. CPU live reference and GPU share this new policy.
> File mode defaults retain width zero and the historical hard switch. This is
> not a claim of exact old-policy output, nor a change to comparison thresholds.

> GPU diagnostic snapshot copies normalized/temporal arrays and percentile bounds
> only when explicitly invoked by the diagnostic harness, not during live use.
> Buffers and owned stream behavior remain bounded; zero-copy remains false.

### Full public comparison

> `out/live-parity-followup/public-continuous/report.json`: 3,267 comparisons,
> 3,266 passed, one failed. Previous run: 3,172 passed, 95 failed. All depth MAE
> and max limits now pass: maximum depth MAE 7.56544e-7, maximum absolute guided
> depth difference 2.98023e-5. All preprocessing comparisons remain exact and
> reset/reuse/ownership/stale-token checks pass.

> Remaining failure: OfficeWalk / Performance / frame 186, changed-pixel fraction
> 0.001006221 > unchanged limit 0.001. RGB MAE 0.00270986 <0.05 and depth max
> 1.68085e-5 <1e-4 do not override this failure.

> `stages-performance/report.json` isolates a percentile-bound difference of
> 3.31764e-5 at this frame, normalized MAE 9.15315e-7, temporal MAE 7.59210e-7,
> and no hard-threshold branch mismatch. Guided-filter-only max is 1.07288e-6.
> Next diagnosis should inspect raw resized depth near the selected percentiles,
> not repeat temporal-threshold tuning. A million sampled RGB colors match the
> existing GPU grayscale integer formula exactly.

> A nested fused vertical-resize experiment, informed by OpenCV's
> [float SIMD resize implementation](https://raw.githubusercontent.com/opencv/opencv/4.x/modules/imgproc/src/resize.cpp),
> did not improve the remaining bound error (3.32964e-5). It was reverted; evidence
> is retained in `stages-fused/report.json`. No fallback or tolerance widening.

> Full-run DLL was `2b1ae95fd76a8104850443efff25964c5bd785ca18e4c87498fe62297f36880b`.
> After reverting the ineffective experiment, the same source was rebuilt as
> `c2efc1647fd09ec264364ee43dc8b84cb5db5f791cb496b74ca47ae6a947e0bb`, pinned by
> the Python adapter and build manifest. The rebuild is covered by the subsequent
> scroll/error/GUI checks; do not label it as another completed 3,267-case run.

### Additional coverage and remaining work

> - Deterministic scrolling text, one-pixel foreground and a scene cut supplement
>   the public default; they are generated fixtures, not web footage or proof of
>   arbitrary desktop text quality. `v1/test_live_gpu_quality.py --suite scroll`.
> - `v1/test_live_gpu_failures.py --output <path>` now preserves earlier results.
> - `v1/compare_live_transition.py --output <directory>` creates an old/new CPU
>   live-policy comparison on public OfficeWalk; top old, bottom new, both SBS.
> - `v1/benchmark_public_output.py --output <directory> --balanced-only` supports
>   separate sequential regression measurements without overwriting past runs.

> Default promotion remains blocked. Other remaining work includes real scrolling
> and fine-motion visual acceptance and a true 60-fps capture/copy/presentation
> envelope. Hour soak, VR playback and release remain deferred as requested.

### Completed follow-up checks

> - `out/live-parity-followup/scroll/report.json`: all 180 generated scroll/text/
>   thin-line/cut frame-mode comparisons pass unchanged limits.
> - `failures.json`: five NaN/poisoned-context/cleanup cycles pass.
> - `gui/report.json`: actual public 1080p GPU/60-target session passes path/rate
>   locking, distinct eyes, fullscreen/Escape, resize, exclusion, stop clearing,
>   restart/source loss and owned-worker crash cleanup.
> - 154 unit tests +30 controller/worker tests pass. Changed Python checks pass.
> - `review/old-new-OfficeWalk.mp4`: 3 seconds, 180 frames, 1920x1080 H.264 at
>   60 fps, ffprobe verified; paired still 92 inspected. Stills alone do not
>   establish motion/VR acceptance. Review report retains source attribution.

> `output/balanced-60/summary.json`: five six-second public FloorballGame windows
> after warmup, idle preflight and GPU observation. Median output 53.567 fps
> (50.966–54.768), processing 54.478 fps, output readback p95 67.310 ms (15/15 valid
> probes). Overload replaced 152 pending frames with <=1 pending. Shared pixel
> memory remains 106,168,320 bytes. This is a regression observation, not proof
> the policy change caused a speedup or that 60 fps / leak freedom is achieved.


<a id="record-result-live-resize-parity"></a>
## live-resize-parity

Checkpoint date recorded in source: 2026-09-06.

### Cause isolated without changing the reference

> Pinned public OfficeWalk frame 186 produces exact raw inference. The existing
> CUDA resize rounded the full source coordinate to float32 *before* subtracting
> its integer part. At large row coordinates this loses fractional precision.
> Installed OpenCV 4.13.0's IPP-enabled float resize uses a different result.
> Disabling IPP in an isolated diagnostic (not in the app or parity harness)
> reduces GPU/CPU resize max error to 1.91e-6, while changing CPU output by 9.35e-5.
> This identifies the accelerated resize path as the relevant reference, not the
> generic implementation. NumPy percentile indexes/weights were also inspected;
> they are not the source of this frame's discrepancy.

> `out/live-parity-followup/resize-probe/`: max resized-depth error 9.25064e-5;
> 98% percentile reference 7.652722759 versus GPU 7.652783041.
> The selected sorted neighbor at rank 2,032,127 differs by 6.1512e-5. This shifts
> normalization across many output pixels, explaining the previous last failure.

### Fix

> Keep source coordinates in double through floor/subtraction, then cast only
> the fractional offsets to float for the cubic weights. No threshold, temporal
> policy, CPU reference, model or output resolution changes in this continuation.
> This preserves the existing owned stream/buffers and adds no normal-path copies.

> `out/live-parity-followup/resize-fraction/`: max resized-depth error 7.62939e-6;
> 98% percentile GPU 7.652721834 (difference 9.25064e-7). The maximum resize error
> is 12.1x smaller and high-percentile error is 65.2x smaller on this named frame.
> These are diagnostic differences, not full-pipeline fps or quality acceptance.

> `v1/probe_live_resize.py --output <new-directory>` is now a reproducible public
> regression with unchanged reference: resize max <=1e-5 and percentile max <=2e-6.
> It reads raw GPU resize only via an explicit diagnostic export after rendering;
> the live worker never calls it. All old diagnostic artifacts are preserved.

> Current native DLL SHA256:
> `e39e95932a0bf261af4f8539ef416c4febf740bb08338514bc258cf1bd1e77a6`.
> Canonical build remains `scripts/build-live-depth.ps1` (SM120 local scope).
> Full public/scroll, lifecycle and promotion results are recorded below.

> The formerly failing OfficeWalk/Performance frame 186 now passes unchanged
> limits: guided-depth max 1.25170e-6, depth MAE 2.11703e-8, RGB MAE 0.000118393,
> changed-pixel fraction 0.0000407504 (previously 0.001006221). This measures the
> complete rendered frame, not merely the resize probe.

### Acceptance and local GUI decision

> `out/live-parity-followup/public-fraction/report.json`: **3,447/3,447 pass**,
> including 3,240 public frames, 27 existing synthetic cases and 180 generated
> scroll/text/cut cases. Same DLL/source for the entire run and follow-up checks.
> All preprocessing is exact. Maximum depth MAE 1.82408e-7, depth max 9.38475e-5,
> changed-pixel fraction 0.000990548, within unchanged gates. Some margins remain
> small: scroll/Video Quality 52 has the largest depth max. This is bounded corpus
> acceptance, not proof of arbitrary-motion or true depth accuracy.

> `resize-regression/report.json` passes the dedicated single-frame resize gate.
> `fraction-failures.json` passes five real NaN/poisoned-context/cleanup cycles.
> `gui-default/report.json` verifies actual default selection without `--path`,
> public capture, distinct eyes, immutable settings, fullscreen/Escape, resize,
> output exclusion, stop clearing, restart/source loss and owned-worker crash
> cleanup. 154 unit +32 controller/worker tests pass; changed Python checks pass.

> Promote GPU only in the prepared local desktop GUI; no model change or portable
> release. Keep initial original-preview state and 30-Hz target unchanged.
> Explicit reference selection and `DEPTHSBS_LIVE_GPU_CANDIDATE=0` remain available.
> Unsupported compute capability or checksum failure raises a visible error;
> there is no automatic reference fallback. Direct low-level worker callers keep
> their legacy default; the GUI always supplies an explicit session snapshot.

> The latest performance regression attempt did **not** start: three consecutive
> GPU idle samples <=5% were unavailable within the preflight window. Foreign
> work was not stopped. The earlier 53.6-fps measurement used the previous DLL;
> do not present it as a measurement of this fix. Next speed work requires a clean
> preflight, then capture/readback/copy/Qt-stage measurement toward sustained 60.
> Hour soak, VR playback, other-GPU validation and release remain deferred/not
> accepted. Human motion/comfort review remains distinct from numerical parity.

> Source investigated: [OpenCV 4.13.0 resize implementation](https://raw.githubusercontent.com/opencv/opencv/4.13.0/modules/imgproc/src/resize.cpp).
> IPP behavior above is a local measured observation; generic source inspection
> alone does not prove the installed accelerated implementation's internals.

### Clean remeasurement after competing applications stopped

> 2026-09-06: user explicitly stopped ComfyUI and both DLSS capture processes,
> then requested remeasurement. `out/live-parity-followup/remeasure-clean-20260906/`
> contains command, idle/during GPU samples, environment, raw windows and summary.
> Same fixed DLL as the passing quality gate; public FloorballGame 1920x1080,
> Balanced, 60-Hz target, discarded six-second warmup, five six-second windows.

> - Output median **51.310 fps**, range **49.705–52.157**.
> - Processing median **51.968 fps**.
> - Paint-to-output-readback median **56.433 ms**, p95 **60.025 ms**;
>   **11/15** clock probes valid. Not physical display latency.
> - Overload replaced 149 frames, pending <=1; short private-memory window delta
>   -0.789 MiB does not establish leak freedom.
> - Sustained 60-fps gate still fails; this completes the previously blocked
>   measurement, not the remaining capture/copy/presentation optimization.

> These current-build measurements supersede the earlier unavailable-rerun status.
> Do not attribute small differences from prior builds to one cause without a
> controlled repeated A/B experiment.


<a id="record-result-live-sbs-results"></a>
## live-sbs-results

Checkpoint date recorded in source: 2026-09-05.

> Environment: Windows, RTX 5090, driver **616.64** (current live check; previous
> capture notes used 616.56), Qt/PySide6 6.10.2, TensorRT 11.2.1.2, CUDA build
> 13.1.80, MSVC 14.44.35207, one physical 3840x2160 SDR display at 150% scaling.
> Results are local development-tree evidence; no clean-machine, other-GPU,
> multi-monitor, VR, long soak or public release claim.

### Gates and evidence

> - `out/live-sbs/paired-parity.json`: six exact-pixel paired-vs-existing-CUDA cases
>   (64x48, 720x480, 1920x1080; conservative coverage off/on), invalid shape and
>   closed-handle rejection. Explicit stereo H2D 22 -> 11 bytes/pixel; two -> one
>   stream synchronizations. Isolated timings are not a pipeline speedup claim.
> - `out/live-sbs/verified-hd/report.json`: actual WGC-generated 1920x1080 source,
>   Full SBS 3840x1080, 92 processed frames / 5.0042 seconds (**18.38 processing
>   fps**, no 30fps claim). Test then exercises fullscreen/Escape, output while
>   main page is hidden, source resize and restart/minimize cleanup. 113 main
>   swaps and 16 output swaps across the functional session prove presentation
>   events, not display refresh/motion-to-photon. Eyes differ in 42,391 channels.
> - `out/live-sbs/final-hd/report.json`: final explicit paired-call boundary also
>   passes actual output clearing after stop and deliberate owned-worker crash
>   cleanup. 80 frames / 5.0043 seconds (**15.99 processing fps**), 97 main swaps
>   and 13 output swaps across the session. The two short HD runs vary from about
>   16 to 18.4 fps; this is not a controlled repeated benchmark or 30fps support.
> - `out/live-sbs/final-pythonw/report.json`: the same live output, stop clearing,
>   restart/source loss and owned-worker crash checks pass under console-free
>   `pythonw.exe`, matching the source GUI launch style (exit code 0).
> - `out/live-sbs/final-visibility/report.json`: final fullscreen/visibility
>   exclusion recheck and pre-capture parent-liveness guard pass with 178 main
>   swaps, 21 output swaps, actual stop clearing and owned-worker crash cleanup.
> - `out/live-sbs/verified-original/report.json`: existing original capture oracle
>   (colors, resize, overload, minimize, close, restart, GUI-close cleanup) passes.
> - `out/live-sbs/file-gui-regression/report.json`: D3D11 GUI and real existing
>   file conversion pass without QML warnings; generated fullscreen pattern
>   remains distinct from the new actual-live output.
> - Python unit suite 140, live controller 14, desktop controller 12, plus one
>   injected worker GPU failure test pass. The failure emits no SBS and joins
>   capture after projection/engine cleanup; no CPU fallback.

> Intermediate `run-*`, `presentation-*`, `basic-*` and `no-vsync-*` records are
> diagnostic attempts, not final passing presentation evidence. Early processing
> results with zero main swaps must not be cited as successful live display.

### Qt update scheduling investigation

> Qt's native DXGI update-callback path stalled in this environment, including an
> independent minimal QQuickWindow. Bringing windows to front, basic render loop,
> QSG_NO_VSYNC and the update-idle setting did not resolve it. Disabling the DXGI
> VBlank service restores platform timer scheduling, preserving D3D11.
> Source references (read at pinned Qt 6.10.2):

> - [QWindowsWindow requestUpdate](https://github.com/qt/qtbase/blob/v6.10.2/src/plugins/platforms/windows/qwindowswindow.cpp)
> - [QDxgiVSyncService environment switch](https://github.com/qt/qtbase/blob/v6.10.2/src/gui/rhi/qdxgivsyncservice.cpp)

> Exact driver/topology cause is not proven. This is a local explicit startup
> configuration, not a runtime silent renderer fallback or blanket Qt defect claim.

### Reproduce

> Use the prepared Python and `PYTHONPATH` entries `v1`, `out/gui-python-deps`,
> `out/capture-python-deps`, `out/v1-python-deps` (and `out/gui-dev-deps` for Ruff).

> ```powershell
> & scripts/build-cuda-projection-spike.ps1 -GpuPreview
> & out/vda-oracle-env/Scripts/python.exe v1/test_live_projection.py
> & out/vda-oracle-env/Scripts/python.exe v1/test_live_sbs.py --hd --output out/live-sbs/new-hd-run
> & out/vda-oracle-env/Scripts/python.exe v1/test_live_worker_failures.py
> & out/vda-oracle-env/Scripts/python.exe -m unittest discover -s v1/tests
> & out/vda-oracle-env/Scripts/python.exe v1/test_live_controller.py
> & out/vda-oracle-env/Scripts/python.exe v1/test_desktop_controller.py
> ```

> The checked local DLL SHA256 is
> `e01f922faab7d839febe084bd113df25c98ce72e654ed7889b465e6a6be9ec73`, source SHA256
> `25e9d27f13cf8d92f30f5c04c388ba43141e9631137f29adcfe18dd5362ac74c`.
> Build metadata: `out/cuda-projection-preview/build-manifest.json`. A rebuilt DLL
> with different bytes must be reviewed/revalidated before updating the allowlist.
> Existing file/portable DLL and their hashes are untouched.

### Still open

> Native WGC/D3D11/CUDA/Qt texture+fence sharing; GPU preprocessing/temporal stages;
> repeated approved real-video live quality/latency matrix; 1080p30/60 target;
> broader GPU/multi-monitor/hotplug/lock/HDR/device-loss cases. Hotplug error logic
> is mocked, not a real multi-monitor validation. User-deferred long soak, VR and
> release gates remain deferred, not passed.


<a id="record-result-public-live-tests"></a>
## public-live-tests

Checkpoint date recorded in source: 2026-09-06.

> Follow-up 2026-09-06: temporal and resize precision repairs clear all failures;
> 3,447 comparisons pass unchanged limits. GPU is the prepared local GUI default,
> not a public release. See [current evidence and scope](stereo.md#record-result-live-resize-parity).
> The historical run below documents the failures that motivated these repairs.

> 2026-09-05. Public footage replaces personal footage as the default for live
> quality, live lifecycle and live output benchmarks. Historical personal results
> remain historical artifacts; they are not rerun implicitly.

### Source and reproduction

> Official source: https://tie-ultravideo.rd.tuni.fi/UVG-VCM/index.html .
> UVG-VCM, Ultra Video Group, Tampere University, CC BY 4.0;
> T. Partanen et al., "UVG-VCM: Benchmarking dataset for machine-oriented visual
> data compression", QoMEX 2026. License: https://creativecommons.org/licenses/by/4.0/ .

> Main fixture: FloorballGame (fast human motion). Additional quality fixtures:
> OfficeWalk (person/interior edges) and ParkingGarage (camera motion/structure).
> These are compressed public previews, not depth ground truth or raw source YUV.
> No endorsement by the creators is implied.

> `v1/public_test_media.py` pins each original preview SHA256, verifies cached
> downloads at `out/public-video-source/uvg-vcm`, and prepares the first six seconds
> at 1920x1080, original 60 fps, Lanczos scaling, H.264 CRF18, without audio.
> Derived files, source URLs, original/derived hashes and modification/attribution
> records are under `out/public-live-default`. Missing downloads fail explicitly;
> there is no personal-video or generated-video fallback. Fetch the named previews
> from the official page into that cache before running in a fresh checkout.

> Canonical entry points (configured development Python/dependencies required):

> - `v1/public_test_media.py`: prepare/verify public default corpus.
> - `v1/test_live_gpu_quality.py --output <new-directory>`: 360 consecutive frames
>   per public scene, all three live modes, plus explicit synthetic cut/thin tests.
> - `v1/test_live_sbs.py --output <new-directory> --hd --path gpu --hz 60`: public
>   source GUI lifecycle, output, session locking and failure handling.
> - `v1/benchmark_public_output.py`: sequential 1080p public-source output matrix,
>   GPU idle preflight (three consecutive samples <=5%), device-wide observation.
> - `v1/benchmark_live_modes.py --output <new-directory> --source FloorballGame
>   --path gpu --hz 60 --sizes 1920x1080 --modes balanced`: individual run.

> Generated fixtures remain explicit supplements (`--source generated`) for
> geometry/text/clock behavior. They do not replace the public default.

### Numerical promotion gate: failed, default retained

> Evidence: `out/live-gui-promotion/public-quality/report.json` and matched SBS PNGs.
> 3,267 frame/mode comparisons completed: 3,240 public, 27 synthetic. 95 failed
> one or more existing limits; 3,172 passed. Reset/reuse/thread ownership/stale-token
> checks passed. Preprocessed model inputs remain exact.

> | Scene | Comparisons | Failures | Largest absolute guided-depth difference |
> |---|---:|---:|---:|
> | FloorballGame | 1080 | 19 | 0.000696004 |
> | OfficeWalk | 1080 | 56 | 0.000993043 |
> | ParkingGarage | 1080 | 20 | 0.000468791 |
> | Synthetic supplements | 27 | 0 | 0.000000477 |

> Existing limits remain depth MAE <=1e-6, max <=1e-4, RGB MAE <=0.05 (0..255),
> changed-pixel fraction <=0.001. OfficeWalk also reaches changed-pixel fraction
> 0.00100574; small average differences do not excuse a failed limit. This is a
> GPU/reference parity comparison, not proof of true depth or comfortable VR.
> The source of the accumulated local discrepancy still needs stage-isolated
> diagnosis. Do not claim the temporal threshold is the proven root cause.

> Normal GUI now exposes an explicit experimental GPU path alongside reference.
> Reference remains the normal default. The explicit candidate launcher still
> selects GPU. No silent fallback, no DLL or model change, no public release.

### Output measurement scope

> The public clip loops in an owned test window with a CRC timestamp band. Only
> that window/output is captured; unrelated desktop pixels are not saved.
> Five six-second measurement windows follow a discarded six-second warmup.
> Output swaps and processing are measured separately; separate output readback
> probes are not photon latency. Source decoding/painting shares the GUI process
> and is included as test load. Neither a 60 fps source nor a 60 Hz target proves
> 60 distinct processed/presented frames per second.

> Evidence: `out/live-gui-promotion/output/` contains per-window JSON, summaries,
> environment/provenance, command records, logs and idle/during-run GPU samples.
> Windows 11, RTX 5090, driver 616.64, Python 3.13.14, Qt 6.10.2, 150% DPI.
> All paths below are experimental GPU, same 1920x1080 FloorballGame source.

> | Mode / output policy | Output fps median (range) | Processing fps median | Readback p95 ms | Valid clock probes |
> |---|---:|---:|---:|---:|
> | Balanced / old 33 ms poll | 28.975 (28.600–29.576) | 43.627 | 82.346 | 15/15 |
> | Balanced / new 30 target | 29.988 (29.969–30.115) | 52.693 | 77.117 | 13/15 |
> | Balanced / new 60 target | 50.465 (49.722–51.428) | 51.862 | 69.227 | 15/15 |
> | Performance / new 60 target | 51.332 (49.746–52.251) | 52.359 | 66.299 | 15/15 |
> | Video Quality / new 60 target | 48.685 (48.298–49.088) | 49.782 | 69.581 | 15/15 |

> Balanced 60-target output median is 74.2% above the old scheduling baseline in
> this local test. Changing polling also changes GUI/source scheduling load; do
> not attribute its processing-fps difference to a faster inference kernel.
> None of the 60-target cases passes a sustained 60-fps gate (>=57 fps in each of
> five windows). Readback latency is from a small valid subset, not physical
> display latency. Overload replaced 110–153 frames with pending output <=1;
> shared pixel storage remained fixed at 106,168,320 bytes. Short private-memory
> observations do not prove leak freedom.

> GUI verification: `out/live-gui-promotion/gui-public-60/` records a real
> FloorballGame GPU/60-target session with distinct eyes, locked path/rate,
> fullscreen/Escape, resize reset, output exclusion, immediate stop clearing,
> restart/source-loss cleanup and owned-worker crash cleanup. Actual GUI PNG
> inspected; page retains its scroll view at the minimum window size. 151 unit
> tests plus 30 controller/worker tests passed; changed Python files pass Ruff.

> Hour stability, VR playback, representative scrolling/text quality and other-GPU support remain separate acceptance work, not implied by short benchmark or numerical tests.


<a id="record-plan-live-parity-followup"></a>
## live-parity-followup

Checkpoint date recorded in source: 2026-09-06.

> Current outcome: parity repair and prepared-local-GUI promotion complete.
> 3,447/3,447 comparisons, dedicated resize regression, five failure cycles,
> actual default-path GUI lifecycle and 186 automatic tests pass. Source/DLL and
> results are in [stereo.md](stereo.md#record-result-live-resize-parity). Clean remeasurement
> subsequently completed at 51.310 fps Balanced. Host optimization and three-mode
> regression are now recorded in [presentation.md](presentation.md#record-result-live-host-throughput).
> Sustained-60 capture/presentation work remains; deferred VR/soak/release gates
> remain deferred. Below is the preserved earlier plan/evidence.

### Demonstrated cause and experimental policy change

> OfficeWalk/Balanced frame 92: exact raw inference; normalized max error 9.30e-6.
> At pixel (1356,966), depth deltas -0.079999983 and -0.080000103 straddle the
> 0.08 threshold, causing a 0.052 temporal difference and 0.0002146 guided error.
> Guided filtering alone differs by only 8.34e-7. Frames 164/169 confirm the same
> mechanism. Evidence: `out/live-parity-followup/stages-original/report.json`.

### Outcome and next boundary

> Continuous policy reduces failures 95 -> 1 across the same 3,267 cases. All
> depth gates pass; one changed-pixel-fraction gate does not. Further stage
> isolation identifies a percentile-bound discrepancy at OfficeWalk/Performance
> 186; fused vertical accumulation did not fix it and was reverted.

> 180 scrolling/text/cut comparisons, five failure cycles, public GUI lifecycle, 184 automated tests and a Balanced public output regression completed. Review video generated and probed. Default remains reference. No 60-fps, hour-soak, VR or release claim. See [stereo.md](stereo.md#record-result-live-parity-followup) for exact evidence and scope.


<a id="record-plan-live-sbs-output"></a>
## live-sbs-output

Checkpoint date recorded in source: 2026-09-05.

### Progress

> - [x] Bounded inference bridge, resource ownership and reset tests.
> - [x] Live model selection and separate fullscreen output controls.
> - [x] Actual GPU/generated-window evidence and regression tests.
> - [ ] Native GPU texture handoff (not satisfied by host bridge).

> GPU transfer improvement: paired-eye upload reuse and one final stream sync,
> six exact-pixel parity cases. Final evidence and commands:
> [stereo.md](stereo.md#record-result-live-sbs-results). Performance below 1080p30 remains visible;
> no release, long soak or headset tests were performed.


<a id="record-plan-live-parallel-projection"></a>
## live-parallel-projection

Checkpoint date recorded in source: 2026-09-06.

### Stage 1 progress

> Standalone probe passes 140 exact owner-map cases: widths 1–4096, empty/full
> rows, leading/trailing and long holes, equal-depth ties and random owner keys.
> Isolated 1080p resolution interval is 0.810–1.021 ms serial versus 0.074–0.090 ms
> parallel across four synthetic patterns (15 timed calls after three warmups).
> This is not a complete projection or live-output speedup. CUDA build and the
> probe remain separate from the preserved old DLL. Full real-depth/public gate
> completed with an additional exact serial/parallel comparison on every frame.

> Completed numerical gate: all 3,447 reference comparisons pass and all 3,447
> serial/parallel SBS outputs match exactly. 198 automatic tests and five actual
> GPU error/cleanup cycles pass; 60-target GUI lifecycle passes. Normal two-window
> performance comparison completed, including reverse-order repeats. Output stays
> about 59.3 fps while worker computation decreases; parallel is now the default.
> The explicit serial diagnostic selection remains. Default 30-Hz GUI lifecycle
> also passes; no frame-rate or visual-quality superiority claim.

### Stage 2 progress and next bounded experiment

> Legacy CUDA graphics registration rejects the NT shared texture on this driver.
> The external-memory / external keyed-mutex route passes 192 exact frames across
> 3840x1080, 1200x420 and 7680x2160, two creation cycles and explicit clears.
> This is still only a same-process two-device synthetic probe.

> Next, build a standalone Qt 6.10.2 native Quick item using the isolated matching
> SDK under `out/qt-sdk`, without replacing the installed Python runtime. Wrap the
> shared texture on the scene-graph render thread, retain ownership until rendering
> finishes, and test visible output, repeated resize, clear, hide/show and shutdown.
> Keep the application host-copy path untouched during this experiment. Fail
> explicitly for non-D3D11, wrong adapter or native synchronization errors. Only
> after these boundaries pass consider process-isolated live output integration.

> Standalone Qt test now passes 300 swaps, five resource generations, resize,
> hide/recreate, black clear and restart using matching Qt 6.10.2. This relies on
> the application's existing `QT_D3D_NO_VBLANK_THREAD=1` setting. Screenshot renders
> can lack afterFrameEnd; their lease is retained until completion is checked at
> the next render or destruction. No application path change.

> Duplicate unnamed NT handles only into the actual parent process, validate adapter/dimensions/format, use bounded synchronous test commands and fixed slots, and verify owned-child shutdown on every generation. This remains an experiment, not promotion of cross-process live output.

> Cross-process Qt lifecycle passes with five owned-child generations and exact
> sampled color/frame checks on six screenshots. No producer remains afterward.
> Next validate actual SBS projection into the shared RGBA surface: a separate DLL
> borrows the already validated live context on its owner thread, reruns projection
> from its current aligned depth/RGB, packs both eyes on GPU, and uses diagnostic
> D3D readback solely for exact comparison. Preserve the pinned application DLL.
> Run the full existing public/synthetic gate with this additional texture oracle.

> The texture oracle passes all 3,447 cases exactly, alongside the unchanged CPU
> limits and exact serial comparison. Normal Qt teardown reports five creations,
> five explicit closes and zero live sources; the owned-worker crash probe fails
> visibly as expected and leaves no tracked descendants.

> Next isolated step: a real-public-video Python worker uses the same model and
> postprocess policy, then publishes directly to the validated surface instead of
> returning CPU SBS pixels. Keep the standalone one-window consumer and test-only
> switch; do not integrate or promote the two-window app path. Retain diagnostic
> readback for numerical gates, verify public-image display/clear/resize/stop, and
> record that dual-consumer demand, full-app latency and capture-side copies remain.

> The public-video prototype passes display/resize/hide/clear/restart with preserved
> SBS aspect, five explicit creations/closes and zero remaining live sources or
> tracked descendants. Injected actual Python producer termination is detected.
> The worker wrapper passes 126 exact comparisons and 12 clears across public and
> flat/cut scenes and all modes. The publisher's full 3,447-case gate also passes
> unchanged reference limits, exact serial pixels and exact texture pixels.
> No native delivery path has been promoted into the application.
