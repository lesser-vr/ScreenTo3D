# Personal non-commercial oVDA experiment

This optional NC runtime directory is not bundled into portable distributions.
Current user path: `../../Run-oVDA.cmd` or `../../scripts/run-ovda.ps1` launches
the source GUI with oVDA and validated CUDA stereo selected. Three
518x686/518x896/518x924 FP32 profiles are installed locally, including 4:3 and
short 4K HEVC compatibility, with no 124-frame user-job limit. See
[ovda.md](../../docs/models/ovda.md) for usage and environment limits.
The older `run.ps1` in this directory remains a <=124-frame diagnostic tool.
oVDA-derived adapter/cache code here is governed by the accompanying
NC-SA-UHDV1.0 LICENSE, not the repository's general license. This does not
relicense unrelated DepthSBS files. It is source-available with non-commercial
restrictions, not unrestricted open source. No commercial clearance is implied.

Credit: Heidelberg University; Johann-Friedrich Feiden, Tim Kuechler, Denis
Zavadski, Bogdan Savchynskyy and Carsten Rother.
Source: https://github.com/FriedFeid/OnlineVideoDepthAnything
revision `4173c24e22f528062a0cf8ae235c58a5d4376a74`.
Weights: https://huggingface.co/FriedFeid/oVDA , revision
`9eda2255e19c51dd1989b9c08b886e665f15007e`, c16 SHA256
`ea531d53a1135a443bafcf106a175b26a6519c05ccc1e994d74e46159e14b7cb`.

Adapter changes: one-frame emission, strict pinned source/checkpoint checks,
CUDA-only FP32, explicit reset and bounded cache, owner/shape/finite validation,
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
The tested FP16 export also failed numerical parity. The application remains
c16 FP32; see [ovda.md](../../docs/evidence/ovda.md#record-result-ovda-expansion-results-2026-09-05).

Do not publish user footage, model weights or experiment derivatives without
reviewing the applicable media/model/code terms and retaining notices.
