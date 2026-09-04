# V1.1 lifecycle and extended-run validation

Status: Lifecycle slice and five-minute smoke verified; longer soak gates remain

Plan: record non-overlapping lifecycle intervals, add a reproducible packaged
worker memory sampler, run unit/regression tests, rebuild, then convert a
five-minute 720p synthetic input (9000 frames, beyond the timing sample cap).

Lifecycle checkpoints cover engine initialization, process/synthesizer setup,
frame loop, decoder drain, encoder drain, resource snapshot, explicit backend
close, mux, and publish. Probe is separate and excluded from the existing
processing_fps denominator for backward comparability. Job elapsed includes
probe/setup but excludes completion callback/final cleanup and process launch.

The extended-run harness samples worker private bytes and working set once per
second into CSV with constant-space accumulation. First post-10-second private
bytes versus final and maximum are observations, not a leak pass threshold.
FFmpeg child-process memory and per-process GPU memory remain unmeasured.
Timeout terminates only the launched worker tree and reports failure.

Acceptance: successful exit, completion event, exact output dimensions/frame
count/audio presence, required lifecycle stages, timing sample cap respected,
and nonempty memory observations. Five minutes is an initial extended-run smoke
test, not proof of hour-long stability or absence of memory leaks.

## Reproduction

Generate an exact-CFR extended fixture (do not stream-copy loop A/V clips,
because container/audio padding can introduce timestamp gaps):

```powershell
ffmpeg -n -v error -f lavfi -i testsrc2=size=1280x720:rate=30 -f lavfi -i sine=frequency=440:sample_rate=48000 -t 300 -c:v h264_nvenc -preset p1 -b:v 2M -pix_fmt yuv420p -c:a aac out/media-smoke/soak-cfr-720p30-300s.mp4
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/soak-v1.ps1 -SourcePath out/media-smoke/soak-cfr-720p30-300s.mp4
```

Artifacts are isolated per run under `out/soak/<random-id>/`: output video,
worker memory CSV, event JSONL and a final result with input hash, media probes,
source revision and package manifest. Failed/timeout runs retain diagnostic
artifacts; no success result is produced. Retention is manual.

## Results (2026-09-04)

- Python tests: 15 passed (including fake-backend full conversion lifecycle);
  C++ regression tests and git diff --check passed. Portable package rebuilt.
- Initial stream-copy-loop fixture contained 8908 input frames due to timestamp
  gaps; that exploratory run was stopped and is not accepted evidence.
- Exact-CFR testsrc2 input: 1280x720, 30 fps, 300 seconds, 9000 frames, AAC.
  Output: 2560x720, 9000 frames, video and audio each 300.000 seconds.
- One Performance run: 243.436 seconds, 36.97 fps including engine startup,
  draining and mux. This is synthetic single-run evidence, not a performance
  baseline or a guarantee for arbitrary content.
- Lifecycle: startup 0.301 s; setup 0.008 s; frame loop 237.299 s;
  encode drain 0.065 s; audio mux 5.761 s. Other checkpoints under 1 ms.
- Frame statistics retained 2048 of 9000 observations as designed.
- Worker private-memory CSV: 242 samples. Early mean (10-40 s) 1009.23 MiB;
  late mean (190-220 s) 1011.45 MiB, a 2.23 MiB increase. Last sample minus
  first post-10-second sample: -11083776 bytes. Sampled maximum 1265180672
  bytes includes startup/transients. These observations do not prove leak freedom.
- Device-wide VRAM: 232 observations, zero probe errors; first/last/sampled max
  all 1920401408 bytes. This excludes unsampled peaks and is not process VRAM.
- Accepted artifact: `out/soak/b288101181a54858bc1d26764e52fae3/result.json`.
- Short-run harness regression also passed; post-10-second memory baseline and
  delta correctly remain null when the process ends earlier.

## Next gates

Repeated open/cancel/failure resource cleanup, hour-long representative inputs,
FFmpeg child memory tracking, and GPU traces remain unverified. Keep V1.1 active.
