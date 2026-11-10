# DA2 Base local use

Balanced uses validated mixed-FP16 TensorRT plans with FP32 input/output and
aspect-preserving model padding. Live sessions use a device-depth adapter.
The normal GPU path keeps depth and SBS
postprocessing on the engine's stream; default `GPU 직접 출력` publishes
the SBS texture directly to Qt. Explicit host/reference paths remain available for
comparison. File conversion uses the same FP16 plans and retains its host-depth contract. Restart
the source GUI to load updates; the portable bundle is not rebuilt automatically.
See [measured results and limits](../implementation-status.md).

Base live window GPU paths use owned WGC/D3D11-to-CUDA capture and CUDA
preprocessing with the same float64 cubic/normalization arithmetic as the CPU
reference. Source-local builds require `scripts/build-base-input.ps1` and
`scripts/build-gpu-capture.ps1`, plus `scripts/build-gpu-load-opt.ps1` for the
current shared depth/Small/native postprocessing artifacts
and validated loader pins. The preprocessing binary's OpenCV notice is generated
beside the DLL. No upstream Veyra/iw3 runtime code or dependency is bundled.

For explicit developer A/B runs, `DEPTHSBS_GPU_CAPTURE=0` selects the existing
mapped capture; `DEPTHSBS_BASE_INPUT=cpu` then selects original CPU preprocessing.
`DEPTHSBS_BASE_INPUT=gpu` is the preprocessing default. Setting GPU capture to `1`
requires Base GPU processing, GPU preprocessing, and the default fused/0ms input
settings; unsupported combinations fail explicitly. Callback-event recording
currently requires mapped capture. The implemented native monitor adapter remains
an explicit diagnostic candidate; normal monitor capture uses the existing path.
These settings are process-start diagnostics, not additional GUI controls.


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
per-eye source dimensions; it doubles width. Mixed-FP16 inference uses a dedicated
CUDA stream with FP32 I/O. File conversion's CPU stereo synthesis and media pipes
remain in use.

The normal loader selects `518x896-fp16/model.plan` and `518x924-fp16/model.plan`.
The retained `*-fp32` folders are historical controls and are not automatic fallback
engines. Install both FP16 profiles to preserve the prepared checkout's complete
profile selection. Missing or modified FP16 artifacts fail explicitly.

The [portable installer](desktop-distribution.md) obtains verified ONNX graphs,
builds both engines on the current GPU and records their tested hashes.
Explicit legacy development plans must match the fixed hashes and byte sizes in
`v1/depthsbs_app/da2_base.py`. Both paths check GPU, runtime and tensor signatures.

For eye-4K Full SBS file conversion, select HEVC with `-OutputCodec hevc`.
Recorded numerical/FP16 results are in [DA2 Base evidence](../evidence/da2-base.md).
The FP16 default is an intentional precision/speed tradeoff authorized after the
[native output/error comparison](../evidence/base-fp16-native-20261105.md), not
FP32 numerical parity. Resize, LayerNormalization and Softmax remain FP32;
preprocessing, depth postprocessing and I/O remain unchanged. See the
[promotion record](../evidence/base-fp16-default-20261105.md) for installation pins
and checks. No additional user-facing precision option is introduced.

For developer diagnostics, `DEPTHSBS_BASE_STAGE_PROFILE=1` records CUDA stage
events in the device engine. `DEPTHSBS_BASE_GRAPH=1` selects an experimental
fixed-buffer TensorRT CUDA graph and requires GPU preprocessing. Both default to
off; neither adds a GUI control. Graph values other than `0` and `1` are rejected.
See [current status](../implementation-status.md) for their measured scope and
default decision. File conversion does not use these device-engine switches.
