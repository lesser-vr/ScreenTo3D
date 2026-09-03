# M2: DA2 Small FP32 Reference Oracle

Status: development oracle validated; official checkpoint validation remains
open.

## Purpose

Quantify the numerical effect of the TensorRT FP16 model and its LayerNorm
warning by comparing its output with the pinned FP32 ONNX using ONNX Runtime on
CPU.

Both paths receive the exact same normalized FP32 tensor. The reference model,
runtime, and generated artifacts are development-only and are not application
dependencies.

## Acceptance budget

- MAE <= 0.01
- RMSE <= 0.015
- maximum absolute error <= 0.05
- mean relative error <= 1 percent
- Pearson correlation >= 0.999

## Validated observation

On the deterministic RGB gradient fixture:

- MAE: 0.00350
- RMSE: 0.00457
- maximum absolute error: 0.01802
- mean relative error: 0.200 percent
- correlation: 0.9999867

These results clear the current error budget. They cover one synthetic input,
so a real-image corpus and direct official-checkpoint comparison are still
required before release.

## Reproduction

Install the local development dependency once:

```powershell
python -m pip install --target out\python-deps -r tools\requirements-reference.txt
```

Then run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/da2-small-reference-check.ps1
```
