# ScreenTo3D

Desktop 2D-to-SBS conversion for games and videos. Run `ScreenTo3D.exe` in the
prepared local environment for the Korean/English Live / Files / Settings app. Live and
file conversion resolve the selected product mode to its permitted installed depth
model without silent fallback. Current source features are not automatically in
old portable builds.

Choose **Settings and diagnostics → Language** to use the system language,
한국어 or English. The selection is saved and can change while SBS is running.

The [current desktop portable build](docs/models/desktop-distribution.md) bundles
DA2 Small and installs Base, VDA Small and optional NVIDIA VFG on demand.
Small, Base and VDA build their TensorRT engines on the user's NVIDIA GPU.

The goal is better depth and easier use than Small + Lossless Scaling FG, with
3840x2160 per eye / 7680x2160 Full SBS at final 60 fps. This is not certified support.

## RGB quality evaluation (2026-11-10)

Native Full SBS and Half TB were evaluated with two references: four procedural
3D scenes with center-input / left-and-right ground truth, and four Spring scenes
with left-camera input / original right-camera ground truth. Spring scores cover
the generated right eye only. Measurements used an RTX 5090, current FP16/mixed-
FP16 models, fixed calibration before scoring, and equal weight per scene.

**Spring Half TB, 1920x1080 logical eye:** higher PSNR/SSIM and lower LPIPS are
better. LPIPS uses AlexNet v0.1.

| Model | PSNR (dB) ↑ | SSIM ↑ | LPIPS ↓ |
|---|---:|---:|---:|
| DA2 Small | 25.745 | 0.7706 | 0.10546 |
| DA2 Base | **27.091** | 0.7948 | 0.09836 |
| VDA Small | 26.676 | 0.8022 | 0.09938 |
| oVDA c16 (experimental) | 26.738 | **0.8032** | **0.09751** |

Base, VDA and oVDA improved all three global metrics over Small in every Spring
Half TB scene. Base had the lowest mean boundary/background RGB errors; oVDA
had the highest mean SSIM and lowest LPIPS. Rankings vary with the content:
Small had the highest PSNR on the procedural binocular scenes. The four-scene
samples do not establish a universal winner among Base, VDA and oVDA.

To match reference cameras, these diagnostic runs disabled disparity compression
and window-edge masks, then froze the fitted projection scale/convergence.
Application defaults were unchanged. These calibrated RGB results do not measure
unchanged-default geometry, real-time FPS or physical viewing comfort.

See [full results, both formats and validation](docs/evidence/sbs-rgb-quality-20261110.md)
and [measurement/reproduction methods](docs/BENCHMARKS.md#full-reference-native-sbs-rgb).
Spring data: [Mehl et al. (2023), DaRUS V2](https://doi.org/10.18419/DARUS-3376),
CC BY 4.0.

## Documentation

- [Product behavior and target](docs/PRODUCT.md)
- [Current paths, measurements and unpassed acceptance](docs/implementation-status.md)
- [Work areas](docs/ROADMAP.md)
- [Architecture](ARCHITECTURE.md)
- [Security](docs/SECURITY.md), [reliability](docs/RELIABILITY.md), [measurement methods](docs/BENCHMARKS.md)
- [Historical evidence](docs/evidence/README.md); model setup links are in PRODUCT.

## Build and test on Windows

Validate the source translation catalog with `python scripts/build-translations.py --check`.
The portable builder compiles and includes the Korean Qt catalog automatically;
English is the source-language fallback.

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
