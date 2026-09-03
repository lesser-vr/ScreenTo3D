# DepthSBS

DepthSBS is an NVIDIA-GPU-first 2D video to VR side-by-side (SBS) converter in
active development. The initial implementation establishes reproducible hardware
capability detection and processing-mode contracts before the media pipeline.

## Current status

- C++20 core builds with MSVC through CMake and Ninja.
- `depthsbs capability` emits machine-readable GPU/runtime capability JSON.
- `depthsbs mode <name>` resolves Performance, Balanced, Video Quality, or
  Offline Quality into an immutable initial processing plan.
- Unit tests cover mode contracts and JSON serialization.
- Video decode, depth inference, SBS synthesis, and encode are not implemented yet.

See [the active V1 plan](docs/exec-plans/active/v1-foundation.md) for milestones
and [the processing-mode specification](docs/product-specs/processing-modes.md)
for product behavior.

## Build and test on Windows

Requirements:

- Visual Studio with the MSVC x64 toolchain;
- Visual Studio's bundled CMake and Ninja;
- an NVIDIA display driver for the live capability probe;
- FFmpeg and ffprobe on `PATH` for media work.

The helper locates Visual Studio through `vswhere` and initializes its developer
environment:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 -Action check
```

Release capability probe:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 `
  -Action capability -Configuration Release
```

The build output is written under `out/build/` and is ignored by git.

## CLI

```text
depthsbs capability [--compact]
depthsbs mode <performance|balanced|video-quality|offline-quality> [--compact]
```

All modes are currently marked experimental. Their frame-rate numbers are
benchmark targets, not support claims.
