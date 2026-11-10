# DepthSBS architecture

Status: Current boundary map, reviewed 2026-09-08 against repository contracts.
This describes delivered paths and their limits; it does not certify performance.
See [implementation-status.md](docs/implementation-status.md) for status and [ROADMAP.md](docs/ROADMAP.md) for priorities.

## Delivered paths

```text
Compact Qt live shell + separate utility window -> immutable job/session plan -> isolated worker

Files: probe -> FFmpeg decode/host frames -> selected depth binding
       -> streaming depth postprocessing
          OR Offline/VDA scene-local centered five-frame depth window
       -> CPU or explicit CUDA SBS -> NVENC/FFmpeg
       -> drain/audio mux/validation -> atomic publication

Live: selected WGC source -> owned D3D11/CUDA latest-frame slot (Small/Base/VDA/oVDA window GPU paths)
                           OR retained mapped latest-frame slot (other SBS paths)
                           OR bounded host BGRA mailbox (original preview)
      -> owned RGB/model input
      -> immutable model-defined binding
         -> DA2 Small fused live path (Performance)
         OR DA2 Base / VDA / explicit oVDA source-resolution device-depth path
         OR explicit reference host-depth path
      -> depth postprocessing / stereo
      -> DA2 Small/Base/VDA/oVDA native texture pool -> Qt/D3D11 private textures (local default)
      OR explicit host mailbox + owned QImage -> Qt output
```

C++ CMake core provides capability/mode foundations. It is not the complete native
NVDEC/CUDA/NVENC pipeline originally proposed. Small/Base/VDA/oVDA window GPU sessions keep full
capture/model input on the GPU; monitor and reference paths retain host capture.
Base/VDA/oVDA live device-depth paths can publish SBS
through the same shared-texture GUI backend as DA2 Small, now the prepared-local
delivery default. Host output remains explicitly available. Selection is separate
from readiness: native registration/loading happens at SBS start, and QML creates
the native surface only after successful registration. Failure releases the live
lease and reports an actionable error without selecting another transport.
Processing-backend default and delivery-path default are separate decisions.

## Components and ownership

`catalogs.py` loads the trusted bundled language and error registries in
`translations/languages.json` and `translations/errors.json` without Qt.
`messages.py` carries ordinary English templates and scalar arguments; errors
carry a stable semantic `error_id`, parameters, optional opaque details and a
public/redacted flag. Error translations use `Errors`/`PublicErrors` contexts
keyed by ID, so changing English wording does not change identity. Exceptions
are detached from tracebacks before retention. Bounded worker error transport
reduces oversized diagnostic strings while preserving the ID and valid JSON;
very small legacy buffers fall back to ID-prefixed diagnostic text. Unknown IDs
keep their identity/details and use a generic description. `error_reporting.py`
retains an explicit adapter for unconverted media-tool English prefixes; typed
application errors bypass it. Default file-worker events omit private values,
details and notes; detailed mode is opt-in.

`localization.py` owns trusted bundled/Qt translators on the GUI
thread, the saved `ui/language` selection and display-number formatting. It
retranslates QML and notifies Python display properties without modifying session
plans. File rows expose a translated `stateLabel` separately from their stable
state code; live stop completion uses a flag rather than matching status text.
The Qt-free launcher reads the same language selection for pre-GUI errors.
Both UI and build discovery use `languages.json`; no per-language Python/C++
branches are required. `scripts/build-translations.py` validates parameter parity
and completeness, compiles all registered catalogs and generates the native
launcher's table from the same definitions. Its `--check` rejects a stale native
table; the EXE/portable builders consume this pipeline. See
[adding languages and errors](docs/LOCALIZATION.md) for the maintenance procedure.

