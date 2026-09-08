# Public depth integration references


Reviewed 2026-09-04. Search findings are not an exhaustive inventory or a claim
that another project's performance transfers to DepthSBS.

| Project | Verified scope | Use in DepthSBS |
|---|---|---|
| [MapMindAI/DepthAnythingOnnx](https://github.com/MapMindAI/DepthAnythingOnnx) | Offline VDA ONNX exporter with explicit standard attention path; MIT | Test source-level MatMul attention export, not a ready streaming backend |
| [nagadomi/nunif (iw3)](https://github.com/nagadomi/nunif) | 2D-to-3D integration with separate VDA online-window and streaming wrappers; MIT | Model boundary, frame accounting, reset and normalization design reference |
| [Video-Depth-Anything_iw3](https://github.com/nagadomi/Video-Depth-Anything_iw3) | Tensor-native PyTorch streaming model; Apache-2.0 | Verify first-two/last-29 history and explicit state reset; not TensorRT evidence |
| [spacewalk01/depth-anything-tensorrt](https://github.com/spacewalk01/depth-anything-tensorrt) | README describes DA1/DA2 C++/Python TensorRT, MIT | Existing framewise backend reference, not temporal VDA |
| [ComfyUI Depth Anything TensorRT](https://github.com/yuvraj108c/ComfyUI-Depth-Anything-Tensorrt) | README describes DA1/DA2/DA3/DAD and temporal smoothing | Do not confuse smoothing framewise depth with VDA cache inference; no code copied |
| [ruffy369 VDA TensorRT artifact](https://huggingface.co/ruffy369/Video-Depth-Anything-Tensorrt) | Model card lists TensorRT 10.8 serialized engine, not reproducible streaming source | Not downloaded or executed; not a Windows/TRT11/RTX5090 compatibility guarantee |

## Pinned source review

- MapMindAI commit `693f8eda3caaf0c453bc96a3e4ef7a5e653f5d19`:
  `videodepthanything/convert_vda_to_onnx.py`, `test_vda_onnx.py`, LICENSE.
  Export wrapper returns only depth for a video window. No cache I/O contract.
  The 4D fallback uses ordinary MatMul/Softmax; its mask-ignoring branch and
  automatic CPU selection are not adopted. The export-only DepthSBS experiment
  independently implements standard attention with mask and upcast handling.
- nunif commit `d23721f1b5f0a4c92c3ee1be013180bf298730c5`:
  `iw3/video_depth_anything_model.py`, `iw3/video_depth_anything_streaming_model.py`.
  Online-window mode has delayed outputs/flush and resets normalization state;
  streaming emits per frame. These are distinct scheduling contracts.
  Its postprocessing `nan_to_num` is deliberately not adopted: we reject
  nonfinite model outputs. Hub downloads/trust_repo execution are not used.
- VDA iw3 commit `1758a70d841cef480bf1532e5707f0dab2e1401b`:
  `video_depth_anything/video_depth_stream_torch.py`,
  `video_depth_anything/motion_module/attention.py`, LICENSE.
  Cache initialization, gap=41 and selection match the current official-source
  adapter. The optional temporal SDPA path is disabled by default in the checked
  code; do not present it as a proven fix for TensorRT NaNs.

No external project source was vendored into the product, and no new third-party
model or serialized engine was executed. Reference clones are under ignored
`out/reference-*` for audit. If code is subsequently copied, preserve applicable
license/copyright notices and perform a component-level dependency review.

## Decision

Use public implementations as the first reference for subsequent backend work.
Retain our verified cache/ownership/reset boundary. Evaluate plain-matmul export
against the existing stable-Softmax rewrite using identical FP32 inputs and
unchanged 1e-3 parity gates. See [vda.md](../evidence/vda.md#record-plan-vda-public-reference).
No ready-made implementation matching our exact streaming cache and TensorRT 11
acceptance requirements was confirmed in this review.
