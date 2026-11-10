# Owl3D comparison output capture compatibility — 2026-11-06

## Trigger and diagnosis

The user reported SBS disappearing only when Owl3D 3D mode is enabled. The
comparison inherited normal output `WDA_EXCLUDEFROMCAPTURE` (0x11). This flag
removes the window from compatible capture paths while leaving physical desktop
presentation intact, matching a compositor-based display omission. See
[Microsoft's API contract](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowdisplayaffinity).

The recent A run (`out/vfg-comparison/20261106-012744-4250-A-baseline/session-1.json`)
ended without a reported error, with positive output and `output_visible: true`
in its last interval. The B run also ended without a reported error, although its
last interval was hidden. These logs do not identify the exact user movement
instant or prove Owl3D's internal compositor path. The capture-policy conflict is
verified in code; actual Owl3D behavior still needs the user's physical check.

## Change

- Normal output still applies capture exclusion. A small controller hook lets
  the explicit comparison subclass apply a different policy to its own result
  window, including show and visibility restoration.
- A/B output now sets affinity 0 and verifies readback. The owner PID is checked
  before marking/changing the window. No other app's window is altered.
- Normal and comparison outputs carry `DepthSBS.OutputWindow.v1`. Enumeration
  skips marked outputs and source validation rejects them again in the worker,
  even across DepthSBS processes. Titles and monitor overlap are not used.
- Comparison input remains window-only. Main/tools/error capture exclusion is
  unchanged. Allowing the SBS output is not an Owl3D-only process allowlist;
  other capture applications can also read it. This policy is documented in
  SECURITY and the comparison instructions, without adding a normal GUI option.

## Executed validation

Both A and B use an owned public 1080p input and actual native output:

- Explicit startup and unsupported-model rejection before capture pass.
- Output affinity readback is 0; main control affinity is 0x11. The actual
  displayed error dialog is checked at 0x11. Closing a dialog may destroy its
  native window, so affinity of a subsequently recreated hidden handle is not
  treated as its visible protection state.
- A separate child process finds the output marker, confirms the output is
  absent from source enumeration and rejects a manually supplied marked HWND.
- Output moves across both connected screens and continues submitting frames;
  hide/restore retains affinity 0 and resumes output.
- A has no generated frames; B has observed generated frames. Stop, restart and
  main-window close clear images and leave zero native pools/nodes.
- 34 scoped tests and Ruff E9/F pass. Tests include the unchanged normal output
  exclusion and fail-closed behavior when output marking fails.

Successful artifacts:

- `out/vfg-owl3d-smoke-A2-20261106/smoke.json`
- `out/vfg-owl3d-smoke-B-20261106/smoke.json`

The first A attempt checked the error dialog after closing/recreating its HWND;
that assertion failed, then was corrected to inspect the visible dialog. This
was a test-lifecycle error, not a decision to relax visible error-window protection.

This validates Windows capture policy, native delivery and screen movement. It
does not claim completed Owl3D 3D-mode/device acceptance or perceptual stereo
quality. Previously running comparison processes must be closed and relaunched.