Stereo arrangement is defined in `stereo_layout.py` and snapshotted per live/file
job. The renderer API defaults to Full SBS; the GUI passes its explicit session
layout. Standard paths synthesize full-resolution eyes before packing:
the native producer writes Full/Half SBS or Full/Half Top-and-Bottom directly
into its final-sized shared texture. Native CUDA Half Top-and-Bottom with VFG
off reduces rows after full-resolution depth/shift preparation, then synthesizes
half-height eyes. It borrows t1/t2/t3/b scratch after guide/make_shift completion;
RGB/depth/motion/range/window histories remain owned by the full-resolution
context. These scratch arrays are fully overwritten before their next guide use.
VFG retains full-SBS interpolation buffers
and packs only on publication. Host/file paths implement the same pair-averaging
contract, rounding up odd half-axis dimensions by replicating the last pixel.
The GUI transports packed dimensions, with the same bounded total pixel count
and a maximum packed height of 4320. Overlay placement follows the selected eye
arrangement; text stays at the same logical size in the output window.

- `desktop_jobs.py` and isolated workers own job/session lifecycle; the GUI does
  not run inference. Live and file work share an exclusive processing lease.
- `desktop_preferences.py` owns validated mode/model/layout selections in the
  existing DepthSBS QSettings namespace, separated by live/file scope. Explicit
  UI activation saves them; diagnostic setters and fixed comparisons do not.
  No source, artifact path, VFG state or license consent is restored from it.
- `model_presentation.py` owns the shared live/file model labels and precision
  explanations. Combined choices map to the existing validated mode/model pair;
  no engine is loaded for presentation. VDA installation inventory distinguishes
  managed mixed precision from legacy FP32 and the uninstalled download target.
- `live_policy.py` resolves immutable temporal/stereo policy. `live_backend.py`
  validates the mode-owned model snapshot and constructs only that binding.
  Backend/profile selection precedes output mutation. Live adapters apply
  model-specific policy overrides before renderer construction and to diagnostics.
- `ovda_geometry.py` selects an installed oVDA canvas and its content rectangle;
  normal oVDA uses the pinned 518x924 mixed-FP16 artifact, with FP32 temporal
  blocks/cache/depth head/floating I/O. Other ratios fit that same canvas. Trial
  allowlists remain explicit and separate; ordinary loading does not fall back
  to archived FP32 plans. UI, backend and engine telemetry identify mixed FP16.
  The source-only frame preprocessor pads model input and crops model depth before
  restoring source dimensions. Host, device and buffered device paths share it;
  original-size changes still invalidate model/cache history.
  The source-only oVDA device engine also supplies the shared borrowed GPU
  execution interface. Its separately pinned `experiments/ovda/gpu_input` kernel
  preserves FP32 half-pixel bicubic, replicated padding, FP32 normalization and
  the all-0/1 input rule with a same-stream device reduction. Its scalar scratch
  stays owned until engine completion/close. No oVDA runtime is added to portable
  bundles; its existing model, precision, history resets and depth restoration
  are unchanged by the input transport.
  `experiments/ovda/device_buffers.py` owns reusable model input, five output
  tensors, sixteen schedule pairs and validation scratch for the live device
  engine. One cache bank is retained and zeroed on reset. At full history, a
  lane-owned same-stream kernel shifts each feature's temporal slots in place.
  A device reduction checks all five outputs for nonfinite values, followed by
  one pinned four-byte readback/wait before lending depth. Consumer completion
  still fences the engine stream before these buffers can be reused or closed.
  The source renderer can use an independent `temporal_depth_alpha`; oVDA's
  separately pinned `experiments/ovda/postprocess` bridge applies that pixel EMA
  and optional `stabilize_depth_range` policy. The latter retains 1024 raw FP32
  anchors (4 KiB), with stationary RGB neighborhoods and robust affine acceptance
  gates; raw anchors avoid feedback from the normalized pixel EMA. Endpoint
  deadband is 2% of span; expansion/contraction time constants are 0.05/0.5 seconds
  on `DepthRangeClock`. Reset adopts current P2/P98. One same-stream kernel replaces
  the legacy range kernel, with no additional production readback or per-frame
  allocation. The bridge borrows the existing LiveDepth layout and stream without
  adding fields or replacing shared native binaries. Anchor storage is released
  after native context destruction fences the stream. CPU live reference rendering
  uses `depth_range.py` with the same policy; ordinary file policies leave both
  overrides disabled. Missing/corrupt bridges close the owned context and fail
  visibly before publication. The bridge keeps only a weak renderer reference.
