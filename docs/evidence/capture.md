# Capture and source isolation

Historical evidence by recorded checkpoint. Current support is in
[implementation status](../implementation-status.md).

## Records

- [live-capture-decision](#record-result-live-capture-decision)
- [live-capture-only](#record-result-live-capture-only)
- [live-source-isolation](#record-result-live-source-isolation)
- [v2-live-capture](#record-plan-v2-live-capture)
- [live-capture-preview](#record-plan-live-capture-preview)

<a id="record-result-live-capture-decision"></a>
## live-capture-decision

Checkpoint date recorded in source: 2026-09-05.

> Status: Accepted for original-preview foundation only. Date: 2026-09-05.
> Owner: DepthSBS desktop / capture boundary.

### Selection

> Select Windows Graphics Capture through windows-capture 2.0.1 for both explicit
> HWND and monitor capture, cursor control and source lifecycle. Keep DXGI Desktop
> Duplication and FFmpeg ddagrab as measured reference alternatives, not automatic
> fallbacks. Qt QScreenCapture/QWindowCapture were reviewed but do not expose the
> required cursor-selection control in the chosen public interface; using them
> would not remove the need for a native capture adapter.

> | Candidate | Local evidence | Decision |
> |---|---|---|
> | WGC | Generated window colors, resize, cursor toggle, minimize/close, monitor and GUI preview pass | Selected for user original preview |
> | Native DXGI duplication | Same generated desktop clock recovered through BGRA readback | Monitor reference; adapter does not expose cursor toggle / exact-window capture |
> | FFmpeg ddagrab | 150 frames / 5 s, no duplicated frames, CPU download + null sink, exit 0 | Reference only, not production raw-pipe buffering |
> | Qt capture | Public API/limitations reviewed, not timed | Not selected for cursor-controlled adapter |

> This is a compatibility/ownership decision, not a claim WGC is the fastest API.
> The API currently reads GPU frames back to CPU. Shared BGRA and owned QImage
> copies plus Qt texture upload are explicit. Next stage must evaluate native
> texture handoff for model inference and presentation; no zero-copy label yet.

### Reproducibility and license

> - Package: windows-capture 2.0.1, cp39-abi3-win_amd64, pinned in
>   `v1/requirements-capture.txt`, isolated `out/capture-python-deps`.
> - Installed native module SHA256:
>   `9464e5a6a05e980418eeab6b3a774441b4c737ba6bd596ff0d1eead3e48bf7aa`.
> - MIT license, copyright 2023 NiiightmareXD. Retain installed `licenses/LICENCE`
>   and package/SBOM notices when packaging; this change does not publish a bundle.
> - The exact installed Python API was inspected, including owned native mapping,
>   row pitch, `window_hwnd`, cursor option, stop and DXGI acquisition behavior.
> - [Upstream source](https://github.com/NiiightmareXD/windows-capture),
>   [Microsoft capture contract](https://learn.microsoft.com/en-us/windows/apps/develop/media-authoring-processing/screen-capture),
>   [FFmpeg ddagrab](https://ffmpeg.org/ffmpeg-filters.html#ddagrab),
>   [Qt window capture](https://doc.qt.io/qt-6/qwindowcapture.html),
>   [Qt screen capture](https://doc.qt.io/qt-6/qscreencapture.html).

### Measured experiment

> `out/live-preview/comparison-final/report.json` and `latency.csv` retain raw
> samples, OS/Python/Qt/capture package, GPU/driver, display color, commit and dirty
> state. Single RTX 5090 / driver 616.56, one physical 3840x2160 SDR 8-bit display,
> 150% desktop scaling. Generated QPainter window encodes a monotonic millisecond
> clock in pixels. Only this known pattern is interpreted; desktop pixels are not
> saved. Five-second samples are exploratory, not a five-repeat performance gate.

> | Measured boundary | P50 ms | P95 ms | P99 ms |
> |---|---:|---:|---:|
> | Generated paint timestamp -> WGC GUI image sample | 32.792 | 48.493 | 52.074 |
> | Generated paint timestamp -> DXGI child readback | 12.125 | 24.343 | 26.865 |

> These endpoints differ: one includes shared-memory/GUI scheduling, the other
> stops at child readback. Do not calculate an API speedup or claim the Performance
> 50 ms target from this table. Neither includes depth/SBS or physical display scanout.

### Verification

> Final counter/cleanup revision was rerun at `out/live-preview/verified-final`:
> 308 received generated-window frames in the short window phase, exact colors,
> resize/overload/minimize/close and GUI-close cleanup pass. Console-free execution
> also passes at `out/live-preview/final-pythonw`. These are short functional tests,
> not sustained cadence or memory claims. Static lint/format and diff checks pass.

> - `test_live_preview.py`: generated RGB/green/white quadrants match exact colors;
>   source resize updates dimensions; 200 ms consumer interval increases replacement
>   counts instead of pending-frame count; stop/restart/minimize/source close pass.
> - `test_capture_cursor.py`: cursor-off/on differs by 165 pixels in a generated
>   region; original pointer position restored. Evidence: `out/live-preview/cursor-01`.
> - `compare_capture_apis.py`: actual WGC monitor, DXGI and FFmpeg tests as above.
> - `test_live_controller.py`: nine lease/privacy/failure/timeout/bounded-metric tests.
> - `test_capture_boundary.py`: five fixed-mailbox/shape/SDR/HDR/unknown-color tests.
> - Existing file GUI conversion passes after capture integration:
>   `out/live-preview/file-regression/report.json` and `converted.mp4`.
> - Full Python suite: 137 tests; existing Qt controller: 12 tests. New Qt live
>   controller: 9 tests. No model/runtime/default policy changes.

> PowerShell test setup:

> ```powershell
> $env:PYTHONPATH = "$PWD/v1;$PWD/out/gui-python-deps;$PWD/out/capture-python-deps;$PWD/out/v1-python-deps"
> & out/vda-oracle-env/Scripts/python.exe v1/test_live_preview.py --output out/live-preview/new-oracle
> & out/vda-oracle-env/Scripts/python.exe v1/test_capture_cursor.py --output out/live-preview/new-cursor
> & out/vda-oracle-env/Scripts/python.exe v1/compare_capture_apis.py --output out/live-preview/new-comparison
> & out/vda-oracle-env/Scripts/python.exe v1/test_live_controller.py
> ```

> Use new output directories; test screenshots contain generated content only.

### Unverified / next

> No multi-monitor hardware was available. Mixed-DPI movement, actual monitor removal, real HDR toggling, actual lock/unlock, protected windows, real device loss, long-duration RAM/VRAM stability and minimum supported GPU remain gates. Read-only checks and injected rejections are not proof of these hardware cases. Thirty-minute M1/M5 and user-deferred one-hour/VR checks are not passed here. User release remains deferred.


<a id="record-result-live-capture-only"></a>
## live-capture-only

Checkpoint date recorded in source: 2026-09-06.

> 2026-09-06. Short diagnostic, not performance acceptance.

> `v1/probe_capture_only.py` owns a separate public FloorballGame Qt source and
> the unchanged production `capture_worker` in another spawned process. Input is
> 1920x1080 SDR with cursor off. No product Qt shell, depth inference, SBS renderer
> or output consumer runs. Native readback and bounded CPU mailbox copy remain.
> No ACK consumer exists: replacement is expected, not measured output loss.

> Each run discards a three-second warmup and records three three-second windows.
> Snapshots retain source/independent callback timestamps, counters and bounded
> events. Quantiles use adjacent callback ordinals only; missing intervals are
> not bridged. Source-time intervals and callback-time intervals are separate;
> their clocks are never subtracted from each other. Ring capacity is 256, so
> longer windows may retain only a tail even if total counters remain complete.

### Evidence

> User previously confirmed monitor off and remote instructions; this run did not
> change monitor power, VSync, product defaults or native DLLs. Source painting
> stayed about 62 fps. Sequential runs under `out/live-capture-only/`:

> | Artifact | Requested capture interval | Python callbacks/s |
> | --- | ---: | ---: |
> | `interval0/report.json` | 0 ms | 43.30–47.65 |
> | `interval16/report.json` | 16 ms | 3.65–3.97 |
> | `interval0-repeat/report.json` | 0 ms | 42.33–42.97 |

> All runs finished with `passed=true`, capture exit 0, no forced stop and a
> complete final telemetry snapshot. No contention, callback failures or missing
> diagnostic events were observed. 199 unit tests pass, including three new
> metric tests; scoped Ruff lint passes.

> At 0 ms, callback-body median is about 0.37–0.41 ms, P95 about 0.40–0.72 ms.
> Typical callback intervals are about 16.5 ms but P99 remains about 255–263 ms;
> the source timestamp deltas also contain long gaps. Those long intervals precede
> the measured callback body and are not explained by mailbox-copy duration alone.
> At 16 ms, callback spacing is roughly 250–270 ms. The 0/16/0 sequence supports
> a condition-sensitive interval effect here, not universal Windows behavior.
> The live SBS application already requests 0 ms; changing that default is not a
> new fix. Independent capture rates of ~4–7/s from the prior full-app runs cannot
> be treated as a universal limit of isolated capture, which is much faster here.

> The experiment changes process topology as well as removing consumers: normal
> SBS runs capture in a thread alongside inference. It therefore does not uniquely
> identify Qt, GIL contention, GPU scheduling or compositor/readback as the cause.
> No native WGC-arrival instrumentation or physical-display measurement is present.


<a id="record-result-live-source-isolation"></a>
## live-source-isolation

Checkpoint date recorded in source: 2026-09-06.

> 2026-09-06. Diagnostic harness change only; product rendering unchanged.

### Why and what

> The original benchmark decoded/painted its video inside the product GUI event
> loop. A display wait could therefore slow both source and consumer, confounding
> attribution. `benchmark_live_modes.py --source-process` now owns a separate
> spawned Qt source process. The default keeps the old in-process baseline.
> Pixels, public clip, dimensions and CRC clock drawing remain `ClockOracle`.
> The capture target uses the child HWND and PID, not the benchmark PID.

> Only one control request is outstanding; bounded snapshots carry counters,
> child observation time/CPU and up to 4,096 paint stamps. There is no frame IPC
> queue. Startup/commands time out; child exit is visible; resize validates positive
> integer dimensions. Shutdown joins, then terminates/kills only the owned child
> if necessary. A child checks parent liveness independently of parent pumping.
> The orphan exit branch is implemented but abrupt-parent-death testing remains
> open; normal close, idempotent close and injected child exit were exercised.

### Actual short-run evidence

> Artifacts: `out/live-source-isolation/`. Current user-confirmed monitor-off
> remote environment; no persistent display settings were changed. All live runs
> use public FloorballGame, 1920x1080 input, Balanced, native texture output,
> 60 Hz target, capture telemetry on, three-second warmup and measured windows.
> These are diagnostic runs, not the complete benchmark protocol.

> | Condition | Source paint fps | Output distinct-ID fps |
> | --- | ---: | ---: |
> | Before change, same process (1 repeat) | 38.39 | 3.61 |
> | Separate source (1 repeat) | 62.48 | 3.97 |
> | Separate source, process-only VSync diagnostic (3 repeats) | 61.93–62.49 | 6.28–6.63 |
> | After change, same-process regression (1 repeat) | 29.99 | 3.62 |

> All four live executions completed overload and stop checks. Same-process source
> rates vary under the current display stall; these single repeats are not a
> throughput A/B acceptance. The legacy option-off path still completes normally.

> The source-only lifecycle test deliberately stalls its parent for three seconds:
> source painting continues at 62.63 fps. Resize, normal close and injected child
> exit checks pass (`source-test-final.json`). 196 unit tests plus 30 focused
> controller/worker/benchmark tests pass; four changed/new Python files pass Ruff
> lint and format checks. Rendering and native DLLs are untouched; the earlier
> 3,447-case parity results are not presented as a new run of this harness.

> Crucially, process-only `QSG_NO_VSYNC=1` does **not** restore full-pipeline 60 fps. Independent Python capture callbacks remain 6.28–6.96 fps, with no measured mailbox contention or lost diagnostic events. Thus source/event-loop separation worked, but source generation is not the remaining throughput limiter. Do not claim the GPU renderer is slow or that VSync alone explains everything.

> Clock readback has only 15 attempts, remains outside throughput windows and
> includes substantial current display delay. It is not physical-display latency
> or a statistically accepted P95 improvement.

### Reproduction and next gate

> Use the prepared Python/dependency environment:

> ```powershell
> python v1/test_live_source_process.py --output <fresh-report.json>
> python v1/benchmark_live_modes.py --output <fresh-directory> --source-process --path gpu-texture --hz 60 --sizes 1920x1080 --modes balanced --seconds 3 --repeats 1 --capture-telemetry
> ```

> Next isolate capture with the independent source and no SBS/render consumer;
> then compare normal-display conditions when available. Trace earlier native
> readback only if that boundary remains limiting. Preview cadence, GPU input,
> async publication and CUDA Graph work should follow evidence, not assume a
> 60-fps source proves 60-fps WGC delivery. No product VSync change is accepted.


<a id="record-plan-v2-live-capture"></a>
## v2-live-capture

Checkpoint date recorded in source: 2026-09-05.

> 2026-09-05 local tasks 4–5: three DA2 Small live profiles and repeated 720p/1080p/4K
> measurements are implemented; see [results](live-performance.md#record-result-live-mode-performance-results).
> This does not close broader V2 performance gates: 1080p30/zero-copy, representative
> quality and whole-resource long-run stability remain open.

### Outcome

> Latest slice, 2026-09-05: [stereo.md](stereo.md#record-plan-live-sbs-output) implements DA2 Small live inference,
> paired CUDA stereo and actual separate monitor/fullscreen output. Native texture
> sharing and the broad M0-M5 production gates are not complete. See
> [stereo.md](stereo.md#record-result-live-sbs-results); earlier sequencing notes below describe
> the original plan, not the current absence of live functionality.

> 2026-09-05 update: the unified desktop foundation is the immediate prerequisite
> to M0/M1. Live / Files / Settings share one shell; existing file conversion stays
> first-class. GUI design and file-worker integration move before capture work;
> M4 now completes live controls rather than starting GUI development. See
> `unified-gui-foundation.md`. Generated Qt graphics tests are not M0 capture proof.

> Deliver a Windows application mode that captures a selected monitor or window,
> processes frames through the validated DepthSBS GPU stages, and presents a
> bounded low-latency SBS preview with explicit cadence, latency, and drop metrics.

### M4 — Live UX, controls, and diagnostics

> - Add source selection, mode selection, start/stop, cursor option, preview, and
>   clear active-capture indication.
> - Show actual capture/processing/presentation fps, P95 latency, drop count, and
>   recoverable errors.
> - Prevent Offline Quality selection for live use with an explanation.
> - Add privacy-safe export of environment, plan, counters, and timings.

> Exit: a user can complete the full live flow and understand degraded cadence,
> drops, and failures without consulting logs.

### M5 — Reliability, quality, and support decision

> - Run 30-minute soak and repeated start/stop tests.
> - Inject source loss, resize, display removal, permission loss, encoder/preview
>   closure, device loss, OOM, and cancellation.
> - Evaluate static UI, scrolling, video playback, rapid motion, games where
>   permitted, scene cuts, thin text, occlusion, SDR, and supported HDR behavior.
> - Benchmark 1080p30/60 and 4K30 hypotheses using the repository protocol.
> - Publish exact supported GPU/driver/display/mode envelopes and reject failures
>   explicitly.

> Exit: V2.0 ships only when reliability, privacy, visual-quality, bounded-memory,
> and end-to-end latency gates pass for at least one declared live envelope.

### Risks and decisions still open

> - Windows Graphics Capture may have different window/monitor, permission, and
>   cursor behavior from Desktop Duplication.
> - Cross-adapter displays can force copies or prevent direct interop.
> - HDR capture and SDR preview require an explicit color-management decision.
> - TensorRT engine time plus stereo/presentation may miss the latency hypothesis;
>   cadence reduction must be disclosed by the resolved plan.
> - Protected-content capture behavior cannot be bypassed and must produce an
>   actionable user message.
> - Direct headset presentation is a separate product/driver boundary and remains
>   outside V2.0 until the preview pipeline is stable.

### Progress

> Local preview update (2026-09-05): `live-capture-preview.md` completes the requested
> source picker, WGC original preview and bounded one-slot scheduler. It includes
> DXGI/FFmpeg references and exact generated-window checks. The full gates below
> remain unchecked because native model/GPU interop, long soak and broader display/
> failure matrices are not yet demonstrated; local preview is not V2 completion.

> - [x] Register real-time screen capture as a formal product goal.
> - [x] Define initial user contract, non-goals, milestones, and acceptance gates.
> - [ ] Complete M0 capture API and latency spike.
> - [ ] Complete M1 deterministic capture oracle.
> - [ ] Complete M2 bounded real-time scheduler.
> - [ ] Complete M3 GPU interop and SBS preview.
> - [ ] Complete M4 live UX and diagnostics.
> - [ ] Complete M5 release audit and support decision.


<a id="record-plan-live-capture-preview"></a>
## live-capture-preview

Checkpoint date recorded in source: 2026-09-05.

### Progress

> - [x] Capture comparison and adapter decision.
> - [x] Source picker, original preview and stop/error states.
> - [x] Bounded scheduler, metrics and exclusive lease integration.
> - [x] Real generated-window and regression evidence.

### Evidence / handoff

> See [capture.md](capture.md#record-result-live-capture-decision). WGC window/monitor, DXGI and
> FFmpeg comparisons pass. `out/live-preview/final-pythonw/report.json` additionally
> proves console-free capture, window resize/minimize/closure, blocked file/setup
> work during capture, overload replacements, restart and GUI-close cleanup.
> Cursor inclusion changes 165 generated-region pixels. Full Python 137 + Qt
> desktop 12 + Qt live 9 tests pass; existing file GUI conversion still passes.
> Screenshot: `out/live-preview/final-pythonw/preview-gui.png`.

> This completes the requested functional preview slice, not all original V2
> M0/M1/M2 production gates. Multi-monitor/actual lock/HDR/device-loss matrices,
> 30-minute soak, native GPU sharing and live model/SBS scheduling remain open.
> No release, one-hour soak or VR playback was performed.
