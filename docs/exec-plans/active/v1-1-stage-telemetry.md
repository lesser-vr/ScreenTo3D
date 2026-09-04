# V1.1 stage timing slice

Status: Stage timing slice verified; broader V1.1 remains active

Plan: add bounded statistics, instrument the worker, preserve telemetry in
benchmark JSON, then run deterministic tests and the existing V1 suite.

Each stage retains its latest 2048 samples. Count, mean and maximum cover the
whole conversion; percentiles describe only that trailing window. All times
are wall-clock milliseconds. Decode-read and encode-write include pipe waiting,
not isolated codec timings. Depth includes transfers and synchronization.
Temporal and stereo currently share one method and are measured together.
Frame total excludes startup, encoder drain and audio mux; existing end-to-end
elapsed time remains the throughput denominator. This does not establish
zero-copy or a product frame-rate target.

Resource counters and sampled device-memory observations are now implemented;
see `v1-1-resource-telemetry.md`. Startup/drain/mux breakdown and an initial
five-minute run are verified in `v1-1-lifecycle-soak.md`. Internal queue
profiling, repeated cleanup and longer resource validation remain open.

## Verification (2026-09-04)

- Python unit tests: 6 passed; C++ regression suite: passed.
- Portable package rebuilt with telemetry.
- Performance mode, 720p/60 frames: one warmup and five measured runs passed
  existing output geometry/frame/audio gates. Every run reported 60 frame
  samples and 30 inference samples, consistent with cadence two.
- End-to-end median 33.816 fps, range 33.009-33.953 fps. This short fixture
  validates instrumentation, not sustained product performance.
- Raw evidence: `out/benchmarks/v1-performance-20260904T011708Z.json`
  (local artifact, excluded from Git).
