# Uncapped native throughput — 2026-11-05

Historical measurement record. App defaults remain unchanged; current measured
scope belongs to implementation-status.md.

## Method

RTX 5090, driver 621.14, Windows 11, Python 3.13.14, Qt 6.10.2,
TensorRT 11.2.1.2. Prepared local Small FP16 / Performance and Base mixed-FP16 /
Balanced use their existing GPU input and CUDA stereo policies. These are product
mode comparisons, not an isolated model-speed comparison. No FG or depth reuse.
The working tree is dirty at base commit 40735a663557b2e45b3db4e1fa8386aacf91f1a5;
environment JSON records implementation, native-library and source hashes.
Engine/model pins are unchanged from the Small GPU input and Base FP16 records.

The diagnostic removes the presentation deadline, polls at 1ms and requests Qt
vsync off via QSG_NO_VSYNC=1 and swap interval 0 before app creation. These are
documented [Qt controls](https://doc.qt.io/QT-6/qtquick-visualcanvas-scenegraph.html),
not a guarantee of physical display refresh. The live fixture's previous 16ms
timer is also removed: its isolated source process advances on a zero-interval
precise timer. That removes deliberate pacing, not CPU decode/paint limits.

Every completed configuration uses six seconds of discarded warmup then five
six-second windows. Counts are **distinct native Qt afterFrameEnd IDs**, not raw
callbacks, physical scanout or motion-to-photon. Source and GUI are visible.
Output is fitted to a 1400x650 logical window. Input/per-eye 1920x1080 yields
3840x1080 Full SBS; 3840x2160 yields 7680x2160 Full SBS. The public FloorballGame
fixture is the existing 1080p excerpt scaled to the requested input dimensions,
not a new native-4K source. Running its sequence faster than 60fps is a load test,
not interpolated video.

## Actual window capture

`out/uncapped-native-final-20261105/` completed all four configurations.

| Input / per eye | Mode / model | Output median | Five-window min–max | Source paint median |
|---|---|---:|---:|---:|
| 1920x1080 | Performance / Small FP16 | 140.96fps | 139.23–142.49fps | 140.90fps |
| 1920x1080 | Balanced / Base FP16 | 92.42fps | 91.48–92.98fps | 138.98fps |
| 3840x2160 | Performance / Small FP16 | 76.24fps | 75.21–77.25fps | 76.05fps |
| 3840x2160 | Balanced / Base FP16 | 54.13fps | 53.79–54.47fps | 76.62fps |

Small reaches the test window's supply rate at both geometries. Its result does
not establish the processing ceiling; the exact source decode/paint bottleneck
was not separately profiled. Base is below source supply. No claim attributes
the 4K source rate to the monitor's refresh rate. Capture sequence deltas are
forwarded/cached sequence proxies, not independent WGC callback telemetry.
All reports show fresh inference for every processed frame, no reused depth,
target 0 and poll 1ms. Every configuration's post-stop snapshot has zero native
pools/nodes. Readback clock probes and deliberate overload run outside timing.

```powershell
$env:PYTHONPATH='v1;out/gui-python-deps;out/capture-python-deps;out/v1-python-deps'
& out/vda-oracle-env/Scripts/python.exe v1/benchmark_live_modes.py --output out/uncapped-native-final-20261105 --sizes 1920x1080,3840x2160 --modes performance,balanced --hz 60 --uncapped --source-interval-ms 0 --path gpu-texture --source FloorballGame --source-process --seconds 6 --repeats 5 --sample-gpu
```

Output directories must be new when reproducing. `--uncapped` overrides the
`--hz` deadline; ordinary application settings are not saved or changed.

## GPU replay scope

The supplementary `--gpu-replay` diagnostic caches 60 hash-verified public frames
in GPU memory, clones one on the owned engine stream per request, and runs the
ordinary preprocessing, depth, stereo and native output path. Setup/decode/upload
are outside timing. The source window is paused and serves only as a geometry
placeholder. Replay excludes real WGC capture, source decoding and window painting;
its timestamps represent synthetic submission, not source capture latency.
The cache is bounded to about 1.99GB at 4K and released when the worker exits.
Output backpressure still uses the existing bounded texture pool.

Replay uses the first 60 frames cyclically and OpenCV linear scaling into BGRA;
live capture uses the painted sequence and its clock overlay. Cadence and
discontinuity behavior also differ. Thus replay diagnoses processing headroom;
subtracting its time from live time does not isolate capture cost or establish
an optimization speedup. Neither path demonstrates general game, sustained
4K60/120, 1:1 fullscreen, Owl3D or VR display acceptance.

`out/uncapped-gpu-replay-repeat-20261105/` completed all configurations and exited
with code 0 after the retained failed attempt below. Both full completed runs
started with sampled GPU utilization at 0%; their device-wide one-second GPU
logs are retained. They were sequential runs, not an interleaved capture A/B.

| Input / per eye | Mode / model | Output median | Five-window min–max |
|---|---|---:|---:|
| 1920x1080 | Performance / Small FP16 | 230.71fps | 229.67–231.25fps |
| 1920x1080 | Balanced / Base FP16 | 127.43fps | 125.08–127.65fps |
| 3840x2160 | Performance / Small FP16 | 127.27fps | 126.63–127.93fps |
| 3840x2160 | Balanced / Base FP16 | 77.43fps | 77.40–77.59fps |

```powershell
& out/vda-oracle-env/Scripts/python.exe v1/benchmark_live_modes.py --output out/uncapped-gpu-replay-repeat-20261105 --sizes 1920x1080,3840x2160 --modes performance,balanced --hz 60 --uncapped --gpu-replay --path gpu-texture --source FloorballGame --source-process --seconds 6 --repeats 5 --sample-gpu
```

Use the same PYTHONPATH as the live command. Replay reports include inference and
reuse rates and label synthetic input explicitly. Clock readback is skipped
because replay has no painted capture clock. Deliberate slow-consumer checking
verifies bounded output; pull replay does not have WGC input-drop counts.

`out/uncapped-summary-20261105.json` aggregates both completed runs. Its assertions
check 20 windows per run, no reused depth, inference count equal to completed SBS
or one ahead for the in-flight frame, target 0, poll 1ms and zero native pools/nodes
after each configuration. Stage counters are not an atomic multi-stage snapshot;
single-window rate differences of one frame are measurement-boundary effects.
Five source protocol tests, scoped Ruff E9/F and `git diff --check` pass.
The prior exact-pixel and lifecycle evidence is reused because ordinary model,
preprocessing and renderer implementation did not change for this diagnostic.
No package was rebuilt or app default changed.

## Retained attempts

- `out/uncapped-native-probe-20261105/`: exploratory 4K live run, one three-second
  window, Small 75.34fps / Base 54.80fps; superseded by the repeated live run.
- `out/uncapped-gpu-replay-probe-20261105/`: exploratory replay, one three-second
  4K window, Small 121.58fps / Base 75.73fps; completed with native cleanup.
- `out/uncapped-gpu-replay-final-20261105/`: incomplete first repeated replay
  attempt. 1080p completed; 4K Small windows ranged 99.89–120.64fps, and the
  following Base session was inactive after warmup. The harness raised
  `AttributeError: 'NoneType' object has no attribute 'pid'` before the Base
  measurement. That attempt lacks final environment/cleanup evidence and is
  not the final replay result. The session's underlying stop reason was not
  retained; the harness now checks activity immediately after warmup and records
  failure status/report rather than masking the original status with that error.
