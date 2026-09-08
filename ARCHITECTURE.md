# DepthSBS architecture

Status: Current boundary map, reviewed 2026-09-08 against repository contracts.
This describes delivered paths and their limits; it does not certify performance.
See [implementation-status.md](docs/implementation-status.md) for status and [ROADMAP.md](docs/ROADMAP.md) for priorities.

## Delivered paths

```text
Qt Live / Files / Settings shell -> immutable job/session plan -> isolated worker

Files: probe -> FFmpeg decode/host frames -> selected depth binding
       -> streaming depth postprocessing
          OR Offline/VDA scene-local centered five-frame depth window
       -> CPU or explicit CUDA SBS -> NVENC/FFmpeg
       -> drain/audio mux/validation -> atomic publication

Live: selected WGC source -> retained mapped latest-frame slot (SBS)
                           OR bounded host BGRA mailbox (original preview)
      -> owned RGB/model input
      -> immutable model-defined binding
         -> DA2 Small fused live path (Performance)
         OR explicit oVDA source-resolution device-depth path
         OR DA2 Base / VDA host-depth path
      -> depth postprocessing / stereo
      -> host mailbox + owned QImage -> Qt output
      OR Performance-only experimental native texture pool -> Qt/D3D11 private textures
```

C++ CMake core provides capability/mode foundations. It is not the complete native
NVDEC/CUDA/NVENC pipeline originally proposed. Native output does not eliminate
host capture/input transfers. The oVDA live device-depth path still returns SBS
through host output; VDA device experiments are not automatically available as a
live GUI backend. Processing-backend default and delivery-path
default are separate decisions.

## Components and ownership

- `desktop_jobs.py` and isolated workers own job/session lifecycle; the GUI does
  not run inference. Live and file work share an exclusive processing lease.
- `live_policy.py` resolves immutable temporal/stereo policy. `live_backend.py`
  validates the mode-owned model snapshot and constructs only that binding.
  Backend/profile selection precedes output mutation.
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
- Live worker/postprocessing owns normalization, EMA and stereo state. A CPU
  background-refinement bridge may remain explicitly counted, not silently removed.
- Native delivery uses worker-owned bounded texture slots and per-consumer leases.
  Metadata acknowledgment cannot replace GPU mutex ownership. Each Qt window
  copies into a private texture within the external-command render boundary.

## State and time contracts

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

File pipes and live capture/input still cross host memory. The SBS capture thread
retains the ownership-bearing WGC mapped NumPy view in one latest-frame slot until
RGB conversion completes; original preview still copies into bounded shared BGRA.
This removes one same-process 4-byte-per-pixel memcpy, not the WGC readback or RGB
host-to-device transfer. GPU postprocessing
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
