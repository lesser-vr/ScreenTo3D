# Host and native presentation

Historical evidence by recorded checkpoint. Current support is in
[implementation status](../implementation-status.md).

## Records

- [live-dual-window-attribution](#record-result-live-dual-window-attribution)
- [live-host-throughput](#record-result-live-host-throughput)
- [live-native-dual-window](#record-result-live-native-dual-window)
- [live-presentation-attribution](#record-result-live-presentation-attribution)
- [live-qt-delivery](#record-result-live-qt-delivery)
- [live-dual-window-attribution](#record-plan-live-dual-window-attribution)
- [live-native-dual-window](#record-plan-live-native-dual-window)
- [live-host-throughput](#record-plan-live-host-throughput)
- [live-presentation-attribution](#record-plan-live-presentation-attribution)
- [live-qt-delivery](#record-plan-live-qt-delivery)

<a id="record-result-live-dual-window-attribution"></a>
## live-dual-window-attribution

Checkpoint date recorded in source: 2026-09-06.

### Observation and change

> Public 1080p Balanced, same capture/image-pool/render policy: visible-main output
> 57.969 fps vs hidden-main 58.604 fps (`out/live-dual-window/visible/`, `hidden/`).
> The difference is small relative to variability; do not automatically hide the
> user's preview or claim hidden-window fps as normal dual-window performance.

> Both cases still requested two provider images per submitted frame (4216/2108
> and 4302/2151). The hidden QML Image kept reloading although it did not display.

> Main image source now depends on main-window visibility and Live-page selection.
> Output image source depends on output-window visibility. Hidden image sources
> become empty; they resume on show/page restore. Main visibility updates the
> controller's preview demand, so when both windows are hidden there is no GUI
> copy/submission work. Capture/inference remains active in bounded latest slots;
> this is not a new pause/resume policy for the GPU worker. Native minimize behavior
> and occlusion are not newly certified by these explicit hide/show checks.

> The app never hides a user window automatically. Visible images retain full
> source/SBS dimensions and current image ownership. No model, quality, capture
> interval or presentation target change. Stop/privacy and source-loss cleanup
> remain in effect.

### Measurement boundaries

> Benchmark reports now retain raw output-window swap callback rate alongside
> pending-frame-associated output swaps. Raw callbacks can represent redraws and
> are **not distinct video frames**. The existing pending-frame count is also an
> association estimate, not a texture/frame-ID presentation trace. Never substitute
> raw callbacks for achieved video fps or physical display refresh.

> Image-provider request rate and QML hash are recorded too. Source advance/paint,
> capture, processing and GUI submission remain separate. Benchmarks retain idle
> preflight, five six-second windows after warmup, separate readback probes and
> environment/raw samples. No readback number is motion-to-photon latency.

### Verification

> 195 automatic tests (158 unit +37 controller/worker) pass. Extended real public
> GUI checks verify one provider request per submitted frame with only output
> visible; no new GUI submissions/requests while both windows are hidden; window
> and page restore; distinct eyes, settings lock, exclusion, fullscreen/Escape,
> resize, stop clearing, restart/source loss and owned-worker crash cleanup.
> Full 3,447 numerical gate was not rerun: the render/copy algorithms are unchanged.

> Actual GUI lifecycle checks at both 30 and 60 targets pass. The 30-target GUI
> still was inspected: controls and two-eye preview are visible; its black/white
> strip is the test timing marker. This is not motion-quality or VR acceptance.

### Fixed-path results

> Public 1080p Balanced, five measurement windows:

> | Main window | Associated output median (range), fps | Processing, fps | Readback p50 / p95, ms |
> | --- | --- | --- | --- |
> | Visible (normal UI) | 57.581 (56.869–58.817) | 61.155 | 50.857 / 66.196 |
> | Hidden (diagnostic) | 58.670 (57.833–59.109) | 62.131 | 40.531 / 52.820 |

> Artifacts: `out/live-dual-window/visible-fixed/`, `hidden-fixed/`, `gui/`
> and `gui-30/`. Readback valid samples are 13/15 and 9/15 respectively;
> these separate probes do not establish physical latency. Both performance runs
> retain two slots and zero pending backlog; each reports 162 overload events.
> Only the hidden diagnostic meets the local 5%-tolerance candidate flag. Neither
> run establishes sustained 60 distinct output frames per second.

> Normal-UI raw swap callbacks range 59.010–59.311 fps while associated output
> ranges 56.869–58.817 fps. Next experiment: frame-ID-aware presentation tracing
> to distinguish missed video frames from pending-frame attribution error before
> selecting another upload/presentation optimization. The hidden-image fix saves
> unneeded work; the observed output differences do not prove a material speedup.


<a id="record-result-live-host-throughput"></a>
## live-host-throughput

Checkpoint date recorded in source: 2026-09-06.

### Scope and measured cause

> Public UVG-VCM FloorballGame, 1920x1080, same DA2 Small model and pinned native
> DLL `e39e95932a0bf261af4f8539ef416c4febf740bb08338514bc258cf1bd1e77a6`.
> All three live modes retain their existing source resolution and quality policy.

> `out/live-host-profile.pstats` records an explicit actual-worker cProfile run.
> It identifies conversion/copy work but includes native waits and profiling
> distortion; do not use its throughput or overlapping call attribution as GPU
> kernel time. Independent host counters corroborate the removable work.

> Before changes, Performance endpoint samples measured input copy 0.51–0.72 ms,
> output copy 0.65–0.76 ms and output color conversion 1.46–2.15 ms. These are five
> latest-frame observations, not a complete frame-latency distribution.

### Change

> - Convert shared BGRA directly into owned RGB while holding the input lock.
> - Convert owned SBS RGB directly into shared BGRA while holding the output lock.
>   Publish dimensions/sequence only after the complete conversion.
> - Skip the unconditional one-millisecond wait when input was ready. Empty input
>   still waits one millisecond outside the mailbox lock; there is no busy spin.

> This removes intermediate input/output BGRA copies and allocations totalling
> 24,883,200 bytes per 1080p frame. It does not eliminate native GPU readback,
> RGB SBS assembly, the GUI-owned QImage copy, or Qt texture upload. Queue capacity,
> ownership, cuts/gaps/reset behavior and file conversion stay unchanged.

> `DEPTHSBS_LIVE_HOST_BRIDGE=legacy` enables the old bridge explicitly for A/B
> diagnosis. Default is `fused`; invalid values fail. This is not automatic fallback.
> `DEPTHSBS_LIVE_PROFILE=<path>` enables diagnostic-only profiling, off by default.

### Reproduction and timing interpretation

> Use the prepared local Python/dependency environment, with no overlapping GPU
> jobs, and run `v1/benchmark_public_output.py --live-modes-only --output <new-dir>`.
> Each mode requires three idle samples <=5%, six-second warmup, five six-second
> measurement windows, separate 15 clock probes, and bounded-overload checks.
> Raw commands, GPU samples, hashes and environment are retained with each run.

> `before/` and `after/` under `out/live-host-throughput/` are the first comparison.
> `legacy-repeat/` and `fused-repeat/` repeat the comparison with identical final
> runtime code and explicit bridge selection. The native DLL never changed.
> Diagnostic profiling is off for all four benchmark groups.

> Final runtime telemetry has 24 bounded latest-value counters. Host fields
> 20–23 are input copy, input conversion, output conversion and output copy.
> In the fused bridge both copy fields are zero: conversion performs the write.
> Stereo timing excludes host output conversion; total timing spans input
> ownership through shared output publication, excluding source wait/capture/Qt.
> The first comparison used the earlier partial total/stereo timing endpoints;
> use repeat runs for diagnostic stage comparison. Full output fps is unchanged
> in definition. Samples are periodic latest values, not every-frame traces.

### Results

> Final-code A/B repeat, output fps median (five windows per cell):

> | Mode | Legacy | Fused | Fused range | Processing median |
> |---|---:|---:|---:|---:|
> | Performance | 50.690 | 53.713 | 50.930–54.693 | 56.019 |
> | Balanced | 50.022 | 54.456 | 53.136–55.150 | 56.595 |
> | Video Quality | 48.706 | 52.165 | 51.312–54.036 | 56.102 |

> Output improvements are 6.0%, 8.9%, 7.1% in this named repeat. The first A/B also
> improved all three output medians: 49.784 -> 52.601, 50.112 -> 51.999,
> 49.555 -> 52.526. These two short sequential comparisons are not randomized
> cross-device trials. **No mode passes sustained 60** (all five windows >=57).

> Periodic-sample median host-copy/color sum dropped 3.511 -> 0.698 ms,
> 3.516 -> 0.695 ms, 3.373 -> 0.649 ms. Total worker ownership-to-publication
> dropped 16.188 -> 13.290 ms, 16.762 -> 13.794 ms, 17.466 -> 14.136 ms.
> Inference stream intervals stayed ~1.38–1.43 ms. These support host-bridge
> attribution, not isolated-inference throughput claims. Samples are not atomic
> cross-stage snapshots; do not add medians as a precise complete-frame trace.

> Final fused readback p50/p95 ms: Performance 43.749/60.923 (14/15 valid),
> Balanced 51.306/56.681 (13/15), Video Quality 48.041/61.819 (14/15).
> Clock probes are separate from fps windows and are **not physical display
> latency**. Invalid probes are retained in attempt counts, not treated as zero.
> All repeat overload checks pass with two slots and at most one pending frame;
> fused replacements 164/168/155. Short worker private-memory ranges are
> 1239.2–1259.1 / 1245.7–1258.3 / 1246.0–1270.1 MiB, not leak-freedom evidence.

### Remaining speed work

> Actual output remains below processed fps (~56), and both remain below 60.
> Next attribution should separate source-window decode/paint cadence, WGC arrival,
> Qt submission and output swaps before selecting another optimization. The
> benchmark's public source itself runs in the GUI process; do not assume its
> cadence is an unlimited source. Native capture/Qt texture sharing remains open.
> No engine/model/precision downgrade was used to improve fps.

### Validation

> 189 unit/controller/worker tests pass, including exact host pixels, alpha,
> ownership, bounded output writes and explicit legacy reuse/gap regression.

> `out/live-host-throughput/quality/report.json`: **3,447/3,447 pass** unchanged
> numerical gates, and all 3,447 host input/output conversions match exactly.
> Maximum depth error remains 9.38475e-5; maximum changed-pixel fraction remains
> 0.000990548. Margins are still narrow in the known cases, not relaxed.
> Reset/reuse/thread/expired-token checks pass. Matched FloorballGame/Balanced
> frame 180 candidate/reference stills were visually inspected; this is not full
> motion or VR comfort acceptance.

> `failures.json`: five real GPU NaN/poisoned-context/ownership/cleanup cycles pass.
> `gui/report.json`: normal default GPU path with public footage, distinct eyes,
> locked active settings, output exclusion, fullscreen/Escape, resize, stop clearing,
> restart/source-loss and owned-worker crash cleanup pass. GUI screenshot inspected.
> This lifecycle run used 720x480 input then resized to 600x420; use the separate
> 1080p benchmark groups above for performance, not lifecycle-run fps.
> All owned jobs exited; post-test GPU utilization returned to 0%.

> Reproduce checks with the prepared environment:

> ```text
> python -m unittest discover -s v1/tests -q
> python -m unittest test_live_worker_failures test_live_controller test_desktop_controller -q
> python v1/test_live_gpu_quality.py --output <new-quality-directory>
> python v1/test_live_gpu_failures.py --output <new-failures-json>
> python v1/test_live_sbs.py --output <new-gui-directory> --hz 60 --expect-path gpu
> ```

> Retain fused bridge as the prepared-local default after both A/B comparisons
> and correctness/lifecycle gates. Hour soak, VR playback, other GPU validation
> and release remain deferred/unaccepted. Sustained 60 remains an open objective.


<a id="record-result-live-native-dual-window"></a>
## live-native-dual-window

Checkpoint date recorded in source: 2026-09-06.

> Status: **Implemented experimental local path**.
> Owner: DepthSBS. Date: 2026-09-06. Not a default or public release.

> The live GUI now offers **GPU 직접 출력 · 실험** (`gpu-texture`). A pure-D3D11 Qt
> broker delivers the owned worker's SBS textures to the main preview and separate
> output. Default host delivery, model/mode/geometry policy and the pinned original
> application DLL remain unchanged. Stop before selecting another path.

### Worker-side foundation

> - `v1/depthsbs_app/texture_mailbox.py` has exactly 19 signed 64-bit words (152
>   payload bytes), one interprocess lock, no pixel allocation and no Qt/CUDA
>   imports. There are two frame records, not a growing queue. IPC lock operations
>   time out after 50 ms; caller error handling must invalidate/stop the session.
> - A pool descriptor validates session, strictly advancing generation, exact owned
>   worker PID, full-SBS dimensions, LUID representation and two distinct handles
>   before native import. Numeric validation is not a substitute for checking the
>   actual opened D3D resource's adapter, format and dimensions.
> - The producer offers a pool, waits for installation, checks a writable slot,
>   waits for GPU key 0, writes and signals key 1, then publishes its frame metadata.
>   A metadata release is allowed only **after** the last native consumer has
>   finished GPU work and returned key 0. Polling does not acknowledge a frame.
>   Duplicate/stale release and non-increasing frame IDs fail explicitly.
> - Retirement stops publication and waits for every outstanding slot release.
>   It also handles an offer canceled before installation. A replacement cannot
>   overwrite a live pool. Frame IDs stay increasing across pool generations;
>   restart uses a new mailbox. Terminal close invalidates metadata but is not a
>   claim that GPU resources have been released.
> - `experiments/cuda_projection/live_texture_pool.cu` owns two source RGBA8
>   textures and their unnamed local NT handles. The GUI duplicates handles from
>   its verified owned worker, using only `PROCESS_DUP_HANDLE`; the producer does
>   not create potentially unreachable handles in the GUI before descriptor ack.
>   Handles stay stable across descriptor reads and are closed with their pool.
> - Diagnostic staging is explicitly optional and disabled in the transport test.
>   The numerical oracle enables staging for comparison only. CUDA input and
>   background-refinement transfers remain; this is not end-to-end zero-copy.
> - The new DLL lives in `out/live-texture-pool`, SHA-256
>   `7a35c1a134edd3bdeb229f9d52bfabe749ebac42d5305c8998db8feda9656110`.
>   Existing pinned DLLs are not rebuilt or overwritten. The oracle checks the new
>   artifact hash and the borrowed `LiveDepth` layout's pinned DLL hash.

### Checked evidence

> - 15 new metadata tests: bounds/types, owned PID, installation, two pending
>   slots after a missed poll, duplicate/stale release, monotonic IDs, retirement,
>   canceled offer, terminal close, bounded lock wait and actual spawn transport.
> - 176 unit tests plus 37 controller/worker tests pass (213 total); scoped Ruff
>   checks pass.
> - `out/live-texture-pool/worker-quality/report.json`: all 126 short public/flat-cut
>   frame comparisons exactly match the existing GPU path across three live modes;
>   12 black clears pass. This exercises the separate public worker wrapper, not
>   live desktop capture.
> - `out/live-texture-pool/transport/report.json`: two normal child lifecycles and
>   one forced owned-child termination pass. Each duplicates two real NT texture
>   handles; parent handles remain valid after child shutdown until explicitly
>   closed, and the child is reaped. CPU staging/readback is disabled and rejected
>   in this test. Installation is a test acknowledgement, **not** Qt resource import.
> - `out/live-texture-pool/quality/report.json` completed with `passed: true`:
>   all 3,447 texture comparisons and serial comparisons are exact. The unchanged
>   reference limits pass (maximum depth difference `9.384751319885254e-5`, maximum
>   changed-pixel fraction `0.0009905478395061727`). Ownership/reset/reuse checks
>   pass. This compares native publication after the existing postprocessing; it
>   does not validate a future refactored live-worker path.

### Reproduction

> Use the prepared repository Python with `v1`, `out/gui-dev-deps`,
> `out/gui-python-deps`, `out/capture-python-deps` and `out/v1-python-deps` on
> `PYTHONPATH`. Output directories must be new; preserve previous evidence.

> ```powershell
> ./scripts/build-live-texture-projection.ps1 -OutputName live-texture-pool
> ./out/vda-oracle-env/Scripts/python.exe -m unittest discover -s v1/tests -q
> ./out/vda-oracle-env/Scripts/python.exe -m unittest test_desktop_controller test_live_controller test_live_worker_failures -q
> ./out/vda-oracle-env/Scripts/python.exe v1/test_texture_pool_transport.py --output out/live-texture-pool/transport-new
> ./out/vda-oracle-env/Scripts/python.exe v1/test_texture_public_worker.py --pool --output out/live-texture-pool/worker-quality-new
> ./out/vda-oracle-env/Scripts/python.exe v1/test_live_gpu_quality.py --compare-pool --compare-serial --output out/live-texture-pool/quality-new
> ```

> Rebuilding a DLL can change its hash; intentionally review and re-pin the oracle
> only after validating the new artifact. Do not bypass the checksum gate.

### Application integration

> `native_delivery.py` lazily loads/registers the pinned Qt 6.10.2 type only after
> explicit selection. `NativeFrame.qml` is loaded dynamically, so missing native
> dependencies do not affect default host delivery. The native DLL links Qt,
> D3D11 and DXGI, not CUDA/TensorRT. The actual GUI test also checks that no Python
> CUDA module was imported into the GUI process.

> The native broker validates opened D3D texture dimensions, RGBA8 format, mip/
> array/sample count and keyed-mutex support, and matches each Qt device's adapter
> LUID. Each consumer has one private GPU texture. During `beforeRendering` it
> acquires key 1, copies the shared source to its private texture, waits for a GPU
> completion query, releases key 1 and drops its frame lease before returning from
> the render callback. Raw commands are bracketed by Qt's
> `beginExternalCommands`/`endExternalCommands`; `updatePaintNode` only updates
> node geometry and the refresh flag. Qt then draws the private texture independently. The last
> frame lease returns key 0, after which the GUI acknowledges the metadata slot.
> No frame lease is stored on a hidden render node. Nodes may retain resource
> references, with two nodes plus the current pool bounding pool generations to
> three. The native layer rejects publication into an unreleased/poisoned slot.
> Copy completion failure poisons the pool instead of acknowledging unfinished work.

> The worker checks metadata availability before CUDA writes, waits for pool
> installation/retirement with a stop-aware five-second deadline, and keeps
> capture's latest-input replacement behavior. Both-hidden windows still drain
> metadata; they perform no private-texture copies. Slow GUI polling backpressures
> the two-slot producer and may replace incoming capture frames. This differs from
> the host mailbox's output-overwrite behavior, without creating a queue.

> `LiveGpuTexture` overrides only the projection/output boundary of
> `LiveGpuCandidate`; preprocessing, guide/temporal/background policy, token
> validation, reset/reuse and completion bookkeeping are shared. Its timed CUDA
> publisher records splat/resolve/**pack**, not SBS D2H. The native path retains a
> 4-byte invalid-depth readback plus eligible background refinement transfers.
> The native output mailbox contains metadata only: fixed shared color capacity
> falls from 106,168,320 to 35,389,440 bytes (capture input only). This excludes
> owned arrays, model tensors and additional GPU textures; it is not a total-memory
> or end-to-end zero-copy claim.

> Per-consumer counters distinguish uploaded IDs and unique Qt `afterFrameEnd`
> submitted IDs. Repainting the same frame does not increment submission count;
> session checks prevent old-session callbacks contaminating a restart. Copy
> intervals include keyed-mutex waiting and completion, not isolated GPU execution.
> Generic host callback latency fields are not substituted for native frame IDs.

> Integration artifacts:

> - Qt DLL: `out/qt-native-delivery/qt_native_delivery.dll`, SHA-256
>   `2b8f6581f0dd3e34f530f6495ee20910b42ff78b90116b6c9d27af294978942c`.
> - Worker runtime: `out/live-texture-runtime/live_texture_runtime.dll`, SHA-256
>   `8bf16e363dd1fc6002be598335029925113b2afa2b9bdd00f12519a8002a9eae`.
> - The runtime's `DEPTHSBS_TEXTURE_TIMING` build switch adds events around the
>   validated publication kernels. Original pinned DLLs are preserved. The prior
>   Qt component-test artifact is preserved under `pre-bound-check`.

### Integration verification

> - `out/live-texture-runtime/quality/report.json`: terminal `passed: true`, all
>   **3,447 runtime/host and serial/parallel comparisons exact**, with the original
>   reference limits unchanged. Maximum depth difference is
>   `9.384751319885254e-5`; maximum changed-pixel fraction against the reference is
>   `0.0009905478395061727`. Native reset/reuse/stale-token checks pass. Unlike the
>   earlier pool oracle, this gate uses the actual `LiveGpuTexture` class and its
>   inherited postprocessing, not a duplicate public-worker implementation.
> - 183 unit tests +39 controller/worker tests pass (**222 total**). Scoped Ruff
>   checks pass. Explicit native-load failure does not start a session; CPU tests
>   cover owned PID validation before import and no ack on failed native import.
> - `out/qt-native-delivery/render-boundary-synthetic/report.json`: eight generated-pattern
>   captures compare every RGBA pixel exactly at the actual 1.5x display scale.
>   Both consumers' frame IDs, one/both hidden, restore, resize, clear and stop pass.
>   Repainting an unchanged frame does not increment submitted IDs; cleanup ends
>   with zero live native nodes/pools.
> - `out/qt-native-delivery/render-boundary-lease-error/report.json`: the native ABI itself
>   rejects attempted publication into a still-leased slot, followed by clean
>   shutdown. This is not a simulated Python-only rejection.
> - `out/qt-native-delivery/render-boundary-live30/report.json` and
>   `out/qt-native-delivery/render-boundary-live60/report.json`: actual application,
>   public FloorballGame source, both windows, path/rate locking, hidden/page
>   restore, source resize, fullscreen/Escape, capture exclusion, stop clearing,
>   restart/source loss and forced owned-worker termination pass. Both consumers
>   submit the new generation after resize. No CPU SBS mailbox buffer or image
>   provider requests occur. Short lifecycle-loop rates are exploratory (about
>   30 and 57 submitted frames/s), not the matched throughput protocol below.
> - `out/live-texture-runtime/failures-final.json`: five real GPU cycles reject
>   non-finite depth and poisoned reuse, and cover idempotent cleanup, wrong-thread
>   engine close and closed tokens. Alternating flat/random inputs exercise both
>   aligned-depth rejection and the native publisher's raw invalid-depth guard.
> - `out/qt-native-delivery/default-host-regression/report.json`: the unchanged
>   default `gpu` selection passes the existing live GUI lifecycle oracle.
> - Output screenshots show the fitted SBS surface. The barcode is the controlled
>   test's frame-clock marker, not production UI. GUI text appearance raised an
>   intermittent overlap concern in captured images; moving copies to the external
>   render boundary is **not a proven fix**. The 30-target repeat's lifecycle also
>   passes, but these automated checks do not judge glyph appearance.
> - `text-old-sync/report.json` and `text-render-boundary/report.json` under the
>   same output root both pass 30 full-header pixel comparisons against a separate
>   text-only window. This reduced fixture did **not** reproduce the actual-UI
>   concern. The actual-application follow-up below supersedes that initial
>   screenshot-only assessment.

> Earlier matched JSON/CSV and environment provenance are stored under
> `out/qt-native-delivery/matched-host-final` and `matched-native-final`. They use
> the same benchmark script, 720x480 public input, Balanced, both normal windows,
> 60-Hz target, six-second warmup and three six-second measurement repeats. Clock
> readbacks and deliberate slow polling are outside throughput windows. Host swap
> rates are callback submission proxies; native rates count distinct afterFrameEnd
> IDs. Neither measures physical scanout, and neither promotes the target into a
> guarantee. These earlier native measurements use the preserved `367b` artifact,
> not the final render-boundary DLL. The updated benchmark's native overload check
> requires capture-input replacement and bounded pools/nodes/leases, not host-output
> overwrite: two native slots backpressure the producer. The first render-boundary
> run completed throughput samples but failed that obsolete host-only assertion;
> its partial `matched-render-boundary` folder is not a completed benchmark.

> The final `matched-render-boundary-final` (native) and
> `matched-host-boundary-final` (host) runs both terminate successfully and retain
> JSON/CSV/environment metadata. Native output is 59.73–59.93 distinct submitted
> IDs/s; host is 59.83–59.96 callback submissions/s. Native image-provider requests
> are zero versus host 119.67–119.92/s. The native 200-ms polling overload replaces
> 149 capture inputs and passes the resource bounds. No throughput gain is proven.
> Both runs record benchmark SHA-256
> `7458cb72516b35a300deb85df0557edeac99060c5f1cd2d0eca21e017a9612e0`;
> only formatter whitespace was changed afterward. These are six-second local
> samples, not soak, physical scanout or visual acceptance evidence.

### Integration reproduction

> With the prepared Python/PYTHONPATH described above, use fresh output folders:

> ```powershell
> ./scripts/build-qt-native-delivery.ps1
> ./scripts/build-live-texture-projection.ps1 -OutputName live-texture-runtime
> ./out/vda-oracle-env/Scripts/python.exe v1/test_native_dual_window.py --output out/native-test-new
> ./out/vda-oracle-env/Scripts/python.exe v1/test_native_dual_window.py --lease-error --output out/native-error-new
> ./out/vda-oracle-env/Scripts/python.exe v1/test_native_live.py --hz 30 --output out/native-live30-new
> ./out/vda-oracle-env/Scripts/python.exe v1/test_native_live.py --hz 60 --output out/native-live60-new
> ./out/vda-oracle-env/Scripts/python.exe v1/test_live_gpu_quality.py --compare-runtime --compare-serial --output out/native-quality-new
> ./out/vda-oracle-env/Scripts/python.exe v1/test_live_gpu_failures.py --native --output out/native-failures-new.json
> ./out/vda-oracle-env/Scripts/python.exe v1/benchmark_live_modes.py --path gpu-texture --hz 60 --sizes 720x480 --modes balanced --seconds 6 --repeats 3 --output out/native-benchmark-new
> ```

> Repeat the last command with `--path gpu` and a different output directory for
> the paired host comparison. Rebuilding requires deliberate artifact re-pinning
> and verification; it does not silently update the runtime allowlist.

### Actual UI text follow-up (2026-09-06)

> The earlier **glyph overlap suspicion is not a reproduced defect**. No production
> renderer, pinned DLL or image-quality tolerance was changed in this follow-up.
> `v1/test_live_ui_text.py` now compares actual `Main.qml` pixels: top 250 logical
> rows (375 physical rows at 1.5x), containing title, navigation, source, mode and
> strength controls. The intentionally different path/rate row, video and dynamic
> statistics are excluded. Twelve captures per run cover redraw, hide/restore,
> page restore and resize/restore, three of each. Screenshots are retained.

> | Evidence under `out/qt-native-delivery` | Same-run redraw differences | Reference result |
> | --- | --- | --- |
> | `ui-text-host` | zero, all 12 | initial host baseline |
> | `ui-text-host-repeat` | zero, all 12 | separate host process: 669 channels differ by 1 |
> | `ui-text-host-restart` | zero, all 12 | same-process host restart: exact, terminal pass |
> | `ui-text-same-process30` | zero, all 12 | host to native: 744 channels differ by 1 |
> | `ui-text-same-process60` | zero, all 12 | host to native: 665 channels differ by 1 |
> | `ui-text-selection-only` | zero, all 12 | menu change without capture: exact, terminal pass; zero native nodes/pools |

> The original suspected `live-30-verified/gui.png` and three render-boundary
> screenshots also differ from the host header by **at most one 8-bit level**;
> their hashes/metrics are preserved in `ui-text-native60-final/report.json`.
> Separate-process final native runs have a maximum difference of 2 in one channel,
> with all remaining changed channels differing by 1. These results do not support
> the earlier impression of displaced/overlapping glyphs. Current full screenshots
> were also inspected at original resolution without finding such overlap.

> Be precise about failed oracles: the initial independent exact comparison, the
> later one-level comparison, and the same-process exact native comparison have
> `passed: false` and are retained. **They are not retroactively called passes.**
> The per-run stable-redraw comparisons are exact; cross-path bitwise UI equality
> is not established. The mechanism causing the small color differences is not
> proven. Do not call it a fixed rendering bug or claim all UI/display configurations
> are visually certified. Three signed-difference unit tests pass, including
> one-level differences and displaced strokes/unsigned-overflow rejection;
> scoped lint and formatting pass.

> Reproduce the strict same-process investigation (a nonzero exit preserves a
> cross-path difference for review):

> ```powershell
> ./out/vda-oracle-env/Scripts/python.exe v1/test_live_ui_text.py --path gpu-texture --host-first --hz 30 --output out/ui-text-investigation-new
> ./out/vda-oracle-env/Scripts/python.exe -m unittest test_live_ui_text_metrics -q
> ```

> Use `--path gpu --host-first` for the same-process host control, and add
> `--selection-only` for the no-capture control. This diagnostic adds no public
> path override or checksum bypass. The appropriate next acceptance slice is
> higher-resolution and longer-duration dual-window validation, retaining visual
> review; a speculative glyph-rendering rewrite is not justified by these results.

### Remaining promotion gates

> The bounded text investigation did not reproduce glyph overlap; it does not
> certify whole-UI or physical-display correctness. Cross-path bitwise UI equality
> is not established. The explicit experimental option remains non-default and
> is not release-ready.
> Higher-resolution/long-duration dual-window runs, independent motion/VR review,
> real device-loss/hotplug recovery and clean-machine packaging remain open.
> The subsequent [1080p comparison](live-performance.md#record-result-live-native-1080p) completes the bounded
> 30-target portion; its 60-target comparison needs a clean paired retest after
> a background-workload change. Long-duration acceptance is not covered.
> There is no claim of improved FPS or physical-display timing. Default promotion
> is a separate decision even after the bounded local integration gates pass.


<a id="record-result-live-presentation-attribution"></a>
## live-presentation-attribution

Checkpoint date recorded in source: 2026-09-06.

### Evidence and decision

> Benchmark-only bounded counters now separate source advance/paint, capture
> sequence arrival, processed frames, GUI submissions and output swaps within
> the same five measured windows. Capture arrival is observed at the last published
> mailbox sequence; endpoint differences of one frame are expected. These are not
> physical display measurements. Public FloorballGame remains the source.

> 4 ms vs 1 ms GUI polling (`out/live-presentation-attribution/poll4/`, `poll1/`)
> produced Balanced median output 53.620 vs 53.355 fps. Do not adopt 1 ms polling.
> Source paint was ~62 fps, while capture arrival was ~56 fps. This contradicts
> the earlier hypothesis that source decode/paint was the current limiting rate
> in this particular benchmark, without certifying arbitrary source workloads.

> The installed capture binding documents `minimum_update_interval` as a requested
> minimum between eligible updates, not guaranteed fps. Explicit SBS-only 16 ms
> vs 0 ms runs (`capture16/`, `capture0/`) measured output 54.814 -> 58.659 fps;
> processing 57.943 -> 62.294 fps. Capture arrivals then tracked source paint
> ~62.3 fps. Same model, DLL, geometry and render policy. The underlying OS/compositor
> reason for the 16 ms request's lost updates has not been proven.

> Repeat with all three modes, zero requested interval (`capture0-modes/`):

> | Mode | Output median | Output range | Processing median | Readback p95 / valid |
> |---|---:|---:|---:|---:|
> | Performance | 56.273 | 54.550–57.120 | 62.333 | 56.679 ms / 10 of 15 |
> | Balanced | 57.099 | 56.628–57.800 | 62.380 | 55.797 ms / 11 of 15 |
> | Video Quality | 56.750 | 56.073–57.801 | 61.722 | 57.840 ms / 15 of 15 |

> The first Balanced test met the existing 5% target tolerance; the mode repeat
> did not. **Do not claim sustained 60**, or select the favorable first run alone.
> All runs have idle preflight, five six-second windows after warmup, environment,
> source/native hashes and raw GPU samples. Readback excludes invalid CRC probes
> but records all attempt counts; it is not motion-to-photon latency.

> Adopt a zero requested minimum for SBS only; original preview retains 16 ms.
> GUI polling stays 4/8 ms for 60/30 Hz, and the default presentation target stays
> 30 Hz. `DEPTHSBS_LIVE_CAPTURE_INTERVAL_MS=16` is the explicit diagnostic baseline;
> only 0 and 16 are accepted. The native Windows/driver update rate is still finite;
> this changes no queue capacity. Slow processing replaces the latest input,
> with the existing gap reset contract. No automatic fallback was introduced.

### Scope and remaining work

> RTX 5090 local SDR/public 1080p only. High-refresh sources, 4K, other GPUs and
> long-run resource usage need separate validation; removing the request can
> increase capture traffic on faster sources. File conversion is unchanged.
> Numerical rendering/host-bridge code and pinned DLL are unchanged from the prior
> 3,447-case quality gate; that full gate was not rerun in this scheduling-only
> change. New tests cover invalid intervals, explicit defaults and zero-interval
> gap/reuse, with real public GUI stop/resize/source-loss/crash validation.

> Processing now approaches source cadence; GUI submission/output swaps remain
> lower. Next investigate owned QImage copy, texture upload and multi-window Qt
> presentation, keeping source/capture/processing counters in future comparisons.
> Native texture sharing, hour soak, VR playback and release remain open/deferred.

### Final validation

> Without an interval environment override, `default/balanced-60/` confirms the
> new 0 ms request: output median 58.460 fps, range 57.339–58.651, processing
> 62.276 fps. Readback p50/p95 44.104/54.977 ms, all 15 probes valid. Overload
> replaced 174 frames, pending 0, slots 2. This passes the 5% local tolerance in
> this run, not stable exact 60 or universal performance. Retain the less favorable
> three-mode repeat above alongside it; variation is material.

> 192 tests (158 unit +34 controller/worker) and changed-file checks pass.
> `gui-zero/report.json` (60 target) and `gui-default/report.json` (30 target,
> no interval override) pass distinct eyes, immutable settings, exclusion,
> fullscreen/Escape, resize, immediate stop clearing, restart/source loss and
> owned-worker crash cleanup. Default GUI screenshot visually inspected; this
> does not establish full motion/VR acceptance. All owned jobs exited and GPU
> returned to 0% utilization after verification.


<a id="record-result-live-qt-delivery"></a>
## live-qt-delivery

Checkpoint date recorded in source: 2026-09-06.

### Attribution and rejected experiments

> Bounded latest GUI copy/notification timings and a cumulative image-provider
> request counter are now available in reports. Benchmark windows additionally
> sample these timings, GUI private memory and process CPU seconds. CPU/memory
> include the benchmark's source-window decode/paint, not just the product UI.
> No GPU texture-upload timing is claimed by these CPU measurements.

> `out/live-qt-delivery/locked/` vs `unlocked/`: moving synchronous frame notification
> outside the mailbox lock gives Balanced output 55.046 vs 55.042 fps. Keep the
> existing default; `DEPTHSBS_QT_NOTIFY_UNLOCKED=1` remains diagnostic only.
> Notification costs ~0.15 ms while the owned image copy costs ~2.1 ms.

> `copy-probe/` and `pool-probe/`: allocating a new QImage and filling its owned
> bits with NumPy costs ~2.34 ms, like the existing QImage.copy path. Do not adopt
> that variant. Two owned reusable slots instead cost ~0.61 ms in a copy-only
> 3840x1080 BGRA probe, with exact bytes and source independence. These probe
> numbers are not end-to-end fps.

### Adopted implementation

> `PreviewCopyPool` owns two QImages at the current dimensions. Each copy writes
> into a slot through `bits()` and returns a distinct QImage handle. Implicit
> sharing/copy-on-write preserves any retained reader when a slot is reused.
> No shared mailbox view survives the copy. Tests retain eight prior handles
> through slot reuse/resize/clear and verify their exact contents.

> Pool entries are released on resize, stop and worker cleanup. This bounds pool
> ownership to two slots, **not all Qt/renderer allocations**: retained readers can
> cause copy-on-write allocations until released. GUI copy failure clears the
> preview and stops visibly without acknowledging a partially copied input.

> Default `DEPTHSBS_QT_COPY_POOL=1`; explicit `0` retains the old diagnostic path.
> SBS capture interval, 30/60 targets, 4/8 ms polling, model, native DLL and all
> rendering/quality policies are unchanged. This is allocation reuse, not zero-copy;
> native readback, host copying and Qt texture upload still occur.

### Public 1080p results

> RTX 5090, FloorballGame, idle-preflight, six-second warmup then five six-second
> windows per case. All commands, source hashes, GPU samples and reports remain
> under `out/live-qt-delivery/`. No overlapping GPU jobs.

> | Pool mode run | Output median | Output range | Readback p95 / valid |
> |---|---:|---:|---:|
> | Performance | 58.021 | 56.974–59.494 | 53.046 ms / 14 of 15 |
> | Balanced | 57.772 | 56.794–58.392 | 63.322 ms / 15 of 15 |
> | Video Quality | 57.502 | 56.906–58.302 | 59.238 ms / 9 of 15 |

> `copy-repeat/` vs `pool-repeat/` Balanced output: **56.787 -> 58.348 fps**.
> Pool range 57.955–58.813, processing median 61.262 fps. Periodic GUI copy median
> 2.129 -> 0.817 ms, notification 0.148 -> 0.146 ms. This supports the copy-cost
> reduction and modest local throughput benefit, not universal speedup.
> Prior turns had individual runs near 58.5 fps; do not compare only best runs.
> The mode matrix still misses the existing all-windows >=57 tolerance. **No
> sustained exact 60 claim**. Readback is separate from throughput and is not
> physical display latency.

> Repeat GUI private-memory ranges: old 586.9–624.5 MiB, pool 601.0–621.8 MiB;
> first/last-window median deltas +7.0/+7.3 MiB. Short observations do not establish
> leak freedom. CPU median 1.561/1.496 core-equivalents includes the source oracle.
> Overload tests retain two cross-process slots and <=1 pending frame; repeat
> pool replaces 174 frames. The image pool does not expand frame history queues.

### Validation and remaining work

> 195 tests (158 unit +37 controller/worker) pass, including retained QImage readers,
> owned-copy independence, resize/clear, and injected copy failure. Full-size
> copy probes pass. Actual `gui-pool/` at 60 target and no-override `gui-default/`
> at 30 target pass distinct eyes, settings lock, fullscreen/Escape, exclusion,
> resize, stop, restart/source loss and owned-worker crash cleanup.
> The earlier 3,447 numerical GPU/reference gate was not rerun: native rendering
> and host RGB conversion code did not change. New coverage targets image delivery.

> Remaining: Qt texture upload/presentation attribution and eventual native texture
> interop. Higher resolutions/devices/long-run behavior need separate validation.
> Hour soak, VR playback and release remain deferred.


<a id="record-plan-live-dual-window-attribution"></a>
## live-dual-window-attribution

Checkpoint date recorded in source: 2026-09-06.

> 1. Compare public 1080p output with the main window visible versus hidden,
>    keeping source and separate output window unchanged. Diagnostic only: do not
>    silently hide a user's preview or interpret hidden-UI fps as normal-UI fps.
> 2. Use source/capture/submission/swap counters and GUI CPU/memory samples to
>    decide whether duplicate rendering contributes materially.
> 3. Adopt only behavior-preserving fixes with evidence; otherwise document the
>    failed hypothesis and the next measurable native presentation boundary.

> Observed: visible 57.969 vs hidden 58.604 fps, insufficient to hide a user's UI.
> Both cases make exactly two provider requests per submitted frame: hidden main
> images still reload. Gate image sources on actual window/page visibility, with
> restore tests. Add raw Qt swap callbacks beside pending-frame-associated swaps;
> do not rebrand raw callbacks as distinct video frames or physical display fps.

> Completed: visibility-gated image demand and restore checks; 195 automated tests,
> lint, actual 30/60-target GUI lifecycle and repeated fixed-path benchmarks pass.
> Normal UI median 57.581 fps, hidden diagnostic 58.670 fps; no sustained-60 claim.
> Raw callback vs associated-frame discrepancy motivates frame-ID presentation
> tracing next. No native render/model changes or release/soak/VR acceptance.
> [Results and measurement limits](presentation.md#record-result-live-dual-window-attribution).


<a id="record-plan-live-native-dual-window"></a>
## live-native-dual-window

Checkpoint date recorded in source: 2026-09-06.

### Verification gates

> 1. Descriptor/state-machine unit tests, dirty-tree preservation, format/lint.
> 2. Native synthetic two-consumer exact-color/frame identity and bounded teardown.
> 3. Actual app GUI at 30/60 targets: both windows, one/both hidden, restore, resize,
>    clear/stop/restart, source loss and owned worker crash. Explicit failure rather
>    than a silent fallback for incompatible Qt/GPU/device state.
> 4. Full unchanged 3,447-case numerical gate for the native publisher and shared
>    postprocess refactor; existing host/reference regression and error tests.
> 5. Matched normal two-window public measurements, raw results/provenance and
>    verified frame-ID submissions; no physical-display or VR/soak claim.

> Native delivery remains experimental even if the bounded gates pass. Promotion
> is a separate evidence-backed decision; no automatic model/resolution changes.

### Progress: worker-side foundation (2026-09-06)

> Implemented the 152-byte two-slot metadata protocol and separate worker-owned
> native pool DLL. Fifteen new protocol tests, 213 total automated regressions,
> 126 short exact video comparisons, 12 clears and three real NT handle/child
> lifecycle cases pass. The full numerical gate completed: all 3,447 texture and
> serial comparisons are exact, unchanged reference limits and ownership/reset/
> reuse checks pass, and the report has terminal `passed: true`. See
> [presentation.md](presentation.md#record-result-live-native-dual-window) for boundaries and reproduction.

> The foundation alone did not expose an application option. Integration follows
> below; promotion remains separate from experimental local completion.

### Implemented; automated integration passes, visual gate remains open

> Pure-D3D11 Qt broker and dynamic QML surfaces, two private render-thread GPU
> textures, actual opened-resource/LUID checks, per-consumer unique submitted IDs,
> stop/retirement handling and an explicit `gpu-texture` selection are connected.
> `LiveGpuTexture` shares inherited postprocessing; only projection delivery is
> overridden. The old/default host path and pinned original DLL remain available.

> 183 unit +39 controller/worker tests pass. Synthetic two-window exact-pixel and
> 30/60-target actual public-video lifecycle runs pass, including hidden/restore,
> resize, page switch, stop clearing, source loss and owned worker crash. Initial
> matched 720x480/60-target three-repeat measurements are about 59.8 fps for both
> paths, not evidence of a throughput increase. Final native slot-bound guards pass
> the synthetic all-pixel/ID gate and deliberate leased-slot error. Actual 30/60
> GUI gates and the unchanged default host GUI regression pass on the final module.
> The full runtime gate completed with all 3,447 exact comparisons and native
> reset/reuse/stale-token checks passing. Five GPU failure cycles pass, covering
> flat aligned-depth and random-frame native raw-depth rejection. See the design
> document for the terminal report paths and pinned artifacts.

> Final Qt copies run in `beforeRendering` bracketed by Qt external-command calls,
> not in scene-graph sync. Final artifact is `2b8f6581...8942c`; the prior artifact
> is preserved. Synthetic pixels/leases and 30/60 actual lifecycle gates pass again.
> Captured actual-UI text raised an intermittent overlap concern; the reduced
> 30-header comparison passes on both versions and does not reproduce it. Do not
> claim this boundary change fixed the visual concern or promote the option.

> The benchmark's overload guard now checks capture-input replacement for native
> backpressure and retains output replacement for the host path. Bounded native
> pool/node/lease counts are also asserted. Preserve the failed preliminary run
> separately from the final run. Next slice: reproduce and resolve actual-UI text
> appearance, then repeat visual gates before packaging/default promotion.

> Final paired runs complete with JSON/CSV/provenance: native
> `matched-render-boundary-final`, host `matched-host-boundary-final`, under
> `out/qt-native-delivery`. Native 59.73–59.93 versus host 59.83–59.96 submitted
> frames/s; no throughput gain claim. Provider requests fall from about 119.8/s to
> zero. The native overload replaces 149 capture inputs while resource bounds
> pass. Final benchmark formatting changes whitespace only after these runs.

### Actual UI text investigation (next user continuation)

> Build a bounded actual-application capture comparison using the same source,
> window size and static header region on host and native delivery. Compare pixels
> across repeated redraws and hide/restore, preserving screenshots and provenance.
> Distinguish a reproducible rendering defect from an unconfirmed screenshot
> impression. Change production rendering only if the experiment identifies a
> cause; do not claim an unreproduced issue fixed. Keep default delivery unchanged.

### Investigation result

> Added the actual-Main.qml top-header comparison and three comparison-metric unit
> tests. Twelve redraw/hide/page/resize cases are exact within each run. Host restart
> and selection-only controls pass exactly. Same-process host-to-native comparison
> differs by only one 8-bit level (744/665 channels at 30/60 targets); its strict
> exact-reference oracle fails and is preserved honestly. The old suspected captures
> also differ by at most one level, not displaced glyphs. Separate-process samples
> include one channel differing by two; do not silently raise the threshold.

> The prior overlap impression is unconfirmed, not a fixed bug. No production code, DLL, default, or SBS numerical tolerance was changed. See the design's evidence table for scope and retained failures.


<a id="record-plan-live-host-throughput"></a>
## live-host-throughput

Checkpoint date recorded in source: 2026-09-06.

> Recorded outcome: bounded host optimization and three-mode regression completed.
> Two sequential A/B comparisons improve all output medians. Final repeat:
> 53.713 / 54.456 / 52.165 fps (Performance / Balanced / Video Quality), still
> below sustained 60. All 3,447 numerical/exact-bridge comparisons, 189 automated
> tests, five GPU failure cycles and actual default GUI lifecycle pass.
> Keep fused host bridge; next speed work is source/capture/Qt cadence attribution.
> See [presentation.md](presentation.md#record-result-live-host-throughput) for evidence and limits.

> 1. Inspect existing stage telemetry and profile the actual capture worker using
>    an explicit diagnostic switch. Keep profiling out of normal performance runs.
> 2. Optimize measured host overhead with bounded ownership; retain comparison
>    evidence and reject changes without a repeatable full-output benefit.
> 3. Run idle-gated public mode benchmarks and unchanged full quality comparisons,
>    relevant unit/lifecycle checks, and document measured scope and remaining gaps.

### Experiment in progress

> Actual-worker diagnostic profile and per-frame host counters identify color
> conversion/copy costs. Performance baseline endpoint samples: input copy
> 0.51–0.72 ms, output copy 0.65–0.76 ms, output conversion 1.46–2.15 ms.
> These five snapshots are attribution, not a latency distribution. cProfile
> perturbs execution and includes native waits; its fps is not a baseline.

> Candidate fuses BGRA-to-owned-RGB under the input lock and RGB-to-shared-BGRA
> under the output lock, publishing metadata only after the write finishes.
> At 1080p this removes two intermediate BGRA arrays/copies (24,883,200 bytes
> per processed frame), not GPU readback or Qt upload. Empty input still waits;
> ready input no longer incurs the unconditional one-millisecond sleep.
> `DEPTHSBS_LIVE_HOST_BRIDGE=legacy` is an explicit diagnostic A/B path, not an
> automatic quality or CPU fallback. Model/DLL/render policy remains unchanged.


<a id="record-plan-live-presentation-attribution"></a>
## live-presentation-attribution

Checkpoint date recorded in source: 2026-09-06.

> Recorded outcome: completed bounded attribution/capture optimization and validation. Reject 1 ms GUI polling; keep 4/8 ms. Adopt SBS-only 0 ms requested capture minimum after 16-vs-0 comparison, three-mode repeat and no-override default run. Final Balanced 58.460 fps; mode-repeat medians 56.273/57.099/56.750, so do not claim stable 60. 192 tests and actual 30/60-target GUI lifecycle pass. Evidence: [presentation.md](presentation.md#record-result-live-presentation-attribution). Release/soak/VR and high-refresh/other-GPU gates remain open.

> 2026-09-06 continuation. Preserve verified fused host bridge, GPU/model hashes,
> resolution and all quality policies. No release, soak, VR or foreign job changes.

> 1. Add benchmark-only source advance/paint, capture arrival, GUI submission and
>    output-swap rates to the same measured windows. Counters are bounded scalars.
> 2. Compare current 4 ms polling with explicit 1 ms diagnostic polling at the
>    unchanged 60 Hz deadline. Do not infer faster physical display from polling.
> 3. Keep a default change only with repeated output evidence and lifecycle tests;
>    otherwise retain the current policy and document the measured next bottleneck.


<a id="record-plan-live-qt-delivery"></a>
## live-qt-delivery

Checkpoint date recorded in source: 2026-09-06.

> Recorded outcome: completed. Reject notify-unlock and new-allocation NumPy variants as
> speed fixes. Adopt two-slot owned QImage pool after exact ownership/copy checks,
> three-mode public output and repeated Balanced comparison (56.787 -> 58.348 fps).
> 195 tests and actual 30/60-target GUI lifecycle pass. Sustained 60 remains open.
> Evidence: [presentation.md](presentation.md#record-result-live-qt-delivery).