- `live_model.py` owns the live adapter registry: GPU capture capability,
  optional capture-engine replacement, host/native renderer factories, RowFlow
  eligibility and reference-path transfer accounting. The worker consumes this
  adapter instead of branching on model names. License/profile validation stays
  in the existing bindings; an unknown model or unsupported capture is rejected.
- `depth_backend.py` provides model-independent binding/factory boundaries.
  Raw depth is finite float32 with declared shape/polarity; raw output and
  normalized display depth are distinct contracts. A binding may also declare a
  file-only offline processor; the pipeline rejects it outside Offline Quality
  and rejects Offline Quality when that processor is absent.
- `offline_depth.py` owns Offline/VDA's bounded scene-local window. Pending samples
  retain source RGB for ordered emission; emitted history retains only reduced
  guides, depth and cached normalization. Cuts drain the old scene before reset,
  and finish must emit exactly the decoded frame count.
- The inference engine owns its CUDA context/stream, allocations and recurrent
  cache. Borrowed device depth validates owner, thread, epoch/generation and
  lifetime; postprocessing resources must be released before their owner stream.
  DA2 Base live tokens retain input and source-sized FP32 depth through consumer
  completion; source resize retires texture leases and destroys postprocessing
  before replacing the engine/stream. Base file conversion keeps host depth.
- `gpu_runtime.py` provides a borrowed `GpuExecution` view of the engine-owned
  stream and shared `GpuInputSupport` for pinned native loading, image validation
  and thumbnail generation. Small supplies its ExternalStream view; Base supplies
  its Torch stream. Frame/capture consumers use the same explicit interface.
  This layer never creates/destroys engine streams or changes token completion.
  Base and Small keep separate preprocessing algorithms and native library pins.
- `gpu_capture.cpp` owns a two-frame WGC pool, one replaceable latest frame, one
  acquired frame and a registered D3D11 bridge on the selected CUDA adapter.
  WGC buffers have fixed 4096x2160 capacity (67.5 MiB for two BGRA buffers,
  excluding driver overhead); only actual ContentSize pixels enter CUDA. Keeping
  capacity bounded avoids pool recreation races on static-window resize.
  Its worker-thread D3D-to-CUDA copy completes before releasing the WGC frame.
  `gpu_capture.py` preserves HWND/PID, input-desktop, visibility and SDR checks.
  `GpuFrame` owns same-stream RGB; `base_input.cu` preserves Base's float64 cubic
  preprocessing arithmetic. Small wraps the existing TensorRT-owned raw stream
  with a non-owning Torch ExternalStream; it does not change the FP16 model.
  `small_gpu_input.py` computes bounded, shape-only IPP cubic coefficients once
  per size. `small_input.cu` resizes captured RGB to uint8 518x518, then applies
  the existing float32 normalization. `live_small_gpu_input.py` retains input and
  coefficient tensors through stream completion and uses a separately pinned
  DLL with the unchanged Small postprocessing/native borrowed layout.
  Device buffers stay owned through SBS completion.
  Exact 32x32 scene pixels and border samples cross to CPU; full RGB readback is
  reserved for explicit diagnostics.
