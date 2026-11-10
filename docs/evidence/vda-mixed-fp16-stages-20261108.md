# VDA Small mixed-FP16 stage timing

Windows, RTX 5090, installed v2 pack, 518×924 warmup/cached pair. The local portable captured the public FloorballGame 1080p preview scaled to 1920×1080 or 3840×2160 per eye. Video Quality, strength 0.5, native Full SBS, 60 FPS pacing, VFG off. Rates are distinct native submissions. Physical display latency was not measured.

## Native throughput and stage timings

Four sessions ran in 1080p / 4K / 4K / 1080p order. After five seconds of warmup, each session collected three adjacent four-second windows with the normal worker. The source advanced at about 62.5 FPS. Stage values are medians of 240 latest-stat snapshots per resolution; FPS is the median of six windows. Stage medians are not additive.

| Stage | 1080p | 4K |
|---|---:|---:|
| Native FPS (min–max) | 56.22 (55.93–56.24) | 46.41 (46.15–46.74) |
| Native interval from FPS | 17.79 ms | 21.55 ms |
| Capture acquire/copy (wall) | 0.618 ms | 0.676 ms |
| Depth path (wall, both branches) | 13.14 ms | 15.17 ms |
| Stereo including slot acquisition and shared texture publication (wall) | 1.024 ms | 2.604 ms |
| Worker capture through mailbox publication (wall) | 15.45 ms | 19.09 ms |
| Whole-device GPU utilization (mean) | 72.3% | 76.9% |

The worker counted 149 gap resets over 1,350 inferences at 1080p and 385 over 1,114 at 4K, with zero scene-cut resets in the measured windows. A shorter second pass in reverse resolution order sampled CUDA events in one of every five inference calls and separated warmup from cached calls. Both the reference and sampled passes used the installed engines. Median marked-pass native FPS was approximately 56.2 / 46.5.

| Live stream interval, cached frames | 1080p (122 samples) | 4K (74 samples) |
|---|---:|---:|
| RGB to normalized model canvas | 0.083 ms | 0.083 ms |
| Assemble history inputs | 0.294 ms | 0.280 ms |
| TensorRT execution | 11.738 ms | 13.594 ms |
| Validate depth and eight cache outputs | 0.658 ms | 0.724 ms |
| Resize depth to source size | 0.049 ms | 0.176 ms |
| Validate resized output | 0.071 ms | 0.093 ms |

On warmup/reset frames, TensorRT took 8.85 ms at 1080p (13 samples) and 11.71 ms at 4K (38). Event intervals can include stream scheduling or host enqueue gaps, especially for validation that synchronizes with the host.

## Controlled replay and layer attribution

The same first 66 decoded frames were replayed at each size twice, with no capture or presentation, maintaining continuous VDA history. The first 12 frames were excluded each time. The native texture consumer read back and released its slot outside the timed region. There were 108 measured frames per size. Median cached TensorRT time was 10.619 / 10.616 ms at 1080p / 4K. BGRA-to-RGB took 0.122 / 0.158 ms, model preprocessing 0.081 / 0.081 ms, depth resize 0.050 / 0.184 ms, and stereo 0.965 / 2.450 ms. Within stereo, the radius-12 guide took 0.196 / 0.777 ms. This distinguishes a source-resolution cost in stereo from the longer elapsed model time observed under live 4K load. The measurements do not identify a specific competing GPU queue or clock change.

In separate runs, TensorRT's layer profiler recorded 24 real input frames after 44 startup frames per branch. The cached run retained real history. The warmup run reset before each input. Values below sum mean layer times; a subset row is included in its parent.

| Profiled component | Warmup | Cached |
|---|---:|---:|
| Sum of all reported layers | 8.87 ms | 10.85 ms |
| Encoder spatial attention score product, Softmax and value product (12 blocks) | 5.22 ms | 5.20 ms |
| ↳ Softmax-family fused kernels | 2.20 ms | 2.21 ms |
| Layers explicitly named for temporal motion modules | 0.77 ms | 1.83 ms |
| ↳ Eight fused key/value projections | 0.11 ms | 1.38 ms |

Each encoder group is a named score MatMul, a fused max/subtract/exp/reduce/divide/multiply kernel and the following value MatMul, verified in order for all twelve blocks. Temporal totals include only explicitly labelled layers; anonymous helper kernels are unassigned.

The first model experiment suggested by this breakdown is selective acceleration of encoder spatial attention. Compare score/value products in mixed precision with stable Softmax and FP32 accumulation against the current engines. Preserve both profiles, independent history, cut handling and final SBS comparisons. The measured 5.20 ms is the current cost of this region, not a predicted saving. For 4K-specific work, the complete stereo stage shows a larger resolution penalty than VDA preprocessing and depth resize.

Local raw data and runners: `out/vda-stage-1a9fcd2f/`, including `native.json`, `marked.json`, per-worker samples, `replay.json`, and the warmup/cached layer profiles.
