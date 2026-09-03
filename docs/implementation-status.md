# Implementation status

Status: Active  
Last updated: 2026-09-03

## Implemented

- C++20 CMake/Ninja build with Debug and Release presets.
- A Windows developer script that locates Visual Studio through `vswhere` and
  provides one configure/build/test/capability entry point.
- A platform-independent processing-mode policy for Performance, Balanced,
  Video Quality, and Offline Quality.
- A Windows capability probe using the CUDA Driver API and safe DLL/executable
  discovery for the NVIDIA driver, GPU inventory, NVDEC, NVENC, TensorRT,
  FFmpeg, and ffprobe.
- Stable JSON output for capability and processing-plan data.
- Six unit tests covering documented mode mappings and JSON escaping.
- A Windows CI workflow that uses the canonical project script.

## Verified locally

- Visual Studio Community 2026 / MSVC 19.51.
- Visual Studio-bundled CMake and Ninja.
- Debug configure, build, and CTest: passed.
- Release configure and build: passed.
- Live probe detected NVIDIA GeForce RTX 5090, compute capability 12.0,
  34,162,016,256 bytes of device memory, NVDEC/NVENC loader availability, and
  FFmpeg/ffprobe on `PATH`.
- TensorRT runtime was not found on the DLL search path. This blocks a real DA2
  TensorRT backend, but not capability detection or the current unit tests.

## Not implemented

- Native FFmpeg/NVDEC demux and decode.
- TensorRT installation/version pinning and DA2 engine generation.
- CUDA preprocessing and SBS synthesis.
- NVENC output and mux finalization.
- Media fixtures, end-to-end tests, benchmark capture, and quality evaluation.

## Next vertical slice

1. Select and pin the TensorRT and FFmpeg development dependencies compatible
   with the local CUDA/driver environment.
2. Add a generated media fixture and native probe/demux descriptor.
3. Establish timestamp-preserving decode/encode passthrough as the M1 oracle.
4. Add the model-independent depth backend contract before downloading weights.
