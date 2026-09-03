# Processing modes

Status: Proposed, with performance targets treated as hypotheses  
Owner: Product and pipeline  
Last reviewed: 2026-09-03

## Product promise

DepthSBS gives users one clear choice about the tradeoff they care about. A mode
is an end-to-end contract, not merely a model picker.

| Mode | Primary promise | Initial depth backend | Temporal policy | Frame-rate intent |
|---|---|---|---|---|
| Performance | Lowest latency and highest throughput | DA2 Small TensorRT FP16 | Full-rate first; propagation may be added only if it improves measured throughput without visible instability | 1080p/4K, 60–120 fps exploration |
| Balanced | Practical default with stronger spatial depth | DA2 Base TensorRT FP16 | Full-rate baseline; adaptive 1:2 inference is an experiment | End-to-end 60 fps target where hardware allows |
| Video Quality | Stable depth over time with low flicker | oVDA Small TensorRT candidate | Stateful online temporal inference; cut-aware cache reset | 60 fps goal, 30–60 fps acceptable test range |
| Offline Quality | Best available SBS quality without realtime guarantee | VDA, DA3 Mono, or later validated backend | Model-native temporal processing or high-quality inference plus propagation | No realtime guarantee; quality first |

These model assignments come from the project discussion and are starting
hypotheses. Backend availability, conversion correctness, licenses, and complete
pipeline measurements must be verified before a mode is called supported.

## Shared behavior

All modes:

- accept a validated H.264 or H.265 input in the V1 compatibility envelope;
- emit an SBS H.264 or H.265 video with monotonic timestamps;
- preserve source cadence unless an explicit future frame-drop policy applies;
- report the resolved backend, engine precision, inference size, temporal
  cadence, stereo configuration, encoder settings, and any approved fallback;
- expose divergence, convergence, and depth-scale controls through validated
  ranges once the V2 quality milestone begins;
- reset temporal state at detected scene cuts;
- fail before processing if required capabilities are unavailable and no
  explicit fallback was approved.

## Resolution and fallback

The application probes GPU, driver, codec, memory, engine, and model availability
before opening the output. It resolves a mode to one immutable processing plan.

Automatic substitution between modes is forbidden. Within a mode, a lower
inference resolution or cadence may be proposed to the user, but the application
must show the changed parameter and its expected impact. CPU inference is never
a silent fallback.

If a backend is experimental, the UI/CLI says so and offers a stable alternative
without renaming the selected mode.

## Mode-specific acceptance criteria

### Performance

- The DA2 Small engine produces correct depth polarity and stable dimensions.
- The complete H.264/H.265 pipeline is benchmarked, not inference alone.
- P95 frame latency, sustained fps, VRAM high-water mark, and GPU utilization are
  recorded for every target workload.
- Any propagation option must beat full-rate inference on end-to-end throughput
  and pass the temporal artifact corpus.

### Balanced

- Balanced is the default only after it completes all V1 reference clips without
  error on the minimum supported GPU profile.
- On identical content, it must improve a declared spatial-quality metric or
  blinded visual score over Performance.
- If it misses realtime, the result clearly identifies the bottleneck and does
  not silently reduce output cadence.

### Video Quality

- Temporal state is deterministic for a fixed engine and input.
- Scene cuts reset caches without carrying geometry across shots.
- Flicker/temporal inconsistency is measurably lower than frame-independent
  Balanced on the temporal corpus.
- Startup/priming latency and steady-state latency are reported separately.

### Offline Quality

- The chosen backend and reason are recorded in output metadata or a sidecar.
- Quality evaluation includes occlusion edges, thin structures, camera motion,
  scene cuts, and depth pumping.
- Cancellation and resume semantics are explicit before long jobs are advertised.
- No speed claim is made beyond measured benchmark artifacts.

## Target workloads

The initial benchmark grid is:

| Resolution | Cadence | Purpose |
|---|---:|---|
| 1920×1080 | 30 fps | compatibility baseline |
| 1920×1080 | 60 fps | primary realtime target |
| 3840×2160 | 30 fps | primary 4K target |
| 3840×2160 | 60 fps | stretch target and bottleneck study |

RTX 4090 and RTX 5090 are reference benchmark machines, not the supported-hardware
definition. Minimum supported hardware is an open decision pending capability and
memory measurements.

## Non-goals for V1

- broad cross-vendor GPU support;
- a polished GUI;
- arbitrary model installation;
- realtime live capture or VR headset playback;
- quality parity with every iw3 control;
- claiming 4K60 support before repeatable end-to-end evidence exists.
