# VDA Small FP32 native SBS performance

2026-11-08. Windows build 26300, RTX 5090, driver 621.14, portable Python 3.13.9, Qt 6.10.2 and TensorRT 11.2.1.2. Video Quality used its locally built engines, mapped WGC capture, CUDA stereo, native texture output and default strength 0.5. VFG was off.

The input was an owned window drawing the pinned FloorballGame 1080p60 public preview, resized to each tested capture size. Its timer advanced the video about 62.5 times per second. The 4K result includes 4K capture, processing and 7680×2160 Full SBS generation from this scaled fixture. GPU load for game rendering or native 4K decoding was outside the experiment.

Each cap used five seconds of warmup after the first native outputs, then two adjacent eight-second windows in the same session. FPS counts distinct output-window submissions. GPU utilization is the arithmetic mean of 16 one-second NVML device samples and includes source playback, desktop and other GPU clients. Source-only used eight samples at each size with the controller open and SBS stopped. These are short runs on one PC.

| Captured pixels per eye | SBS FPS at cap 60 | GPU at cap 60 | SBS FPS unlimited | GPU unlimited | Source-only GPU |
|---|---:|---:|---:|---:|---:|
| 1920×1080 | 26.06 | 41.31% | 27.49 | 44.06% | 13.75% |
| 3440×1440 | 16.93 | 44.19% | 17.49 | 43.88% | 15.38% |
| 1080×1920 | 26.24 | 39.19% | 28.10 | 42.75% | 9.38% |
| 3840×2160 | 11.18 | 50.94% | 11.49 | 52.69% | 23.12% |

When capture outpaced processing, VDA's stateful binding reset history on skipped source sequence numbers. At 1080p unlimited, 432 gap resets accompanied 440 inferences across the two windows. At 4K unlimited, the counts were 184 and 184. Reset and inference counters are sampled independently and can differ by one at a window boundary. These rates largely characterize inference with frequent warmup. GPU utilization alone cannot identify the limiting stage.

In a second 1080p session the same fixture advanced at 14.87 FPS (67 ms input timer). At cap 60, 239 inferences produced 14.93 output FPS, with zero gap or cut resets across both measurement windows. GPU utilization averaged 23.25%, versus 3.75% for the slower source alone. This establishes continuous-history behavior at that input rate; the maximum continuous-history rate was not measured.
