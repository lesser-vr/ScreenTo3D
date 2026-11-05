# Minimal Qt/QML UX — 2026-11-05

Scoped implementation/verification record; product behavior belongs to PRODUCT.md.
No framework replacement or model/precision/resolution change was made.

## Implementation

- Main: 420x260 logical pixels, minimum 380x260; explicit source picker,
  start/cancel/stop and secondary menu. No sidebar or in-app SBS consumer.
- Existing file/setup flows move into an independently closable utility window;
  mode/strength/cursor controls are in a compact quality view.
- Output X and Stop hide output and clean the owned session. Minimize retains the
  session. F11/context menu enters fullscreen; Escape returns. Normal output
  position persists locally without source titles/pixels.
- No initial implicit source selection. Opening the picker refreshes while
  preserving HWND/PID identity; disappearing/reused windows require selection.
- Utility and error windows check capture exclusion before display. Failed error
  exclusion keeps the dialog hidden and stops live capture with the original error
  retained in status. Ctrl+C/Close/Escape behavior remains.

## Checks

| Check | Result / local artifact |
|---|---|
| Controller and placement tests | 48 passed (`python -m unittest v1.test_live_controller v1.tests.test_output_placement`) |
| Actual Qt UI at DPR 1.5 | `out/minimal-ux-qa-20261105-r4/report.json`; no Qt warnings |
| Final UI at DPR ~1.0 | `out/minimal-ux-final-100-20261105/report.json`; measured 1.00000000005 |
| Final UI at DPR 2.0 | `out/minimal-ux-final-200-20261105/report.json`; measured 2.0 |
| Real WGC / DA2 Base / GPU host output | `out/minimal-base-live-20261105/report.json` |
| Real WGC / DA2 Base / native output | `out/minimal-base-native-20261105/report.json` |
| Native output lifecycle | `out/minimal-native-lifecycle-20261105-r2/report.json`; zero pool/node assertions after stop and crash |
| Separate file-conversion GUI | `out/minimal-file-gui-20261105/report.json`; actual fixture conversion completed, no Qt warnings |

UI checks use generated labels and mocked processing states; no user screen is
captured. They exercise real QTest mouse/keyboard input, source refresh and
identity loss, menu navigation, long title/minimum geometry, forward/reverse focus,
start routing, preparation cancel, running stop, utility capture affinity and
native error copying/closing. Final runs also exercise same-page utility reopen
after minimize and injected error affinity failure.

Real start tests use a separate generated source process. Both delivery paths
exercise actual Base inference, sole output consumption, F11/Escape, minimize,
X-to-stop, restart with saved position, button stop and startup cancellation.
Output capture affinity was 17 (WDA_EXCLUDEFROMCAPTURE). Source aspect and output
pixel dimensions remain owned by the existing pipeline.

Native lifecycle uses the prepared public FloorballGame fixture and verifies
resize/generation retirement, hidden output restoration, utility navigation,
fullscreen, stop/restart, minimized-source loss and worker crash. The report's
native_delivery snapshot is taken during playback (one pool/node); the test
separately asserts zero pools/nodes after cleanup. Short measured frame counts
are diagnostic only, not a new throughput comparison.

## Findings fixed during verification

- Moving controls to a plain Window lost the dark palette; using an
  ApplicationWindow with the shared palette corrected the utility controls.
- Slider.live shadowed the Python context property; an explicit controller
  property corrected binding and produced warning-free final runs.
- Same-page menu selection did not restore a minimized utility; openPage now
  restores and activates it even when the selected page has not changed.
- Output hide before another render retained native nodes. The output window now
  disables persistent scene graphs. The first lifecycle run failed its zero-node
  assertion; the corrected run passed all lifecycle checks.
- Independent finish review found unchecked error-window exclusion. The new guard
  and injected-failure GUI test address that finding.
  Final independent verdict: ship the reviewed UX scope; error exclusion,
  minimized utility reopening, hidden-output native cleanup and scaling evidence
  were scored resolved, with no partial/unresolved items in that review.
- The initial directory named `minimal-ux-100pct-20261105` actually recorded DPR
  1.5; it is not 100% evidence. Only the final measured ~1.0 run is used for that
  claim. Earlier failed intermediate runs remain local for diagnosis.

## Limits

Screenshots were visually reviewed at 100%, 150% and 200%; interaction runs are
automated. These checks do not establish user acceptance, prolonged playback,
physical monitor removal, actual device loss or Owl3D/VR behavior. Topology changes
still stop and require restart rather than promising seamless continuation.
TensorRT emitted the existing device-plan compatibility warning during real runs.
No commit, package rebuild or redistribution certification is implied.
