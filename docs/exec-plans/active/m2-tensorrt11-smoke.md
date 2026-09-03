# M2 TensorRT 11 engine smoke

Status: Completed vertical slice on 2026-09-03

## Result

The standalone TensorRT 11 C++ smoke path successfully:

- generated a trusted ONNX 1.20 fixture with FP16 input/output tensors;
- configured and built against TensorRT 11.2.1 and CUDA 13.1;
- parsed the ONNX model through `nvonnxparser_11`;
- built a serialized engine on an RTX 5090;
- deserialized the in-memory engine immediately for validation;
- verified two FP16 I/O tensors;
- wrote a temporary plan and atomically published the final file.

Measured local result:

```text
engine size: 12,084 bytes
build + validation: 3,471 ms
I/O tensors: 2
FP16 I/O: true
deserialization validated: true
atomic publication: true
```

Canonical command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\tensorrt11-engine-smoke.ps1
```

Python package `onnx==1.20.0` is installed only under the ignored
`out/python-deps` development directory to generate the fixture. It is not a
runtime or end-user dependency.

## TensorRT 11 findings

- TensorRT public headers require the CUDA Toolkit include directory.
- MSVC builds on a Korean Windows code page require `/utf-8` so warnings in
  NVIDIA headers do not fail a `/WX` build.
- The historical `BuilderFlag::kFP16` is not available in TensorRT 11.2.1.
  Precision must be represented by the network/tensor precision policy; this
  smoke uses FP16 ONNX I/O explicitly.

## Next step

Replace the identity fixture with a pinned DA2 Small ONNX export, then add tensor
contract validation, SHA-256 cache identity, smoke inference against a known
input/output, and concurrent cache publication tests.
