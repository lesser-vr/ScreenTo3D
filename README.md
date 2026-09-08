# DepthSBS

Desktop 2D-to-SBS conversion for games and videos. Run `Run-DepthSBS.cmd` in the
prepared local environment for the Korean Live / Files / Settings app. Live has
Original preview and DA2 Small SBS; file conversion includes explicit installed
model choices. Current source features are not automatically in old portable builds.

The goal is better depth and easier use than Small + Lossless Scaling FG, with
3840x2160 per eye / 7680x2160 Full SBS at final 60 fps. This is not certified support.

## Documentation

- [Product behavior and target](docs/PRODUCT.md)
- [Current paths, measurements and unpassed acceptance](docs/implementation-status.md)
- [Work areas](docs/ROADMAP.md)
- [Architecture](ARCHITECTURE.md)
- [Security](docs/SECURITY.md), [reliability](docs/RELIABILITY.md), [measurement methods](docs/BENCHMARKS.md)
- [Historical evidence](docs/evidence/README.md); model setup links are in PRODUCT.

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
