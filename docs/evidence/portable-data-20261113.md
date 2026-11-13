# Portable app data — 2026-11-13

Local implementation and Windows RTX 5090 correctness evidence. No commit,
push, public release replacement, new GPU support or visual-quality claim.
Product behavior is owned by [PRODUCT](../PRODUCT.md); component boundaries by
[ARCHITECTURE](../../ARCHITECTURE.md).

## Scope

The desktop and native launcher use executable-relative `data/`. Preferences use
an explicit fallback-disabled INI, including fullscreen debug information. Output
placement, app-managed models/runtimes, caches, logs and temporary files follow
the same root. The existing frozen entry also resolves the executable folder.
Normal startup does not import app registry settings or silently fall back to
AppData. A pinned unpackaged source interpreter avoids Store Python redirection.

The first-use/settings utility performs explicit background import under the
processing lease. It inventories old files without mutation, copies and hashes
them, preserves current conflicts, and handles cancellation/failure. Original
removal starts unchecked and applies only after successful copy/verification to
unchanged matching files. App settings registry is read only after the explicit
selected import action and remains unchanged. Import does not collect old logs.

Verified model source packs are retained for future engine preparation. Managed
Base/VDA availability checks decrypt the user-bound receipts and match the GPU;
workers still verify actual plan bytes. Rebuilding preserves an incompatible old
directory before publishing the newly verified build. No TensorRT precision,
stereo calculation, capture behavior or native CUDA DLL changed in this task.

## Executed checks

- `out/portable-data-20261113/contracts-final.json`: **572 CPU/Qt contracts pass**.
  Added cases cover explicit INI persistence/corruption, no implicit registry
  import, source/copy mutation, insufficient space, cancellation, linked paths,
  conflicts, opt-in cleanup, processing ownership/close, source retention,
  incompatible receipts/replacement and fixed-root version update preservation.
  Earlier concurrent GUI runs interfered with focus-sensitive tooltip tests;
  the final complete run was serialized and passed.
- `dependencies.json`: **121 Qt PE binaries**, no missing static/delay imports.
- `import-qa/report.json`: actual physical old cache → fresh app `data`, **45
  files / 3,240,056,869 bytes**, all source/destination SHA-256 equal, no conflicts,
  no originals removed, all three legacy settings snapshots unchanged, INI
  confirmed, Base/VDA receipts reusable, no QML warnings. The initial completion
  text undercounted retained originals; corrected and verified as 45 in
  `moved-data-qa/report.json`.
- `live-qa/report.json`: Small/Base/VDA each submitted at least eight native
  frames from an owned generated source, all three compatibility output markers
  recognized, clean stop and zero live native nodes/pools afterward.
- `files-qa/report.json`: Small/Base/VDA at 320×180 and VDA at 320×192;
  each converted **12 frames**, retained audio and passed full FFmpeg decode.
  This reuses the separately pinned QA FFmpeg, bypassing only the media-download
  requirement; it is a worker/storage correctness check, not a new download test.
- The whole prepared app was moved into a real directory containing Korean and
  a space. `moved-launcher.json` verifies Windows-only PATH EXE launch/normal
  close. `moved-data-qa/report.json` rechecks all 45 files/INI/receipts and unchanged
  legacy settings; `moved-live-qa/report.json` reruns all three native outputs.
  The app was then moved back intact to the final directory.
- `package-check.json`: the ZIP is **182,737,523 bytes**, **3,260 files**, fixed
  `ScreenTo3D/` root, no `data/` or Python bytecode, all ZIP CRCs and SHA-256 pass.
  ZIP SHA-256: `2e078a81f4be8d6d1c31b1ee267f1d5aaf333c9d0a5656f885c2832d5f6294fc`.
  Four official runtime and two model anonymous header/prefix probes passed
  (HTTP 206). These do not replace full hashes checked during installation.
- `extract.log` / `extracted-launcher.json`: the distributed PowerShell helper
  verified/extracted the actual ZIP; the extracted EXE opened and closed normally
  with only Windows paths available. This caught an old versioned-root allowlist
  in the helper; it now accepts the fixed root and legacy versioned roots while
  rejecting mixed/unsupported roots and escaped paths. An executed Windows
  fixture regression covers current/legacy roots and traversal rejection.
- The package contains the current source for all **145** canonical app files
  recorded in `build-manifest.json`. Qt/CUDA native pins were unchanged. Git
  whitespace validation passed. The separate extraction helper's checksum was
  regenerated after its correction; the application ZIP itself was unchanged.

Screenshots of the actual protected import utility are local under
`out/portable-data-20261113/import-qa` and `moved-data-qa`; they are not packaged.
The prepared app remains under `out/portable-data-20261113/final/ScreenTo3D`.

## Limits

Checks on another Windows account/GPU are simulated receipt-rejection tests,
not a second-machine runtime certification. Live checks are short lifecycle
checks, not FPS or perceptual-quality benchmarks. No user-owned capture input or
shutdown command was used. Actual global AppData originals were preserved;
cleanup tests use isolated fixtures. Public v1.0.0 assets remain unchanged.
