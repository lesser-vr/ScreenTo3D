# M2: Depth Anything V2 Small Engine Vertical

Status: engine build validated; inference correctness remains open.

## Outcome

Build a TensorRT 11 engine from a pinned Depth Anything V2 Small FP16 ONNX on
the user's GPU. The model and generated engine remain local cache artifacts and
are not committed.

## Pinned artifact

- Upstream: `depth-anything/Depth-Anything-V2-Small`
- ONNX source: `onnx-community/depth-anything-v2-small`
- Revision: `4472b7362082ad9968fee890ca0f1e5aca36b93d`
- File: `onnx/model_fp16.onnx`
- SHA-256: `2df6223f206b5164e21f664ace61dabeb9bb6a49b8b5a3e00510b4807d0f5b04`
- License: Apache-2.0

The community ONNX is an integration artifact, not the final provenance
boundary. Before release, compare its output against the official checkpoint or
replace it with an internally exported and validated ONNX.

## Tensor contract

- Input: `pixel_values`, FP32, `[1, 3, 518, 518]`
- Output: `predicted_depth`, FP32, `[1, 518, 518]`
- ONNX opset: 14
- The file contains FP16 weights but exposes FP32 I/O.

## Validated result

On TensorRT 11.2.1 and an RTX 5090 (SM 12.0), the model parsed and generated a
strongly typed engine successfully. The observed engine size was about 51.1 MiB
and engine generation took about 19.8 seconds.

TensorRT warned that FP16 LayerNorm reductions after self-attention may
overflow. Release acceptance therefore requires numerical comparison with the
official model on a representative image corpus. An opset 17 export using a
normalization operator is a candidate mitigation if the comparison fails.

## Reproduction

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/da2-small-engine-smoke.ps1
```

The script verifies byte length and SHA-256 before building. It does not claim
inference correctness; `inference_validated` remains false until the numerical
oracle is implemented.

## Next acceptance gates

1. Add deterministic image preprocessing matching the official processor.
2. Run one TensorRT inference and validate tensor shape and finite values.
3. Compare depth maps with the official checkpoint using documented metrics.
4. Record mode-specific resolutions and engine cache keys.
