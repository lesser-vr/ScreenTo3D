# Torch-free Small GPU-memory experiment

This source-only prototype replaces Torch allocations/stream wrappers around the
existing Small live kernels. Production model selection and distribution do not
use it. It requires the prepared checkout's pinned CUDA, capture, preprocessing,
postprocessing and TensorRT artifacts plus a supported NVIDIA GPU.

`native_buffers.py` owns CUDA allocations on the engine thread/device, validates
generation/lifetime before borrowing pointers and releases rendering/capture
resources before the engine stream. `convert.cu` only converts captured BGRA to
RGB; all depth and stereo algorithms remain the production algorithms.

Build from the repository root with the prepared MSVC/CUDA toolchain:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File experiments/native_gpu_runtime/build.ps1
$env:PYTHONPATH='out/sbs-quality-python-deps;out/spring-python-deps;experiments/ovda;v1;out/gui-python-deps;out/capture-python-deps;out/ovda-python-deps;out/v1-python-deps'
out/vda-oracle-env/Scripts/python.exe experiments/native_gpu_runtime/probe.py --output out/native-gpu-runtime-proof-new
out/vda-oracle-env/Scripts/python.exe experiments/native_gpu_runtime/probe.py --output out/native-gpu-runtime-proof-new --baseline
```

The native probe forbids importing Torch and captures only its own generated WGC
window. It writes diagnostic RGB/output readbacks; the baseline uses those exact
inputs with the existing Torch-backed Small path. The comparison requires every
output RGBA byte to match, including temporal state, default strength 0.5, detail
postprocessing, odd-size Half TB packing and a fixed 60 Hz fixture clock.

The reviewed `native_rgb.dll` SHA-256 is
`ee96ffe58d518f4af56f6c9c9392dffdd50a4fd90701be1bc8d4c94221b49935`.
Rebuilding can change the binary identity; a new hash must be reviewed and the
probe rerun before changing its pin. An arbitrary local DLL is never accepted.

On RTX 5090, the 16-frame native probe imported no Torch, rejected access to a
closed buffer and published Half TB to the existing native texture pool. The
paired baseline had maximum pixel difference zero on every frame. Reports are
`out/native-gpu-runtime-proof/{native,parity}.json`.

This does not establish sustained FPS, physical/Qt presentation, static-frame
reuse or Base/VDA/VFG parity. Diagnostic readbacks are intentionally included.
Torch cannot be removed from the normal portable package based on this proof.
