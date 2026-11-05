# DA2 Base local use

Live Balanced uses the same validated FP32 plans and aspect-preserving model
padding through a device-depth adapter. The normal GPU path keeps depth and SBS
postprocessing on the engine's stream; advanced `GPU 직접 출력 · 실험` also publishes
the SBS texture directly to Qt. The explicit reference path remains available for
comparison. File conversion and its host-depth contract are unchanged. Restart
the source GUI to load updates; the portable bundle is not rebuilt automatically.
See [measured results and limits](../implementation-status.md).


Implemented 2026-09-05 on the current Windows RTX 5090 development machine.
From the repository root, launch the GUI with DA2 Base selected:

```powershell
.\scripts\run-da2-base.ps1
```

Choose input and output, then Convert. The model selector includes `da2-base`;
the launcher supplies the validated engine directory and runtime. Base weights
are CC-BY-NC-4.0 (non-commercial). Existing packaged executables do not contain
this addition. The prepared local Python/runtime files must remain installed.

```powershell
.\scripts\run-da2-base.ps1 -Diagnostics
.\scripts\run-da2-base.ps1 -InputVideo '<supported-input.mp4>' -OutputVideo '.\out\base-sbs.mp4'
```

The launcher selects from `out/da2-base-local`: 518x896 for the supplied 1056x608
clip, and 518x924 for standard 16:9 (720p/1080p/4K). Their direct preprocessing
is unchanged with the matching plan installed. Other source ratios, including portrait
and ultrawide, fit proportionally into the installed canvas with the least relative
padding. Edge pixels fill the model-only margins; the depth map is cropped back to
content before upsampling. Thin/very wide content gets fewer effective model pixels.
Source bounds remain 16..4096 pixels wide and 16..2160 high; encoder constraints
still apply. Other GPUs and TensorRT versions require separately validated builds.
Unsupported geometry is rejected before output mutation. Full SBS preserves
per-eye source dimensions; it doubles width. FP32 inference uses a dedicated
CUDA stream; CPU stereo synthesis and media pipes remain in use.

The application accepts only the exact locally validated plan hash and byte size
listed in `v1/depthsbs_app/da2_base.py`, and checks GPU, runtime and tensor signatures.
A fresh rebuild may have a different hash and requires validation and an explicit
allowlist update. This is a fixed local installation, not a general artifact
installer. No upstream source/checkpoint is imported at application runtime.

For eye-4K Full SBS file conversion, select HEVC with `-OutputCodec hevc`.
Recorded numerical/FP16 results are in [DA2 Base evidence](../evidence/da2-base.md).
The current application uses validated FP32; changing precision is a candidate
implementation/evaluation, not prohibited research.
