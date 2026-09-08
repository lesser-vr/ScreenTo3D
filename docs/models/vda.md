# VDA Small local preview


Status: Implemented and locally verified, 2026-09-04. Not a public release.

## What works

An explicitly selected VDA Small **streaming TensorRT FP32** backend runs through
the application GUI/worker: video decode, full-rate depth inference, cut reset,
existing mode-controlled temporal/stereo processing, NVENC encode and audio mux.
The app no longer imports the upstream source or experiment adapter at runtime.
DA2 remains the default for all four modes and existing portable packages.

Select `vda-small` with Balanced, Video Quality or Offline Quality. Performance
is rejected because its every-other-frame policy violates streaming VDA's cache
contract. Selecting Offline Quality here still uses streaming VDA, **not** the
offline windowed VDA algorithm. This is not an oVDA integration or an automatic
mode-to-model reassignment. Mode-specific existing EMA remains enabled.

## Current compatibility limits

- Windows, RTX 5090 (SM 12.0), TensorRT 11.2.1.2; validated driver 616.56.
- Two validated model profiles: `[1,1,3,518,896]` for the supplied 1056x608
  aspect ratio, and `[1,1,3,518,924]` for standard 16:9 (720p/1080p/4K).
  Source aspect-preserving lower-bound resize must map to an installed profile.
  The launcher automatically matches from its trusted profile root; a missing
  profile, portrait or other unsupported ratio fails with no stretching/fallback.
  One job loads only its selected pair of engines. 1080p has a full 124-frame
  conversion gate; 4K has a short 12-frame HEVC compatibility gate, not a sustained
  performance or native-4K quality certification. 720p mapping is unit-tested.
- H.264/HEVC input and MP4 H.264/HEVC output within the existing pipeline limits.
  The source pixel dimensions and cadence are retained; Full SBS doubles width.
- Local source launcher uses the isolated CUDA PyTorch environment for buffers
  and resize, OpenCV for preprocessing, and explicit FFmpeg/TensorRT paths.
  This is not a zero-copy pipeline. The normal launch uses existing CPU stereo.
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
.\scripts\run-vda.ps1 -InputVideo '<supported-input.mp4>' `
  -OutputVideo '.\out\avatar-vda-sbs.mp4' -Mode video-quality
# Optional HEVC output:
.\scripts\run-vda.ps1 -InputVideo '<supported-input.mp4>' `
  -OutputVideo '<output.mp4>' -OutputCodec hevc
```

`-EngineDirectory` and `-RuntimeDirectory` explicitly override trusted local
paths. EngineDirectory accepts either a single artifact (only that shape) or
a parent with allowlisted `518x896-fp32` / `518x924-fp32` children. It never scans
arbitrary subdirectories, follows escaping child links or falls back to another
shape. A corrupt installed profile causes startup to fail. Diagnostics probes
each installed profile sequentially and reports its actual input shape.
4K Full SBS requires explicit `-OutputCodec hevc`; H.264 stays capped at 4096
output pixels wide. Only use locally built/trusted engines: checksum integrity is not proof
of authenticity. Native TensorRT plans must never come from untrusted sources.

## Reproduce the developer build

Existing prepared environment and artifact:

- Python: `out/vda-oracle-env/Scripts/python.exe` (3.13.14).
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
out/vda-oracle-env/Scripts/python.exe v1/test_vda_application.py --input '<supported-clip.mp4>'
# A profile root supports either accepted ratio:
out/vda-oracle-env/Scripts/python.exe v1/test_vda_application.py --input '<1080p-clip.mp4>' --engine-dir out/vda-local
out/vda-oracle-env/Scripts/python.exe v1/test_vda_gui.py --input '<supported-clip.mp4>'
out/vda-oracle-env/Scripts/python.exe v1/compare_vda_application.py --input '<supported-clip-up-to-124-frames.mp4>'
out/vda-oracle-env/Scripts/python.exe v1/test_vda_widescreen.py --widescreen '<1080p-clip.mp4>' --original '<1056x608-clip.mp4>'
```

`compare_vda_application.py` now auto-selects either installed profile and accepts
`--engine-dir`, `--runtime-dir`, and `--max-frames 124`. It compares complete clips
with source dimensions <=1920 per axis, not 4K; actual decoded/inferred frames
are bounded even if metadata is wrong. Missing/extra frames or differing input
hashes fail the comparison. It emits normalized, labeled lower-frame regions and
reports the reference runtimes separately. The widescreen harness
creates an explicitly upscaled 12-frame 4K fixture; it does not alter the input.

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