- Live worker/postprocessing owns normalization, EMA and stereo state. Conditional
  uniform-background refinement is shared by the live CUDA renderers through
  `flat_background_gpu.py` and the hash-pinned `flat_background.dll`. It borrows
  only the validated `LiveDepth` prefix and owner stream; model/live ABI is unchanged.
  Full-resolution byte masks and 4-connected horizontal-run components identify
  border-connected background and foreground components. A 4096-bin normalized-depth
  median and truncated jump-flood chamfer weights (eight final local propagation
  passes for concave boundaries) implement the bounded quality
  approximation to the CPU reference. Component means use FP64 accumulation.
  Three small eligibility/completion waits replace full RGB/depth D2H and corrected
  depth H2D; early bypasses use fewer waits. The corrected depth stays in `aligned`.
  A lazy per-session workspace owns `30*N + ceil(N/32)*4 + 16396` buffer bytes
  (about 238.3 MiB at 3840x2160), plus event handles. Reused buffers are fenced and
  freed before the borrowed renderer/engine stream; errors poison the session.
  DA2 adapters declare coalesced-history support. The worker validates both frame
  sequence and source time: forward capture index skips within 100 ms retain
  postprocessing history; cuts, replay/backwards clocks, pauses and shape changes
  reset it. VDA declares `single_skip_history`: live accepts one missing capture
  with a positive source interval <=50 ms, while consecutive captures keep their
  existing <=100 ms bound. Larger skips, invalid indices/clocks, cuts and source
  or shape changes reset model and renderer. The strict legacy policy remains an
  explicit diagnostic. The oVDA adapter separately declares `short_skip_history`; its live
  capture-index/time policy is resolved before updating model or renderer state,
  independently of DA2 coalescing and renderer-quality feature selection. Cache
  positions count accepted model updates; no capture-ID remapping or fake-frame
  insertion is used. File stateful/requires-every-frame contracts remain strict.
  Six appended bounded metadata counters expose retained oVDA gaps, cached past
  slots, full-context inferences and update streaks; they do not retain pixels.
  Two further fixed metadata fields carry device-wide GPU percentage and its
  monotonic sample time. `gpu_usage.py` owns optional worker-local NVML setup,
  maps the active CUDA device UUID rather than assuming NVML ordinal zero, samples
  at most once per second and shuts down before the engine scope closes. The GUI
  formats the shared reading without importing CUDA/NVML or spawning a command.
  Live DA2 CUDA synthesis adds a bounded five-candidate triangle reconstruction
  around the existing near-surface winner, rejecting depth-different neighbors.
  The default live mode's coverage reconstruction retains the weight sum when
  it is below one. At most two source neighbors in the uncovered direction are
  searched for a farther surface separated by more than 0.04 normalized depth;
  only the uncovered fraction is filled from that local visible sample. Full
  coverage and unresolved holes keep their existing behavior. Coordinate differences
  are evaluated before adding fractional shifts to avoid rounding away tiny coverage.
  LR geometry and reconstruction stay shared with host/native/VFG publication.
  The optional content-plane diagnostic reads a fixed 32x32 depth sample and owns
  one bounded tracker; the default live mode does not perform this readback.
  Every LiveDepth allocator and borrowed-layout consumer is rebuilt and hash-pinned
  together, including Small's separate input DLL.
- Native delivery uses worker-owned bounded texture slots and per-consumer leases.
  The controller's `configureOutputCapture` applies its output capture policy
  before/after showing and on visibility restoration. Normal launch excludes
  output from capture; the explicit Owl3D comparison subclass allows capture of
  only its owned output and verifies affinity readback. Every output is marked
  with `DepthSBS.OutputWindow.v1`; source enumeration and validation reject that
  marker across processes, independently of title or screen placement.
  Renderers acquire a writable slot before projection by default. An explicit
  `requires_texture_slot=False` renderer may project into its own bounded GPU
  buffer; its publisher must acquire the real metadata/GPU lease immediately
  before writing the shared texture. This does not waive mutex ownership.
  Metadata acknowledgment cannot replace GPU mutex ownership. Each Qt window
  copies into a private texture within the external-command render boundary.
  The minimal product shell uses only the separate output consumer. Its
  non-persistent scene graph releases native nodes when Stop hides the window;
  cleanup does not depend on a later visible frame. Diagnostic dual-consumer
  transport remains an API capability, not an in-app preview control.
- `presentation_policy.py` owns the unlimited/30/60 scheduling rules. Non-VFG
  native sessions snapshot `WorkCadence` in the worker: it retains the planned
  deadline for at most 3ms of jitter (bounded also by period/4), otherwise
  re-anchors after the late work. It waits for a deadline and one writable slot
  BEFORE acquiring the latest input. Deadline waits use the interruptible stop
  event for the remaining time (at most 50ms); due-but-blocked slots retain a
  bounded 1ms GPU-ack wait. The retained displayed slot need not be free.
  `NativeDeliveryCadence` guards publication spacing at period minus that jitter
  bound, rather than imposing a second full-period rate. Host and timed VFG
  consumers keep `PresentationCadence`'s strict relative full-period cap. Their
  producers retain existing pacing; unlimited work/delivery remains unpaced.
