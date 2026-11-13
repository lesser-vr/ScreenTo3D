# oVDA local use


Scope: prepared local source application, personal/non-commercial use. Not a
portable public release or clean-machine installer. oVDA uses the adopted
518x924 mixed-FP16 engine; the application's default DA2 Small selection is unchanged.

## Start

Run the prepared source application:

```powershell
./scripts/run-ovda.ps1
```

The GUI starts with `ovda-small-c16`, Video Quality, CUDA stereo and the installed
engine root selected. CPU stereo can be chosen explicitly; no fallback occurs.
The same adopted mixed-FP16 engine is used by normal desktop live oVDA and file
conversion. Encoder/spatial attention use mixed FP16; temporal blocks, cache,
depth head and floating input/output remain FP32. The UI and diagnostics label
this as mixed FP16.
Choose input/output MP4 paths, read `experiments/ovda/LICENSE`, confirm
personal/non-commercial use with the oVDA checkbox, then Convert. Progress and
Cancel use the normal app worker. Completion means final mux/publication finished.
The output contains both eyes side by side: each eye preserves input dimensions.
Source and SBS geometry retain the selected dimensions and aspect ratio. Model
input alone may use replicated-edge padding; depth is cropped to that content
region before resizing to the original source.

oVDA is a Video Quality choice only. Performance is incompatible with its
full-rate temporal cache, Balanced belongs to DA2 Base, and Offline Quality now
belongs to VDA plus the dedicated centered five-frame processor. The launcher
rejects those mismatches instead of silently changing model or processing.
H.264 remains the default output; HEVC is an explicit user choice.

```powershell
./scripts/run-ovda.ps1 -Diagnostics -NonCommercial
./scripts/run-ovda.ps1 -CheckInstallation
./scripts/run-ovda.ps1 -NonCommercial -InputVideo 'out/public-live-default/FloorballGame.mp4' -OutputVideo 'out/new-ovda-sbs.mp4'
./scripts/run-ovda.ps1 -NonCommercial -InputVideo 'out/public-live-default/FloorballGame.mp4' -OutputVideo 'out/new-ovda-hevc-sbs.mp4' -OutputCodec hevc
./scripts/run-ovda.ps1 -StereoRenderer cpu
# Actual cache/reset lifecycle on pinned public frames:
./scripts/validate-ovda-lifecycle.ps1 -NonCommercial -OutputReport out/new-ovda-lifecycle.json
```

`-NonCommercial` confirms the stated scope; it is not a commercial license grant.
The GUI always requires its own checkbox even if this switch was supplied.
The GUI's `Check oVDA setup` button and `-CheckInstallation` do not load engines:
they report verified profiles, dependencies, GPU, runtime/media files and CUDA
stereo installation. `-Diagnostics -NonCommercial` then verifies actual native
projection and engine loading. Missing/unsupported components give explicit errors.
No model, precision or CPU fallback occurs on error. Failed/cancelled conversions
preserve any prior output. Successful conversions replace the selected output;
choose a new name if you want to retain an earlier successful version.

## Supported environment and geometry

- NVIDIA GeForce RTX 5090 (SM 12.0), Windows. The adopted mixed-FP16 plan was
  validated on driver 621.14; prior FP32 evidence used older recorded drivers.
- TensorRT 11.2.1.2 runtime; `-RuntimeDirectory` may override its DLL location.
- Prepared Python 3.13 packages under `out/vda-oracle-env`, torch 2.7.1+cu128.
  If its old launcher points at a removed WindowsApps interpreter, the launcher
  resolves an installed compatible CPython 3.13; the 2026-09-08 runs used 3.13.9.
- Source width 16..4096, height 16..2160. The installed 518x924 mixed-FP16
  canvas supports 4:3, ultrawide, portrait, square and other ratios by aspect-fit.
  Matching 16:9 native inputs retain their original transform; other ratios fit
  the same 518x924 canvas without changing source/eye dimensions.
  Verified examples: 4:3 960x720, original 1056x608, standard 1280x720,
  1920x1080 and short 3840x2160 HEVC input/output.
