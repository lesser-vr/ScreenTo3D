# oVDA FPS review — 2026-11-09

This review adds diagnostics only. Production oVDA remains FP32, with its
existing CPU preprocessing, capture, history and output policies.

## Findings and bounded measurements

`FramePreprocessor` converts the full RGB frame to CPU FP32, checks its maximum,
resizes with bicubic interpolation, pads to the installed canvas and normalizes.
`OvdaDeviceTrt` then uploads that tensor. Unlike Small, Base and VDA, the oVDA
adapter does not enable GPU capture. The implementation also allocates schedule
and output tensors per inference, synchronizes execution, checks finite outputs
and shifts history tensors when full. These observations identify candidates;
they do not establish each candidate's end-to-end cost.

`experiments/ovda/profile_preprocessing.py` used one pinned public FloorballGame
RGB frame, scaled to each size, with five warmups and twenty timed samples per
case. The diagnostic environment initially reported one Torch CPU thread. No
explicit Torch thread override was found in the live application or launch
scripts searched. The actual GUI worker's thread count was not instrumented.

| Preprocessing path | 1920x1080 median ms | 3840x2160 median ms |
|---|---:|---:|
| CPU, 1 thread | 17.76 | 45.09 |
| CPU, 2 threads | 9.31 | 30.73 |
| CPU, 4 threads | 5.04 | 29.04 |
| CPU, 8 threads | 4.89 | 26.68 |
| Naive Torch GPU prototype, including RGB upload and synchronization | 32.61 | 17.34 |

All CPU thread variants produced an exactly equal preprocessing tensor on this
frame. The GPU prototype differed by up to 6.28e-5 absolute tensor value. This
is not a depth/cache/SBS parity test. Fixed ordering, a single frame, pageable RGB
upload and short sampling limit generalization; the GPU prototype is not a
measurement of a fused GPU-capture path. Artifact:
`out/ovda-fps-review-20261109/preprocessing.json`.

## Recommended order

1. Compare four and eight CPU threads in the actual native SBS worker, retaining
   FP32. Record the worker's effective count, distinct output FPS, latency, CPU
   load and GPU utilization under matched playback. The isolated stage suggests
   a useful low-risk candidate, not an established FPS increase. Restore thread
   settings or scope the change to the worker to avoid affecting other tasks.
2. Extend the existing GPU-capture/input ownership framework to oVDA, with
   model-specific fused preprocessing. Avoid full-frame CPU FP32 conversion and
   the return upload. Preserve bicubic coordinates, arithmetic, aspect padding,
   restoration and oVDA's special normalization of all-0/1 uint8 inputs. Merely
   moving the present Torch operations to CUDA was slower at 1080p in this trial.
3. Measure and consolidate validation synchronizations and reuse small schedule
   and output buffers while preserving finite-output errors and ownership fences.
   Do not prioritize duplicating the large history banks: older separate-pipeline
   fixed-buffer experiments gained less than 1% while roughly doubling cache
   storage (`live-performance.md`, allocation experiments).
4. Revisit encoder + spatial FP16 after the input path is isolated. Previous
   actual native output improved 25.08->29.97 FPS at 1080p and 9.20->10.62 at
   scaled 4K, but strict depth/cache parity failed. This remains an intentional
   precision/quality change requiring its own acceptance, not a transparent
   optimization. See [precision evidence](ovda-precision-aspect-20261109.md).

Changing missed-frame history resets is a separate temporal-quality experiment.
At input rates exceeding inference, the current policy can reset often; relaxing
it changes the history's time spacing and needs cuts/gaps and motion validation.
Neither history shortening nor reset relaxation is counted as a free speedup.

No new end-to-end FPS, long-run stability or physical-display quality claim is
made by this preprocessing diagnostic.
