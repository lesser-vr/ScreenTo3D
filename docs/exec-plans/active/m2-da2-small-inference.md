# M2: Depth Anything V2 Small Inference Smoke

Status: TensorRT inference contract validated; official-reference accuracy is
still open.

## Scope

Run the locally built 518 x 518 TensorRT engine with a deterministic normalized
RGB input and reject malformed or numerically invalid depth output.

The input is an RGB gradient in `[0, 1]`, converted to NCHW FP32 using the
pinned processor mean `[0.485, 0.456, 0.406]` and standard deviation
`[0.229, 0.224, 0.225]`.

## Acceptance checks

- Tensor name is `predicted_depth`.
- Tensor shape is `[1, 518, 518]`.
- Element count is 268,324.
- Every value is finite and non-negative.
- Standard deviation is greater than `1e-6` to reject constant output.

This smoke test establishes execution and tensor integrity. It does not prove
depth accuracy or equivalence with the official checkpoint.

## Reproduction

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/da2-small-inference-smoke.ps1
```

## Next gate

Export or execute the official checkpoint, run identical image preprocessing,
and define numerical acceptance metrics for the TensorRT result. The FP16
LayerNorm warning from the engine build makes this comparison release-critical.