- 4K requires explicit HEVC output (Full SBS 7680x2160). H.264 output is rejected
  at that width. The 30-frame 4K test is compatibility evidence, not sustained FPS.
  This gate uses 8-bit SDR media; HDR color-management correctness is not certified.
- Padding is confined to depth inference. It is removed before depth restoration,
  never added to the input or SBS eyes. Missing all validated engines, invalid
  dimensions and unsupported HDR remain explicit errors.
- No 124-frame application limit. The model retains 16 cache slots regardless
  of duration; scene cuts clear temporal state. Long-duration stability and VR
  playback are not certified by removing the short diagnostic limit.
- H.264/HEVC video input through existing app decoding; audio follows the shared
  app mux policy. Converted results retain source frame count and cadence.

## Local installation and reproducibility

Live window GPU output now uses WGC GPU capture and an oVDA-specific FP32 input
kernel. Build the optional local kernel with `./scripts/build-ovda-input.ps1`;
the runtime verifies `out/ovda-gpu-input-resolution/ovda_input.dll` against its source pin.
Live source-depth stereo also requires `./scripts/build-ovda-postprocess.ps1`,
which builds the separately pinned `out/ovda-postprocess-range/ovda_postprocess.dll`.
It separates pixel EMA from source-time depth-range stabilization and is source-only,
like the model runtime. Rebuild this bridge when updating from the pixel-EMA-only
version; an older bridge is rejected rather than silently falling back.
It also uses the existing trusted GPU-capture and Base input thumbnail binaries.
This kernel remains outside portable bundles. Missing/corrupt input binaries
fail visibly; there is no automatic CPU fallback. File conversion, explicit host
reference output and default monitor input retain CPU preprocessing. The shared
diagnostic `SCREENTO3D_GPU_CAPTURE=0` explicitly selects the original live input path.

The current workspace is prepared. These files are not included in Git/old
portable builds; copying just the launcher is insufficient on another computer.
There is no general end-user installer for oVDA yet.

### Explicit live resolution / mixed-FP16 comparison

The prepared workspace has an isolated live comparison launcher:

```powershell
./scripts/run-ovda-resolution-trial.ps1                         # 518x924 mixed FP16
./scripts/run-ovda-resolution-trial.ps1 -Variant fp32-current   # 518x924 FP32 control
./scripts/run-ovda-resolution-trial.ps1 -Variant low-fp32       # 392x700 FP32
./scripts/run-ovda-resolution-trial.ps1 -Variant low-fp16       # 392x700 mixed FP16
```

Select the source and confirm the normal non-commercial-use checkbox. The
launcher selects oVDA, strength follows the normal 0.5 default, Half TB and 60 Hz.
It changes live inference only; source/eyes keep their dimensions and file
conversion uses the adopted mixed-FP16 path. Trial settings/placement are isolated
under `out/ovda-resolution-20261109/manual/`, and trial precision is labelled.
The ordinary application now selects the 518x924 mixed-FP16 artifact. Trial plan
hashes, builds and results are in the
[resolution/precision evidence](../evidence/ovda-resolution-fp16-20261109.md).

### Required local assets

1. `out/vda-oracle-env/Lib/site-packages`, with the pinned torch/TensorRT/CV
   environment recorded above, plus a compatible Python 3.13 interpreter. The
   launcher handles the known stale WindowsApps base-path case; do not downgrade
   the package set using upstream requirements.
2. App dependencies in the existing `out/v1-python-deps` path; the optional
   NC runtime source and license in `experiments/ovda` remain required.
3. FFmpeg/FFprobe at `out/gpu-preview/ScreenTo3D-GPU-Preview/_internal/ffmpeg`.
   CUDA stereo additionally uses the checksum-validated local preview
   `_internal/projection/projection.dll`. CPU selection does not require this DLL.
