# Benchmark methodology

Status: Proposed; becomes Accepted after the first reproducibility audit  
Owner: Performance and quality  
Last reviewed: 2026-09-03

## Purpose

Benchmarks decide whether a mode is supported and identify the limiting stage.
They do not exist to produce one favorable headline number.

## Required environment record

Every run writes machine-readable JSON or CSV with:

- git commit and dirty-worktree flag;
- build type and compiler version;
- OS, NVIDIA driver, CUDA, TensorRT, FFmpeg, and Video Codec SDK versions;
- GPU name, compute capability, VRAM, power mode, and relevant clock state;
- model name/version/checksum, engine build parameters, precision, and shapes;
- complete resolved processing plan;
- input fixture checksum and media metadata;
- warmup count, measured frame count, run number, and wall-clock start time.

## Corpus

Use checked-in manifests that point to legally redistributable or generated
fixtures. The minimum corpus includes:

- static locked shot;
- slow camera pan;
- fast camera motion;
- hard cuts and fades;
- thin structures and hair/foliage;
- foreground occlusion and disocclusion;
- dark, noisy, low-texture, and high-detail scenes;
- 1080p30, 1080p60, 4K30, and 4K60 encodes for H.264 and H.265 where supported.

Generated fixtures test geometry, PTS behavior, eye order, and cut resets. Real
content tests perceptual behavior but must not be committed without permission.

## Performance protocol

1. Reboot or document competing GPU workloads and thermal/power state.
2. Build a release configuration with instrumentation enabled.
3. Warm the engine and pools; report startup separately.
4. Run at least five measured repetitions after one discarded warmup run.
5. Process enough frames to reach steady-state clocks and expose queue behavior.
6. Record wall time, throughput, P50/P95/P99 frame latency, and each stage's GPU
   and CPU timing.
7. Record queue occupancy, copy bytes/count, synchronization count, VRAM fixed
   and peak usage, GPU utilization, encoder/decoder utilization, and power.
8. Report median plus range; retain raw data and trace for anomalous runs.

The stage budget is diagnostic. Support claims use sustained end-to-end throughput
and correct output duration. For 60 fps, 16.67 ms is the nominal frame interval,
not an automatic pass threshold for each isolated stage in an overlapped pipeline.

## Comparisons

When comparing with iw3 or another baseline, hold input, output resolution, frame
cadence, codec, quality/rate-control target, model family/size where possible, and
stereo parameters constant. If equivalence is impossible, list the differences
beside the result.

Never compare one tool's inference-only number to another tool's end-to-end fps.

## Quality protocol

Automated checks cover output decodability, duration/PTS, frame count, depth
polarity/range, eye order, borders/holes, cut reset, and deterministic output.

Candidate mode changes then run:

- temporal flicker and depth-change metrics outside motion/occlusion masks;
- edge/occlusion artifact measurements on synthetic geometry;
- side-by-side golden-image comparison with documented tolerances;
- blinded A/B review on the perceptual corpus.

No single metric is a complete 3D-comfort score. The review records depth pumping,
edge tearing, cardboard effect, excessive parallax, eye strain, and scene-cut
carryover separately.

## Support gates

A workload is marked supported only when:

- all repetitions produce valid media and preserve the declared A/V policy;
- no unbounded memory growth or queue growth occurs;
- P95 latency and sustained throughput meet that mode's declared threshold;
- quality checks pass for the selected mode;
- the exact hardware/software/model envelope is published with the result.

Until then, numbers are labeled exploratory.
