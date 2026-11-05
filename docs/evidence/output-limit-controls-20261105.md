# Output limit controls — 2026-11-05

Historical implementation and verification record. PRODUCT.md owns behavior;
implementation-status.md owns current delivered scope.

## Change

- The settings picker now exposes unlimited (default), 30 FPS and 60 FPS, locked
  during an active session. Zero is the internal unlimited value. Live controller,
  cadence and descriptive mode defaults agree.
- Native delivery previously published before the controller's deadline check.
  It now checks the shared cadence immediately before native publication. A capped
  poll publishes at most one new frame, then schedules from that actual publication
  time. Delayed callbacks do not cause catch-up bursts. Host image notification
  uses the same policy; native metadata notification does not consume its deadline
  a second time or starve health/status updates.
- Import, native error checks and completed GPU lease release remain active between
  deadlines. Pool retirement drains pending GPU leases without waiting for pacing,
  including retirement racing a capped poll. Metadata release still follows native
  GPU completion. Texture slots remain bounded to two; there is no extra frame queue.
- App creation requests Qt vsync off and swap interval zero. The application limit
  is independent of physical monitor refresh, which driver/compositor constraints
  can still affect. The 1ms precise timer services all three choices. Existing model,
  preprocessing, CUDA renderer, native DLL pins and capture exclusion are retained.

This deliberately changes presentation scheduling. Existing exact-input/depth/SBS
pixel evidence is reused; this is not a claim of equal temporal output when selecting
a lower FPS limit. Backpressure may skip capture frames as before. No FG is added.

## Automated and actual GUI verification

- 61 scoped tests pass: four cadence, twelve native protocol and 45 controller
  tests. Coverage includes zero/invalid limits, late-poll spacing, at most one frame
  per capped deadline, unlimited delivery, continued GPU release/error reporting,
  retirement while waiting, concurrent retirement and session setting locks.
  Logs: `out/output-limit-{policy,native,controller}-tests-20261105.log`.
- `out/output-limit-ui-20261105/report.json`: actual Qt keyboard changes from
  unlimited to 30, 60 and back, default selection, disabled active control, existing
  window/menu/start/stop/error behavior and capture exclusion pass. Zero Qt warnings.
  The settings screenshot was inspected: the label, selection and focus border fit.
  This UX harness explicitly selects host diagnostic output for its mocked frames;
  the screenshot's host selection does not represent the app default.
- `out/output-limit-lifecycle-30-20261105/`: actual Base FP16/native at a 30 FPS
  limit passes start, hide/restore, fullscreen/Escape, resize/retirement, stop/restart,
  source loss, worker crash and preparation cancellation. The identical suite also
  passes for Small FP16/unlimited in `out/output-limit-lifecycle-unlimited-20261105/`.
  Both suites assert zero native pools/nodes at final shutdown. These are bounded
  local lifecycle checks, not long-session or physical-display acceptance.
- Scoped Ruff E9/F and `git diff --check` pass. No portable package was rebuilt.

## Actual output limits

RTX 5090 / driver 621.14, public FloorballGame, Small FP16 Performance, default
native transport and existing GPU capture/input. Each case discards three seconds
of warmup and measures five three-second windows. No benchmark-only `--uncapped`
override or GPU replay is used; `--hz 0/30/60` invokes the product setter. Input and
per-eye dimensions match; combined Full SBS is twice input width. Output is fitted,
not physical scanout. Count distinct native Qt afterFrameEnd IDs.

The first matrix (`out/output-limit-{30,60,0}-20261105/`) completed at both 1080p and
4K, with zero native pools/nodes after every session. All capped windows are below
their selected limit. Its event pump still slept 2ms and artificially reduced
delivery cadence, especially at 1080p. The benchmark now pumps at 0.5ms when the
app timer is 1ms; the corrected 1080p rerun is below. This is a measurement harness
correction, not a further product performance optimization.

| Input / per eye | Selected limit | Output median | Five-window min–max | Record |
|---|---|---:|---:|---|
| 1920x1080 | 30 FPS | 29.53 | 29.22–29.56 | `output-limit-fine-30-20261105` |
| 1920x1080 | 60 FPS | 57.79 | 56.15–58.12 | `output-limit-fine-60-20261105` |
| 1920x1080 | Unlimited | 135.94 | 132.79–139.16 | `output-limit-fine-0-20261105` |
| 3840x2160 | 30 FPS | 28.49 | 27.83–28.79 | `output-limit-30-20261105` |
| 3840x2160 | 60 FPS | 56.27 | 56.22–56.64 | `output-limit-60-20261105` |
| 3840x2160 | Unlimited | 75.81 | 74.24–76.87 | `output-limit-0-20261105` |

30/60 are publication upper limits, not guaranteed rates. Timer jitter, minimum
spacing, Qt consumption and source/processing load can yield lower output. In a
short observation window, a boundary frame can change the reported rate by 1/N
for an N-second window. The summary checks capped windows against limit + 0.4fps,
unlimited medians above 60fps, and zero remaining native pools/nodes.
Raw runs/environment JSON retain actual configuration and hashes;
`out/output-limit-summary-20261105.json` contains the aggregated results.
After measurement, only the descriptive LivePolicy default was aligned to zero;
the controller had already overridden that report field with the selected value.
The final controller tests verify both defaults.

Example reproduction (choose a new output directory):

```powershell
$env:PYTHONPATH='v1;out/gui-python-deps;out/capture-python-deps;out/v1-python-deps'
& out/vda-oracle-env/Scripts/python.exe v1/benchmark_live_modes.py --output out/output-limit-repro --sizes 1920x1080,3840x2160 --modes performance --hz 30 --source-interval-ms 0 --path gpu-texture --source FloorballGame --source-process --seconds 3 --repeats 5
```

Change `--hz` to 60 or 0 for the other choices. These are functional limit checks
and short local throughput observations, not sustained game/VR support claims.
