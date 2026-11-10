# VFG desktop option — 2026-11-06

Scope: the normal prepared DepthSBS desktop now offers optional Medium 2x VFG.
The behavior contract is owned by [PRODUCT](../PRODUCT.md); current status is
owned by [implementation-status](../implementation-status.md#vfg-experiment).
No commit, public upload, portable release or license clearance was performed.

## Implementation checked

- `LivePreview.vfg_enabled` starts false for every new app instance. The existing
  `화질과 입체감` utility contains one checkbox and a short cost/latency explanation.
  It uses the existing visual components; no control was added to the main window.
- The enabled flag is an immutable worker-session argument. Small/Base, window
  GPU capture, native output and CUDA stereo are required. Unsupported settings
  have a reason; a checked option can still be disabled while idle. Runtime errors
  use the existing separate error window. There is no implicit non-VFG fallback.
- Product-owned `vfg_runtime`, `vfg_delivery` and `vfg_renderer` modules are derived
  from the previously tested experiment. Normal `sbs_worker` explicitly selects
  the renderer and publisher, with no model-registry monkeypatching. The GUI
  imports no GPU renderer. VFG off does not validate or load the optional SDK.
- The five-DLL official wheel runtime is staged under `out/vfg-runtime/1.3.0.0`.
  All five DLLs and the DepthSBS native bridge are hash-checked before native load.
  `scripts/prepare-vfg-runtime.py` stages only the pinned wheel and retains its
  licenses/notices; it makes no downloads, system PATH edits or runtime replacement.
- The A/B experiment launchers retain their fixed old measurement implementation
  and hide the normal toggle. Their capture policy remains separate from normal
  app capture exclusion. No external-display or recapture policy was changed.

## Validation

- Platform regression group: **98 passed**, including four new VFG checks for
  default-off/type validation, allowed settings, rejection of corrupted/missing
  runtime dependencies, timing/reset behavior and leased-slot protection.
  Report: `out/vfg-option-platform.json`.
- Existing experiment comparison/timing suites: **12 passed**.
- Python compilation and scoped `git diff --check` pass. Ruff was not available
  in the prepared Python environment and was not counted as a passed check.
- Actual normal Qt desktop harness, `v1/check_vfg_option.py`, captured only its
  owned public FloorballGame source. Final report:
  `out/vfg-option-final-20261106/result.json`.
- Initial default false, no native object or GPU renderer/Torch import in the
  GUI, actual QML click handler, unsupported-option explanation and ability to
  uncheck, and incompatible-path error in the separate dialog all pass.
- In one app: Base off → Base on → Base off → Small on → Small off all produce
  native output. Enabled sessions contain generated-frame records. Disabled
  sessions use ordinary native delivery. Attempts to change the option while
  running leave the session setting unchanged.
- Enabled Base/Small output hide/show recovery passes. Small enabled also retires
  and recreates pools across 1920×1080 → 3840×2160 → 1920×1080 source sizes; the
  4K input pool is 7680×2160 Full SBS. Every session stops with zero live native
  pools/nodes and no remaining displayed frame.
- The default-state utility screenshot was inspected:
  `out/vfg-option-20261106/options-default.png`. The switch is visible and unchecked.

The initial unit run caught a missing ctypes import in the separated mailbox;
this was corrected before the passing regression and both actual GUI runs.
The final GUI run expands the first smoke with error-dialog and 4K resize checks.
Session submitted-frame counts are smoke evidence, not benchmark FPS or physical
display measurements. The prepared TensorRT engine emits its existing device-plan
portability warning; this run does not qualify other GPUs.

## Boundaries

The native shaders and interpolation algorithm were not changed. Prior original
frame/SDK parity evidence remains scoped to its tested inputs. This turn verifies
integration and lifecycle, not sustained FPS, new binocular quality acceptance or
Owl3D eye comfort. Clean-machine/live-app packaging and redistribution entitlement
remain as recorded in the earlier bundle/license reviews. VFG is not enabled by
default or silently restored as enabled on the next app launch.
