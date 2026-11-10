# Owl3D native window ownership integration — 2026-11-06

## Confirmed failure boundary

After capture exclusion was removed only from the comparison result window, the
user confirmed it stayed visible but still appeared as SBS. The user had already
enabled Stereo 3D Playback and confirmed that fullscreen and explicit Full SBS
also failed. Treating this as simply an unselected playback mode was incorrect.

Read-only local logs establish stereo-only processing, not Live 3D conversion.
The 01:51 session records the user's `FSBS` selection and `FULLSCREEN`/`ALWAYS`
scope changes reaching the native worker. Earlier attempts remained on the
`detected-candidates` route, `sourceFullscreen=0`, with uninformative candidate
regions and a 12-second preparation timeout (`camera_ready=Y render_ready=N`).
Thus manual format selection alone did not establish a usable input region.

Win32 readback from the old comparison process confirmed that the SBS HWND's
`GW_OWNER` and `GA_ROOTOWNER` were the small controller HWND. Nested QML Window
ownership is unsuitable for consumers that discover a fullscreen root window.
The [GetAncestor contract](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getancestor)
describes the root-owner traversal. This identified a concrete interop candidate;
the following execution validates its effect without claiming access to Owl3D's
private implementation.

## Change

`create_comparison` calls `output_window.setTransientParent(None)` after creating
the ordinary shell. Only the interactive A/B launchers change. Output has no
native owner and is its own root owner. QObject lifetime, output close-to-stop,
capture policy, cross-process recursion rejection, texture leases and native
frame delivery remain unchanged. No model, source dimensions, SBS packing,
native DLL, Owl3D binary or Owl3D settings were modified.

## Actual Owl3D observation

An owned public FloorballGame source produced Full SBS on the revised A output.
The test moved it across both displays, then showed it fullscreen on Shift for
six seconds. OS readback covered `[3840, 0, 7680, 2160]`, with no native owner.
Owl3D 2.4.2 / screen 0.0.31 was already running in the user's session.

Its native log changed in sequence:

1. 01:55:30.531 — revised Qt HWND recognized as `fullscreen=1`,
   `sourceFullscreen=1`; route changed to `whole-source`.
2. 01:55:31.152 — picture crop accepted as supported.
3. 01:55:32.150 — picture crop confirmed and automatic packing changed from
   unresolved to `FullSBS`, aspect 3.555556.
4. 01:55:32.158 — `weave enabled reason=ready regions=1 HasRegions=Y
   IsFullyReady=Y EyeReady=Y`.

Immediately before the route change it held the 2D frame with `no-sbs-regions`.
This is actual external compositor integration evidence, beyond DepthSBS's
internal submission counts. It does not certify what the user sees with both
eyes, every source aspect/content, or windowed automatic detection.

The VFG B run repeats the result: at 01:57:09.380 its own HWND becomes
`sourceFullscreen=1`, at 01:57:11.003 the whole-source crop resolves to FullSBS,
and at 01:57:11.011 weaving is enabled. A/B both pass two-screen movement,
hide/restore, restart and zero-pool/node shutdown. The existing 34 scoped CPU
checks remain applicable; Ruff and whitespace checks pass after this change.

A negative control uses the same public source and fullscreen bounds but restores
the original transient parent (`check_comparison.py --owned-output-control`).
Its output is physically fullscreen and its root owner is the small controller,
while Owl3D continues using `detected-candidates` / `sourceFullscreen=0` instead
of whole-source localization. It can intermittently classify a candidate as SBS,
but also alternates with `no-sbs-regions`. Thus ownership does not make all
windowed classification impossible; the confirmed repair is reliable entry to
the external full-screen source route in these bounded runs.

Local artifacts:

- `out/vfg-owl3d-root-A-20261106/smoke.json`
- `out/vfg-owl3d-root-A-20261106/owl3d-integration.log`
- A session reports with balanced native cleanup.
- `out/vfg-owl3d-root-B-20261106/smoke.json` and `owl3d-integration.log`
- `out/vfg-owl3d-owned-control-20261106/smoke.json` and `owl3d-integration.log`

Both historical failed settings checks and the user's Full SBS report remain
valid observations of the prior window. Instructions now require relaunching the
comparison app to apply the new native ownership, then testing fullscreen.
