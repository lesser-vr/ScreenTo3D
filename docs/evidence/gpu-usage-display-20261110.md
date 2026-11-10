# GPU utilization in SBS title and overlay — 2026-11-10

`LivePreview.outputSummary()` now appends `GPU n%` to the existing original,
output, interpolated FPS and latency text. The QML title and both fullscreen eye
labels already share that string; no QML layout or font change was needed.
The approved upper-right green 8px text, margins and Half-format compensation
are preserved.

`gpu_usage.py` loads the NVIDIA driver-provided NVML DLL from Windows System32.
The processing worker resolves its current CUDA ordinal to a UUID and uses NVML's
UUID lookup. It never guesses NVML device zero, spawns `nvidia-smi`, imports CUDA
in the GUI or launches extra GPU work. The worker publishes one integer percent
and monotonic timestamp in two appended fixed metadata fields (43 total).
It polls at most once per second, including while waiting for input or reusing
static output. Initialization/query failures are optional: unavailable is -1,
and display shows `GPU —` on failure, before the first reading, after stop or
when a sample is older than three seconds. NVML is shut down with worker cleanup.

The value is device-wide utilization, including other applications, not model-
or process-only usage. It is an NVML sample, not instantaneous per-frame GPU work.

## Verification

- Five NVML/sampler/formatter tests: UUID selection, real zero versus unavailable,
  cleanup after failed binding, rate limiting, query failure and stale/future/
  inactive timestamps.
- Three renderer/metadata checks, including the fixed 43-field capacity.
- Fifty-three controller/hotkey tests, including shared GPU summary formatting,
  stale-value clearing and existing lifecycle/privacy behavior.
- Actual QML/WGC/native Small Half TB and oVDA Half SBS tests require a numeric GPU
  percent in the title and identical text in both fullscreen labels. Both pass
  with the existing 8px font and per-format geometry checks, F11/Esc, monitor
  movement, minimize/continue, stop/restart and preparation cancellation.
- Saved fullscreen screenshots were inspected: the added field is present in both
  upper-right labels. This is desktop rendering verification, not optical
  Owl3D/binocular comfort acceptance.
- Fifty explicit real-driver reads: median 0.0007 ms, maximum 0.1838 ms. These
  bypass the production one-second throttle solely to measure the call; the
  figures do not establish overall application FPS parity.

Artifacts: `out/gpu-usage-display-20261110/` contains `query-cost.json`,
`small-half-tb/report.json`, `ovda-half-sbs/report.json` and screenshots.
The synthetic source tests observed GPU 85% and 84% respectively; these are
incidental device-wide values, not benchmark results or expected utilization.
