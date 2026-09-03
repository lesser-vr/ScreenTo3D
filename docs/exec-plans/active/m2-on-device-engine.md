# M2 on-device TensorRT engine

Status: Active design; implementation pending model artifact

## Outcome

Build a trusted DA2 Small ONNX model into a GPU-specific TensorRT FP16 plan on
first use, validate it, publish it atomically to the per-user cache, and reuse it
on the next run.

The governing design is `docs/design-docs/on-device-engine-build.md`.

## Local prerequisite result

Validated on 2026-09-03:

- TensorRT 11.2.1.2 Windows SDK at `C:\TensorRT\TensorRT-11.2.1.2`;
- `trtexec.exe`, `NvInfer.h`, `nvinfer_11.lib`, `nvonnxparser_11.lib` present;
- `nvinfer_11.dll` and `nvonnxparser_11.dll` load when the SDK `bin` directory is
  applied to the current process PATH;
- RTX 5090 builder resource (`sm120`) present;
- current Codex process predates the environment-variable change, so a process
  restart or explicit script refresh is required.

Canonical verification:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\tensorrt-check.ps1 -UpdateCurrentProcess
```

## Milestones

1. Add an explicit `DEPTHSBS_TENSORRT_ROOT` CMake cache variable and validate
   headers, import libraries, runtime DLLs, and version at configure time.
2. Define engine build request, cache identity, manifest, status/error, and
   progress event types without TensorRT types leaking into product policy.
3. Select a legally distributable DA2 Small ONNX artifact and pin its hash,
   tensor contract, preprocessing, and output normalization.
4. Implement ONNX parsing, fixed-shape FP16 build, serialization, and detailed
   parser/build diagnostics.
5. Add cache locking, temporary files, atomic publication, validation, quarantine,
   one-shot rebuild, and garbage-collection boundaries.
6. Add deterministic smoke inference and compare against a reference output.
7. Package required runtime DLLs in a staging directory and verify operation on a
   machine without a separately installed TensorRT SDK.

## Exit criteria

- Clean-cache and warm-cache tests pass.
- Engine build and steady-state inference measurements are reported separately.
- Invalid ONNX, plan corruption, version/GPU mismatch, cancellation, OOM, and
  concurrent build tests pass.
- The staged application runs with only a supported NVIDIA driver installed.
- Redistribution inventory and notices are reviewed before release.
