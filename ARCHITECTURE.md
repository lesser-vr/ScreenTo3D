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

Live: selected WGC source -> owned D3D11/CUDA latest-frame slot (Small/Base window GPU paths)
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
NVDEC/CUDA/NVENC pipeline originally proposed. Small/Base window GPU sessions keep full
capture/model input on the GPU; other model/monitor paths retain host capture.
Base/VDA/oVDA live device-depth paths can publish SBS
through the same shared-texture GUI backend as DA2 Small, now the prepared-local
delivery default. Host output remains explicitly available. Selection is separate
from readiness: native registration/loading happens at SBS start, and QML creates
the native surface only after successful registration. Failure releases the live
lease and reports an actionable error without selecting another transport.
Processing-backend default and delivery-path default are separate decisions.

## Components and ownership

- `desktop_jobs.py` and isolated workers own job/session lifecycle; the GUI does
  not run inference. Live and file work share an exclusive processing lease.
- `live_policy.py` resolves immutable temporal/stereo policy. `live_backend.py`
  validates the mode-owned model snapshot and constructs only that binding.
  Backend/profile selection precedes output mutation.
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
  Exact 32x32 scene pixels and border samples cross to CPU; full RGB is read back
  only for the existing conditional background refinement or explicit diagnostics.
- Live worker/postprocessing owns normalization, EMA and stereo state. A CPU
  background-refinement bridge may remain explicitly counted, not silently removed.
- Native delivery uses worker-owned bounded texture slots and per-consumer leases.
  Metadata acknowledgment cannot replace GPU mutex ownership. Each Qt window
  copies into a private texture within the external-command render boundary.
  The minimal product shell uses only the separate output consumer. Its
  non-persistent scene graph releases native nodes when Stop hides the window;
  cleanup does not depend on a later visible frame. Diagnostic dual-consumer
  transport remains an API capability, not an in-app preview control.
- `PresentationCadence` owns the shared unlimited/30/60 FPS publication policy.
  Native delivery checks it immediately before publishing a GPU frame; host
  delivery checks it before copying/notifying a new image. Native metadata/health
  polling and GPU release/retirement are independent of the deadline. Capped
  delivery publishes at most one frame per deadline and schedules the next from
  that publication, without catch-up bursts. The existing two texture slots bound
  backpressure. Retirement drains unpublished leases without waiting for pacing;
  no metadata-only release is introduced. Qt vsync is disabled by request at app
  creation, while actual display scheduling remains outside this policy.

## State and time contracts

The explicit local `rowflow-sym` adapter subclasses the source-depth consumer.
Its pinned bridge copies the final normalized/guided depth and RGB into owned
PyTorch tensors on the engine stream, including conditional background refinement.
Resolution-specialized compiled RowFlow v3 symmetric produces a calibrated
right/left swap into DepthSBS eye order. Finite checks precede uint8 publication.
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

File pipes and live paths other than Small/Base window GPU input still cross host memory. Their SBS capture thread
retains the ownership-bearing WGC mapped NumPy view in one latest-frame slot until
RGB conversion completes; original preview still copies into bounded shared BGRA.
This removes one same-process 4-byte-per-pixel memcpy, not the WGC readback or RGB
host-to-device transfer. Small/Base window GPU capture instead performs D3D/CUDA device
copies and one completion wait per accepted capture; this is not a zero-copy path.
GPU postprocessing
borrows TensorRT output/stream through owner/thread/generation checks. Eligible
CPU background refinement remains explicitly counted. Host delivery copies owned
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
