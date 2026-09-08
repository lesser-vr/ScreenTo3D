# Current implementation status

Reviewed 2026-09-08. The validated hybrid guided filter is now in the prepared-local
product DLL. Scoped regression coverage and measurements are connected below; they
do not establish general 4K60 support.

This page owns current path status and measured-envelope summaries. Product goals
are in [the live specification](PRODUCT.md); work areas are
in [ROADMAP](ROADMAP.md). Unpassed acceptance is recorded below.

| Path | Delivered scope | Limits and evidence |
|---|---|---|
| C++ bootstrap | CMake/MSVC core, capability probe and mode contracts; CI/dev entry point exists | Not a complete native NVDEC-to-NVENC media pipeline; `CMakeLists.txt`, `.github/workflows/ci.yml`, `scripts/dev.ps1` |
| Python file conversion | DA2 TensorRT, SBS, FFmpeg/NVENC, audio/publication and cancellation; explicit local Base/VDA/oVDA options | Artifact/shape/license-specific local use; [model specifications](PRODUCT.md#files-and-models); existing packages do not inherit every source-app change |
| Live original preview | Explicit WGC window/monitor capture, source transitions and isolated worker | No depth in original mode; [original preview](PRODUCT.md) |
| Live DA2 Small / host output | Three live policies, prepared-local GPU processing default, explicit reference, 30/60 output targets and separate fullscreen output | GPU processing default does not imply native texture delivery is default; [resize decision](evidence/stereo.md#record-result-live-resize-parity), [host throughput](evidence/presentation.md#record-result-live-host-throughput) |
| Live native texture output | Explicit experimental `gpu-texture` transport into Qt/D3D11 windows, worker-owned bounded textures | Capture input still crosses host memory; native delivery promotion and broad visual acceptance remain open; [integration](evidence/presentation.md#record-result-live-native-dual-window) |
| Temporal/model GPU experiments | Device boundaries and selected NVOF components have bounded evidence | Components are not general live model integration; fixed 1:2 NVOF cadence is rejected; [actual skip](evidence/nvof.md#record-result-ovda-nvof-actual-skip-2026-09-07) |
| Post-SBS Streamline DLSSG proposal | Feasibility review completed | Current adapter rejected at input-contract boundary; not a rejection of all external RGB FG; [feasibility](evidence/frame-generation.md#record-result-dlssg-feasibility-2026-09-07) |

## Measured envelope, not general support

The [guarded native baseline](evidence/live-performance.md#record-result-live-guarded-baseline) records DA2
Small on RTX 5090, 1920x1080 input / 1920x1080 per eye / 3840x1080 Full SBS,
with native distinct-output rates of 59.70–59.99 fps across three live policies.
These were warmup plus five ten-second windows per policy under the documented
Premiere-closed, monitor-off condition. They do not establish physical scanout,
VR latency or long-run stability; their conditions are not used to infer 4K behavior.

A separate [monitor-on eye-4K run](evidence/live-performance.md#record-result-eye-4k60-monitor-on)
used DA2 Small Balanced with 3840x2160 input/per eye and 7680x2160 Full SBS.
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
clips, in all three live modes/radii. A saved OfficeWalk Balanced review pair and
16x difference image were visually checked and matched the exact-RGB result.

Only after that pass, five order-alternated 20-frame 3840x2160 Balanced repeats
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
FloorballGame source at about 62.5 fps, DA2 Small Balanced, 3840x2160 input/per eye,
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
rejected as a global replacement after its radius-4 Performance guide regressed
2.03%. A hash-pinned hybrid instead keeps the exact current radius-4 kernels and
uses rolling chunks at radii 8/12. Its 99/99 quality matrix passed, including exact
final RGB; native-boundary gates passed with 0.00%/-0.42% guide/throughput change
in Performance, +31.20%/+13.08% in Balanced and +39.46%/+22.60% in Video Quality.
A fresh Balanced Floorball actual-app pair measured +3.59% processed, +0.78%
output and 27.98% lower sampled-guide P50. Five real-GPU native failure/cleanup
cycles also passed.

The hybrid has now been promoted into the canonical production source: Performance
keeps exact direct radius-4 sums, while Balanced/Video Quality use 64-pixel rolling
chunks at radii 8/12. The final candidate DLL SHA-256
`f67fc53ccaa37a29474ba90bac80d3cb2bff12e8c685a24df9f7382db0c00fa7`
repeated the 99/99 quality pass and all native gates. A separately linked product
DLL, SHA-256
`946225fb6abaff0f9e94bea212995bb073da97fb461d5ff062886a388fae4448`,
matched that candidate exactly in all 99 depth, RGB and temporal comparisons and
passed five real-GPU failure/cleanup cycles. A default-path Floorball 4K Balanced
smoke loaded that exact product hash and produced 52.43 distinct output IDs/s; its
8% device-wide GPU preflight makes it a functional smoke, not a performance claim.
Fifteen separately captured OfficeWalk output frames were all distinct and sampled
stills showed advancing motion, plausible eye order/letterbox and no black/frozen
output. This is sampled-still review, not continuous playback or headset acceptance.
See the
[hybrid record](evidence/live-performance.md#record-result-guide-hybrid-isolated).

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

## Unpassed acceptance

| Claim | Evidence still needed |
|---|---|
| Better depth than the user's baseline | Matched spatial/temporal/binocular review against Small + LSFG, including games and video |
| Eye-4K final 60 fps | Bounded monitor-on current, rolling and hybrid runs remain near 59 fps; the hybrid output median was 59.84 fps and maximum 60.04 fps, not a sustained/median 60 result. 1:1 fullscreen/physical-display behavior, applicable FG path, broader content and sustained acceptance remain |
| Native-texture default suitability | Guided-filter promotion is complete, but the native-texture transport itself remains experimental; continuous actual-UI playback/VR review and broader acceptance remain |
| Broad content and VR comfort | Continuous playback and the applicable display/headset evaluation; scalar parity or stills alone are insufficient |
| Long-session reliability / real device loss | Actual long-duration/device scenarios for that claim; short or injected tests do not establish it |
| Public/other-GPU support | Declared hardware/runtime envelope, clean-machine and packaging/license evidence |

These gaps qualify claims. They do not add an approval or prerequisite to
independent experiments. The recorded resize/default-processing gate passed;
earlier failed processing-default attempts are not current blocks. Fixed 1:2 NVOF
and the tested DLSSG adapter remain rejected in their tested scope, not global bans.
