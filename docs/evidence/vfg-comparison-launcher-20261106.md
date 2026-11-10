# User-selected VFG A/B launcher — 2026-11-06

Added two prepared-local entry points, `Run-Compare-A.cmd` and
`Run-Compare-B-VFG.cmd`, through `scripts/run-vfg-comparison.ps1` and the isolated
`experiments/vfg/compare_desktop.py`. The ordinary GUI retains explicit selection,
start/stop, error dialog, capture exclusion, fullscreen and owned worker cleanup.
The experimental subclass rejects unsupported model/capture/output configurations
before capture. Native loading still occurs only at SBS start.

Both variants use the timed observer and the same Base FP16 / CUDA stereo path;
B installs the Medium VFG worker. Variant labels and recent metrics use window
titles, without adding primary controls or a normal app setting. No captured
images, source window titles or source identities enter comparison JSON. Bounded
samples and the last 60 windows per session are saved atomically. Reports separate
original/generated FPS and source/midpoint/oldest-input ages. These are Qt
completion observations, not physical display latency. A/B placement has its own
preference file. Run only one active comparison at a time.

## Executed checks

- `check_comparison.py` in separate baseline and VFG processes with an owned
  public FloorballGame window at 1920x1080. Both begin with no source selection,
  no capture worker and no native delivery object.
- Invoking the Qt start slot with Small selected rejects before capture and
  opens the existing error path. Returning to Base permits the ordinary
  `startMinimal` slot used by the SBS start button.
- Both paths produce positive observed output rates; A has zero generated
  output and B has positive generated output. Titles display measured FPS.
  Two measurement windows are collected per first session. This is a functional
  smoke, not a replacement for the matched 4K performance benchmark.
- Stop clears image/pools/nodes. Restart then the normal main-window close
  request stops the owned worker and leaves zero native pools/nodes. Both saved
  session reports confirm cleanup and contain no test source title.
- All 33 scoped unit tests pass: two comparison-metric tests, four timing/mailbox
  tests and the existing 27 native-delivery/mailbox tests. Ruff E9/F and whitespace
  checks pass.
- The actual PowerShell entry path opens A and B with the expected native window
  titles. Computer Use enumerated the windows and closed the test-owned windows.
  The initial process-level title probe was inconclusive because the environment's
  `pythonw.exe` launches the actual GUI in `pythonw3.13.exe`; it was not an app
  startup failure. Capture exclusion was retained, so this is not screenshot-based
  visual acceptance.

Artifacts:

- `out/vfg-comparison-smoke-A-20261106/smoke.json`, `session-1.json`, `session-2.json`
- `out/vfg-comparison-smoke-B-20261106/smoke.json`, `session-1.json`, `session-2.json`
- Interactive launcher startup logs under `out/vfg-comparison/`

The existing [native VFG measurements](vfg-native-20261106.md) remain applicable
to the GPU candidate. Actual user-selected games, continuous binocular review,
long sessions and physical display behavior remain user/device validation work.