- `FrameWakeup` owns a local nonblocking socket pair and Qt read notifier for a
  native session. Only the writer is duplicated into the worker with its mailbox.
  Successful offer/publish/retire operations signal AFTER releasing metadata;
  notifications carry only one byte, never pixels, descriptors or acknowledgments.
  The GUI drains bounded chunks; a full writer coalesces notifications because
  unread bytes already guarantee a wakeup. There is no clear-event race or
  helper thread. Windows loopback writes disable packet coalescing.
  Native health polling falls back every 50ms. A separate precise single-shot
  timer services the earliest pending publication/VFG due time, or retries at
  1ms only while older GPU leases/retirement still need acknowledgments. A sole
  retained current frame does not cause retries. Stop cancels that timer; the
  socket pair closes after the owned worker exits, before the next session.
  The existing two texture slots bound backpressure. Retirement drains unpublished
  leases regardless of pacing; no metadata-only release is introduced. Qt vsync
  is disabled by request, while actual display scheduling remains outside this policy.
  The controller advances the QML surface revision and requests rendering when
  `NativeDelivery.consume` changes the broker frame or retires it. This is shared
  by ordinary and timed VFG delivery. Worker statistics are acknowledged separately
  and never trigger native rendering: they may arrive before a capped publication,
  so using them as a render notification can strand a ready frame until the next
  input. Host image delivery retains its copy/notification/deadline sequence.

## State and time contracts

Live DA2 Small/Base CUDA postprocessing owns range normalization independently
of pixel EMA and model inference. `DepthRangeClock` supplies elapsed source time
and discontinuity resets to the worker-owned renderer; `LiveDepth` keeps its
existing two GPU bounds and one host response interval. The range kernel uses
1,024 fixed spatial samples and a bounded two-pass affine fit against previous
smoothed depth, accepting only photometrically stable, unclipped anchors with
sufficient spread and agreement. This transports old bounds into current model
units before the adaptive time response. A failed fit uses the time response
without transport. Reduction uses one 256-thread block and shared scratch;
no extra frame buffers, readback, capture or future frame is introduced.
Cut/size/source/timestamp resets bypass transport and use current percentiles.
`range` includes the prior coverage reconstruction; explicit `coverage` keeps
the previous frame-weighted range behavior. Reference/file, RowFlow and stateful
model paths do not opt into this live-only range policy. All borrowed-layout
bridges are rebuilt/pinned with the appended interval field.

`motion` includes `range` and remains an explicit pre-window comparison control.
`MotionHistory` owns an independent hash-pinned CUDA module and an NVOF session;
it borrows the validated renderer layout and engine stream without changing their
ABI. It computes both flow directions on a grid with maximum edge 640, with NVOF
temporal hints disabled for alternating directions. A bounded full-resolution
kernel warps one previous guided depth, rejecting inconsistent round trips,
photometric mismatch, depth changes and local silhouettes. Accepted contributions
decay with source age and have a capped normalized-depth step. Static pixel EMA
and range fitting retain their existing state: motion changes only projection
depth, storing the pre-motion result for the next frame. Two full-depth buffers,
one RGB history and bounded flow buffers are owned per renderer. On repeated
native DA2 detail inputs a lazy snapshot holds the last probed projection depth
and two range bounds. The worker checks convergence on the engine stream, then
leaves the broker's finished texture in place and advances the source clocks.
An exact RGB change invalidates the hold before inference. There is no
future frame or normal-path host depth readback. Explicit
diagnostics may allocate an acceptance mask and read back depth.
Cuts/discontinuities reset; applied flat-background refinement invalidates
motion history and bypasses correction. Resize replaces the session. Native
driver failures stop the worker visibly. All motion resources are drained and
destroyed before the borrowed renderer/stream; cleanup attempts remaining owners
even after a motion cleanup error. Explicit `range` remains a comparison control.

