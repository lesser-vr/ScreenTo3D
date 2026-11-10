# VDA Small local preview

The [desktop installer](desktop-distribution.md) builds both streaming profiles
from verified ONNX on the current GPU. The v2 pack uses mixed FP16 for the
encoder patch convolution and 48 linear projections. Temporal layers, external
cache bindings and depth outputs use FP32. The development artifacts and hardware
measurements below describe the original prebuilt profiles.


Status: Implemented and locally verified through 2026-09-08. Not a public release.

## What works

The VDA Small **streaming TensorRT** engine runs through the application
GUI/worker: video decode, full-rate depth inference, cut reset, CUDA or CPU stereo,
NVENC encode and audio mux. Video Quality consumes each streaming depth directly.
Offline Quality pairs the same VDA engine with a dedicated scene-local centered
five-frame processor: two past/two future reduced depth observations are
color/depth gated, every source frame is emitted in order, and cuts are flushed
without crossing scenes. It deliberately does not warp moving content without a
trusted motion-vector input. The app does not import upstream VDA source at runtime.

The source desktop selects `vda-small` for Offline Quality and defaults Video
Quality to VDA while still allowing an explicit oVDA choice. Performance is
rejected because its every-other-frame policy violates VDA's cache contract.
The current portable includes the VDA Small streaming integration.

Live VDA Small window capture uses the WGC/D3D11 CUDA bridge and a pinned
float32 cubic preprocessing kernel on the TensorRT stream. The same aspect-fit
rectangle drives CPU and GPU processing. Monitor capture and file conversion use
CPU preprocessing; `DEPTHSBS_GPU_CAPTURE=0` selects the mapped window path for
diagnostic comparisons. The installed VDA model serves both paths.

## Current compatibility limits

- Windows, RTX 5090 (SM 12.0), TensorRT 11.2.1.2. Engines were validated on
  driver 616.56; the 2026-09-08 public runs observed driver 616.64.
- Two validated model profiles: `[1,1,3,518,896]` for the supplied 1056x608
  aspect ratio, and `[1,1,3,518,924]` for standard 16:9 (720p/1080p/4K).
  Previously matched source ratios use their original profile. Other ratios
  use aspect-preserving fit into an installed profile, with replicated borders
  only for inference. Host and live device paths crop that border from the depth
  before resizing. The source bounds remain 16–4096 wide by 16–2160 high;
  narrow portrait content uses fewer horizontal depth samples.
  One job loads only its selected pair of engines. 1080p has a full 124-frame
  conversion gate; 4K has a short 12-frame HEVC compatibility gate, not a sustained
  performance or native-4K quality certification. 720p mapping is unit-tested.
- H.264/HEVC input and MP4 H.264/HEVC output within the existing pipeline limits.
  The source pixel dimensions and cadence are retained; Full SBS doubles width.
- Local source launcher uses the isolated CUDA PyTorch environment for buffers
  and resize, OpenCV for preprocessing, and explicit FFmpeg/TensorRT paths.
  This is not a zero-copy pipeline. The current launcher defaults to explicit
  CUDA stereo; `-StereoRenderer cpu` remains available with no silent fallback.
- No CPU/model/precision fallback, no automatic engine download, no resume.
- Real device loss, long-duration stability, wider content quality, VR playback,
  other GPUs and clean-machine distribution remain unverified/deferred.

## Run on the current development machine

From the repository root, open the GUI:

```powershell
.\scripts\run-vda.ps1
```

The launcher preselects VDA + Video Quality and supplies `out/vda-local` as the
trusted profile root plus runtime/media-tool directories. Choose input/output
and press Convert; input preflight matches the engine before output mutation.
Do not launch the old portable executable expecting VDA: it has not been rebuilt.

Capability/engine diagnostic and command-line conversion:

