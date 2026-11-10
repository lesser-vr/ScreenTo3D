# Genuine public 4K120 input / native SBS comparison — 2026-11-06

## Source and provenance

Official [Ultra Video Group dataset](https://ultravideo.fi/dataset.html),
[sequence metadata](https://github.com/ultravideo/UVG-4K-Dataset):
Jockey (horse race/panning) and Beauty (face/hair), each captured at
3840x2160, 120 FPS, 600 frames / five seconds. Attribution: Ultra Video Group,
Tampere University; A. Mercat, M. Viitanen, J. Vanne, *UVG dataset: 50/120fps 4K
sequences for video codec analysis and development*, ACM MMSys 2020.
These clips use [CC BY-NC 3.0](https://creativecommons.org/licenses/by-nc/3.0/).
This is a local noncommercial experiment; the media are not app release assets.

Downloads:

- `https://ultravideo.fi/video/Jockey_3840x2160_120fps_420_8bit_HEVC_RAW.hevc`
- `https://ultravideo.fi/video/Beauty_3840x2160_120fps_420_8bit_HEVC_RAW.hevc`

The raw HEVC streams lack useful container timestamps; their default ffprobe
25 FPS value is not the official shooting rate. Preparation assigns the
documented 120 FPS, decodes with NVDEC and encodes with H.264 NVENC, p3/CQ18.
No resize, interpolation or frame duplication is used. Both resulting MP4s
probe as 3840x2160, 120/1, 600 frames, 5.000 seconds. Each has 600 different
decoded 64x36 grayscale frame hashes. This validates distinct content, not
lossless preservation of the HEVC source. `out/public-hfr/manifest.json` retains
source and prepared-file SHA-256 values and attribution.

Preparation command (replace `{clip}` with Jockey or Beauty):

```text
ffmpeg -hwaccel cuda -hwaccel_output_format cuda -r 120 -i out/public-hfr/{clip}.hevc -an -c:v h264_nvenc -preset p3 -cq 18 -fps_mode passthrough out/public-hfr/{clip}-120.mp4
```

## Playback and measurement contract

The initial FFplay 9.0.1 SDL/software and CUVID/D3D11 attempts delivered only
63.1–63.3 changing FPS. Hardware decoding did not remove that limit, so decode
load alone is not an established cause. FFplay's automatic Vulkan path lost
its owned window before capture; its root cause was not established.
These are player diagnostics, not model throughput results.

A portable mpv build linked from the [official installation page](https://mpv.io/installation/)
removed the observed input bottleneck. Build: `20261106-git-9028187538`, x86_64;
[release](https://github.com/shinchiro/mpv-winbuild-cmake/releases/tag/20261106).
The archive matches the GitHub release asset digest
`ed887972d3f575d46d48feb469b4f5ff9a65d142749ab8ebff13b64c7210eb64`;
the executable is pinned in `experiments/zipdepth/hfr_source.py`.
No installer or user-player configuration is modified.

Playback uses D3D11VA hardware decode, D3D11 output, VSync interval 0, no audio,
no interpolation, normal speed, repeated five-second clips, and `--no-config`.
Only the newly owned player's PID/HWND is captured. Primary monitor reports
239.991 Hz; display settings were not changed. Ten-second source-only checks:

| Clip | WGC captured FPS | Changing-content FPS | Distinct thumbnails across loops |
|---|---:|---:|---:|
| Jockey | 119.60 | 119.50 | 600 |
| Beauty | 119.29 | 119.19 | 600 |

Both capture buffers are exactly 3840x2160 BGRA, with strictly increasing WGC
timestamps. Evidence: `out/public-hfr/{clip}-source-preflight-mpv.json`.

The actual app path is GPU window capture → GPU preprocessing → model → shared
depth stabilization/detail stereo → native D3D11/Qt Full SBS. RTX 5090, existing
Small FP16 and exact-forward ZipDepth mixed-FP16 plans, Performance policy,
strength 0.25, detail enabled, VFG disabled, unlimited output. Input is native
4K; the output texture is 7680x2160, checked in both controller metadata and
the native pool. This is a windowed native-texture benchmark, not a physical
4K display scanout/photodiode measurement or Owl3D capture-compositor benchmark.

Each clip/model uses three consecutive ten-second samples after startup and
three seconds of warm-up, in separate app processes. Order: Jockey Small,
Jockey ZipDepth, Beauty ZipDepth, Beauty Small. Input rate is the WGC sequence
forwarded by the worker and cached by the GUI; output rate counts distinct
Qt `afterFrameEnd` frame IDs. Output IDs are matched to their capture timestamps
with 99.86–100% interval coverage (one frame differs at a timestamp/counter
sampling boundary in Beauty Small). Callback-to-output age is a same-clock software proxy;
WGC-source age is also saved but its cross-clock interpretation is unverified.
Neither age includes physical screen scanout. Loop boundaries remain in samples.

## Completed results

Each table entry is the median of three ten-second intervals. Parentheses show
the output FPS range across those intervals. All four sessions completed without
reported app errors; native pools/nodes were zero after each stop. Combined,
8,951 native frame-ID age samples were recorded. Python compilation passed.

| Clip / model | Input received FPS | Native output FPS (range) | Callback age P50 ms | Callback age P95 ms | Output interval P95 ms |
|---|---:|---:|---:|---:|---:|
| Jockey / Small | 119.79 | 73.10 (72.79–73.29) | 22.08 | 28.90 | 18.89 |
| Jockey / ZipDepth | 119.79 | 76.59 (75.69–77.10) | 21.26 | 27.79 | 17.91 |
| Beauty / Small | 119.59 | 71.29 (71.29–73.40) | 22.40 | 28.93 | 18.94 |
| Beauty / ZipDepth | 119.79 | 76.89 (76.70–76.99) | 21.39 | 27.93 | 17.97 |

ZipDepth gains **4.8% / 7.9%** over Small on Jockey / Beauty in this envelope.
The earlier approximately 62 FPS comparison was input-limited; here the capture
arrival rate remains near 120 while output is approximately 71–77 FPS. The full
pipeline, rather than the nominal source rate, now limits these measured runs.
This experiment does not isolate which remaining processing/delivery stage is
dominant, and isolated inference throughput is not an end-to-end speed claim.

The two five-second clips and 30-second samples per model/clip establish a bounded
local performance result, not universal maximum FPS or long-session support.
No new quality, temporal-wobble or physical Owl3D comfort acceptance follows.
No app default, model choice, VFG setting or production processing code changed.
All owned test players/apps were closed after measurement.

Raw results: `out/public-hfr/{Jockey,Beauty}-{small,zipdepth}-hfr-final.json`;
aggregate and validation: `out/public-hfr/summary.json`. Player and run logs are
adjacent. Reproduce with the prepared environment/PYTHONPATH in
`experiments/zipdepth/README.md`, then `latency.py --model small|zipdepth
--clip Jockey|Beauty --tag <fresh-tag>`; run GPU cases sequentially.

## Diagnostic failures retained

The first GUI harness run stalled before SBS startup and was stopped by
terminating only its owned processes. Synchronous cross-process window placement
was suspected; its blocked stack was not captured. The helper now uses
asynchronous, nonactivating window placement, which completed subsequent runs.
A v2 run stopped before playback because of a transcription error in the
player hash pin; correcting the pin matched the independently verified file.
A v3 run measured three intervals but failed a diagnostic geometry assertion
that mistook output metadata for input metadata (7680 versus 3840 width).
The corrected contract requires 7680x2160 output; the final comparison was rerun.
These attempts are retained under `out/public-hfr` and excluded from final results.

## Whole-GPU telemetry follow-up

Jockey was rerun with Small then ZipDepth, three ten-second intervals each,
using the same processing/source settings. `gpu_telemetry.py` reads nvidia-smi
every 200ms and selects samples using the benchmark's monotonic interval bounds
(149 Small samples, 150 ZipDepth samples). Hardware: RTX 5090, driver 621.14,
32607 MiB reported capacity, configured power limit 480W; no power/clock setting
was changed. These values cover the entire GPU, including player, desktop and
other applications, not DepthSBS alone. The five-second pre-run baseline was
2% GPU, 43.24W and 4122 MiB allocated VRAM.

| Metric | Small | ZipDepth |
|---|---:|---:|
| Mean GPU utilization | 82.97% | 82.21% |
| GPU utilization range | 80–85% | 73–84% |
| Mean power | 305.52W | 299.13W |
| Allocated whole-GPU VRAM | 6827 MiB (6.67 GiB) | 6971 MiB (6.81 GiB) |
| Mean memory activity | 22.26% | 24.61% |
| Mean decoder activity | 9.07% | 9.22% |
| Mean SM clock | 2955 MHz | 2957 MHz |
| Mean temperature | 57.93 C | 59.32 C |
| Median output FPS in this repeat | 76.19 | 79.79 |
| Median received FPS | 119.69 | 119.69 |

Both runs completed with zero pools/nodes after stop. The later run has higher
absolute FPS than the earlier comparison; its +4.7% relative ZipDepth gain is
similar to the earlier Jockey +4.8%. Do not merge these repeated measurements
as if simultaneous. No claim that the GPU monitor caused the rate difference
is supported. The GPU is substantially active in both configurations, and
ZipDepth does not reduce whole-pipeline GPU activity much here.

[NVIDIA defines GPU utilization](https://docs.nvidia.com/deploy/nvidia-smi/index.html)
as time with one or more kernels executing, not percentage of peak FLOPS or
Tensor Core occupancy. Memory utilization is time with device-memory activity,
not percentage of peak bandwidth. These counters cannot identify the bottleneck
or predict the FPS gain from reaching 100%. Power samples were below the
configured limit, but throttle-reason counters were not measured.

Evidence: `out/public-hfr/gpu-20261106.json` and the paired
`Jockey-{small,zipdepth}-gpu-20261106.json` files. Scripts compile successfully;
no production processing or app default was changed.