`window` includes `motion` and remains the pre-budget comparison control.
`LiveDepth` owns four additional GPU floats (target/displayed left/right widths),
a source interval and a reset flag. The common shift kernel reduces crossed
disparity only where a source pixel would leave one eye's image. Widths are capped
at 1.5% of one eye, expand immediately and decay with a 200ms source-time constant.
The shared projection path applies a straight fractional-coverage black mask to
the left eye's left edge and right eye's right edge after reconstruction. It never
alters depth/history or shifts coordinates. There is no host readback in normal
operation. Cut/clock resets are supplied by the worker-owned source clock; resize
replaces the allocation. All allocators and borrowed consumers, including motion,
VFG and the dormant RowFlow bridge, are rebuilt and hash-pinned to this layout.
VFG additionally owns two two-float GPU snapshots paired with its original RGBA
buffers. Publication swaps both pairs together. After interpolation a bounded GPU
mask uses the larger width from the two source frames; source RGBA buffers are
not mutated. This protects the frame window from interpolation-edge artifacts.

`budget` includes `window` and remains the pre-detail comparison control.
An appended boolean in `LiveDepth` enables a pointwise compression in the shared
shift kernel, after depth history and before mask-width reduction or projection.
For signed total disparity `d`, the unchanged core ends at 0.25% of one-eye width
for near/crossed and 0.35% for far/uncrossed disparity. Beyond the knee `k`,
`abs(d)` maps to `k + (L-k)*(abs(d)-k)/(L-k+abs(d)-k)`, with asymptotes `L` at
0.6% near and 0.8% far. It preserves sign, has continuous unit slope at the knee,
and derivative in (0,1]. Fixed width-relative parameters require no statistic,
new temporal state, allocation or normal-path readback. Model, history and fixed
convergence are unchanged. The previous strength remains the input to this curve.
The optional shift snapshot is diagnostic only and returns the scratch array;
after a complete two-eye projection it contains right-eye shifts. All allocators
and borrowed consumers are rebuilt/pinned in separate `*-budget` directories.
Reference/file, RowFlow and VDA/oVDA paths do not enable the curve.

`detail` is the prepared-local DA2 live default and includes `budget`.
`stereo_detail.cuh` owns the independent contour/fill flags in appended
`LiveDepth.detail_mode` (bits 1/2). The contour kernel fully overwrites existing
guided-filter scratch `t0` after filtering/motion on the same owned stream; no
additional full-frame allocation or temporal state is introduced. Only shift
generation reads that corrected depth. Splat visibility ordering, same-surface
reconstruction and background classification continue to read immutable `aligned`:
using the corrected depth there crossed discrete surface thresholds and caused
large RGB changes in the first candidate. The current split avoids that coupling.
The corrected shift is further clamped inside the original floor/ceil splat
interval (integer shifts stay exact). Thus contour correction cannot change
destination cells, owner winners or hole topology. The diagnostic corrected-depth
snapshot precedes this shift clamp and is not a claim of fully applied geometry.

Contour correction uses a five-pixel horizontal stencil: two stable depth sides,
an intermediate center, strong RGB edge and a matching center/side color. Smooth
confidence gates cap the depth-equivalent adjustment at 0.025; sharp one/two-pixel
objects do not satisfy the stencil. Background fill reuses original source RGB,
depth, per-eye shifts and owner map after the ordinary resolve. It seeks valid
owners at most 32 destination pixels to either side, chooses the farther surface
only at a real depth discontinuity, and preserves outer/unresolved gaps. Visible
source samples use linear interpolation with same-depth confidence. Occluded
samples use a three-neighbor local gradient only within four source pixels;
depth, gradient, curvature and distance smoothly attenuate it. Partial coverage
uses the same sampler. Both eyes share the functions; no host readback is added.
The optional corrected-depth snapshot is diagnostic only. All six current
allocators/borrowed consumers are rebuilt and hash-pinned under `*-detail`.
File/reference, RowFlow and VDA/oVDA do not enable these flags.

