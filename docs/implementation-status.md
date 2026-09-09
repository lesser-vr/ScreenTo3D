# Current implementation status

Reviewed 2026-09-09. The validated hybrid guided filter is now in the prepared-local
product DLL, and the SBS worker retains the owned WGC mapped frame instead of
copying it into a second 4K BGRA buffer. Scoped regression coverage and measurements
are connected below; they do not establish general 4K60 support.

This page owns current path status and measured-envelope summaries. Product goals
are in [the live specification](PRODUCT.md); work areas are
in [ROADMAP](ROADMAP.md). Unpassed acceptance is recorded below.

| Path | Delivered scope | Limits and evidence |
|---|---|---|
| C++ bootstrap | CMake/MSVC core, capability probe and mode contracts; CI/dev entry point exists | Not a complete native NVDEC-to-NVENC media pipeline; `CMakeLists.txt`, `.github/workflows/ci.yml`, `scripts/dev.ps1` |
| Python file conversion | Mode-owned routing now enforces Performance/DA2 Small, Balanced/DA2 Base, Video Quality/explicit oVDA or VDA, and Offline Quality/VDA with a dedicated centered five-frame processor; SBS, FFmpeg/NVENC, audio/publication and cancellation remain shared | Offline is bounded, future-aware and file-only; it is not motion-warped or a new trained model. Artifact/shape/license-specific local use; [model specifications](PRODUCT.md#files-and-models) |
| Live original preview | Explicit WGC window/monitor capture, source transitions and isolated worker | No depth in original mode; [original preview](PRODUCT.md) |
| Live depth modes / host output | Immutable session routing selects Performance/DA2 Small, Balanced/DA2 Base, or Video Quality/explicit oVDA or VDA; VDA/oVDA live depth remains on its owner CUDA stream through GPU SBS | DA2 Base retains a host-depth boundary. Offline Quality is file-only; correct artifacts, shapes and oVDA confirmation are required with no fallback |
| Live native texture output | Explicit experimental `gpu-texture` transport into Qt/D3D11 windows supports DA2 Small plus VDA/oVDA device-depth live sessions with worker-owned bounded textures | Capture/model input still crosses host memory; DA2 Base is ineligible; native delivery default promotion and broad visual acceptance remain open; [integration](evidence/presentation.md#record-result-live-native-dual-window) |
| Temporal/model GPU experiments | Device boundaries and selected NVOF components have bounded evidence | Components are not general live model integration; fixed 1:2 NVOF cadence is rejected; [actual skip](evidence/nvof.md#record-result-ovda-nvof-actual-skip-2026-09-07) |
| Post-SBS Streamline DLSSG proposal | Feasibility review completed | Current adapter rejected at input-contract boundary; not a rejection of all external RGB FG; [feasibility](evidence/frame-generation.md#record-result-dlssg-feasibility-2026-09-07) |

## Measured envelope, not general support

The [guarded native baseline](evidence/live-performance.md#record-result-live-guarded-baseline) records DA2
Small on RTX 5090, 1920x1080 input / 1920x1080 per eye / 3840x1080 Full SBS,
with native distinct-output rates of 59.70–59.99 fps across three legacy policy
labels. It is DA2 Small transport/policy evidence, not model-specific Balanced or
Video Quality evidence under the product contract.
These were warmup plus five ten-second windows per policy under the documented
Premiere-closed, monitor-off condition. They do not establish physical scanout,
VR latency or long-run stability; their conditions are not used to infer 4K behavior.

A separate [monitor-on eye-4K run](evidence/live-performance.md#record-result-eye-4k60-monitor-on)
used DA2 Small with the legacy Balanced policy at 3840x2160 input/per eye and
7680x2160 Full SBS. It did not run the Balanced mode's required DA2 Base model.
After ten seconds of warmup, five ten-second windows recorded median fresh/base
SBS 59.127 fps and final distinct native IDs 59.028 fps (58.789-59.482 range).
This is bounded application submission with a scaled public source and 1400x650
logical output window, not 1:1 fullscreen scanout, native-4K detail quality, FG,
VR acceptance, another mode/content/GPU or long-session support.

Boundary attribution over all 200 retained stage samples confirms the native path
already reduces output readback to a four-byte validity flag per frame. The remaining
explicit input traffic is 25,688,172 bytes per processed frame (about 1.495 GB/s in
that session), while the largest sampled P50 stage is the guided filter at 4.122 ms.
A direct owned-BGRA input alternative was rejected before integration: its exact
518x518 RGB result still took 4.169 ms versus 1.651 ms for the current host path and
would add 8,294,400 H2D bytes per 4K frame. No runtime/default changed from this
attribution; see the linked eye-4K evidence record.

An exact-order shared-memory guided-filter candidate also remains unselected. It
passed 27/27 exact depth/SBS comparisons, but its isolated 4K guide P50 improved
only 0.147%, below the predeclared 3% gate. That candidate remains rejected and
isolated for evidence; the product now uses the separately validated hybrid
described below.

Valid diagnostic decomposition attributes about two thirds of the 4K guided-stage
P50 to `coefficients_y` (1.407 ms, 34.2%) and `moments_x` (1.311 ms, 31.9%).
Instrumentation preserved 27/27 exact comparisons, added 0.182% to the enclosing
guide event and closed its event sum within 0.0059 ms. This is component timing,
not another application throughput claim.

A subsequent isolated chunked rolling-window candidate reduces the separable box
sum work while intentionally changing floating-point addition order. Its declared
bounded quality gate passed all 99 current-versus-candidate cases: maximum aligned
depth MAE/max were `8.49e-24`/`3.89e-19`, with exact final SBS RGB and exact
consecutive-frame RGB-change values. The corpus covered minimum/odd synthetic
motion and cuts plus six contiguous frames from each of three licensed public
clips, under all three legacy policy/radius combinations. A saved OfficeWalk
DA2 Small review pair using the legacy Balanced policy and
16x difference image were visually checked and matched the exact-RGB result.

Only after that pass, five order-alternated 20-frame 3840x2160 DA2 Small repeats
using the legacy Balanced policy
measured guide-event P50 at 4.1186 ms current versus 2.7945 ms candidate, a 32.15%
reduction above the declared 3% gate. Whole host-output FPS medians were 29.88 and
29.66 and do not show an end-to-end gain because this isolated harness retains
full SBS readback. The candidate supports an integrated validation step, not a
4K60 or visual/VR claim.

A no-readback native-publication boundary A/B then measured guide P50 4.1175 ms
current versus 2.7684 ms candidate (32.77% lower) and unpaced processing medians
90.95 versus 102.43 fps (12.62% higher). The first harness attempt correctly timed
out after two slots because it omitted the consumer's keyed-mutex acknowledgement;
the final isolated runtime adds a no-copy acquire/release consumer and passed equal
transfer/synchronization counters.

Finally, sequential actual-app WGC-to-Qt runs used the same scaled public
FloorballGame source at about 62.5 fps, DA2 Small with the legacy Balanced policy,
3840x2160 input/per eye,
7680x2160 Full SBS, ten-second warmup and five ten-second windows. Final distinct
output-ID median/range was 52.45 (51.54-53.01) fps current versus 58.83
(57.79-59.45) fps candidate, 12.17% higher. Sampled guide P50 was 5.2024 versus
3.5666 ms (31.44% lower), and exact transfer formulas stayed valid. The candidate
did not reach 60 fps in any measured window. These sequential single-content runs
support broader validation but not physical scanout, native-detail/VR quality,
sustained or general support.

The raw rolling implementation remains isolated and rejected as a global
replacement. See the
[rolling guide record](evidence/live-performance.md#record-result-guide-rolling-isolated).

Broader rolling-candidate actual-app coverage now spans FloorballGame, OfficeWalk
and ParkingGarage: all three improved processed, output and sampled-guide medians,
but no candidate output median reached 60 fps. The raw rolling implementation was
rejected as a global replacement after its radius-4 legacy Performance-policy guide regressed
2.03%. A hash-pinned hybrid instead keeps the exact current radius-4 kernels and
uses rolling chunks at radii 8/12. Its 99/99 quality matrix passed, including exact
final RGB; native-boundary gates passed with 0.00%/-0.42% guide/throughput change
in Performance, +31.20%/+13.08% in Balanced and +39.46%/+22.60% in Video Quality.
A fresh Balanced Floorball actual-app pair measured +3.59% processed, +0.78%
output and 27.98% lower sampled-guide P50. These labels describe DA2 Small policy
tests, not the product mode models. Five real-GPU native failure/cleanup
cycles also passed.

The hybrid has now been promoted into the canonical production source: the legacy
Performance policy keeps exact direct radius-4 sums, while the legacy Balanced and
Video Quality policies use 64-pixel rolling chunks at radii 8/12. This promotion
changes postprocessing only; it does not implement their required model routing.
The final candidate DLL SHA-256
`f67fc53ccaa37a29474ba90bac80d3cb2bff12e8c685a24df9f7382db0c00fa7`
repeated the 99/99 quality pass and all native gates. A separately linked product
DLL, SHA-256
`ad0871cce22011926b0948a59368ae1f71d9727962160110bdea7974f5e296eb`,
matched that candidate exactly in all 99 depth, RGB and temporal comparisons and
passed five real-GPU failure/cleanup cycles. A default-path Floorball 4K DA2 Small
using the legacy Balanced policy loaded that exact product hash and produced 52.43
distinct output IDs/s; its
8% device-wide GPU preflight makes it a functional smoke, not a performance claim.
Fifteen separately captured OfficeWalk output frames were all distinct and sampled
stills showed advancing motion, plausible eye order/letterbox and no black/frozen
output. This is sampled-still review, not continuous playback or headset acceptance.
See the
[hybrid record](evidence/live-performance.md#record-result-guide-hybrid-isolated).

An opt-in page-locked full-RGB staging candidate was evaluated after guide
promotion. It owns one bounded 24,883,200-byte host allocation at 3840x2160 and
copies the existing RGB frame into it before the unchanged product DLL. Its
261/261 quality matrix and five real-GPU failure/cleanup cycles passed. In a
matched Floorball 4K DA2 Small using the legacy Balanced policy, the sum
of sampled host input
conversion/staging P50 and GPU RGB-transfer/depth-resize P50 fell 4.3686 ->
3.5228 ms (19.36%), while processed/output medians changed only +0.10%/+0.05%
and output remained 59.93 fps. A first unpaced native-boundary trial narrowly
passed its 3% throughput gate, but the final source-hash repeat measured 38.51%
lower RGB-transfer P50 and only 2.71% higher native throughput, below that
predeclared gate. The candidate is therefore rejected for product promotion;
the normal native path and product DLL remain unchanged. See the
[pinned-input record](evidence/live-performance.md#record-result-pinned-input-rejected).

The next selected input-boundary change removes the 33,177,600-byte 4K WGC
callback memcpy. Because WGC's array view retains its owned mapped-frame exporter,
the same SBS worker now holds that view in a single latest-frame slot until RGB
conversion completes, then releases the last view before native capture stop.
The original preview keeps its bounded shared BGRA copy. In matched 4K DA2 Small
using the legacy Balanced policy, callback P50 fell 1.8641 -> 0.0402 ms
(97.84%) and owned-worker
CPU fell 9.99%; capture/processed/output changed -0.02%/+0.43%/-0.06% and worker
private-memory P95 rose 32.39 MiB, passing all declared gates. A final default-path
DA2 Small using the legacy Balanced policy at 0% GPU preflight recorded 62.48
capture, 62.14 processed and
59.83 distinct output IDs/s, a 0.0373 ms callback P50, zero shared capture-pixel
allocation and zero native pools/nodes after stop. These are short application
submission and lifecycle results, not sustained 4K60, scanout, continuous visual
or headset acceptance. See the
[retained-capture record](evidence/live-performance.md#record-result-retained-capture-promoted).

The source desktop now enforces the model-defined mapping for file and live
sessions. A sequential 1280x720 actual-GPU smoke loaded DA2 Base for Balanced,
then VDA for Video Quality, and both emitted matching model/policy provenance.
The one-second windows observed 12.94/13.93 and 17.89/16.90 processed/output
submission fps. This establishes routing and execution only, not comparative or
sustained performance, visual quality, 4K, oVDA or Offline Quality acceptance.
See the
[model-routing record](evidence/live-performance.md#record-result-model-defined-live-routing).

Clean-worktree repeated live measurements now cover all three non-Small live
choices on the public FloorballGame source. At 1920x1080 per eye, median
processed/output submission rates were 7.94/7.94 fps for DA2 Base, 8.43/8.43 for
VDA and 7.77/7.78 for oVDA. At 3840x2160 per eye with 7680x2160 Full SBS, they
were 2.48/2.48, 2.64/2.64 and 2.48/2.48 fps. Capture remained above 62 fps. The
4K sampled latest-stage medians put depth at 93-117 ms and SBS at about 288-290
ms, selecting the host-depth/SBS/output boundary for the next optimization
experiment. These are five short six-second windows on one resized public source,
not sustained 60 fps or a quality comparison. See the
[model performance record](evidence/live-performance.md#record-result-model-defined-live-performance).

The source desktop now keeps explicitly selected oVDA live depth on the model's
owned CUDA stream through temporal/guided postprocessing and stereo. Public
component parity was exact on 12/12 frames and the integrated wrapper completed
12/12 owned tokens without a pending result. A clean-commit actual-GUI run raised
1920x1080-per-eye median
processed/output submission from 7.77/7.78 to 21.35/21.49 fps. At 3840x2160 per
eye and 7680x2160 Full SBS it raised both from about 2.48 to 7.27/7.28 fps.
Explicit native delivery now raises output further to 22.54 and 9.44 fps at those
geometries. The path still has host capture/model input and is `zero_copy=false`;
60 fps, sustained performance and continuous visual/VR acceptance remain open.
See the [native-live record](evidence/live-performance.md#record-result-ovda-native-live-promoted).

VDA Small live sessions now use the same owned source-resolution device-depth
contract while file and Offline sessions retain the host-depth engine. The public
component rerun was exact for 12/12 raw-depth, host-SBS and shared-texture frames;
the integrated product wrapper also matched 12/12 final SBS frames, completed
every token and recorded no depth download. A clean actual-GUI run raised
1920x1080-per-eye processed/output from 8.43/8.43 to 23.99/23.99 fps. At
3840x2160 per eye and 7680x2160 Full SBS it raised 2.64/2.64 to 8.61/8.75 fps.
Explicit native delivery now raises output further to 28.15 and 11.92 fps at
those geometries. The path still has host capture/model input, is `zero_copy=false`,
and is not 60 fps. See
the [VDA native-live record](evidence/vda.md#record-result-vda-native-live-2026-09-09).

The file-only Offline Quality path now uses VDA Small inference plus a scene-local
centered five-frame processor. A final-code public 1080p60 FloorballGame conversion
emitted and decoded all 360 frames as 3840x1080 H.264 at 5.37 processing fps. The bounded
window held at most five samples / 47,174,400 bytes and used future context on
359 frames. On its first 120 public frames, a flow-aligned normalized-depth-change
proxy was 0.765x raw VDA overall and 0.819x at detected edges. A separate public
OfficeWalk-to-ParkingGarage hard cut was detected at annotated frame 60, flushed
once, produced two scenes and preserved 120/120 frames. These are temporal-stability
proxies and a short media/lifecycle run, not ground-truth depth, ghosting, visual,
VR comfort or sustained-performance acceptance. See the
[Offline record](evidence/vda.md#record-result-offline-centered-window-2026-09-08).

The optional oVDA Video Quality path also completed a license-confirmed public
1080p60 FloorballGame file run: 360/360 frames, 3840x1080 H.264, 6.997 processing
fps, full decode. A separate actual-engine public-frame check retained two
sequential cache positions, cleared the cache at a scene cut, accepted geometry
changes only after discontinuity/source-change reset, and rejected a skipped-frame
policy. This establishes the named local path and lifecycle contract, not quality,
long-run, public-release or commercial-use suitability. See the
[oVDA record](evidence/ovda.md#record-result-ovda-public-file-lifecycle-2026-09-08).

Older 720p30 / 1080p18 / 4K3 guidance belongs to the
[earlier generated-window reference-path experiment](evidence/live-performance.md#record-result-live-mode-performance-results).
It is not a current limit for all paths, and the separate runs are not a matched
optimization A/B. Native output must not be confused with zero-copy input.

Short 4K file fixtures establish only the codec/geometry scope recorded in the
model results. 7680x2160 allocation/encode compatibility is not a final 4K-per-eye
60 fps viewing result. Record input, per-eye, combined SBS, fresh-depth, base-SBS
and generated-output rates separately in future results.

## Build and evidence navigation

Use [README build/test commands](../README.md#build-and-test-on-windows), shared
with the C++ CI entry point. Model-specific setup and diagnostic commands remain
in `docs/models/`. No claim here certifies another GPU or a clean
machine.

## Regression coverage

The [scoped regression entry points](BENCHMARKS.md#scoped-regression-entry-points)
connect CPU contracts, current profiles, synthetic quality/protocol checks,
real FFmpeg fixtures and explicit local GPU/Qt checks. CI configuration includes
CPU and media jobs; remote execution is not confirmed until these local changes
are committed/pushed. Worker error privacy, path alias protection and cleanup
before final publication are implemented in the source app. Existing packages
require a rebuild to inherit these changes. The comparison harness records
predeclared thresholds and review frames while keeping visual acceptance pending.
Its optional product-baseline contract records and validates the workload,
environment, exact path descriptions, geometry, five distinct pipeline rates,
latency state and product review decisions. No matched Small + LSFG capture has
yet been supplied, so this closes comparison setup ambiguity, not the quality gate.
The 2026-09-09 native-output extension also passed 258 discovery tests, 27 live
controller tests, scoped Ruff checks and Python bytecode compilation; its actual
GPU/GUI evidence is recorded in the linked VDA/oVDA native-live records.

## Unpassed acceptance

| Claim | Evidence still needed |
|---|---|
| Product mode contract | Mode routing, mismatch rejection, a license-confirmed public oVDA file/lifecycle run, the dedicated bounded Offline/VDA processor and short repeated actual-GUI live runs for all three non-Small choices are implemented. Offline is intentionally file-only; matched visual quality, broader content and sustained performance remain open |
| Better depth than the user's baseline | Matched spatial/temporal/binocular review against Small + LSFG, including games and video |
| Eye-4K final 60 fps | Baseline model-defined DA2 Base/VDA/oVDA host-output paths measured only 2.48/2.64/2.48 fps median at 3840x2160 per eye and 7680x2160 Full SBS. Integrated device-depth/host-output paths reached 8.75 fps for VDA and 7.28 for oVDA; explicit native texture raises these to 11.92 and 9.44 fps. Earlier near-59 fps runs use native-texture DA2 Small with legacy policy labels. Model/cache cost, 1:1 fullscreen/physical-display behavior, applicable FG, broader content and sustained acceptance remain |
| Native-texture default suitability | Guided-filter promotion is complete, but the native-texture transport itself remains experimental; continuous actual-UI playback/VR review and broader acceptance remain |
| Broad content and VR comfort | Continuous playback and the applicable display/headset evaluation; scalar parity or stills alone are insufficient |
| Long-session reliability / real device loss | Actual long-duration/device scenarios for that claim; short or injected tests do not establish it |
| Public/other-GPU support | Declared hardware/runtime envelope, clean-machine and packaging/license evidence |

These gaps qualify claims. They do not add an approval or prerequisite to
independent experiments. The recorded resize/default-processing gate passed;
earlier failed processing-default attempts are not current blocks. Fixed 1:2 NVOF
and the tested DLSSG adapter remain rejected in their tested scope, not global bans.