4. Trusted validated `model.plan` at `out/ovda-local/518x924-fp16/model.plan`,
   91370692 bytes, SHA256
   `394894301beee2302decaf43e7dd4912c043cae469a07f19f4848774a5eb0ec1`.
   It is installed from the validated `out/ovda-precision-20261109/encoder-spatial`
   candidate. Old FP32 plans can remain on disk but are not automatic substitutes.
   The loader fails explicitly if this adopted artifact is missing or corrupt.

The application verifies plan size/SHA256 before deserialization, GPU/runtime and
all tensor signatures. Runtime inference uses exact-validated local preprocessing
and does not import the original checkout, invoke Git, load checkpoint weights,
or need build-only `out/ovda-python-deps` packages.

Rebuild is a developer validation operation, not an automatic GUI download:

Build/reference tools still need the clean official source at
`out/ovda-source` revision `4173c24e22f528062a0cf8ae235c58a5d4376a74`, Git,
ONNX and the additive pinned `experiments/ovda/requirements-extra.txt` dependencies
in `out/ovda-python-deps`. Do not install upstream requirements over the app stack.

```powershell
$env:PYTHONPATH='experiments/ovda;v1;out/ovda-python-deps;out/v1-python-deps'
out/vda-oracle-env/Scripts/python.exe experiments/ovda/build_engine.py --fold-position --width 924 --input '<16:9 calibration clip with at least 32 frames>'
# The known verified FP32 export is then lowered using the selected recipe:
out/vda-oracle-env/Scripts/python.exe experiments/ovda/precision_trial.py --spatial-only --output '<new mixed-FP16 build directory>'
```

Build additionally requires the pinned, checksum-verified c16 checkpoint at
`out/models/ovda/oVDA_c16.pth` (source/weight URLs and hashes in the experiment
README). It runs original-vs-export position checks and 32 self-fed comparisons
of depth and all four cache outputs at atol/rtol .001 for the FP32 reference.
The mixed-FP16 candidate intentionally uses the separate numerical quality
contract in the [resolution/precision evidence](../evidence/ovda-resolution-fp16-20261109.md),
not a claim of strict FP32 parity. Inspect the respective build/validation reports.
Different regenerated hashes require explicit
validation and an allowlist update in `v1/screento3d_app/ovda.py`, not trust in an
arbitrary engine manifest. See the user integration execution plan for evidence.

For another GPU, build and validate on that device before extending its loader
profile; changing only a GPU name or manifest is not sufficient. Quality, precision decisions and final repeated
benchmarks are in [ovda.md](../evidence/ovda.md#record-result-ovda-expansion-results-2026-09-05).
The tested CUDA path is faster but still not a real-time guarantee. Cache size,
inference resolution and precision are not additional normal user options;
validated c16 518x924 mixed FP16 is the selected oVDA model configuration.

## License and delivery boundary

oVDA-derived code remains in `experiments/ovda`, with NC-SA-UHDV1.0 and attribution.
This optional integration does not claim unrestricted open-source/commercial
compatibility or settle obligations for a redistributed combined product.
The user's intended program is public but personal/noncommercial; publication
does not remove the NC-SA-UHDV1.0 attribution, share-alike and noncommercial
obligations. Do not bundle/publish it under the repository's general license alone.
Existing portable distributions remain unchanged.
## Validating a new device/profile

Record actual GPU, driver, runtime and shape. The pinned c16 checkpoint SHA256 is
`ea531d53a1135a443bafcf106a175b26a6519c05ccc1e994d74e46159e14b7cb`.
Use `experiments/ovda/validate_preprocessing.py` and the existing builder with
`--fold-position --precision fp32 --width <686|896|924> --runtime-dir <trusted-directory>`
on matching calibration content. Source/local preprocessing is compared exactly;
the builder compares 32 self-fed depth/cache outputs at atol/rtol .001.

Before integration, check affected reset/cache/lifecycle and media behavior and
record the validated engine signatures/hash/device profile. Validate a rebuilt
CUDA stereo component separately. Broader hardware, long-run or performance
claims need their matching evidence; a development branch or a blanket full test
matrix is not an additional documentation requirement. Existing failure records
and build provenance are in [oVDA evidence](../evidence/ovda.md).