```powershell
.\scripts\run-vda.ps1 -Diagnostics
.\scripts\run-vda.ps1 -InputVideo '.\out\public-live-default\FloorballGame.mp4' `
  -OutputVideo '.\out\new-vda-sbs.mp4' -Mode video-quality
# Dedicated five-frame Offline Quality processing:
.\scripts\run-vda.ps1 -InputVideo '.\out\public-live-default\FloorballGame.mp4' `
  -OutputVideo '.\out\new-vda-offline-sbs.mp4' -Mode offline-quality
# Optional HEVC output:
.\scripts\run-vda.ps1 -InputVideo '<supported-input.mp4>' `
  -OutputVideo '<output.mp4>' -OutputCodec hevc
```

`-EngineDirectory` and `-RuntimeDirectory` explicitly override trusted local
paths. EngineDirectory accepts either a single artifact (only that shape) or
a parent with allowlisted `518x896` / `518x924` children suffixed `-fp32` for
development and legacy artifacts, or `-fp16` for the installed v2 pack. It never scans
arbitrary subdirectories or follows escaping child links. Native ratios require
their matching profile. A corrupt installed profile causes startup to fail. Diagnostics probes
each installed profile sequentially and reports its actual input shape.
4K Full SBS requires explicit `-OutputCodec hevc`; H.264 stays capped at 4096
output pixels wide. Only use locally built/trusted engines: checksum integrity is not proof
of authenticity. Native TensorRT plans must never come from untrusted sources.

## Reproduce the developer build

Existing prepared environment and artifact:

- Prepared packages: `out/vda-oracle-env/Lib/site-packages` for Python 3.13.
  If the old environment launcher points at a removed WindowsApps interpreter,
  `run-vda.ps1` resolves an installed compatible CPython 3.13. The 2026-09-08
  public runs used that fallback with CPython 3.13.9.
- Source: `out/vda-source`, official revision
  `4f5ae23172ba60fd7bc11ef671cca678842c7072`, clean worktree.
- Small checkpoint: `out/models/vda-small/video_depth_anything_vits.pth`, SHA256
  `13379300b739e659f076a59d52e9801bd8d38c541a7e71f73bbca4dcfb013609`.
- Artifacts: `out/vda-local/518x896-fp32/manifest.json` and
  `out/vda-local/518x924-fp32/manifest.json`, each with its own two `.plan` files.

For a fresh isolated environment, follow the pinned source/checkpoint acquisition
commands in [the oracle plan](../evidence/vda.md#record-plan-vda-small-oracle). Use
Python 3.13 and CUDA 12.8 PyTorch 2.7.1 / torchvision 0.22.1, not the upstream
Python-era dependency list. Do not install xFormers. Additional build dependencies:

```powershell
out/vda-oracle-env/Scripts/python.exe -m pip install onnx==1.18.0 onnxruntime==1.22.1 protobuf==7.36.1
out/vda-oracle-env/Scripts/python.exe -m pip install --no-deps `
  'C:\TensorRT\TensorRT-11.2.1.2\python\tensorrt-11.2.1.2-cp313-none-win_amd64.whl'
out/vda-oracle-env/Scripts/python.exe v1/build_vda_artifact.py `
  --input '<supported-validation-clip-with-at-least-64-frames.mp4>' `
  --output out/vda-local/new-518x896-fp32
# Build the independent 16:9 profile (new folder only):
out/vda-oracle-env/Scripts/python.exe v1/build_vda_artifact.py `
  --input '<16-by-9-validation-clip-with-at-least-64-frames.mp4>' `
  --profile 518x924 --output out/vda-local/new-518x924-fp32
```

The builder exports pinned weights, decomposes eight temporal Softmax nodes per
graph, folds constant positional Resize, builds both TensorRT plans, and requires
585 FP32 depth/cache comparisons (64 frames + reset) at rtol/atol 0.001. Only then
does it publish a new artifact directory. Existing directories are not overwritten;
failure logs stay in a uniquely named `.building-*` directory. ONNX Runtime CPU
is used only to evaluate the constant positional subgraph in the build, not as
video-inference fallback. No externally supplied serialized model is executed as
Python; the checkpoint is hash-checked and loaded with `weights_only=True`.

