# Personal non-commercial oVDA experiment

This optional NC runtime directory is not bundled into portable distributions.
Current user path: `../../scripts/run-ovda.ps1` launches
the source GUI with oVDA and validated CUDA stereo selected. The adopted
518x924 mixed-FP16 profile supports other ratios by aspect-fit, including 4:3 and
short 4K HEVC compatibility, with no 124-frame user-job limit. See
[ovda.md](../../docs/models/ovda.md) for usage and environment limits.
The older `run.ps1` in this directory remains a <=124-frame diagnostic tool.
oVDA-derived adapter/cache code here is governed by the accompanying
NC-SA-UHDV1.0 LICENSE, not the repository's general license. This does not
relicense unrelated ScreenTo3D files. It is source-available with non-commercial
restrictions, not unrestricted open source. No commercial clearance is implied.

Credit: Heidelberg University; Johann-Friedrich Feiden, Tim Kuechler, Denis
Zavadski, Bogdan Savchynskyy and Carsten Rother.
Source: https://github.com/FriedFeid/OnlineVideoDepthAnything
revision `4173c24e22f528062a0cf8ae235c58a5d4376a74`.
Weights: https://huggingface.co/FriedFeid/oVDA , revision
`9eda2255e19c51dd1989b9c08b886e665f15007e`, c16 SHA256
`ea531d53a1135a443bafcf106a175b26a6519c05ccc1e994d74e46159e14b7cb`.

Adapter changes: one-frame emission, strict pinned source/checkpoint checks,
CUDA-only with FP32 I/O/cache and mixed-FP16 encoder/spatial operations, explicit
reset and bounded cache, owner/shape/finite validation,
deterministic cleanup, no upstream full-video loader/output accumulation in app.
Upstream source stays unmodified. Local GUI access is explicit and license-aware;
no default/general-release acceptance is implied.

Dependencies are an additive isolated directory `out/ovda-python-deps`; existing
torch/TensorRT environment is not downgraded. Do not install upstream requirements
over the working environment. These extra packages and the source checkout are
now build/oracle-only: the user runtime uses the exact-validated local
`preprocessing.py` and does not import Git/source/checkpoints. Reproduce the
original oracle with:

```powershell
$env:PYTHONPATH='experiments/ovda;v1;out/ovda-python-deps;out/v1-python-deps'
out/vda-oracle-env/Scripts/python.exe experiments/ovda/validate_oracle.py --input '<short-video>'
```

c8 was separately checked against original batch inference and compared on three
clips, but is not adopted due to mixed/worse temporal-edge results. Its pinned
checkpoint SHA256 is
`af3788fbc6517704d3430ee1886f27e648b8d61e2da10b739b3bb59f4e8f585d`.
The earlier broad FP16 export failed strict numerical parity; see
[ovda.md](../../docs/evidence/ovda.md#record-result-ovda-expansion-results-2026-09-05).
The subsequently validated encoder/spatial mixed-FP16 recipe is now adopted;
see [normal-path verification](../../docs/evidence/ovda-fp16-adoption-20261109.md).

The 2026-11-09 source runtime adds aspect-fit and cropped depth restoration for
ultrawide, portrait and square input without changing source/SBS geometry.
The encoder-only trial stays isolated; the encoder/spatial mixed-FP16 trial is
now the application's 518x924 configuration. Current-device controls, precision differences,
actual native FPS/GPU results and artifact pins are recorded in the
[new experiment](../../docs/evidence/ovda-precision-aspect-20261109.md).

Do not publish user footage, model weights or experiment derivatives without
reviewing the applicable media/model/code terms and retaining notices.

The source live window GPU path uses `gpu_input.py` and `gpu_input.cu` for
same-stream FP32 preprocessing. Build its separately pinned local binary using
`../../scripts/build-ovda-input.ps1`. A device reduction preserves the upstream
all-0/1 normalization rule without reading the image back to CPU. Bicubic resize,
aspect-fit padding and model precision remain unchanged. This optional NC runtime
is not part of the general portable CUDA build or distribution.

The live device runtime also uses `device_buffers.py` and the pinned native
runtime for fixed input/output/schedule buffers, single-bank cache reuse and
one combined finite-output validation wait. Source-resolution depth allocation
and consumer-completion fences remain. Model precision and cache values are not
changed. The older two-bank `OvdaBufferedDeviceTrt` stays an explicit experiment;
it is not the selected application runtime.

The optional `postprocess.py`/`postprocess.cu` bridge separates the live pixel-depth
EMA from depth-range stabilization. Build it with
`../../scripts/build-ovda-postprocess.ps1`. The live model adapter owns the pixel
weight and causal range policy; file policy defaults remain unchanged. The bridge
borrows the validated LiveDepth layout and engine stream. Its 4 KiB raw-anchor
buffer is released after native completion. It stays outside portable distributions.
Response/stability comparisons are recorded in
[the pixel-EMA evidence](../../docs/evidence/ovda-pixel-ema-20261109.md) and
[the depth-range evidence](../../docs/evidence/ovda-depth-range-20261109.md).

The explicit `392x700` resolution trial and retained-resolution mixed-FP16
comparison use `evaluate_resolution.py` and `trial_runtime.py`, retaining the
current cache/range/pixel policies. Normal selection now uses the retained-resolution
518x924 mixed-FP16 candidate; low-resolution candidates stay experimental.
`../../scripts/run-ovda-resolution-trial.ps1` opens the isolated live comparison
GUI. Methods, pinned builds, measured tradeoffs and unpassed visual acceptance are
in [the resolution/FP16 evidence](../../docs/evidence/ovda-resolution-fp16-20261109.md).
