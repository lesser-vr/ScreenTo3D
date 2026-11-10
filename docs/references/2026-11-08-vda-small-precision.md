# VDA Small streaming precision review

The desktop builds TensorRT 11.2.1.2 engines locally from four pinned FP32 ONNX graphs. The two canvas widths (896 and 924, height 518) each have a warmup graph and a cached graph. The cached call consumes 31 time steps in eight tensors. The live backend and installer validate FP32 image, depth and cache bindings. A separate graph pack and versioned numeric references can reuse the local build and device-specific receipt mechanism.

## Mixed FP16

The official streaming implementation runs feature extraction and temporal prediction under CUDA autocast. The depth head explicitly casts the input of its final output convolution to float32 with autocast disabled. A public FP16 ONNX conversion exists, but its 154×266 input and three-graph interface would change both resolution and runtime integration. [Upstream streaming source](https://github.com/DepthAnything/Video-Depth-Anything/blob/4f5ae23172ba60fd7bc11ef671cca678842c7072/video_depth_anything/video_depth_stream.py) · [Depth head](https://github.com/DepthAnything/Video-Depth-Anything/blob/4f5ae23172ba60fd7bc11ef671cca678842c7072/video_depth_anything/dpt_temporal.py) · [Community export](https://huggingface.co/EmreGneri/video-depth-anything-small-stream)

On an RTX 5090, two instances of the pinned upstream PyTorch model processed identical RGB frames with independent histories, alternating execution order. At each geometry, both models processed 50 FloorballGame frames, reset their histories, then processed 10 ParkingGarage frames. Both runs used the pinned Small checkpoint, PyTorch 2.7.1 CUDA 12.8, TF32 off. The reported median call time excludes the first five frames of each clip and includes input preparation and depth readback. All 120 paired depth maps were finite.

| Source | Median FP32 → autocast call | Worst frame mean absolute depth error | Worst frame mean absolute depth-change error |
|---|---:|---:|---:|
| 1056×608 | 33.99 → 27.60 ms | 0.01415% | 0.01371% |
| 1920×1080 | 40.22 → 33.91 ms | 0.01246% | 0.01035% |

Percentages use each FP32 frame's 2nd-to-98th percentile depth range. The temporal column compares signed consecutive-frame changes at matching pixels within a clip. These means can hide local edge differences. This is an upstream model comparison; the shipping engine, capture and SBS renderer did not participate. The experiment and raw output are in `out/vda-radius12-release-9b05e5fd/amp_probe.py` and `amp.json`.

For the first TensorRT candidate, keep input/output and cache bindings FP32 and encode mixed precision in the graph. Prioritize large encoder matrix multiplications and convolutions. Preserve the final output convolution, normalization and the existing stable temporal Softmax decomposition in FP32 initially. TensorRT 11 uses explicit tensor types. Validate each graph pair on independent histories beyond 42 entries with cuts, then check per-eye edges, temporal disparity error and native 1080p/4K FPS. The existing FP32 pack remains a reproducible control. [TensorRT 11 precision migration](https://docs.nvidia.com/deeplearning/tensorrt/latest/api/migration/tensorrt-10x-to-11x-trtexec.html)

## INT8

The official Small repository lists the original PyTorch checkpoint. No official calibrated, compatible INT8 streaming graphs were identified. The Small weights carry the Apache-2.0 license. [Official artifact list](https://huggingface.co/depth-anything/Video-Depth-Anything-Small/tree/main)

An initial INT8 experiment could quantize encoder linear layers offline with ModelOpt post-training quantization and ONNX QuantizeLinear/DequantizeLinear nodes. Preserve temporal attention, depth head and state in higher precision first. Use representative public footage from both profiles, including motion, flat areas, hard cuts and real cached inputs from continuous histories. Use separate clips for evaluation. Publish calibrated graphs only after comparing speed and quality against mixed FP16; GPU-local engine building can then remain the install procedure, with no end-user calibration. This review did not build an INT8 engine or measure TensorRT mixed-precision throughput. [NVIDIA ONNX PTQ guide](https://github.com/NVIDIA/Model-Optimizer/blob/main/examples/onnx_ptq/README.md)
