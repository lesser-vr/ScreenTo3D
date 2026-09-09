# Live performance and measurement conditions

Historical evidence by recorded checkpoint. Current support is in
[implementation status](../implementation-status.md).

Where a record explicitly names DA2 Small together with Performance, Balanced or
Video Quality, the latter name is the legacy temporal/stereo policy selected by
that run. It is not evidence for a different model required by the current
[model-defined product contract](../PRODUCT.md#live-capture-and-output).

## Guarded run condition

The recorded user condition for reproducing the monitor-transition FPS-collapse
experiment is to use `--abort-output-below-fps 20`: a collapse saves the alert,
stops that owned run, and waits for monitor-on confirmation before retrying.
It does not block independent work; intentional readback/overload probes were
excluded from that guard. This is a scoped reproduction condition, not a
general requirement to ask before tests.

## Records

- [eye-4k60-monitor-on](#record-result-eye-4k60-monitor-on)
- [guide-shared-rejected](#record-result-guide-shared-rejected)
- [guide-subkernel-profile](#record-result-guide-subkernel-profile)
- [guide-rolling-isolated](#record-result-guide-rolling-isolated)
- [guide-hybrid-isolated](#record-result-guide-hybrid-isolated)
- [pinned-input-rejected](#record-result-pinned-input-rejected)
- [retained-capture-promoted](#record-result-retained-capture-promoted)
- [model-defined-live-routing](#record-result-model-defined-live-routing)
- [model-defined-live-performance](#record-result-model-defined-live-performance)
- [ovda-native-live-promoted](#record-result-ovda-native-live-promoted)
- [ovda-device-live-promoted](#record-result-ovda-device-live-promoted)
- [live-gpu-idle-recheck](#record-result-live-gpu-idle-recheck)
- [live-gpu-speed-results](#record-result-live-gpu-speed-results)
- [live-guarded-baseline](#record-result-live-guarded-baseline)
- [live-headless-sbs](#record-result-live-headless-sbs)
- [live-mode-performance-results](#record-result-live-mode-performance-results)
- [live-native-1080p](#record-result-live-native-1080p)
- [live-performance-redesign](#record-result-live-performance-redesign)
- [live-gpu-idle-recheck](#record-plan-live-gpu-idle-recheck)
- [live-native-1080p](#record-plan-live-native-1080p)
- [live-performance-redesign](#record-plan-live-performance-redesign)
- [live-gpu-speed](#record-plan-live-gpu-speed)
- [live-gui-promotion-output](#record-plan-live-gui-promotion-output)
- [live-modes-performance](#record-plan-live-modes-performance)

<a id="record-result-model-defined-live-performance"></a>
## model-defined-live-performance

Checkpoint date: 2026-09-08, source commit `d5efff6`. The accepted runs used a
clean worktree, RTX 5090, driver 616.64, TensorRT 11.2.1.2, the current retained
WGC capture path and `model-host-depth-cuda-stereo`. The source process decoded
the pinned CC BY 4.0 UVG-VCM FloorballGame excerpt and painted at about 62.5 fps.
For the 4K rows that 1920x1080 public content was resized by the source window to
3840x2160; it is not native-4K source detail.

Each model discarded six seconds of warmup, then recorded five six-second
windows. Input geometry was either 1920x1080 or 3840x2160 per eye; corresponding
Full SBS processing geometry was 3840x1080 or 7680x2160. `output` below is the
host callback submission proxy, not physical scanout or distinct native texture
IDs. Capture, processing and output rates are medians across the five windows.

| Per-eye input | Product model | Capture | Processed | Output |
|---|---|---:|---:|---:|
| 1920x1080 | Balanced / DA2 Base | 62.39 | 7.94 | 7.94 fps |
| 1920x1080 | Video Quality / VDA Small | 62.83 | 8.43 | 8.43 fps |
| 1920x1080 | Video Quality / oVDA c16 | 62.52 | 7.77 | 7.78 fps |
| 3840x2160 | Balanced / DA2 Base | 63.11 | 2.48 | 2.48 fps |
| 3840x2160 | Video Quality / VDA Small | 64.32 | 2.64 | 2.64 fps |
| 3840x2160 | Video Quality / oVDA c16 | 64.04 | 2.48 | 2.48 fps |

The worker exposes the most recent stage duration; the harness sampled that
snapshot every 250 ms. Medians below therefore describe sampled latest-frame
durations, not CUDA utilization or an all-frame latency distribution.

| Per-eye input | Model | Depth inference | SBS | Worker total |
|---|---|---:|---:|---:|
| 1920x1080 | DA2 Base | 47.54 | 76.43 | 126.36 ms |
| 1920x1080 | VDA Small | 41.27 | 75.82 | 118.90 ms |
| 1920x1080 | oVDA c16 | 49.43 | 75.41 | 127.22 ms |
| 3840x2160 | DA2 Base | 106.73 | 289.66 | 407.00 ms |
| 3840x2160 | VDA Small | 92.98 | 288.00 | 391.18 ms |
| 3840x2160 | oVDA c16 | 116.65 | 288.65 | 415.13 ms |

Device-wide GPU utilization medians during the measured windows were 29/24/26%
at 1080p and 22.5/24.5/18.5% at 4K for DA2 Base/VDA/oVDA respectively. Together
with the stage split, this selects the non-Small host-depth/SBS/output boundary
for the next bounded optimization experiment; it is not proof that any single
copy alone explains the complete gap.

All three models saved 15/15 unique review-frame hashes at each resolution.
Selected frames were visually inspected and showed advancing Floorball content,
plausible eye order/aspect and no black/frozen output. The grabs were downscaled
output-window images, not 1:1 7680x2160 review, continuous playback, matched
quality comparison or VR acceptance. Source-paint-to-grab P50 was 193-195 ms at
1080p and 655-671 ms at 4K; this diagnostic includes sampling delay and is not
photon latency. Overload replacement passed, each session stopped, no FFmpeg
process remained and the GPU returned to 0%; this is not a long-run leak test.

Accepted evidence:

- `out/model-performance-1080-da2base-vda-20260908-v3`
- `out/model-performance-1080-ovda-20260908`
- `out/model-performance-4k-da2base-vda-20260908`
- `out/model-performance-4k-ovda-20260908`

The initial 1080p folder without a suffix is excluded because the original
single review directory collided on the second mode. The `-v2` rerun completed
but is superseded because it truthfully recorded the pending harness fix as a
dirty worktree. Commit `d5efff6` scopes review directories by size and mode; the
four accepted directories all record `dirty: false`.

<a id="record-result-ovda-native-live-promoted"></a>
## ovda-native-live-promoted

Checkpoint date: 2026-09-09. Clean commit `e9b27f0` connects oVDA's existing
source-resolution device-depth path to explicitly selected `gpu-texture` delivery.
The common texture-output mixin changes publication only. The host-output choice,
license confirmation, trusted plans, c16 cache contract and every-frame policy
remain unchanged.

The product-class diagnostic on pinned public FloorballGame matched host-reference
final SBS pixels exactly on 12/12 frames. All alpha planes were opaque, all 12
device tokens completed, no token remained pending and no depth download was
recorded. Evidence: `out/ovda-native-product/public-floorball-20260909/report.json`.

The clean actual-GUI run used retained WGC input, both Qt/D3D11 consumers, a 60 Hz
target, six-second warmup and five six-second windows per geometry:

| Per-eye input / Full SBS | Capture | Processed | Distinct native output |
|---|---:|---:|---:|
| 1920x1080 / 3840x1080 | 62.27 | 22.38 | 22.54 fps |
| 3840x2160 / 7680x2160 | 62.09 | 9.44 | 9.44 fps |

Against the preceding clean device-depth/host-output medians, distinct output is
4.89% higher at 1080p and 29.71% higher at eye-4K. Five-window output ranges were
19.38-25.53 and 7.94-9.77 fps respectively, so the medians do not establish a
stable frame-time guarantee. Every session ended with zero live pools/nodes. All
15 review captures per geometry had unique hashes; inspected first/middle/last
samples advanced, retained plausible Full SBS layout and showed no black/frozen
frame. These are downscaled output-window grabs, not 1:1 eye-4K, continuous
playback, physical scanout, VR or long-session acceptance. Capture/model input
remain host-mediated and `zero_copy=false`. Evidence:
`out/model-native-ovda-clean-20260909`.

<a id="record-result-ovda-device-live-promoted"></a>
## ovda-device-live-promoted

Checkpoint date: 2026-09-08. A fresh public FloorballGame component rerun kept
oVDA's source-resolution depth on its owning CUDA stream. Host-depth/host-SBS,
device-depth/host-SBS and a separately isolated two-slot shared-texture consumer
matched exact SBS pixels on 12/12 diagnostic frames. Three order-alternated
measured runs gave these medians:

| Boundary | Rate | Change |
|---|---:|---:|
| Host depth -> host SBS | 27.842 fps | baseline |
| Device depth -> host SBS | 29.337 fps | +5.37% |
| Buffered device depth -> host SBS | 29.590 fps | +0.86% from device depth |
| Device depth -> shared texture | 30.305 fps | +2.87% from matched device/host SBS |

The fixed-buffer variant was not selected: its additional gain was small and the
previous allocation experiment already showed the duplicated cache cost. Shared
texture remains deferred because this pass does not yet integrate its D3D11
consumer into the non-Small live worker. The selected product change uses the
single-pending owned device token, same-stream CUDA postprocessing and host SBS
output. It fails on foreign/expired tokens and retains the existing explicit oVDA
license confirmation and trusted engine checks.

The rebuilt local product DLL is SHA-256
`ad0871cce22011926b0948a59368ae1f71d9727962160110bdea7974f5e296eb`.
The new entry point does not change the existing DA2 path: 18 public/generated
mode-scene comparisons passed their declared numerical limits, native runtime
readback was exact, serial/parallel output stayed exact, and five injected
failure/cleanup cycles passed. The integrated oVDA product wrapper separately
matched exact SBS on 12/12 public frames, completed all 12 device tokens, left no
pending token and reports 99,532,800 depth-readback bytes avoided.

The final actual-GUI run used clean commit `66ab8f0`, the same public source and
five six-second windows at each geometry. It recorded the selected
`model-device-depth-gpu-stereo-host-output` path and the pinned product DLL hash:

| Per-eye input / Full SBS | Capture | Processed | Output | Sampled depth / SBS / total |
|---|---:|---:|---:|---:|
| 1920x1080 / 3840x1080 | 62.49 | 21.35 | 21.49 fps | 37.00 / 8.48 / 46.54 ms |
| 3840x2160 / 7680x2160 | 62.66 | 7.27 | 7.28 fps | 90.70 / 38.55 / 136.23 ms |

Against the preceding clean host-depth path this is about 2.75x processed and
2.76x output at 1080p, and 2.94x for both at eye-4K. The stage values are medians
of 120 sampled latest-frame snapshots per geometry, not all-frame distributions
or physical latency. The benchmark stopped cleanly, had no pending mailbox frame,
left no FFmpeg process and the GPU returned to 0% utilization.

All 30 review grabs had unique hashes. Sampled first/middle/last frames at both
geometries showed advancing Floorball content, plausible eye order/aspect and no
black or frozen output. The 2100x975 grabs are downscaled window captures, not
1:1 7680x2160 review, continuous playback or VR acceptance. The earlier
`out/model-performance-1080-ovda-device-20260908` pre-commit run is retained but
superseded because it truthfully records `dirty: true`.

Artifacts:

- `out/ovda-device-post/public-floorball-20260908/report.json`
- `out/ovda-device-texture/public-floorball-20260908/report.json`
- `out/ovda-live-product/public-floorball-20260908/report.json`
- `out/live-gpu-quality/product-source-entry-20260908`
- `out/live-gpu-quality/product-source-entry-failures-20260908.json`
- `out/model-performance-1080-ovda-device-20260908`
- `out/model-performance-ovda-device-clean-20260908`

<a id="record-result-eye-4k60-monitor-on"></a>
## eye-4k60-monitor-on

Checkpoint date recorded in source: 2026-09-07.

> The user confirmed the monitor was on before the accepted run. A preceding
> monitor-transition preflight stopped as designed at 3.995 distinct native
> output fps over 3.003 seconds and retained
> `out/eye4k60-exploratory/balanced-native60-current/stop-alert.json`. It was not
> reused as a performance sample.

> The clean preflight then passed at 58.792 fps. The measured run used DA2 Small,
> Balanced, WGC, `gpu-texture`, a 60 Hz presentation target, an owned public
> FloorballGame source process, 3840x2160 capture/per-eye geometry and 7680x2160
> Full SBS. It discarded ten seconds of warmup and recorded five ten-second
> windows with the same 20-fps stop guard. Premiere and other user processes were
> retained; device-wide GPU preflight was 0% with 5136 MiB allocated. The source
> content is the existing licensed 1920x1080 excerpt resized by the owned source
> window to the measured capture geometry, not native-4K source detail.

> | Rate or bound | Result |
> |---|---:|
> | Capture published, median | 61.011 fps |
> | Fresh depth / base SBS, median (range) | 59.127 (58.789-59.482) fps |
> | Final distinct native IDs, median (range) | 59.028 (58.789-59.482) fps |
> | Reused-depth frames | 0 |
> | Source-paint to output readback, P50/P95/P99 | 55.80 / 66.04 / 69.41 ms, 11 valid probes |
> | Measured-window device-wide GPU utilization | median 73%, range 68-76%, 51 samples |
> | Device memory during measured windows | 6817 MiB |

> The overload probe replaced 150 capture inputs with pending output zero, two
> mailbox slots, one live pool and two live nodes. The owned session exited and
> the GPU returned to 0% activity. Evidence is in
> `out/eye4k60-measured/balanced-native60-monitor-on/{runs.json,runs.csv,environment.json,gpu-samples.csv}`.

> A follow-up boundary attribution combined all 200 retained stage snapshots.
> Explicit counters were formula-exact across 3,580 processed frames: 25,688,172
> H2D bytes/frame (804,972-byte 518x518 inference input plus 24,883,200-byte
> full-resolution RGB), four D2H bytes/frame and two synchronizations/frame. Over
> the cumulative 61.513-second session this is about 1.495 GB/s explicit H2D; the
> four-byte invalid flag confirms that native output avoids a full SBS readback.
> The reported inference counter is one ahead of processed frames at the final
> asynchronous snapshot, so processed frames are the transfer denominator.
>
> | Retained sampled stage | P50 | P95 |
> |---|---:|---:|
> | Guided filter | 4.122 ms | 7.757 ms |
> | Full RGB H2D + depth resize | 2.891 ms | 3.985 ms |
> | Host BGRA-to-RGB ownership/color | 1.677 ms | 1.962 ms |
> | Native projection + publication | 1.590 ms | 3.540 ms |
>
> CUDA event intervals may include host enqueue gaps and are not additive GPU
> utilization. The reproducible analysis is
> `v1/analyze_live_gpu_boundary.py`; its output is
> `out/eye4k60-measured/balanced-native60-monitor-on/gpu-boundary-analysis.json`.
>
> The smallest input-boundary alternative was tested before integration and
> rejected. On the same 3840x2160 synthetic BGRA buffer, 30 measured CPU iterations
> gave 1.651 ms median for the current full BGRA-to-RGB conversion followed by
> 518x518 resize, versus 4.169 ms for an owned BGRA copy, four-channel resize and
> small RGB conversion. The 518x518 RGB result was exact, but the candidate was
> 2.518 ms slower and a CUDA implementation would upload an additional 8,294,400
> bytes per frame. Raw samples are in
> `out/live-input-layout/bgra-rejected-20260907/report.json`; this is a host-only
> microbenchmark, not a live throughput A/B. No product path, DLL or default was
> changed.

> This establishes a bounded monitor-on application path with eye-4K geometry and
> near-60 fresh/base/final submission rates on the named machine. The output
> window was 1400x650 logical pixels, so this is not 1:1 fullscreen scanout,
> motion-to-photon latency, native-4K detail quality, FG, continuous playback/VR
> acceptance, another mode/content, another GPU, or long-session stability.

<a id="record-result-guide-shared-rejected"></a>
## guide-shared-rejected

Checkpoint date recorded in source: 2026-09-08.

> The 4K boundary attribution identified the existing guided filter as the largest
> retained sampled P50 stage. A separate candidate therefore preserved each
> per-pixel floating-point accumulation order while staging horizontal and vertical
> reflected tiles in CUDA shared memory. It is isolated in
> `experiments/cuda_projection/live_depth_guide_shared.cu` and built only as
> `out/live-depth-guide-shared/live_depth.dll`; the application still checks and
> loads pinned current DLL SHA-256
> `465b26c193041db613807c1fbcfe4cc7c6ae636dddb3023edc4c476853c98b8e`.

> Exactness covered 16x16, 127x69 and 640x360, three frames each in Performance,
> Balanced and Video Quality (guide radii 4, 8 and 12): all 27/27 aligned-depth
> bit comparisons and final SBS RGB comparisons passed. The odd and minimum sizes
> exercise partial horizontal/vertical tiles, not just divisible 4K geometry.

> With the GPU preflight at 0%, the gated timing used 3840x2160 Balanced synthetic
> frames, five order-alternated repeats of 20 frames per path and a predeclared 3%
> minimum guide-stage improvement. Across 100 CUDA-event samples per path, current
> guide P50/P95 was 4.1195/4.1235 ms and the candidate was 4.1134/4.1196 ms: only
> 0.147% P50 improvement. It failed the effect gate and is not promoted. Whole-path
> host-output medians are retained but are not the decision metric because they
> include full SBS D2H/allocation and varied between repeats.

> The final report is
> `out/live-guide-shared/isolated-4k-balanced-gated-20260908/report.json`; candidate
> DLL SHA-256 is
> `6a73a753f7400efa0fe588867274e5a3bacd3e29b5566f12b5b7879fdabbb087`.
> The earlier shorter and pre-isolation runs remain historical diagnostics, not
> promotion evidence. No application path, product default or pinned DLL changed.

<a id="record-result-guide-subkernel-profile"></a>
## guide-subkernel-profile

Checkpoint date recorded in source: 2026-09-08.

> A second isolated DLL reproduces the current global-memory guided-filter kernels
> and inserts five CUDA events around `moments_x`, `coefficients_y`,
> `coefficients_x` and `guided_y`. Its wrapper owns and destroys a bounded event
> set per live context; it is never selected by the app. The build artifact is
> `out/live-depth-guide-profile/live_depth.dll`, SHA-256
> `527c731b5bd620342e0ba3de71ade511794387c2f62129c07e21236e36fb0ac9`.

> The diagnostic comparison used the same 16x16, 127x69 and 640x360 three-mode,
> three-frame matrix as the rejected shared-memory candidate. All 27/27 aligned
> depth bit comparisons and SBS RGB comparisons matched the pinned current DLL.
> At 3840x2160 Balanced, five order-alternated 20-frame repeats produced 100
> samples per path. The enclosing guide P50 was 4.1052 ms current and 4.1127 ms
> instrumented, only 0.182% overhead versus the declared 3% maximum. The maximum
> difference between the four subevents' sum and the enclosing event was 0.0059
> ms, below the declared 0.02 ms gate.

> | Current 4K Balanced guide subkernel | P50 | Share of subkernel P50 sum |
> |---|---:|---:|
> | `coefficients_y` | 1.4070 ms | 34.2% |
> | `moments_x` | 1.3113 ms | 31.9% |
> | `guided_y` | 0.7342 ms | 17.9% |
> | `coefficients_x` | 0.6574 ms | 16.0% |

> The first vertical coefficient pass and first horizontal moment pass therefore
> account for about 66% of the observed guided-filter interval. Combined with the
> rejected exact-order shared-memory result, merely staging the same neighbor
> reads is not a useful optimization on this RTX 5090. Reducing the O(radius)
> summation work with a prefix/integral formulation would change floating-point
> addition order and requires a new intentional-quality comparison contract; it
> is not implemented or accepted here.

> Final raw evidence is
> `out/live-guide-profile/current-4k-balanced-final-20260908/report.json`. The
> earlier report under `current-4k-balanced-20260908` used the pre-cleanup
> diagnostic DLL and remains historical only. Full host-output FPS is retained in
> the JSON but is not the attribution metric. The product DLL/default and all user
> processes remained unchanged.

<a id="record-result-guide-rolling-isolated"></a>
## guide-rolling-isolated

Checkpoint date recorded in source: 2026-09-08.

> The subkernel profile showed that repeated separable box summation dominated the
> guided stage. The isolated follow-up assigns one CUDA thread to a 64-pixel chunk,
> computes the first reflected window directly, then updates its four moments or
> two coefficient sums by subtracting the departing sample and adding the entering
> sample. This changes floating-point addition order and was therefore evaluated
> as an intentional numerical change, not claimed as exact or behavior-preserving.
> Source is `experiments/cuda_projection/live_depth_guide_rolling.cu`; the isolated
> DLL SHA-256 is
> `c938bc431b6e8e29f4145b0c5fbe0ebc5f0f827ef187be217af1f59641376230`.

> Before measurement, the declared per-frame limits were depth MAE <= `1e-6`,
> depth max <= `1e-4`, RGB MAE <= `0.05`, and RGB changed fraction <= `0.001`.
> The comparison covered 16x16, 127x69 and 641x359 synthetic motion/cut sequences
> plus six contiguous 1920x1080 frames from each of FloorballGame, OfficeWalk and
> ParkingGarage, in Performance, Balanced and Video Quality (radii 4, 8 and 12).
> All 99/99 cases passed. Maximum depth MAE/max were `8.4843e-24`/`3.8868e-19`;
> final SBS RGB changed zero pixels. Consecutive-frame RGB change increase and
> absolute error were also zero in this run, recorded as non-gating proxies because
> no separate temporal threshold had been predeclared. Saved current/candidate
> OfficeWalk Balanced frames and a 16x difference image were visually inspected;
> they matched the exact-RGB result. This still is not a perceptual or VR review.

> The passing quality report then authorized the separate timing gate, which
> verified the same DLL hash. With GPU preflight at 0%, the timing used 3840x2160
> Balanced, five order-alternated 20-frame repeats and 100 CUDA-event samples per
> path. The predeclared minimum guide P50 improvement was 3%.
>
> | Path | Guide P50 | Guide P95 | Median host-output FPS |
> |---|---:|---:|---:|
> | Pinned current | 4.1186 ms | 5.5912 ms | 29.88 |
> | Rolling candidate | 2.7945 ms | 4.0752 ms | 29.66 |
>
> The 32.15% guide P50 reduction passes the isolated effect gate. The full-output
> median did not improve and is supplementary because this harness performs full
> 7680x2160 SBS host readback and allocation; it is not the native texture path.
> The result supports moving the candidate to an integrated native-path validation,
> but does not establish capture cadence, scanout, sustained 60 FPS, visual quality,
> VR comfort, lifecycle behavior or another GPU/mode/content envelope.

> Raw quality evidence and review images are under
> `out/live-guide-rolling/quality-20260908/`; its report SHA-256 is
> `306b8755e009935291e6c70b61f90716e39b11d04fbbc70fd63f8ef6b1ef879a`.
> Raw timing evidence is
> `out/live-guide-rolling/performance-4k-balanced-20260908/report.json`, SHA-256
> `93250115a8f13108af64befd582c851af933845a29a053a37dd8147def771ad0`.
> The application default and pinned DLL were not changed.

> A follow-up native-publication boundary harness retained inference, postprocess,
> CUDA/D3D11 publication, two-slot synchronization and the four-byte validity
> readback while replacing Qt with a test-only no-copy keyed-mutex consumer. The
> first attempt under `native-boundary-4k-balanced-20260908/` omitted that consumer
> and correctly failed on the third publication with a wait timeout; it is retained
> as a harness-contract failure, not performance evidence. The corrected isolated
> runtime DLL SHA-256 is
> `e93394ff5c0a9a0f66366916383e05485d217cf15daae8a310930018875f0a93`.
> Five order-alternated 20-frame 3840x2160 Balanced repeats then passed the
> predeclared 3% guide and native-processing gates:
>
> | Native boundary metric | Current | Rolling candidate | Change |
> |---|---:|---:|---:|
> | Guide P50 | 4.1175 ms | 2.7684 ms | 32.77% lower |
> | Unpaced processing median | 90.95 fps | 102.43 fps | 12.62% higher |
>
> Both paths processed 105 frames with equal counters: 2,697,258,060 H2D bytes,
> 420 D2H bytes, 210 synchronizations and no CPU background refinements. Repeat
> throughput varied substantially, so the median is bounded evidence rather than
> a sustained-rate claim. The final report is
> `out/live-guide-rolling/native-boundary-4k-balanced-final-20260908/report.json`,
> SHA-256
> `cf0d8ed32b50131b04358ea08ca8f9e0ded590d92aaf0d5cafd4ab5ce546e70e`.

> The candidate was then selected only in the benchmark's owned child through a
> fixed hash-pinned wrapper; the normal app path and default remained unchanged.
> Matched sequential actual-app runs used WGC, DA2 Small with the legacy Balanced
> temporal/stereo policy, native texture
> delivery and Qt output submission with 3840x2160 input/per eye and 7680x2160
> Full SBS. Each path used the same scaled public FloorballGame source process,
> 60 Hz presentation target, 1400x650 logical output window, ten-second warmup,
> five ten-second windows, device-wide GPU sampling and a 20 fps output stop guard.
> GPU preflight was 2% current and 3% candidate; the benchmark/model/QML/native
> delivery/texture runtime/source hashes and relevant settings matched.
>
> | Actual-app metric | Current | Rolling candidate | Observed change |
> |---|---:|---:|---:|
> | Source advance median | 62.48 fps | 62.49 fps | matched input |
> | Capture arrival median | 62.29 fps | 62.26 fps | matched input |
> | Fresh processing median (range) | 52.25 (51.64-53.11) fps | 58.93 (57.99-59.45) fps | 12.78% higher |
> | Final distinct output median (range) | 52.45 (51.54-53.01) fps | 58.83 (57.79-59.45) fps | 12.17% higher |
> | Sampled guide P50, 200 samples/path | 5.2024 ms | 3.5666 ms | 31.44% lower |
> | Source-paint to output-readback P50 | 63.71 ms, 14/15 valid | 55.54 ms, 15/15 valid | 8.17 ms lower |

> The output-readback clock is not physical motion-to-photon latency. Both transfer
> analyses exactly matched 25,688,172 H2D bytes, four D2H bytes and two
> synchronizations per processed frame. Each overload probe replaced capture input,
> remained within two mailbox slots and exited cleanly; neither rate guard tripped.
> Candidate final output did not reach 60 fps in any window, so this is a material
> actual-app benefit but not a 4K60 pass. It covers one scaled public clip, one mode,
> one logical-window/display condition and about one minute per path, not 1:1
> fullscreen scanout, native-4K source detail, FG, broader visual/VR acceptance,
> another GPU or long-session stability.

> The validated comparison is
> `out/live-guide-rolling/app-comparison-4k-balanced-20260908.json`, SHA-256
> `516fae0dbed5da0c606e3949016a3e37af53771d5875d8366009b2b454cd84d5`.
> Current and candidate raw runs, GPU samples, environments and boundary analyses
> are retained under `out/live-guide-rolling/app-{current,candidate}-4k-balanced-20260908/`.
> At this checkpoint, the normal product DLL/default remained unchanged pending
> broader validation. The later hybrid promotion is recorded below.

<a id="record-result-guide-hybrid-isolated"></a>
## guide-hybrid-isolated

Checkpoint date recorded in source: 2026-09-08.

> Two more six-second-window actual-app pairs broadened the raw rolling candidate
> to OfficeWalk and ParkingGarage under the same 3840x2160 input/per-eye,
> 7680x2160 Full SBS, DA2 Small with the legacy Balanced policy, 60 Hz native-output
> contract. This is not DA2 Base Balanced-mode evidence. Across all
> three clips and 15 windows per path, processed-rate improvement was 4.24-12.78%
> (4.73% median), output-ID improvement was 0.10-12.17% (1.10% median), and the
> sampled guide reduction was 4.65-31.44% (19.74% median). All transfer formulas
> passed, both added pairs had 0% device-wide GPU preflight, and no output guard
> tripped. Candidate processing exceeded 60 fps on two clips, but output median
> reached 60 on none. The hash-validated aggregate is
> `out/live-guide-rolling/app-corpus-4k-balanced-20260908.json`, SHA-256
> `fc956251f2524cbcfbfc9b91e695105918bb83cae86229269d6baab7e71d205a`.

> The same rolling kernel was then checked outside Balanced. At 4K Performance
> radius 4 it regressed guide P50 by 2.03% while native throughput changed only
> +0.03%, so the global candidate was rejected. At Video Quality radius 12 it
> reduced guide P50 by 39.46% and raised the native-boundary median by 22.72%.
> This mode split led to a new isolated hybrid: retain the exact current direct
> summation for radius 4 and use the 64-pixel rolling chunks only for radii 8/12.
> Source is `experiments/cuda_projection/live_depth_guide_hybrid.cu`; DLL SHA-256
> is `fb0e209df70649d1dbfd244732433f9ea9185bb1ee468cd05dd9feb8f1627045`.

> The hybrid quality matrix passed 99/99 cases. Performance was exactly identical;
> maximum aligned-depth MAE/max across the rolling radii were `8.4843e-24` and
> `3.8868e-19`, and final/consecutive-change RGB remained exact. The saved
> OfficeWalk Balanced 16x difference frame was visually checked as fully black,
> consistent with the pixel result; this is still not motion or headset review.
> Quality report SHA-256 is
> `fbef35a73fb28282ba5e7b9c665f7ee61c8763d5746afe0a718cb858cde572c2`.

> Native publication used five order-alternated 20-frame repeats per mode. The
> predeclared Performance non-regression gate allowed at most 1% loss; Balanced
> and Video Quality each required at least 3% improvement in both guide P50 and
> complete native-boundary throughput.
>
> | 3840x2160 mode | Guide current -> hybrid | Guide change | Native median current -> hybrid | Native change |
> |---|---:|---:|---:|---:|
> | Performance, radius 4 | 2.3245 -> 2.3245 ms | 0.00% | 116.75 -> 116.25 fps | -0.42% |
> | Balanced, radius 8 | 4.1155 -> 2.8313 ms | 31.20% lower | 95.41 -> 107.89 fps | 13.08% higher |
> | Video Quality, radius 12 | 5.9086 -> 3.5768 ms | 39.46% lower | 81.56 -> 99.99 fps | 22.60% higher |

> All three declared gates passed. Reports are under
> `out/live-guide-hybrid/native-boundary-4k-{performance,balanced,video-quality}-20260908/`.
> Five additional real-GPU native failure cycles passed non-finite rejection,
> poisoned-context behavior, idempotent cleanup, wrong-thread rejection and
> closed-token rejection; their report SHA-256 is
> `8d933cd873eaa5768b7b54f7297c6f2238332e0ee3f53e5f4d852a6999b8a5a3`.

> A fresh hash-pinned FloorballGame actual-app A/B used six-second warmup plus five
> six-second windows per path with matched 0% GPU preflights. Processed median was
> 59.71 -> 61.86 fps (+3.59%), output-ID median was 59.38 -> 59.84 fps (+0.78%),
> and sampled guide P50 was 5.3877 -> 3.8804 ms (27.98% lower). The candidate
> output maximum reached 60.04 fps, but its median remained below 60. The validated
> pair is `out/live-guide-hybrid/app-comparison-floorball-4k-balanced-20260908.json`,
> SHA-256
> `5b851363425b6fe630c6cb16c90e50bae608600935a61000c8b83358b3efba18`.
> This supports the hybrid design but not a 4K60, physical scanout, native-detail,
> motion/VR, sustained, other-GPU or packaging claim.

> The hybrid was then moved into canonical `live_depth.cu` and rebuilt as final
> candidate SHA-256
> `f67fc53ccaa37a29474ba90bac80d3cb2bff12e8c685a24df9f7382db0c00fa7`.
> Its fresh 99/99 quality report passed with the same maximum aligned-depth
> MAE/max (`8.4843e-24`/`3.8868e-19`) and exact final/temporal RGB; report SHA-256
> is `0be528c4f1fb82502242b362576c55ebd5a26ae19812effeab5e4bb464715e52`.
> Fresh five-repeat native reports all passed their declared gates:
>
> | 3840x2160 mode | Guide current -> final | Guide change | Native median current -> final | Native change |
> |---|---:|---:|---:|---:|
> | Performance, radius 4 | 2.31834 -> 2.31838 ms | -0.002% | 116.34 -> 115.84 fps | -0.43% |
> | Balanced, radius 8 | 4.10933 -> 2.80574 ms | 31.72% lower | 95.26 -> 108.78 fps | 14.19% higher |
> | Video Quality, radius 12 | 5.90582 -> 3.56454 ms | 39.64% lower | 81.02 -> 100.91 fps | 24.55% higher |
>
> Their report SHA-256 values, in table order, are
> `ab6eeb60d4be4eb58b410f3802a8097cc76a78194a32af92cdb10a75a183b666`,
> `3471e5b5a0fe8677c562971447412aaade42492934963e64fa6001b8bdd887c1`,
> and `8129af16ce0eb77bd40b5913a57e69b426529a7a99d696cc4640a7fece33fc6b`.

> The matching final-candidate actual-app pair measured 59.1887 -> 62.2306
> processed fps (+5.14%), 59.1887 -> 59.9139 output IDs/s (+1.23%), and
> 5.37752 -> 3.98574 ms sampled guide P50 (25.88% lower). Output still did not
> establish a 60 fps median. Separately, 15 post-measurement OfficeWalk readbacks
> were all hash-distinct; three sampled stills and a contact sheet showed advancing
> camera motion, plausible stereo order/letterbox/major contours, and no
> black/frozen frame. This is sampled-still inspection outside timing, not
> continuous playback, motion-to-photon or headset review.

> The same canonical source was linked into the prepared-local product path as DLL
> SHA-256
> `946225fb6abaff0f9e94bea212995bb073da97fb461d5ff062886a388fae4448`.
> Candidate-to-product comparison passed 99/99 with exactly zero depth, final RGB
> and temporal differences; report SHA-256 is
> `ad729d79acd6da9df1f3006d539666d0d55b714418ce3ce45e0d45fc65133039`.
> The product hash passed five real-GPU failure/cleanup cycles (report SHA-256
> `40d1d4e824fd3704a536cd768adfb88b4cbba05ea11b07a144753f7ef06618d2`)
> and a default-path Floorball 4K DA2 Small functional smoke using the legacy
> Balanced policy. That smoke loaded the
> exact product hash and produced 52.26 processed / 52.43 distinct output IDs/s,
> but its device-wide preflight was already 8%, so it is not used as comparative
> performance evidence. Python 234/234, C++ 1/1 and scoped static checks passed
> after promotion. Continuous visual/headset review, sustained 4K60, real device
> loss, packaging and other-GPU support remain unverified.

<a id="record-result-pinned-input-rejected"></a>
## pinned-input-rejected

Checkpoint date recorded in source: 2026-09-08.

> After guided-filter promotion, sampled actual-app attribution left a large
> full-resolution RGB host-to-device interval. The bounded candidate allocates
> one 24,883,200-byte page-locked host RGB buffer for a 3840x2160 session, copies
> the already converted RGB frame into it, and passes that exact byte array to
> the unchanged product DLL. It does not change capture format, depth, guide,
> projection, eye geometry or native texture publication. Candidate source
> SHA-256 is
> `03b02d737c249e36664f2681c73d261f2160ff02a2b27ee17abb7e9de926fcf8`.

> The existing numerical oracle passed all 261/261 public, synthetic cut and
> scrolling-text cases across Performance, Balanced and Video Quality.
> Preprocessing remained exact; maximum depth MAE/max were `1.8241e-7` and
> `9.3848e-5`, while maximum RGB MAE/changed fraction were `0.007827` and
> `0.0001961`, all within the existing declared limits. Report SHA-256 is
> `2e51416522e9eb91991d32dda043751e53ba5e1f44de003bd5fb95fb7736c53a`.
> Five source-hash-pinned real-GPU cycles passed non-finite rejection,
> poisoned-context behavior, idempotent cleanup, wrong-thread rejection and
> closed-token rejection. Their report SHA-256 is
> `f7eb48d298f71a2dddf27bd916b4b686248d3153ae71924dc9a8aed0bb32e089`.

> The actual-app A/B used separate 0%-GPU-preflight sessions, FloorballGame,
> 3840x2160 input/per eye, 7680x2160 Full SBS, DA2 Small with the legacy Balanced
> policy, 60 Hz native
> output, a six-second warmup and five six-second windows. The current/candidate
> processed medians were 62.2189/62.2818 fps (+0.10%); distinct output medians
> were 59.9022/59.9336 fps (+0.05%). Two candidate windows exceeded 60, with a
> 60.1285 maximum, but the median did not. Across 120 samples per path, host
> input conversion/staging P50 plus GPU RGB-transfer/depth-resize P50 fell from
> 4.3686 to 3.5228 ms (19.36%). These stage intervals are diagnostic and not an
> additive physical latency measurement. Raw run SHA-256 values are
> `f46a3deeb203d5c3c5db6d046ec87b302a6c71b7f5a59ff185da360bac2bd5d3`
> current and
> `e45bfd4f0aa64a6eb2b23ae197513332c35fab32fed291b22f8851401a125abc`
> candidate.

> The unpaced native gate removed WGC, worker IPC and Qt, then alternated five
> 20-frame repeats per path. Before execution it required at least 20% lower RGB
> transfer P50, at least 3% higher whole native throughput and no more than 1%
> guide regression. The final source-hash run measured RGB transfer P50
> 2.0916 -> 1.2862 ms (38.51% lower) and guide P50 2.8159 -> 2.7730 ms (1.53%
> faster), but native throughput median was only 107.22 -> 110.13 fps (+2.71%).
> It therefore failed the declared whole-throughput gate; report SHA-256 is
> `9dfb944b77a977f7b5d012707d1bfc306575e8af4c66b238fd1fdcd0e36b8bd0`.
> A preceding semantic version of the candidate had narrowly measured +3.19%,
> so the final failure also shows the gain did not reproduce with enough margin.
> The candidate is rejected for promotion and the prepared-local product path is
> unchanged. The result does not establish sustained 4K60, scanout or VR quality.

<a id="record-result-retained-capture-promoted"></a>
## retained-capture-promoted

Checkpoint date recorded in source: 2026-09-08.

> The SBS worker and its WGC capture callback share one process. The selected
> candidate therefore transfers the ownership-bearing `windows-capture` NumPy
> mapped-frame view into a locked latest-frame slot instead of copying every
> 3840x2160 BGRA frame into a 33,177,600-byte `RawArray`. RGB conversion, model,
> depth/stereo math, native publication, source selection and the original-preview
> path are unchanged. Replacing a pending view releases its former native owner;
> stop clears the retained view before draining native capture.

> Unit coverage verifies exact view identity, replacement release, release before
> native stop, validation and the unchanged copy helper. The final product also
> allocates metadata only for SBS capture input, while original preview retains
> its fixed shared BGRA mailbox. Application tests passed 45/45 and contract/unit
> tests passed 240/240 after promotion.

> The predeclared actual-app comparison required at least 80% lower callback P50,
> at least 5% lower owned-worker CPU, no more than 1% regression in capture,
> processing or output rate, and no more than 64 MiB worker private-memory P95
> growth. Sequential sessions used the same public FloorballGame source,
> 3840x2160 input/per eye, 7680x2160 Full SBS, DA2 Small with the legacy Balanced
> policy, 60 Hz native
> output, six-second warmup and five six-second windows. Device-wide GPU preflight
> was 1% current and 0% candidate.
>
> | Actual-app metric | Copied current | Retained candidate | Change |
> |---|---:|---:|---:|
> | Callback duration P50 | 1.8641 ms | 0.0402 ms | 97.84% lower |
> | Owned-worker CPU | 2.6611 cores | 2.3953 cores | 9.99% lower |
> | Capture published | 62.0812 fps | 62.0707 fps | -0.02% |
> | Fresh processing | 61.5329 fps | 61.7979 fps | +0.43% |
> | Distinct output IDs | 59.8788 fps | 59.8455 fps | -0.06% |
> | Worker private-memory P95 | 1739.92 MiB | 1772.31 MiB | +32.39 MiB |
>
> All declared gates passed. Callback timing begins after native readback and
> Python/GIL entry, so the result attributes the removed host copy rather than
> total capture latency. Output IDs are Qt/native application submissions, not
> scanout. The comparison report is
> `out/live-retained-capture/comparison-floorball-4k-balanced-final-20260908/report.json`,
> SHA-256
> `4a6a2b4de73466c319a1f7873c5bca58aa73be83e14b2e335195028ae4ef5c0a`;
> current/candidate `runs.json` hashes are
> `eadedb577e77c0ca6d2ccfd2f85beeb17bb9ee8a48550bb423a90e363e6fb7e3`
> and `6f600769be561680c47bce23788e9c62b2a30f3a4ef33dc78a3a0dffcf93ddb8`.

> A second-session stall seen during early multi-mode work reproduced on the
> copied baseline: the hidden benchmark had removed every demand-driven native
> consumer while waiting for submissions. Exposing one initial frame per session
> and one stopped cleanup frame fixed that harness error. Baseline Performance/VQ
> restart controls and retained Performance/VQ functional runs then completed;
> every final sequential run reported zero native pools and nodes after stop.

> After product wiring and removal of the unused shared capture allocation, a
> final default-path (no candidate flag), 0%-GPU-preflight DA2 Small smoke using
> the legacy Balanced policy recorded
> 62.4751 capture, 62.1446 processed and 59.8307 distinct output IDs/s, callback
> P50/P95 0.0373/0.0656 ms, and zero shared capture-pixel bytes/pools/nodes after
> stop. Its `runs.json` SHA-256 is
> `39386f07d5ad092cf5c88799cc5c9afe9d83791ad541630e8914caf1dea6a846`.
> The recorded final source SHA-256 values are
> `4290f0f8ec2a683fb0d93de5bcd0bbdd6fb598ff3c77bee7fcb4fb80abc8ceed`
> for `live_sbs.py`,
> `efcf736b498b34c0663ba13bc2156f1ef61924131e2da51496fdfe15caffb5e2`
> for `capture_worker.py`, and
> `e30ffd36d9fe6ed743c32688c16608f15f6d81477cfadc4610cc7245b0967920`
> for `live_preview.py`.
> This short single-content smoke confirms product wiring and cleanup only. The
> selection does not establish sustained 4K60, 1:1 fullscreen/physical scanout,
> continuous visual quality, VR comfort, long-session/device-loss behavior,
> packaging or another GPU.

<a id="record-result-model-defined-live-routing"></a>
## model-defined-live-routing

Checkpoint date recorded in source: 2026-09-08.

> The source desktop now owns one mode-to-model contract used by both file jobs
> and immutable live session snapshots: Performance selects DA2 Small, Balanced
> selects DA2 Base, Video Quality permits only oVDA or VDA, and Offline Quality
> remains file-only with streaming VDA as the currently installed placeholder.
> Cross-mode model combinations, missing engine/runtime paths and unconfirmed oVDA
> use fail before worker launch. The UI changes the model with the mode and exposes
> a second model choice only for Video Quality. There is no model fallback.

> Performance retains the fused DA2 Small and optional native-texture paths.
> DA2 Base, VDA and oVDA currently return host depth into the existing CUDA stereo
> path; native texture selection is rejected for those models. Stateful engines
> receive start, cut, discontinuity and source-change resets from the live owner.
> Input profile changes recreate the selected engine rather than reuse an engine
> with the wrong shape.

> All 233 GPU-free core/platform/profile/quality contract tests passed in one
> classified run. A focused 58-test routing, GUI-controller, backend and
> existing-mode set also passed.
> Read-only binding checks validated the installed 3840x2160 DA2 Base and VDA
> profiles and trusted plan manifests. One initial Balanced smoke stopped before
> model creation because the ad-hoc runner omitted the prepared PyTorch path; it
> is not a product failure or performance result and was preserved separately.

> A final sequential actual-GPU source-window smoke used an RTX 5090, generated
> 1280x720 content, 30 Hz presentation target, one-second warmup and one measured
> second per mode. Balanced reported `model=da2-base`, and Video Quality reported
> `model=vda-small`; both policy backend fields matched and both used the declared
> `model-host-depth-cuda-stereo` path. Observed processed/output submission rates
> were 12.94/13.93 fps and 17.89/16.90 fps respectively. These tiny generated-source
> windows prove routing, execution and sequential restart only. They do not support
> comparative performance, sustained throughput, visual quality, 4K, scanout, VR,
> oVDA execution, dedicated Offline Quality or long-session cleanup claims.

> The sequential `runs.json` SHA-256 is
> `f007c7b71e14c46d9299406856b20876626ced1ee7572f2b293d1381f19b6556`;
> `environment.json` is
> `ec36a8abd0bacf76e7a4a839f1ab5b90793797a205b37bc42cf083b96e23740d`.

<a id="record-result-live-gpu-idle-recheck"></a>
## live-gpu-idle-recheck

Checkpoint date recorded in source: 2026-09-05.

> 2026-09-05. The user confirmed other GPU work during the previous comparison.
> Rendering/model/policy code is unchanged. This remeasurement uses the same
> 1080p generated WGC source, Full SBS output and actual Qt output swap counting.

> Each mode/path has a fresh session, eight initial frames, six discarded warm-up
> seconds and five six-second windows. Path order is reference/candidate for
> Performance, candidate/reference for Balanced, reference/candidate for Video
> Quality. Fifteen timestamp/CRC output-readback probes run separately from the
> throughput windows. Readback latency is not physical motion-to-photon.

> `v1/remeasure_live_gpu.py` requires three device-wide utilization samples <=5%
> before each session (retrying up to 30 samples while prior work settles) and logs
> GPU utilization, memory-controller utilization,
> VRAM, power, temperature and SM clocks during each session. Observation runs on
> a separate thread with `nvidia-smi` about once per second, identically for both
> paths. It does not kill or pause any other process. Resident WDDM applications,
> including Comfy Desktop, remain; preflight idleness is not exclusive ownership.

> Raw reports/logs/manifest and GPU observations are retained under
> `out/live-gpu-speed/recheck-idle-20260905/`. Older artifacts are not overwritten.
> Source hashes and GPU/driver/model environment are recorded by each child run.

### Results

> All six sessions completed: 30 measured windows total. RTX 5090 / driver 616.64,
> same pinned CUDA candidate DLL and DA2 Small model as the previous comparison.
> Output fps is median (min–max) across five windows, not isolated inference speed.

> | Mode | Reference output fps | Candidate output fps | Readback P95 reference → candidate, ms | Valid probes reference / candidate |
> |---|---:|---:|---:|---:|
> | Performance | 19.22 (19.00–19.38) | 29.16 (28.64–29.78) | 153.9 → 85.4 | 15/15 / 15/15 |
> | Balanced | 19.05 (19.03–19.19) | 29.16 (28.78–29.60) | 129.8 → 72.9 | 14/15 / 15/15 |
> | Video Quality | 18.86 (18.53–19.04) | 29.43 (28.94–29.65) | 148.6 → 80.8 | 13/15 / 15/15 |

> Candidate processed-fps medians were 59.26, 57.92 and 57.98 respectively, but
> actual output remains about 29 fps with the current 33 ms GUI polling. These
> numbers do not establish 60 fps output or maximum GPU throughput.

> All candidate windows meet the same local >=28.5 output-fps criterion (30 Hz
> minus 5%). Video Quality's prior ~25 fps output trough did not recur. Together
> with the user's confirmation, this is consistent with competing work influencing
> the previous run; the earlier slowdown is not sufficient evidence of an inherent
> Video Quality defect. This is still a short generated-source test on one machine,
> not an exact sustained 30 fps, long-run stability, representative-video quality,
> or VR-comfort guarantee. Default promotion is not part of this remeasurement.

> The observer recorded no query errors. Preflight's accepted trailing three samples
> were <=5% for every session. The initial observer saw 0% GPU utilization and about
> 2282 MiB resident device memory. A first attempt to start Balanced immediately
> after Performance saw 7%, then 0%, 0%; it stopped before creating that benchmark.
> The wrapper was changed to wait for three consecutive quiet samples (up to 30),
> then resumed only the four unfinished sessions. The failed preflight JSON is
> retained. No completed session or unfavorable window was discarded.

> One-slot overload tests still pass for all six runs. Candidate worker private
> memory ranged about 1239–1298 MiB, with first/last window median changes near zero
> or negative. Reference Video Quality's short-window median increased ~15.6 MiB;
> this is not a memory-stability acceptance run. GPU samples are device-wide, and
> WDDM process memory is unavailable from the process query; no per-process VRAM or
> exclusive-GPU claim is made. Other applications were not closed or terminated.

> No rendering code, mode setting, model, resolution, or DLL changed. Only the
> measurement wrapper, evidence and documentation were added/updated; its Ruff
> format/check passed. Previous regression-test results are not represented as
> newly rerun tests in this measurement-only task.


<a id="record-result-live-gpu-speed-results"></a>
## live-gpu-speed-results

Checkpoint date recorded in source: 2026-09-05.

> 2026-09-05. Prepared-local, explicit opt-in. No public release, silent fallback,
> resolution reduction or model replacement. Default live/file paths are retained.

### Measured bottleneck and implementation

> The bounded matched 1080p CPU profile (`out/live-gpu-speed/baseline/`) measured
> median preprocess 2.33 ms, inference 2.23 ms and temporal/stereo 43.02 ms, total
> 47.70 ms. cProfile adds overhead; this excludes capture and Qt, so is diagnostic,
> not end-to-end fps. Across 60 frames guide work consumed ~1.19 s, including
> ~0.75 s in six box filters per frame. This motivated GPU postprocessing first.

> `experiments/cuda_projection/live_depth.cu` and `live_gpu_candidate.py` now own:

> - CUDA input normalization/layout; exact OpenCV uint8 cubic resize stays on CPU.
> - TensorRT output borrowed directly on its owning stream, with no raw-depth D2H.
> - CUDA depth cubic enlargement, CUB radix sort/percentiles, temporal normalization,
>   local motion dilation and image-guided filtering.
> - Existing conservative, deterministic paired-eye projection using device depth
>   and disparity, without uploading host depth/shift on the normal path.

> Uniform-background refinement remains the existing CPU connected-component /
> distance-transform implementation when its border eligibility predicate passes.
> That path explicitly downloads aligned depth and uploads it only when refinement
> actually changes it. It is not disabled to obtain better speed. Performance's
> existing policy disables this refinement; no mode policy changed here.

### Transfer and ownership contract

> For N input pixels and full-rate inference, reference explicit H2D is
> 11N + 3*518*518*4 bytes; candidate normal-path H2D is 3N + 3*518*518 bytes.
> Reference D2H is 6N + 518*518*4 bytes; candidate normal-path D2H is 6N + 4 bytes
> (the finite-output flag). Eligible CPU background checks add 4N D2H and one
> synchronization, and actual refinement adds 4N H2D. Input reuse avoids the small
> input upload. No claim includes TensorRT-internal or profiler-measured traffic.

> The normal candidate path has one final synchronization. The depth engine and
> postprocessor share one stream; inference submission is not completion. Raw
> device depth is validated as a generation-scoped borrowed object belonging to
> that engine, stream and owner thread. Next inference expires it; closing the
> engine invalidates it. GPU resources are closed before the borrowed stream.
> Fixed per-resolution arrays, radix-sort scratch and nine timing events are
> allocated once; resize closes the old allocation set before creating the next.
> Cuts/gaps reset depth/temporal state without allocating another frame queue.

> CUDA failure/non-finite depth stops the session, never switches to CPU. The
> wrapper becomes unusable after a reported native/numeric failure. Partial native
> allocation errors attempt all releases; release errors remain visible. WGC
> readback, host BGRA/RGB conversion, input resize, output copies/shared mailboxes,
> QImage and Qt upload remain: **zero_copy=false**.

### Numerical gate and known differences

> Before the extended comparison, the candidate gate was set to aligned-depth
> MAE <=1e-6, max <=1e-4; SBS RGB MAE <=0.05 byte levels and changed-pixel fraction
> <=0.001. Input tensor normalization must be exact. These are engineering
> regression thresholds, not perceptual/VR acceptance criteria.

> 45 real-engine comparisons cover the user's six-frame avatar hand interval,
> moving flat-background/thin-structure/cut fixtures, and random cut frames across
> all three live modes. Input tensors are exact; all numerical gates pass. Explicit
> reset equals a fresh candidate, reused depth remains valid until the next
> inference, and stale/cross-thread use is rejected. Local reference/candidate hand
> images are retained; none were published.

> An initial GPU grayscale implementation used 14-bit coefficients, differing from
> this OpenCV build. A million RGB samples identified exact 15-bit coefficients;
> the corrected pipeline reduced aligned-depth errors substantially. Another first
> test falsely reported input errors because `empty_like` preserved the reference
> tensor's non-contiguous strides; using a contiguous readback buffer restored
> exact comparison. Failed artifacts remain separate, not counted as passes.

> GPU/CPU arithmetic is not generally bit-identical. Near depth/shift quantization
> ties can change a small number of projected pixels. Therefore this candidate is
> explicitly opt-in, not a replacement for the accepted default or proof that the
> user's residual hand artifact is eliminated.

### Reproduction and use

> Run `Run-DepthSBS-GPU-Candidate.cmd` to open the unified GUI with the explicit
> `DEPTHSBS_LIVE_GPU_CANDIDATE=1` snapshot; the mode description says **실험 GPU 가속**.
> Select DA2 Small SBS and a live profile normally. The standard `Run-DepthSBS.cmd`
> does not set this option. File conversion is unchanged. This build is restricted
> to compute capability 12.0 (locally tested RTX 5090), not broad NVIDIA support.

> Build with `scripts/build-live-depth.ps1`; it records CUDA/compiler, architecture,
> native source/projection source and DLL hashes in `out/live-depth-candidate/`.
> The Python adapter pins the validated DLL hash; a different rebuild requires
> review and revalidation, not automatic trust. No additional model/runtime is
> downloaded. Existing CUDA Toolkit/CUB is used only in the developer build.

> Diagnostics use the prepared Python/PYTHONPATH from the earlier live results:

> ```powershell
> python v1/profile_live_gpu.py
> python v1/test_live_gpu_quality.py --output out/live-gpu-speed/new-quality
> $env:DEPTHSBS_LIVE_GPU_CANDIDATE='1'
> python v1/benchmark_live_modes.py --output out/live-gpu-speed/new-candidate --sizes 1920x1080 --seconds 6 --repeats 5
> ```

> Use fresh artifact directories. Source/fixture local paths are not public assets.
> Full-live benchmark results and final regression status are recorded below.

### Historical 1080p measurements with competing GPU work

> The user subsequently confirmed another GPU workload was active during these
> measurements. Retain the data as contention observations, not an idle baseline
> or evidence of an intrinsic Video Quality slowdown. See
> [idle remeasurement](live-performance.md#record-result-live-gpu-idle-recheck) for the follow-up comparison.

> RTX 5090, driver 616.64, Windows 11 build 26200, Python 3.13.14, Qt 6.10.2 D3D11,
> CUDA 13.1.80, TensorRT 11.2.1.2; single SDR 4K display at 150% DPI/240 Hz.
> Final DLL SHA256 `f2d3b3f30cca3145b29920818afee59ab699aa6eac2ef219de8c252c6c955fb4`.
> The moving generated source, Full SBS geometry, strength, five six-second windows
> after discarded warm-up, and separate timestamp/CRC output-readback probes follow
> [the previous protocol](live-performance.md#record-result-live-mode-performance-results). Candidate then reference
> ran sequentially, not randomized/interleaved. Other desktop workloads were not
> controlled. This is a short local characterization, not a reproducibility audit.

> | Mode | Reference output fps median (range) | Candidate output fps median (range) | Readback P95 reference → candidate, ms |
> |---|---:|---:|---:|
> | Performance | 13.42 (13.40–19.19) | 29.28 (28.80–29.80) | 148.7 → 72.4 |
> | Balanced | 19.02 (18.55–19.05) | 29.11 (28.77–29.37) | 133.2 → 88.7 |
> | Video Quality | 15.72 (13.41–16.74) | 28.14 (24.52–29.28) | 157.2 → 65.7 |

> Candidate processed-fps medians were 58.63 / 58.39 / 35.25, separate from output
> cadence. The generated source itself is paced, so these do not establish maximum
> processing throughput or 60 fps output. Valid clock probes were 14/15, 15/15,
> 12/15 for both paths respectively. Readback latency is not physical scanout;
> small valid subsets outside throughput windows do not describe every frame.

> Performance and Balanced met the local 28.5 fps minimum-window candidate criterion;
> Video Quality did not. Keep the low windows: candidate Video Quality's first two
> windows processed only ~26 fps and output ~25 fps before recovering. Latest CUDA
> intervals showed large H2D/resize and projection/D2H delays while sort and guide
> stayed comparatively small. These intervals also contain stream/host enqueue gaps:
> they do not prove a PCIe, WDDM or thermal root cause. Reference runs also varied
> substantially. Do not advertise a universal speedup ratio or stable 1080p30 across
> all modes. Earlier reference results near 18 fps remain historical evidence.

> Balanced's five latest per-window GPU interval samples had guide around 1.04 ms
> (one 1.59 ms sample), input upload/normalization ~0.18–0.22 ms, raw-depth resize plus
> RGB upload ~0.51–0.63 ms, sort/bounds ~0.08–0.09 ms and projection/readback ~2.71–3.44
> ms. These are sparse stream intervals, not isolated GPU busy-time percentiles or
> the complete-frame denominator. Host guards/resize, capture and Qt costs remain.

> Artificially slowing GUI consumption to 200 ms caused 150–167 output replacements
> per candidate group, with pending <=1. Candidate worker private memory sampled
> ~1247–1301 MiB; first/last window medians did not grow in the final run. Earlier
> candidate runs did grow by up to ~12 MiB. Neither observation proves leak freedom;
> whole-process/VRAM peaks and deferred long-run verification remain open. The
> candidate allocates more GPU scratch than the reference and has not been measured
> at 4K; do not transfer the old 4K support/throughput numbers to this backend.

### Verification and retained artifacts

> - 177 unit/controller/worker tests pass (148 + 15 + 12 + 2).
> - 45 numerical comparisons pass; maximum aligned-depth MAE 1.79e-7, maximum
>   absolute error 4.98e-6, maximum RGB MAE 0.01013 and changed-pixel fraction
>   0.000113 (about 0.0113%). These are per-case maxima, not identical pixels.
> - Five actual-GPU NaN/failure/close cycles reject bad output, poison failed
>   contexts, reject wrong-thread close and invalidate tokens after engine close.
>   Invalid geometry fails before allocation. This is not real device-loss recovery.
> - All three final candidate GUI lifecycle tests pass; Balanced includes real
>   1080p capture before resize. Stop, fullscreen/Escape, exclusion, source-loss and
>   worker termination cleanup are retained. Existing GUI file conversion completes
>   with no QML warnings. Hand-frame images were inspected locally, not VR-reviewed.
>   A final Balanced lifecycle run using `pythonw.exe`, as used by the launcher,
>   also passes and records `gpu-candidate` in its report.
> - Ruff checks target Python 3.13; new/changed live test files are formatted.
>   Unrelated legacy formatting in the TensorRT module is preserved.

> Local artifacts under `out/live-gpu-speed/`:

> - `baseline/`: 60-frame CPU profile, raw stage rows and explicit backend traffic.
> - `live-final/` and `reference-final/`: final five-window results, summaries,
>   environment and implementation-file hashes. Sparse CUDA interval snapshots are
>   in each row's report; newer harness runs also sample those intervals every 250ms.
> - `live-candidate/`, `live-reference/`: earlier exploratory runs, not substituted
>   for the final ranges above. The earlier reference run overlapped developer build
>   activity; it is not the controlled-comparison baseline.
> - `quality-final/`, `quality-final-accounting/`: numerical/ownership comparisons;
>   `quality/` retains the failed stride-layout test, `quality-contiguous/` its fix.
> - `gui-*-final/`, `file-regression/`, `failures.json`: final lifecycle evidence.

> Source hashes in the timed runs precede formatting and final completion-counter bookkeeping; no kernel or rendering math changed afterward. No release, one-hour soak or headset verification was performed. Native WGC/CUDA/Qt texture interop and full GPU flat refinement remain separate unfinished work, not claimed by this implementation.


<a id="record-result-live-guarded-baseline"></a>
## live-guarded-baseline

Checkpoint date recorded in source: 2026-09-06.

> 2026-09-06. Current user-reported condition: Premiere Pro closed after a monitor
> on/off transition; monitor now off. This is not a monitor-on acceptance test.
> No product renderer, VSync setting, model, precision or output geometry changed.

> An explicit `--abort-output-below-fps 20` guard checks three-second output-rate
> windows after showing output, including warmup. A collapse saves `stop-alert.json`
> and stops the run. Per user request, notify and wait for monitor-on confirmation
> before retesting; do not continue causal diagnostics. It is not armed during
> intentional clock-readback/overload probes. Three unit tests cover window length,
> elapsed-time normalization, threshold and a simulated rate collapse. No actual
> low-FPS event was deliberately induced in this batch.

### Actual result

> Separate public FloorballGame source, 1920x1080 input / 3840x1080 Full SBS,
> Balanced, native GPU texture path, both product windows visible, 60 Hz target,
> capture telemetry on, no VSync override. A 3-second preflight passed at 59.56
> output fps; then 10-second warmup and five 10-second measurement windows passed.

> | Metric | Five-window range |
> | --- | ---: |
> | Source paint | 62.30–62.46 fps |
> | SBS processed | 62.27–62.39 fps |
> | Native distinct output IDs | 59.79–59.99 fps |

> No rate guard triggered. The separate 15-attempt clock-readback diagnostic had
> P50 27.94 ms and P95 39.03 ms; it is a small paint-to-readback sample, **not**
> physical scanout or VR latency. Deliberate 200ms consumer polling replaced 150
> capture inputs with pending=0 and slots=2; overload and normal stop passed.
> 205 unit tests and scoped Ruff lint/format pass. No test children remain.

> Evidence: `out/live-baseline-guarded/preflight/` and
> `out/live-baseline-guarded/balanced-native60/`, including runs JSON/CSV,
> environment and one-second device-wide GPU samples. Raw GPU samples include
> warmup/probes; filter by each row's wall-time endpoints before aggregation.

> This establishes the current native60 baseline, not the full mode/path
> matrix, long soak, visual/VR acceptance, zero-copy or a fix for the earlier stall.
> Do not compare this state against Premiere-open or pre-monitor-transition runs
> as if they were an optimization A/B. Remaining redesign stages are still open.

### Performance and Video Quality extension

> All three labels in this section resolve to **DA2 Small**. They compare live
> stereo/temporal policies only; they are not DA2 Small vs Base vs oVDA model
> results. The original roadmap associates models with modes, while current
> delivery defaults retain Small. See [model-comparisons.md](model-comparisons.md#record-result-explicit-backend-performance-2026-09-06)
> for the subsequently requested model-explicit comparison.

> Both additional modes passed their own 3-second preflight, then 10-second
> warmup and five 10-second measurements, sequentially without overlapping jobs.
> The guard never triggered; overload and normal stop passed in all runs.

> | Mode | Native output range | Mean of five window rates |
> | --- | ---: | ---: |
> | Performance | 59.80–59.99 fps | 59.92 fps |
> | Balanced | 59.79–59.99 fps | 59.87 fps |
> | Video Quality | 59.70–59.91 fps | 59.84 fps |

> All three delivered 15/15 valid separate clock readbacks; their diagnostic P95
> values are 39.81, 39.03 and 39.21 ms respectively, not physical presentation
> latency. These small differences do not establish one mode is faster. Output is
> near the 60Hz target with this source; visual quality differences were not judged.
> Offline Quality remains file-only and is not a missing fourth live mode.

> `v1/summarize_guarded_baseline.py` verified shared benchmark/source/production,
> model, QML and native-DLL hashes plus fixed device/driver/configuration across
> the three runs, five valid windows each, dimensions and overload bounds. The
> result and raw artifact hashes are in
> `out/live-baseline-guarded/three-mode-summary.json`. The new runs are in
> `performance-native60/` and `video-quality-native60/` beneath the same root;
> their corresponding `*-preflight/` folders preserve short checks.

> 205 unit tests pass after the extension; the summary script passes Ruff and its
> actual three-mode artifact check. No product code or settings were modified.


<a id="record-result-live-headless-sbs"></a>
## live-headless-sbs

Checkpoint date recorded in source: 2026-09-06.

> 2026-09-06. Diagnostic harness only; no production rendering changes.

> `probe_capture_only.py --sbs-host` launches the unchanged production SBS worker,
> including its capture thread and GPU candidate, with Balanced, strength 1.0,
> 1920x1080 input and explicit capture interval 0. One preallocated BGRA consumer
> buffer receives each latest host output while holding its mailbox lock; ACK is
> written only after the complete copy. It never imports or acknowledges native
> textures. This path includes GPU-to-host transfer and is not a native-headless
> consumer test. No product Qt window is created.

### Current sequential observations

> Artifacts are under `out/live-headless-sbs/`. Public FloorballGame, separate
> source, three-second warmup/windows, three repeats except capture control (one).

> | Run | Measured rate |
> | --- | ---: |
> | `host/report.json`, headless GPU SBS processed | 61.95–62.62 fps |
> | `host-gui/runs.json`, host GUI output submission proxy | 59.52–60.43 fps |
> | `native-gui/runs.json`, native distinct output IDs | 59.24–60.30 fps |
> | `capture-control/report.json`, capture-only callbacks | 62.16 fps |

> Headless source/capture remained ~62 fps. Consumed rates can exceed processed
> rates by one frame at a measurement boundary because an already-published frame
> can be copied inside the next window; they are not duplicate-presentation counts.
> Shared worker statistics are latest samples, not coherent per-frame traces.

> All runs completed normally. Both GUI runs passed existing overload/pending-slot
> guards and stop checks. Headless and capture control finished without forced
> termination and with complete capture telemetry. 202 unit tests and scoped Ruff
> lint/format checks pass, including copy-before-ACK, failed-copy and invalid-shape
> tests. This does not rerun numerical render parity: product renderer is unchanged.

### Interpretation and limit

> The earlier ~4–7 fps full-app stall did not reproduce in this batch. Even the
> capture-only control now measures ~62 fps instead of the preceding ~42–48 fps.
> The GUI environments record `qsg_no_vsync=null`, `qsg_render_loop=null` and capture
> interval 0. No product optimization or persistent display setting was changed.
> These results cannot be attributed to a rendering fix or used to declare the
> intermittent stall resolved. The user previously reported monitor-off operation;
> The user subsequently clarified: they turned the monitor on, closed Premiere
> Pro, then turned the monitor off again. Monitor-off alone therefore does not
> explain the earlier stall. Premiere resource contention and a display-state
> transition remain confounded possibilities, not proven causes.

> The headless test proves current production GPU SBS can process the supplied
> source at ~62 fps without output windows. Current GUI comparison does not prove
> that GUI caused the earlier stall, because the environment/state is not proven
> identical across the old and new runs. Host and native counters also differ in
> meaning. These short tests do not establish sustained performance or physical
> scanout/VR latency.

> Next preserve a matched baseline with Premiere closed and monitor off. Per the
> user's subsequent instruction, if a similar stall recurs, stop and notify them;
> wait for monitor-on confirmation before retesting rather than tracing causes.
> Use the normal benchmark protocol before prioritizing preview cadence/GPU-input/
> async changes. Do not implement speculative fixes from the low-FPS snapshot.


<a id="record-result-live-mode-performance-results"></a>
## live-mode-performance-results

Checkpoint date recorded in source: 2026-09-05.

> 2026-09-05. Tasks 4–5 complete for prepared-local implementation and measurement,
> not a public release or completion of V2's 1080p30/zero-copy milestone.

### Implemented policy

> The GUI exposes immutable Performance, Balanced (default), and Video Quality
> sessions, all explicitly DA2 Small. Offline Quality is file-only. Performance
> reduces guide/refinement work and reuses depth only when RGB is exactly unchanged
> on a non-cadence frame. Even one changed pixel forces inference. Sequence gaps,
> resize and scene cuts invalidate cached state. See [contract](../PRODUCT.md).

> VDA/oVDA are not silently enabled. Prior file measurements do not establish live
> capture throughput; streaming drop/reset behavior and oVDA non-commercial terms
> still need explicit integration/validation. See [model decision](model-comparisons.md#record-result-live-action-model-decision-2026-09-05).

### Protocol and environment

> Windows 11 build 26200, RTX 5090 32607 MiB, driver 616.64, Python 3.13.14,
> NumPy 2.5.2, Qt 6.10.2 D3D11, TensorRT 11.2.1.2. Single SDR 3840x2160 display,
> 150% DPI, 240 Hz. DA2 Small ONNX SHA256:
> `2df6223f206b5164e21f664ace61dabeb9bb6a49b8b5a3e00510b4807d0f5b04`.
> Paired projection DLL SHA256:
> `e01f922faab7d839febe084bd113df25c98ce72e654ed7889b465e6a6be9ec73`.
> Environment JSON records dirty checkout `55112b673dc405722efa8f678b9d98beadc0ce0f`;
> that commit alone does not reproduce the uncommitted source snapshot.

> `v1/benchmark_live_modes.py` paints an owned moving test window, captures via WGC,
> runs the real worker and displays Full SBS in a Qt output window. No unrelated
> desktop screenshots are saved. After eight initial processed frames and six
> discarded warm-up seconds, each profile/resolution has five six-second windows
> in one session (not five independent cold starts). Nine final groups contain 45
> windows. Other GPU workloads/clocks/thermals are not experimentally controlled;
> this is a local characterization, not a cross-device benchmark certification.

> Separate latency probes embed a 48-bit monotonic millisecond timestamp and CRC16
> in source pixels. Output-window readback recovers it within bounded disparity
> search and verifies it against actually painted timestamps. Fifteen probes per
> group run outside throughput windows because readback perturbs scheduling.
> Latency is **source paint to Qt output readback**, not physical motion-to-photon.
> Only successfully decoded probes enter percentiles; small valid subsets can bias
> them and are not all-frame latency distributions. Output fps counts actual Qt
> frameSwapped events; processing fps is distinct and may exceed output scheduling.

### Results

> Input dimensions are per eye; Full SBS doubles output width. Output fps is the
> median of five windows, with min–max in parentheses. Latency P95 is milliseconds.

> | Input | Profile | Output fps | Process fps median | Readback P95 | Valid probes |
> |---|---|---:|---:|---:|---:|
> | 1280x720 | Performance | 29.97 (29.82–30.14) | 43.77 | 110.2 | 14/15 |
> | 1280x720 | Balanced | 29.81 (29.69–30.13) | 43.12 | 89.4 | 13/15 |
> | 1280x720 | Video Quality | 29.93 (29.63–30.14) | 42.91 | 87.6 | 15/15 |
> | 1920x1080 | Performance | 18.52 (18.20–18.54) | 18.50 | 158.9 | 15/15 |
> | 1920x1080 | Balanced | 18.21 (18.02–18.34) | 18.18 | 151.4 | 14/15 |
> | 1920x1080 | Video Quality | 18.19 (18.04–18.22) | 18.05 | 155.1 | 15/15 |
> | 3840x2160 | Performance | 3.29 (3.12–3.30) | 3.29 | 699.8 | 10/15 |
> | 3840x2160 | Balanced | 3.29 (3.13–3.30) | 3.29 | 640.7 | 13/15 |
> | 3840x2160 | Video Quality | 3.14 (3.13–3.30) | 3.14 | 653.4 | 15/15 |

> 720p meets the local candidate criterion: every window >=28.5 output fps (30 Hz
> minus 5%). 1080p30 and 4K real-time do not pass. GUI guidance recommends a 720p
> source and shows these limits, without resizing behind the user's back. Other
> resolutions/hardware/content remain unvalidated. This workload changes the clock
> every frame, so Performance normally infers rather than benefiting from reuse.
> Neither mode names nor these short timings establish a visual-quality winner.

### Bounded overload and memory limits

> Input/output each have one fixed latest-frame slot (106,168,320 shared pixel
> bytes total). Artificially slowed GUI consumption increased replacement counters
> with pending output <=1 in every final group. The 720p/1080p poll interval was
> 200 ms; 4K needed 911–956 ms to become slower than processing. The earlier 4K
> 200 ms experiment did not overload a 3 fps producer and failed its assertion;
> it is retained as failed evidence, not counted as a pass.

> Worker private-memory samples ranged approximately 1117–1165 MiB at 720p,
> 1166–1250 MiB at 1080p and 1394–1817 MiB at 4K. Final-window versus first-window
> median growth at 4K was 13–19 MiB over this short run: **no leak-freedom or stable
> plateau claim**. These samples exclude other processes and VRAM. Fixed queues
> bound backlog, not every native/model allocation. Longer memory investigation
> remains necessary; the deferred one-hour soak was not performed.

### Optimization and regressions

> Combined 2nd/98th percentile evaluation replaces two scalar NumPy percentile
> calls. Casting results to the original dtype preserves scalar float32 rounding.
> Tests checked three depth shapes, 100 additional random arrays (exact quantiles),
> and 12 complete SBS RGB cases across all three profiles (exact pixels). Five
> isolated CPU timing repeats measured about 14.93 ms versus 11.52 ms median,
> roughly 23% less for this operation only, not the complete pipeline.

> Performance's exact-RGB guard also replaces an expensive float/local-density
> motion test for live processing only. Its stronger guard intentionally avoids
> reusing depth on small hand changes. The non-interleaved baseline/final runs are
> not sufficient for a robust end-to-end speedup claim. File mode policies remain
> unchanged. Host preprocess/temporal work and transfers remain; this is not zero-copy.

> All three actual GPU GUI lifecycle runs passed: selected QML mode, distinct eyes,
> display exclusion, fullscreen/Escape, resize, stopped-output clearing, restart,
> source loss and worker-crash cleanup. All 173 unit/controller/worker tests passed
> (144 + 15 + 12 + 2). Actual GUI file conversion completed with no QML warnings.
> Ruff checks use the installed Python 3.13 target; changed live/test files pass
> format checks. The shared pipeline file's unrelated legacy formatting is retained.

### Local artifacts and reproduction

> - `out/live-modes/repeated/{runs,summary,environment}.json`: final Balanced and
>   Video Quality 720p/1080p; Performance here is superseded.
> - `out/live-modes/performance-final/{runs,summary,environment}.json`: final
>   Performance 720p/1080p with exact-RGB guard.
> - `out/live-modes/final-4k/{runs,summary,environment}.json`: all final 4K profiles.
> - `out/live-modes/quantile-parity.json`: exact pixel cases and isolated timings.
> - `out/live-modes/gui-{performance,balanced,video-quality}/`: lifecycle reports
>   and generated-source screenshots; `file-regression/`: file GUI regression.

> Use the prepared Python environment and PYTHONPATH documented in
> [foundation results](stereo.md#record-result-live-sbs-results), then run:

> ```powershell
> python v1/benchmark_live_modes.py --output out/live-modes/new-run --seconds 6 --repeats 5 --sizes 1280x720,1920x1080,3840x2160
> python v1/summarize_live_modes.py out/live-modes/new-run
> ```

> Artifacts are local/ignored, not published. Next work is representative motion,
> text/UI and scene-cut quality plus longer whole-resource stability (task 6),
> followed by GUI/settings polish (task 7). Native GPU preprocessing/temporal and
> capture-to-output transfer optimization remain necessary for a 1080p30 goal.
> No release, headset validation or one-hour soak was performed.


<a id="record-result-live-native-1080p"></a>
## live-native-1080p

Checkpoint date recorded in source: 2026-09-06.

> Status: **30-target bounded comparison complete; 60-target comparison provisional**.
> Owner: DepthSBS. Date: 2026-09-06. No default promotion or release.

### Conditions and provenance

> RTX 5090, public FloorballGame window, actual capture 1920x1080 and Full SBS
> 3840x1080 (asserted for every repetition). Same DA2 Small model, mode policy,
> strength, QML and processing source hashes across four batches. Both normal
> windows; output configured at 1400x650 logical pixels, so this is not a 1:1
> fullscreen-display benchmark. Five ten-second measurements after ten seconds
> of discarded warmup per mode/target/path: 60 measured intervals total.

> Raw JSON/CSV, one-second device telemetry, initial GPU/process inventories and
> environment records are under `out/qt-native-delivery/1080p-{host30,native30,native60,host60}`.
> All four processes terminated successfully and passed dimension/overload checks.
> The qualified summary is `out/qt-native-delivery/1080p-summary-qualified/summary.json`.
> The earlier `1080p-summary` is the unqualified aggregation; use the qualified
> record for interpretation. Benchmark SHA-256:
> `3d32760832583a7e19f24e2a4d9142bddb771983547e97d54153c50e68900ace`.
> Native/runtime DLLs are unchanged from the dual-window integration.

### 30-target results

> Output figures are median (minimum–maximum) of five repetitions, in submitted
> frames/s. Native counts distinct afterFrameEnd IDs; host remains a callback
> submission proxy. Neither measures physical scanout.

> | Mode | Host | Native |
> | --- | --- | --- |
> | Performance | 30.003 (29.917–30.079) | 29.981 (29.952–30.055) |
> | Balanced | 30.010 (29.885–30.083) | 29.984 (29.969–30.079) |
> | Video Quality | 30.016 (29.943–30.089) | 30.020 (29.973–30.066) |

> CPU is median core-equivalent usage, with GUI **including the source video
> decoder/painter**, then the owned SBS worker. GPU values are device-wide medians
> restricted to measurement windows, including normal desktop activity.

> | Mode | Host CPU GUI + worker | Native CPU GUI + worker | GPU utilization host / native | Device VRAM host / native, MiB |
> | --- | --- | --- | --- | --- |
> | Performance | 1.349 + 1.928 | 1.018 + 0.938 | 27% / 24% | 3575 / 3594 |
> | Balanced | 1.438 + 1.903 | 1.024 + 0.999 | 32% / 26% | 3575 / 3593 |
> | Video Quality | 1.469 + 1.820 | 0.941 + 1.121 | 34% / 28% | 3575 / 3593 |

> Both paths remain near the 30 target. Native lowers measured CPU cost and device
> activity here, but does **not** lower device VRAM: its median is about 18–19 MiB
> higher. Absolute VRAM includes the desktop baseline (2567/2566 MiB preflight,
> both 0% GPU activity); it is not an isolated model allocation or a leak test.

> Clock readback ages are separate diagnostic probes, P50/P95 milliseconds:

> | Mode | Host age (valid/attempts) | Native age (valid/attempts) |
> | --- | --- | --- |
> | Performance | 43.10 / 65.26 (15/15) | 39.72 / 56.38 (11/15) |
> | Balanced | 53.34 / 57.09 (15/15) | 43.52 / 58.05 (13/15) |
> | Video Quality | 49.82 / 65.32 (15/15) | 39.54 / 52.27 (10/15) |

> Invalid CRC readbacks are excluded, not assigned zero age. The small and unequal
> valid sample counts do not establish a stable latency advantage or photon latency.
> Full distributions, private-memory samples and latest-value stage timings remain
> in the raw reports.

### 60-target measurements: comparison confounded

> | Mode | Host median (range) | Native median (range) |
> | --- | --- | --- |
> | Performance | 58.615 (58.044–58.776) | 59.838 (59.626–59.973) |
> | Balanced | 58.097 (57.614–58.463) | 59.781 (59.329–59.994) |
> | Video Quality | 58.182 (57.969–59.046) | 59.744 (59.036–60.060) |

> These figures are **provisional, not a fair speedup claim**. Native60 preflight
> was 0% GPU / 2566 MiB; host60 preflight was 5% / 4876 MiB. Premiere Pro, its
> helper and another Python GPU process appeared in the recorded inventory between
> these batches. The changed baseline is not attributable to DepthSBS by these
> device-wide counters. Host60 median VRAM 5825–5869 MiB must not be compared to
> native60's 3594–3690 MiB as a memory-saving result. Other programs were not stopped.

> The summary flags nonzero preflight activity or a baseline shift over 512 MiB as
> a confound; this is a screening warning, not proof of isolation when clear.
> Repeat **both** 60-target paths while other GPU work is paused, with fresh output
> folders. The user has been asked whether a roughly seven-minute retest is possible.
> 30-target evidence is preserved; no need to discard or overwrite completed runs.

### ComfyUI-unloaded paired retest (retest3)

> At the user's request, unloaded ComfyUI models and executor cache after confirming
> the actual running/pending queue was empty. Server and jobs were not terminated.
> Device memory dropped from about 29 GiB to 5778 MiB. The interrupted retest2 is
> preserved and excluded. Both retest3 batches completed 15 windows each; the
> summary's shape, overload, configuration and benchmark-hash assertions passed.

> | Mode | Host median fps | Native median fps |
> | --- | --- | --- |
> | Performance | 53.021 | 55.587 |
> | Balanced | 51.927 | 56.506 |
> | Video Quality | 51.690 | 56.856 |

> Preflight memory was closely matched (native 5597 / host 5599 MiB), but native
> preflight GPU utilization was 5% versus host 0%. The background-warning gate
> therefore remains flagged. These are observed results, not an isolated causal
> speedup or sustained 60-fps acceptance. Both paths were slower than the earlier
> session; unloading alone does not establish the cause of that difference.
> Native median GUI/source CPU was 0.998–1.051 cores and worker 0.920–1.056,
> versus host 1.378–1.560 and 1.618–1.716. Device-wide median VRAM was 6625 MiB
> native and 6607 MiB host; no memory-saving claim. No production code changed.

> Evidence: `out/qt-native-delivery/1080p-native60-retest3`,
> `1080p-host60-retest3`, and `1080p-summary-retest3/summary.json` under the same
> root. Original 30-target batches are reused without modification.

> With the prepared repository Python and documented PYTHONPATH:

> ```powershell
> ./out/vda-oracle-env/Scripts/python.exe v1/benchmark_live_modes.py --path gpu --hz 30 --sizes 1920x1080 --seconds 10 --repeats 5 --sample-gpu --output out/new-1080p-host30
> ./out/vda-oracle-env/Scripts/python.exe -m unittest test_benchmark_live_metrics -q
> ```

> Change path/target for the remaining conditions. The summary supports
> `--sixty-suffix` for a fresh paired 60-target retest without overwriting originals.
> Three CPU/statistics guard tests and scoped lint/format pass. No production
> processing changes, quality-tolerance changes, DLL rebuilds, commits or pushes.
> This is not the separate long-duration, device-loss, VR or packaging acceptance.


<a id="record-result-live-performance-redesign"></a>
## live-performance-redesign

Checkpoint date recorded in source: 2026-09-06.

> 2026-09-06. Phase 1 correctness verified; no throughput acceptance yet.

### Independent callback observations

> `DEPTHSBS_CAPTURE_TELEMETRY=1` is an explicit diagnostic switch (default off).
> `benchmark_live_modes.py --capture-telemetry` enables it in the benchmark process
> and owned children. Invalid values fail session startup. The regular input/output
> mailbox remains unchanged. An additional fixed 256-record ring and seven counters
> are allocated only for this diagnostic, not a frame queue. Each record contains
> callback ordinal, entry/exit QPC nanoseconds, WGC source time and outcome
> (0 published, 1 mailbox lock contention, 2 failed).

> The sole callback writer accumulates independent totals and attempts to publish
> under its own nonblocking diagnostic lock. Busy readers cause missing diagnostic
> records, not delayed capture; those misses are counted in the next coherent
> snapshot. Busy snapshots are unavailable, never zero. Ring overwrite is expected;
> record ordinals permit detecting gaps. Completion is marked only after normal
> capture-control stop and a successful nonblocking final publish. An incomplete
> snapshot after failure/crash is not proof that capture is still running.

> These timestamps start inside the Python callback, **after** upstream native
> readback and Python entry/GIL scheduling. They cannot distinguish WGC capture
> delay from native readback or establish physical-display latency. Source clocks
> are not subtracted from QPC without calibration. Endpoint snapshot lag and
> diagnostic loss remain visible. Legacy `capture_arrival_fps` is retained for
> compatibility but explicitly labeled a forwarded/cached sequence proxy. New
> `capture_observation_rates` uses independent callback-snapshot time bounds.
> The benchmark source still runs in the GUI process. Native readback tracing,
> separate-source benchmarking and end-to-end frame-ID traces remain future work.

### Compact scene history

> The live GPU candidate retains a 32x32 RGB float32 thumbnail (12,288 bytes),
> instead of a full-resolution RGB copy used only for scene-cut detection
> (6,220,800 bytes at 1920x1080). This is cut-history storage, not total process
> or GPU-memory saving. GPU temporal RGB and inference-reuse history are unchanged.

> The resize remains OpenCV's default interpolation, float32 absolute difference
> and mean, Python float conversion/division by 255 and strict threshold comparison.
> The live worker passes one owner/epoch/frame-validated observation to rendering.
> Render commits it only after successful GPU processing. Reset, gap and resize
> invalidate observations; initial/reset frames are inspected again as needed.
> Standalone rendering computes its own observation. File/reference processing,
> inference input cubic resize, models, strengths and quality thresholds do not change.

> The standalone public texture worker uses the same compact history; it must not
> silently continue writing the removed full-frame history field. Existing native
> DLL layouts and hashes remain unchanged.

### Verification and next gate

> Unit tests compare 180 old/new predicates across three sizes, five thresholds,
> random/flat frames and resets; verify one resize in the shared observation path,
> owned immutable compact history and rejection after reset/commit/foreign use.
> Telemetry tests cover wrap, unavailable snapshots, diagnostic contention,
> cross-session rejection, real spawn transport and fake capture publication/drop.
> Completed checks: 233 unit/controller/worker/metrics tests; all 3,447 GPU cases
> pass unchanged reference limits and are exact against serial and runtime paths;
> 126 public-worker exact comparisons and 12 clears; five GPU failure cycles;
> native 30/60-target and default-host 30-target GUI lifecycle checks.
> Artifacts are under `out/live-performance-redesign/`: `quality/report.json`,
> `worker-quality`, `failures.json`, `gui-native60`, `gui-native30`, `gui-host30`.
> No FPS improvement is inferred from fewer CPU copies or isolated timings.

### Monitor-off diagnostic limitation

> The user confirmed the monitor was off and instructions were remote. This does
> not establish an RDP session. Native-60 diagnostics measured only 2.49–2.98 output
> fps; the telemetry-off control measured 2.49–2.70 fps. These are not accepted
> normal-display performance results. Callback diagnostics showed zero mailbox
> contention and diagnostic misses, but cannot attribute upstream readback waits.

> An owned source-only probe, with no capture/depth worker, isolated GUI coupling:
> the static product shell sustained 62.25–62.63 source paint fps, while updating
> both Qt Quick windows yielded about 3.66 fps after warmup and 244–246 ms
> `processEvents` P95. Process-local `QSG_NO_VSYNC=1` restored about 62.30 fps and
> 2.6 ms P95. This supports display/VSync waiting in the current environment,
> not a new model/scene-history bottleneck. It does not justify a production
> VSync change or prove physical-display latency. No persistent setting changed.

> Reproduce using the prepared Python environment and existing dependency
> `PYTHONPATH`: run `v1/probe_live_source_loop.py --shell --output <fresh.json>`,
> then add `--two-windows`, then repeat with process-local `QSG_NO_VSYNC=1`.
> Each run records three 3-second intervals; the first includes warmup. Saved
> evidence: `source-shell.json`, `source-two-windows.json`, and
> `source-two-windows-no-vsync.json` in the artifact directory above.
> `benchmark_live_modes.py --profile-gui` optionally writes `gui.pstats`; it is
> off by default and measures GUI CPU call attribution, not GPU kernel latency.
> The `gui-profile` artifact records dominant `processEvents` time.

> Next performance gate requires a normal-display baseline or an explicitly
> separate headless contract, plus source isolation before comparing throughput.
> Preview cadence, native GPU input, asynchronous completion and CUDA Graphs
> remain unimplemented follow-up stages.

> Plan: [live-performance.md](live-performance.md#record-plan-live-performance-redesign).


<a id="record-plan-live-gpu-idle-recheck"></a>
## live-gpu-idle-recheck

Checkpoint date recorded in source: 2026-09-05.

> 2026-09-05, completed. User confirmed competing GPU work during prior timing.
> Do not change rendering math or terminate other applications. Re-run 1080p all
> three modes, reference and candidate, five six-second windows per fresh mode/path
> session using the existing clock/readback protocol. Alternate path order between
> modes; record initial idle samples and concurrent device-wide utilization/power/
> temperature/clocks. Preserve prior contaminated measurements as historical, not
> a valid no-competing-work comparison. Resident WDDM processes and device-wide
> samples cannot prove exclusive GPU ownership. Publish all repeats and anomalies.

> All six sessions / 30 windows completed; candidate output medians 29.16 / 29.16 /
> 29.43 fps. Prior Video Quality trough did not recur. All raw observations and a
> transient failed preflight are retained. See [results](live-performance.md#record-result-live-gpu-idle-recheck).


<a id="record-plan-live-native-1080p"></a>
## live-native-1080p

Checkpoint date recorded in source: 2026-09-06.

### Result / next required check

> All four batches completed (60 measured windows), shape/overload guards passed,
> and model/source/benchmark hashes match. Three instrumentation/statistics unit
> tests and scoped lint/format pass. 30-target comparison stays near 30 fps in both
> paths with lower native CPU usage and similar/slightly higher device VRAM.

> The 60-target comparison is provisional: preflight changed from 0%/2566 MiB to
> 5%/4876 MiB, with Premiere/helper/another Python GPU process appearing. Preserve
> the measurements but do not claim an unbiased speedup or VRAM saving. Asked the
> user whether other GPU work can pause for a paired 60-target retest. No external
> program was terminated. See [live-performance.md](live-performance.md#record-result-live-native-1080p) and the
> qualified summary; item 1 is not fully accepted until that retest is complete.

> User confirmed other work paused. First native60 retest attempt is preserved at
> `out/qt-native-delivery/1080p-native60-retest`: it stopped before measurement
> because the input desktop is `Screen-saver`, not `Default` (read-only Win32
> query confirmed). GPU was idle at 0%, with 28287 MiB resident and 3900 MiB free;
> this was not an out-of-memory error. Do not bypass the desktop guard. Resume in
> a fresh output directory after the user returns to the ordinary desktop.

> User authorized dismissing the screensaver while away. The supported Computer
> Use tool returned a black window capture; a single non-text Shift input attempt
> failed with Windows access denied (`GetCursorPos`, 0x80070005). No authentication,
> security-setting change or alternate input-injection bypass was attempted. No
> new benchmark started. Normal interactive desktop access is still required.

> User restored the desktop; native60 retest2 was interrupted at the user's
> request to unload ComfyUI models. Preserve its partial results. The live ComfyUI
> queue was empty; requested model/cache release without stopping the server or
> canceling jobs. Device VRAM fell from about 29 GiB to 5778 MiB, GPU idle 0%.
> Repeat both paths into fresh retest3 folders and validate matched preflights.

> Retest3 completed both 15-window batches, summary assertions passed. Native
> median output 55.587/56.506/56.856 fps versus host 53.021/51.927/51.690.
> VRAM baselines match within 2 MiB, but native preflight 5% versus host 0%
> still flags the background-warning gate. Document observed performance without
> claiming isolated speedup or sustained 60 support; fair-isolation acceptance
> remains open. No production changes or user-process termination.


<a id="record-plan-live-performance-redesign"></a>
## live-performance-redesign

Checkpoint date recorded in source: 2026-09-06.

### oVDA device-depth spike (approved continuation)

> The same-consumer substep also passed. The separate
> `ovda-device-post-spike` DLL produced exact left/right SBS pixels for 12/12
> frames. Three order-alternated measured runs were 27.61 fps for host depth and
> 29.21 fps for device depth (+5.8%) through identical CUDA temporal, guided and
> SBS stages. Evidence is `out/ovda-device-post/current-v2/report.json`. This is
> still a host-RGB/host-output spike, not integrated live output or zero-copy.

> Allocation/cache candidate measured and rejected for promotion. It retained
> 12/12 exact final SBS frames, but median throughput only changed 29.28 -> 29.42
> fps (+0.47%) while two fixed cache banks reserve 381,714,432 bytes instead of
> one 190,857,216-byte active cache. Fixed output buffers reserve another
> 13,843,104 bytes. Evidence is
> `out/ovda-device-post/current-v3/report.json`; the experimental class remains
> isolated and unselected. The useful result remains device-depth handoff itself,
> not cache-bank duplication.

> The shared-texture substep passed. Diagnostic readback matched exact SBS RGB and
> opaque alpha on 12/12 frames. With readback removed from timed runs, the same
> device-depth backend measured 29.26 fps with host SBS and 30.06 fps with the
> two-slot shared texture (+2.75%). Relative to the matched host-depth/host-SBS
> path in the preceding three-way run, the combined boundary improvement is about
> 8.6% (27.68 -> 30.06 fps). Evidence is
> `out/ovda-device-texture/current/report.json`. This remains an isolated
> same-process diagnostic consumer with host RGB input and explicit synchronization;
> it is not end-to-end zero-copy or a 60 Hz live-backend acceptance result.

### VDA device-boundary continuation

> Completed component result: `out/vda-device-pipeline/current-v2/report.json`
> passed. Raw depth, host SBS and shared-texture SBS each matched exactly on 12/12
> frames; token reuse and expiry checks passed. Three measured runs were 27.544 fps
> for host depth/host SBS, 29.486 fps for device depth/host SBS (+7.05%), and
> 30.270 fps for device depth/shared texture (+2.66% from device host output,
> +9.89% combined). The test avoids 497,664,000 depth-readback bytes and
> 746,496,000 host-SBS-readback bytes per 60 frames. It does not establish cuts,
> integrated live output, steady-state memory, fresh 60-Hz depth or VR quality.
> See [vda.md](vda.md#record-result-vda-device-boundary-2026-09-06).


<a id="record-plan-live-gpu-speed"></a>
## live-gpu-speed

Checkpoint date recorded in source: 2026-09-05.

> Recorded outcome: Completed local opt-in candidate and verification, 2026-09-05.
> Default promotion and native capture/display interop remain open.

> 1. Profile the current 1080p complete live path and separately attribute CPU
>    preprocess, depth normalization/temporal/refinement, projection and copies.
> 2. Move measured CPU work to explicit CUDA implementations, preserving reference
>    semantics; compare depth and SBS pixels before enabling a new path.
> 3. Keep TensorRT depth on device through stereo where parity permits. Capture
>    and Qt host bridges remain explicit until independently implemented/tested.


<a id="record-plan-live-gui-promotion-output"></a>
## live-gui-promotion-output

Checkpoint date recorded in source: 2026-09-06.

> Latest 2026-09-06: the quality blocker below has been repaired. GPU is now the
> prepared local GUI default after all 3,447 comparisons and default-path GUI
> checks passed. See [stereo.md](stereo.md#record-result-live-resize-parity); sections below
> preserve the original implementation/promotion history.

> - Verify official public video provenance/license and pin sources; reuse verified
>   local downloads. Public motion clips become defaults; synthetic geometry/text
>   remains a supplement, not claimed as public footage.
> - Run longer matched public-video GPU/reference comparisons and failure/reset
>   checks before changing default selection. Keep explicit reference choice and
>   visible capability failures; no silent fallback.
> - Integrate path selection into the normal GUI and snapshot it per session.
> - Add explicit 30/60 Hz presentation targets and measure actual output/latency,
>   with bounded latest-frame semantics. Targets are not achieved-speed promises.
> - Record performance with idle preflight and no concurrent agent GPU jobs.
> - Preserve file conversion, no public release/hour soak/VR test. Document gates
>   that remain unproven; do not equate numeric parity with human quality approval.

### Outcome

> - Done: pinned official UVG-VCM previews, public defaults in quality/lifecycle/
>   output tests, source/derived hashes and attribution; no personal default.
> - Done: normal GUI explicit GPU/reference selector and 30/60 target selector,
>   immutable session settings, bounded latest-frame deadlines, no fallback.
> - Done: 3,267 numerical comparisons, 25 public benchmark windows across five
>   sessions with idle preflight/GPU samples, real public GUI lifecycle checks,
>   181 automatic tests and Python static checks.
> - Not promoted: 95 public comparisons exceed existing limits. Normal default
>   remains reference; investigate stage-by-stage differences before promotion.
> - Improved: Balanced public output 28.975 -> 29.988 fps at 30 target and
>   50.465 fps at 60 target. None of the three modes meets sustained 60 fps.
> - Remaining: promotion parity diagnosis, representative scroll/text quality,
>   true 60-fps capture/copy/presentation work. Deferred hour soak/VR/release remain
>   deferred. No model or native DLL change this turn.

> Full scope, source/license, raw paths and results:
> [stereo.md](stereo.md#record-result-public-live-tests).


<a id="record-plan-live-modes-performance"></a>
## live-modes-performance

Checkpoint date recorded in source: 2026-09-05.

> Recorded outcome: Completed prepared-local implementation and measurement, 2026-09-05.
> Requested tasks 4 and 5; not completion of the broader V2 performance milestone.

> - Add immutable Performance/Balanced/Video Quality live profiles using shared
>   mode policies. Reject Offline Quality. Keep DA2 Small explicit; assess added
>   models against complete-pipeline costs before changing defaults.
> - Performance explicitly trades background/edge refinement for lower cost;
>   motion/cut/gap guards must force fresh depth when cadence would otherwise reuse.
> - Optimize shared percentile evaluation without changing output; prove parity.
> - Measure generated source paint timestamps through SBS to actual Qt output
>   readback and swaps. Do not call readback or swap timing photon latency.
> - Warm up then run five repeats per live profile/resolution, retain raw metrics,
>   environment, plan, memory samples and overload/latest-frame evidence.
> - Publish tested/exploratory/rejected envelopes, not universal real-time claims.
> - No release, hour-long soak, headset tests or silent resolution/model fallback.

<a id="provenance-docs-product-specs-live-sbs-preview-md"></a>
### Additional provenance: live-sbs-preview

> Prepared local Windows/RTX 5090 installation only. Existing DA2 Small ONNX,
> TensorRT runtime/cache, capture and Qt dependencies are reused. The new pinned
> paired-eye DLL is `out/cuda-projection-preview/projection.dll`; missing or changed
> bytes fail visibly. No download occurs. A missing DA2 engine cache may require
> local TensorRT engine construction; startup timeout is 120 seconds. This is not
> an installer/clean-machine guarantee or a requirement that end users build CUDA.
