# On-device TensorRT engine build

Status: Accepted

## Decision

DepthSBS ships a trusted ONNX model and builds an optimized TensorRT engine on
the user's NVIDIA GPU during first use. Later runs reuse a validated local cache.
The user does not install the TensorRT SDK or CUDA Toolkit separately.

The application installer supplies the TensorRT and CUDA runtime components that
the selected deployment license permits. Users supply a supported NVIDIA GPU and
driver. Development machines use the complete TensorRT SDK, headers, import
libraries, ONNX parser, and `trtexec`.

## Why

- TensorRT plans are sensitive to TensorRT version, platform, GPU compute
  capability, memory constraints, shapes, precision, and builder configuration.
- Building on the target machine chooses tactics for that GPU and avoids shipping
  a large matrix of device-specific plans.
- A single installer can cover the intended RTX hardware range while preserving
  device-specific performance.
- Model and build provenance remain inspectable and reproducible.

The cost is a larger application runtime and a one-time compilation step. Startup
UX and cache recovery are therefore product behavior, not implementation detail.

## Installed application contents

The exact redistributable set is established by dependency tracing and NVIDIA
license review. The expected categories are:

- signed DepthSBS executables and libraries;
- trusted ONNX model plus checksum and license notice;
- TensorRT full runtime/builder and ONNX parser DLLs required for local builds;
- required TensorRT builder resource DLLs for supported compute capabilities;
- CUDA runtime libraries that are not provided by the display driver;
- FFmpeg/media runtime and its notices;
- a machine-readable component manifest with versions and checksums.

Development-only headers, import libraries, samples, Python wheels, and
`trtexec` are not installed for end users.

## First-use flow

```text
select mode
  -> resolve model, precision, and fixed/dynamic shape profile
  -> probe GPU, driver, TensorRT, and available memory
  -> calculate cache key
  -> validate cached manifest and plan if present
  -> otherwise acquire per-key build lock
  -> parse trusted ONNX
  -> build and validate TensorRT plan
  -> run deterministic smoke inference
  -> write plan + manifest to unique temporary files
  -> atomically publish cache entry
  -> execute video pipeline
```

Progress reports distinguish download/install, ONNX parsing, tactic selection,
serialization, smoke inference, and completion. Cancellation removes temporary
artifacts and never publishes an unvalidated plan.

## Cache identity

The cache key includes at least:

- engine schema version;
- model identifier and ONNX SHA-256;
- TensorRT major/minor/patch/build;
- CUDA compatibility and application build version;
- GPU UUID, compute capability, and relevant hardware-compatibility setting;
- input/output tensor names, dtypes, layouts, and shape profile;
- precision flags, workspace limit, tactic sources, optimization level, and
  plugin identifiers/checksums;
- mode-relevant preprocessing and depth-normalization contract version.

Suggested Windows location:

```text
%LOCALAPPDATA%\DepthSBS\engines\v1\<cache-key>\
  engine.plan
  manifest.json
  build-report.json
```

The cache is disposable. Failure to validate or deserialize quarantines/removes
the entry and triggers one controlled rebuild. A second failure is reported and
does not loop indefinitely.

## Trust and safety

- Only bundled or signed-update ONNX models with expected hashes are parsed.
- TensorRT plans are executable artifacts; DepthSBS never loads plans supplied by
  arbitrary media files or untrusted directories.
- Cache files are created with user-only permissions where supported.
- File sizes, tensor dimensions, shape ranges, workspace, and build duration have
  explicit limits.
- The plan is deserialized and smoke-tested before publication.
- Logs contain model/hash/build metadata but no video frames.

## Compatibility and updates

An application, runtime, model, profile, or relevant GPU change produces a new
cache key. Old entries may coexist until garbage collection removes unused
versions under a size/age budget.

Version-compatible or hardware-compatible TensorRT flags may be evaluated later,
but they are not the default because they can restrict tactics or reduce
performance. On-device rebuild is the primary compatibility mechanism.

## Acceptance gates

- First build succeeds from a clean cache on every supported hardware profile.
- Warm launch selects the same cache entry without rebuilding.
- Corrupt, truncated, incompatible, or untrusted plans are rejected.
- Two concurrent jobs for the same key produce one published engine.
- Cancellation, OOM, device loss, and application termination leave no valid-looking
  partial cache entry.
- Build time, peak host/device memory, plan size, and smoke-inference output are
  recorded independently from steady-state video benchmarks.