The normal live controller snapshots `vfg_enabled=False` by default. Only an
explicit opt-in selects `vfg_delivery`'s timed mailbox/consumer and the worker's
`vfg_renderer` producer. The ordinary worker owns interpolation directly, without
monkeypatching the model registry. Renderer creation and texture publication are
the two VFG extension points; the existing depth/capture/reset and pool-retirement
owners remain intact. `LivePreview` coordinates running VFG changes by stopping
and joining its owned worker before starting the same source with a new session
and ordinary/timed delivery. A single transient QImage holds the last output
while its window remains open; stop, failure and the first new frame clear it.
Runtime preflight precedes teardown. `vfg_hotkey.py` owns Windows RegisterHotKey
registration, the non-repeating Ctrl+Alt+S callback and application shutdown
unregistration; fixed comparison launchers do not register it. The GUI never
imports the GPU renderer or loads VFG DLLs.
`vfg_runtime` defines the supported selection and verifies all five official
wheel DLLs plus our bridge before native load. The prepared runtime is under
`out/vfg-runtime/1.3.0.0`, staged by `scripts/prepare-vfg-runtime.py` from the
hash-verified official wheel with its notices. Native DLL search directories and
the VFX environment setting are scoped to the owned worker renderer lifetime.
This local setup is not yet a relocatable live-app package.

The isolated `experiments/vfg` launchers retain their fixed comparison paths and install timed native delivery for Small
or Base baseline measurement; enabling VFG composes shared output ownership and
interpolation with the selected model's existing renderer. Small retains its GPU
cubic preprocessing and 518-square depth path; Base retains its source-depth
path. The shared VFG layer borrows each engine's checked stream view, including
Small's non-owning Torch wrapper over its raw CUDA stream. Normal application
startup does not import it.
Its interactive comparison launcher clears the output's QWindow transient parent
for external full-screen discovery. The output HWND has no native owner and is
its own GA_ROOTOWNER; QObject ownership and close/stop resource cleanup remain
with the existing desktop controller. Normal application window parenting is
unchanged.
Its renderer owns previous/current/generated linear RGBA buffers and borrows the
engine stream. Publication retains the existing two-slot native pool. Generated
and original output IDs are distinct from inference IDs; an auxiliary per-slot
record carries source/midpoint time, oldest input, due time and frame kind.
Baseline and VFG publication preserve the raw WGC source timestamp and actual CPU ready
time independently: fast Small processing can finish before the compositor stamp.
The first due time follows both; source leads over 100ms fail before publication.
Generated midpoint/source and actual ready times remain separate, so a future
compositor stamp is scheduled without inventing an earlier capture or later ready time.
Timed delivery waits for due time and the preceding Qt completion, while
retirement still drains leases. Every actual depth discontinuity resets pair history; invalid or
over-100ms source intervals cannot interpolate. Capture index gaps alone do not
invalidate timestamp-valid pairs. Stop destroys effect/buffers before the borrowed
stream owner. The experiment does not alter the base mailbox wire format or
introduce a normal GUI mode.

The explicit local `rowflow-sym` adapter subclasses the source-depth consumer.
Its pinned bridge copies the final normalized/guided depth and RGB into owned
PyTorch tensors on the engine stream, including conditional background refinement.
Resolution-specialized compiled RowFlow v3 symmetric preserves upstream
left/right order. CPU and CUDA forward projection likewise place positive
near-depth displacement in the left eye; the right eye uses its negation.
Finite checks precede uint8 publication.
Host output reads back the full SBS; native output packs into the existing
two-slot keyed-mutex protocol. Neither path changes Base TensorRT inference.
The worker snapshots renderer selection and compiles before offering a pool;
resize retires the old pool/consumer before replacing the engine. Compiler work
and descendants belong to a worker-owned Windows kill-on-close job. Preparation
status is advisory shared memory without a lock that forced cancellation could
strand. The existing watchdog cancels that owned worker; normal CUDA sessions
do not load RowFlow, its checkpoint or Triton. Artifact pins live in `rowflow.py`.