The build tool currently targets the documented TensorRT installation path.
The builder defaults to 518x896; select 518x924 explicitly for 16:9. A custom
output name can be used as a single artifact; automatic matching only discovers
the exact allowlisted child names above. Changing runtime version or adding other
profiles requires implementation and fresh validation, not a manifest edit.
Build logs/reports are opt-in local diagnostics
and may contain full local paths. Do not publish them without review.

## Optional validation commands

```powershell
.\scripts\test-v1.ps1
$env:PYTHONPATH = 'v1'
out/vda-oracle-env/Scripts/python.exe v1/test_vda_application.py --input '.\out\public-live-default\FloorballGame.mp4'
# A profile root supports either accepted ratio:
out/vda-oracle-env/Scripts/python.exe v1/test_vda_application.py --input '.\out\public-live-default\FloorballGame.mp4' --engine-dir out/vda-local
out/vda-oracle-env/Scripts/python.exe v1/test_vda_gui.py --input '<supported-clip.mp4>'
out/vda-oracle-env/Scripts/python.exe v1/compare_vda_application.py --input '<supported-clip-up-to-124-frames.mp4>'
out/vda-oracle-env/Scripts/python.exe v1/test_vda_widescreen.py --widescreen '<1080p-clip.mp4>' --original '<1056x608-clip.mp4>'
# Public raw-vs-centered temporal proxy and an annotated public hard cut:
.\scripts\evaluate-offline-vda.ps1 -OutputReport out\new-offline-proxy.json
.\scripts\evaluate-offline-vda.ps1 -Clip OfficeWalk -CutClip ParkingGarage `
  -OutputReport out\new-offline-cut-proxy.json
```

`compare_vda_application.py` now auto-selects either installed profile and accepts
`--engine-dir`, `--runtime-dir`, and `--max-frames 124`. It compares complete clips
with source dimensions <=1920 per axis, not 4K; actual decoded/inferred frames
are bounded even if metadata is wrong. Missing/extra frames or differing input
hashes fail the comparison. It emits normalized, labeled lower-frame regions and
reports the reference runtimes separately. The widescreen harness
creates an explicitly upscaled 12-frame 4K fixture; it does not alter the input.
The Offline evaluator is capped at 124 frames and uses only the pinned public
UVG-VCM corpus by default. Its Farneback-aligned normalized-depth change is a
temporal proxy, not ground truth, a spatial-quality score or a VR-comfort result.

### Experimental black-bar backdrop correction

The source GUI reports input/per-eye and Full-SBS dimensions after probing,
and reports actual applied/confirming/bypassed correction counts on completion.
This option neither adds nor removes source bars. Zero applied frames is not a
conversion failure: normal flat-background refinement can still apply.

The local source GUI now has an off-by-default checkbox:
`Experimental: refine flat backdrops inside black bars`.
To launch it preselected:

```powershell
.\scripts\run-vda.ps1 -LetterboxRefinement
```

The same switch works with `-InputVideo` and `-OutputVideo`; the Python app uses
`--letterbox-refinement`. Existing portable executables were not rebuilt.
Modes and model defaults are unchanged. This is a stereo correction, not a
different VDA model or a crop/stretch operation.

Three consecutive eligible identical content regions are required. Captions,
changed bounds or failed eligibility disable correction immediately; cuts reset
confirmation. Initial confirmation frames retain prior rendering behavior.
Only active frames restore source black-bar pixels in both eyes before encoding.
Completion telemetry reports warmup, applied, restored, bypass and cut resets.

Recorded comparisons, cancellation and black-bar results are in
[the VDA evidence](../evidence/vda.md); general-content/VR effectiveness is unestablished.
