# VDA live FPS optimization review

RTX 5090, Windows, driver 621.14, TensorRT 11.2.1.2. The local portable build used Video Quality, the existing FP32 engines, native SBS, default strength 0.5, unlimited output and VFG off. The owned FloorballGame 1080p60 preview window was painted at each test size and advanced at 62.4–62.5 FPS. The 4K test scales this fixture. The [previous measurement](vda-native-fps-gpu-20261108.md) describes the source and output counters.

The diagnostic worker replaced only VDA RGB preprocessing, in memory. A float32 table maps each possible byte to the reference division by 255. OpenCV resizes with the existing cubic kernel and replicates the same borders. Splitting channels lets NumPy perform the original float64 normalization directly into contiguous float32 CHW output. The production package and engines were untouched.

| Capture and path | Native output FPS | Whole-GPU mean | CPU preprocess ms | Depth stage ms (includes preprocess) | Stereo stage ms |
|---|---:|---:|---:|---:|---:|
| 1080p original | 27.74 | 37.31% | 17.44 | 31.68 | 2.13 |
| 1080p candidate | 37.43 | 56.19% | 7.99 | 23.20 | 2.11 |
| 4K original | 11.55 | 53.19% | 47.46 | 68.07 | 12.58 |
| 4K candidate | 18.11 | 57.50% | 16.24 | 40.42 | 12.11 |

Each cell used the same five-second warmup and two adjacent eight-second windows within one session. Order was original/candidate at 1080p and candidate/original at 4K. Output counts distinct native output submissions; GPU load includes playback and the desktop (16 NVML samples per cell). CPU preprocessing and depth stage timings are per-frame wall-clock medians. Stereo timing is the median of periodic observations of the worker's most recent completed stage. The three times are not additive.

Preprocessing matched the reference element-for-element on random, noncontiguous mirrored and constant RGB inputs at five geometries (1056×608, 1080p, 4K, 3440×1440 and portrait 1080×1920). It also matched on 15 public frames at each of three crops. End-to-end runs measure throughput; exact preprocessor parity does not imply byte-identical unpaired live SBS frames when the faster path receives a different sequence.

At 1080p, 211/599 observed candidate inferences used temporal cache versus 5/443 originally. At 4K, only 1/290 candidate inferences used it. A separate controlled replay of the same 30 1080p frames, outside capture/stereo, measured the backend call including binding, execution and output checks. With history reset each frame the two run medians were 11.04 and 11.05 ms; with continuous history they were 13.63 and 13.27 ms (first five frames discarded each run). Suppressing resets alone is not supported as a throughput optimization. The effect on temporal quality across missing inputs requires its own comparison.

The first implementation candidate is the parity-tested CPU change. Next, test the existing D3D11/CUDA capture bridge with VDA-specific preprocessing (including float32 source scaling and aspect-fit), owned input lifetime and matching output depth. If 4K remains the focus, measure the sub-stages of the 12-pixel guidance and stereo projection before specializing either kernel. Potential gains from GPU input, FP16 engines and cached-state buffer reuse have not been measured here.