| State | Owner / boundary |
|---|---|
| Model recurrent cache / position | Selected engine; its declared input timeline and reset API |
| Depth scale, normalization, EMA / stereo history | Depth postprocessing/stereo path; not implicitly the model cache |
| Flow/propagation source, confidence | Explicit propagation candidate; rejected fixed 1:2 is not product policy |
| Offline centered window / lookahead | File-only offline processor; five samples maximum, scene-local flush, ordered emission |
| Output pacing and any future FG pair/PTS | Presentation path; generated output does not masquerade as fresh inference |

Capture sequence, selected model-input sequence, fresh-depth sequence, base SBS
and generated output are distinct. Cuts/source/shape changes reset or re-prime
the appropriate owners. Existing stateful file bindings reject unsupported skips;
a proposed new sampled timeline requires independent validation, not a silent
change to those guards. Calling the same skipped input a new timeline does not
remove recurrent drift.

## Invariants

1. Validate dimensions, color, timestamp, tensor and resource descriptors before
   allocation/submission. Retention requires an ownership-bearing handle.
2. Use bounded queues/pools. Offline preserves frame order/timestamps; live uses
   declared latest-frame/drop policy with counters, not an unbounded backlog.
3. No silent model/precision/resolution/CPU fallback. Session policy is immutable.
4. Stop/error invalidates consumers and releases/reaps owned resources in order.
   Failed publication preserves the previous output; device loss is not certified.
5. Profile copies, synchronization and overlap before claiming zero-copy or gain.
6. Preserve eye order and color; record model/artifact provenance and license scope.

## GPU measurement details

The prepared local postprocessing build is `scripts/build-gpu-load-opt.ps1`,
producing the three pinned DLLs under `out/static-sbs`. Small resizes its raw
518×518 depth on the owning stream. The source-depth adapter accepts depth at
the input image size. Both pass the prepared buffer to `finish_live_depth`
for range normalization, temporal filtering, guidance and history update. Guidance at radii 4 and 8
uses fixed-radius 2-D kernels and two FP32 sum components: TwoSum retains each
addition's residual, then FP64 combines the components for the original mean
and final float conversion. This changes the numerical representation under a
bounded-error comparison contract; tested public/synthetic output is exact, not
a proof for arbitrary floats. Input resolution, radius, epsilon, guide products
and temporal state are unchanged. Other radii above 4 use rolling sums across 64-pixel chunks.
Stereo resolve uses 32-pixel
occupancy words to find the same nearest valid neighbors and preserve depth
winner/tie decisions. `LiveDepth` layout is unchanged; native, motion, VFG and
RowFlow consumers retain explicit validated allocator pins. The VFG bridge
itself retains its earlier projection kernels.

File pipes and live paths other than Small/Base window GPU input still cross host memory. Their SBS capture thread
retains the ownership-bearing WGC mapped NumPy view in one latest-frame slot until
RGB conversion completes; original preview still copies into bounded shared BGRA.
This removes one same-process 4-byte-per-pixel memcpy, not the WGC readback or RGB
host-to-device transfer. Small/Base window GPU capture instead performs D3D/CUDA device
copies and one completion wait per accepted capture; this is not a zero-copy path.
GPU postprocessing
borrows TensorRT output/stream through owner/thread/generation checks. Eligible
GPU background refinement and its small eligibility readbacks remain explicitly counted. Host delivery copies owned
BGRA/QImage data; native delivery returns a slot only after the last GPU lease.

Submitted copy bytes are not measured bus traffic. Device-wide memory is not
process peak memory. Detailed hashes/readbacks are optional diagnostics; frame
callbacks and Qt/readback timing are not physical scanout. Measure completed
pipeline work, including file drain/audio/publication, before performance claims.
The comparable result owns its exact timing denominator.

## Change boundaries

These are the current components, not a prescribed future architecture. Refactor
or replace stages when it serves the user goal; keep externally visible contracts
explicit and validate changed ownership, timing or quality. Platform APIs belong
at adapters rather than hidden product-policy branches.

Current user behavior: [PRODUCT](docs/PRODUCT.md). Trust and failure contracts:
[SECURITY](docs/SECURITY.md), [RELIABILITY](docs/RELIABILITY.md). Historical results:
[evidence index](docs/evidence/README.md).
