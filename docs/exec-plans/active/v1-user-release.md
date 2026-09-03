# V1 User Release

Status: active

## Goal

Deliver a Windows release candidate that a user can launch, select a video and
one of four modes, and convert it to a full side-by-side H.264 MP4 while
retaining audio.

## Release scope

- Native TensorRT 11 inference through the bundled Python binding.
- DA2 Small FP16 ONNX bundled as the validated V1 depth backend.
- Per-GPU engine creation on first use and reuse from LocalAppData.
- FFmpeg decode/probe/mux and NVENC H.264 encode.
- Deterministic CPU stereo reference synthesis with bounded one-frame memory.
- CLI worker with JSON progress and a Tkinter Windows GUI.
- Performance, Balanced, Video Quality, and Offline Quality policies.
- Cancellation, temporary output cleanup, and atomic final publication.
- Portable Windows directory containing executable, model, FFmpeg, and required
  TensorRT runtime/builder DLLs.

## Mode policy for the first user release

All four modes use the licensed and validated DA2 Small backend. This is an
intentional V1 stabilization decision; unresolved DA2 Base, oVDA, and DA3 model
assignments remain future work and are not silently advertised as supported.

| Mode | Depth cadence | Temporal smoothing | Stereo strength | NVENC preset |
|---|---:|---:|---:|---|
| Performance | every 2 frames | light | low | p3 |
| Balanced | every frame | medium | medium | p4 |
| Video Quality | every frame | strong | medium | p6 |
| Offline Quality | every frame | strong | high | p7 |

## Data path

```text
FFprobe -> FFmpeg RGB decode -> resize/normalize -> TensorRT DA2 Small
        -> depth normalization/EMA -> symmetric stereo remap
        -> FFmpeg NVENC video -> FFmpeg audio mux -> atomic MP4 publish
```

The first release is a correctness-oriented CPU/GPU hybrid. Decode, stereo
synthesis, and raw-frame transfer include host copies and must not be described
as zero-copy.

## Acceptance gates

1. A short H.264 + AAC fixture converts through the packaged worker.
2. Output is double-width SBS, preserves frame cadence, contains audio, and has
   a duration within one frame of the source.
3. Each mode completes and records its resolved policy.
4. Cancellation removes partial output.
5. GUI launches, validates input/output, reports progress, and surfaces errors.
6. Portable package runs without project Python, CUDA Toolkit, or TensorRT SDK
   on the development machine after isolation of PATH to packaged dependencies
   plus the NVIDIA driver.
7. Unit/reference tests and the numerical depth oracle remain green.

## Known V1 limitations

- NVIDIA GPU and compatible driver are required.
- Output is H.264 full SBS MP4.
- Rotation/color HDR metadata handling is not release-complete.
- Stereo synthesis is the deterministic CPU reference path, not zero-copy CUDA.
- Model quality is DA2 Small for every mode; modes tune the end-to-end policy.
