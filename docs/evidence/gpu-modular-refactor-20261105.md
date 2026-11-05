# Common live GPU interfaces — 2026-11-05

Historical implementation/test record. Current architecture is owned by
ARCHITECTURE.md; support and measurements by implementation-status.md.

## Scope

Behavior-preserving Python refactor after Small GPU input promotion:

- `gpu_runtime.py`: `GpuExecution` supplies the engine-owned stream scope/handle,
  owner checks and CUDA image validation. `GpuInputSupport` shares pinned DLL
  verification/loading and the existing exact thumbnail implementation.
- Small supplies its existing non-owning ExternalStream, Base its existing
  Torch stream. The common layer does not create, destroy or transfer ownership
  of streams, model buffers or depth tokens. Frame and capture consumers no
  longer infer which stream representation an engine uses.
- `live_model.py`: explicit immutable adapter records supply GPU capture and
  RowFlow capabilities, optional capture-engine replacement, existing host/native
  renderer factories and reference transfer accounting. The worker consumes
  this interface; repeated Small/Base/VDA/oVDA name branches were removed.
- Existing binding validation still owns mode/profile/license checks. Adapters
  import native/GPU implementations lazily. Unsupported models/capture fail
  visibly; no fallback or new model choice was introduced.

Small's cubic coefficients/rounding, Base's resizing/padding, model precision,
stateful-model behavior and consumer token lifetimes remain model-specific.
CUDA sources/DLL pins, output defaults and UI behavior are unchanged in this
refactor. Native DLL consolidation was outside this scope.

## Verification

- `out/gpu-refactor-unit-20261105.log`: 53 tests pass, covering the common
  stream/image contract, owner expiry, wrong-thread/stream rejection, corrupted
  DLL rejection before load, adapter matrix, native/host selection, unsupported
  capture rejection, lazy engine replacement, transfer accounting, routing,
  scene history, depth ownership and actual spawned texture-mailbox transport.
  The initial stdin test runner could not spawn on Windows; the guarded file
  runner passes the same suite. Scoped Ruff and `git diff --check` pass.
- `out/gpu-refactor-base-input-20261105/report.json`: 66 actual CUDA Base
  preprocessing cases are exact against the original CPU implementation,
  including pitched BGRA and thumbnail comparisons; invalid inputs/foreign
  stream checks pass.
- `out/gpu-refactor-small-parity-20261105/report.json`: 27 exact preprocessing
  cases and 72 exact model-input/raw-depth/postprocessing/native-host SBS cases.
  Public FloorballGame/OfficeWalk/ParkingGarage at 1080p, ultrawide, portrait and
  4K, with cuts and flat fixtures. All final zero-error gates pass.
- `out/gpu-refactor-base-parity-20261105/report.json`: 24 real Base cases across
  those four shapes retain exact input/raw-depth/native-host parity and the
  existing legacy CPU postprocessing tolerance.
- `out/gpu-refactor-small-lifecycle-20261105/` and
  `out/gpu-refactor-base-lifecycle-20261105/` (plus their `.log` files): both
  actual default native paths pass startup, fullscreen/Escape, hide/restore,
  resize/lease retirement, stop/restart, source loss, worker crash and preparation
  cancellation. Shutdown assertions verify zero remaining native pools/nodes.

Runtime evidence uses the same prepared RTX 5090 / TensorRT 11.2.1.2 local
environment as the immediately preceding Small/Base input work. No portable
package was rebuilt and no commit/push was requested.

## Native performance check

`out/gpu-refactor-native-20261105/`: public FloorballGame in a separate source
process, 3840x2160 per eye, 7680x2160 Full SBS, fitted native output, target
60Hz, six-second warmup then five six-second windows per mode, no FG.

| Mode/model | Output median | Five-window range |
|---|---:|---:|
| Performance / Small FP16 | 59.92fps | 59.63–60.00fps |
| Balanced / Base FP16 | 57.36fps | 57.02–57.80fps |

The preceding final Small run measured 59.92fps; the prior Base FP16 run
measured 54.78fps. These reused baselines and the current run show no observed
performance regression. They are not contemporaneous interleaved A/B runs,
so the higher Base result is not attributed to this refactor. Source content,
mode policy and the existing DLL/engine pins were retained. Both input DLL
SHA-256 values were rechecked unchanged after the run.

Rates count distinct Qt afterFrameEnd IDs, not physical scanout. Input is a
1080p excerpt scaled to 4K. These bounded checks do not establish long-session,
real-game, physical-display/device-loss or general other-GPU support. VDA/oVDA
adapter selection is covered by unit tests; their runtime inference was not
retested during this refactor.
