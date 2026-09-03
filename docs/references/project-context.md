# Project context

Status: Source summary, not an implementation contract  
Captured: 2026-09-03

## Product discussion

The shared project discussion starts from the `nunif/iw3` workflow: use monocular
depth inference to convert 2D image/video into side-by-side 3D output. It favors a
separate NVIDIA-focused project over a language-only rewrite when the goal is
maximum throughput and quality.

The discussion proposes:

- C++20, CUDA, TensorRT, FFmpeg, NVDEC, and NVENC;
- a GPU-resident decode → preprocess → depth → stereo → encode path;
- DA2 Small/Base as stable performance baselines;
- oVDA Small as the Video Quality candidate because temporal consistency matters;
- VDA, DA3, or later models for Offline Quality;
- optional optical-flow or motion-compensated depth propagation so inference need
  not run on every output frame;
- a V1 performance phase followed by V2 stereo/temporal quality work;
- stage timings for decode, preprocess, depth, stereo, encode, GPU utilization,
  VRAM, and end-to-end fps on 1080p/4K at 30/60 fps.

Source: [shared ChatGPT discussion](https://chatgpt.com/share/6a991f33-b728-83e9-b2f0-bbe498efdb88)

## Harness-engineering guidance applied

The repository treats `AGENTS.md` as a short map, stores deeper knowledge in an
indexed `docs/` tree, versions active/completed plans and debt, makes observability
agent-readable, and aims to turn architectural preferences into tests and tooling
rather than relying on prose alone.

Source: [OpenAI, Harness engineering](https://openai.com/ko-KR/index/harness-engineering/)

## External technical references

- [NVIDIA Video Codec SDK documentation](https://docs.nvidia.com/video-technologies/video-codec-sdk/13.1/index.html)
- [Depth Anything V2 official repository](https://github.com/DepthAnything/Depth-Anything-V2)

External performance numbers are not copied into the support contract. The local
benchmark protocol is the authority for DepthSBS claims.
