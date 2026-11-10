# Small interactive comparison and half-strength default

2026-11-06, prepared local checkout, RTX 5090 / Windows.

## Delivered change

- `Run-Compare-Small.cmd` / `scripts/run-vfg-comparison.ps1 -Small` opens
  DA2 Small FP16, GPU window capture and native output without VFG. It shares
  the current coverage reconstruction and Owl3D-compatible independent output
  window with Base A/B. The selected input remains explicit; opening the app
  does not capture or load the native renderer.
- Ordinary live GUI and all comparison launchers initialize strength to 0.5.
  The quality-window reset action restores the same single default constant.
  Mathematical policy defaults and explicit diagnostic strengths are unchanged.
- Small plus VFG is rejected before app creation. Base A and Base B retain
  their existing model/renderer choices. No commit or model artifact change.

## Timestamp failure and correction

The first Small smoke stopped because the timing adapter assumed source time
must precede processing completion. Three attempts reproduced a negative
source-to-ready interval. The diagnostic run measured source-to-ready -1.1584ms
and callback-to-ready +6.0318ms. Thus the raw compositor stamp led CPU completion;
this was not a leased-slot overwrite. No clock offset cause was established.

Microsoft defines [SystemRelativeTime](https://learn.microsoft.com/en-us/uwp/api/windows.graphics.capture.direct3d11captureframe.systemrelativetime)
as the compositor frame's QPC time. Both that raw source stamp and the measured
CPU ready time are retained unchanged. Original output is now scheduled at the
later of the two. Source leads over 100ms fail before timing/slot mutation.
Generated frames retain the original source-before-ready check and VFG timeline.
Delivery already waits for due time; retirement still drains pending leases.

## Executed validation

- `python -m unittest discover -s experiments/vfg -p test_*.py`: **9 passed**.
  Includes model routing, Small+VFG rejection before app creation, preserved
  future compositor/actual-ready metadata, excessive lead rejection, and existing
  lease, generated-timing and metrics checks.
- `experiments/vfg/check_comparison.py --model da2-small`: **passed** against
  an owned public FloorballGame 1920x1080 input, 3840x1080 Full SBS.
- The same real-GUI check with Base A and with `--vfg` Base B: **both passed**.
- Each check verifies 0.5 startup/reset via Qt slot, explicit-only capture,
  selected model guard, actual original/generated output counts, capture-enabled
  output/protected controls and error window, cross-process recapture rejection,
  movement across two connected screens, F11 fullscreen, hide/restore,
  stop/restart/close and zero live pools/nodes with no retained frame.

Artifacts: `out/small-comparison-20261106/{smoke-final,base-a,base-b}/` contains
`smoke.json` and session reports. Initial failing attempts are retained under
`smoke`, `smoke-diagnostic`, `smoke-clock`; adjacent log files retain errors.
Small's first two stable pre-movement 2.25/2.00-second windows counted about
120.87/107.97 original Qt completions per second, no generated frames, and
8.96/11.19ms median source-to-completion age. These short 1080p lifecycle samples
are **not a controlled model benchmark, physical scanout or sustained 4K result**.
Subsequent windows include movement, fullscreen and hiding and are not comparable.
Existing TensorRT plan-portability warnings were printed; tested native runs
completed without runtime errors.

Actual Small binocular comfort/quality on Owl3D remains for user review.
