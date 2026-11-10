# Language registration and stable error IDs — 2026-11-10

This extends the [initial localization evidence](localization-20261110.md).
Behavior is owned by [PRODUCT](../PRODUCT.md#desktop-experience); the maintenance
procedure is in [LOCALIZATION](../LOCALIZATION.md).

## Scope

`languages.json` now drives picker entries, resolution, locale/catalog loading
and builds. `errors.json` contains 135 semantic IDs; the Korean catalog includes
728 finished entries. Errors use ID-based Qt contexts with English fallback,
parameters and detached opaque diagnostics. The native launcher table is generated
from the same definitions/catalog; its error IDs are also generated.

Known application failures are raised or reported with `ErrorMessage` while
keeping their exception types. Qt-free workers transport IDs; bounded mailboxes
reduce long strings without truncating JSON or losing the root ID. Unknown IDs
keep identity/details and use a generic description. File error events preserve
their existing category alongside `error_id`; typed errors bypass text-prefix
classification. The remaining explicit prefix adapter serves legacy media tools.
Default file-worker events contain no private parameters, detail or cleanup notes;
detailed mode retains diagnostics. Corrupt or conflicting localized metadata
cannot replace the event's declared ID or original diagnostic.

## Checks

- `out/i18n-error-ids-cpu-final2.json`: 431 CPU/Qt contracts passed. Added cases
  cover stable identity after rewording, pickle/JSON/mailbox transport, unknown
  IDs, malformed metadata, long UTF-8 strings, source-only worker imports, safe
  catalog paths, third-language registration/scaffolding/native generation,
  placeholder mismatch, default error privacy, error-window copy/retranslation,
  conflicting worker IDs and hidden-error diagnostics.
- `out/i18n-error-ids-core-ci.json`: 97 core tests passed with only the CPU
  contract dependency path, separately from Qt dependencies.
- `out/i18n-error-ids-runtime.json`: 26 runtime contracts passed. Additional
  desktop preferences/controller suites passed 10 and 14 tests respectively.
- `out/i18n-error-ids-media/report.json`: actual CPU FFmpeg cases pass for fixture
  decoding plus H.264/HEVC success, cancellation and encoder failure; prior output
  retention, PTS, geometry, audio and full decoding remain covered.
- `scripts/build-translations.py --check`: both registered languages, all 135
  error IDs and 728 Korean entries validate. The generated native table matches.
- `scripts/build-desktop-launcher.ps1` and the Release native core check pass.
  Root `ScreenTo3D.exe` SHA-256:
  `0a156d8fc1d5518e4bb699d2b5379cee5121440648613849dd3a89306f15d585`.
  Prior local EXE is preserved at
  `out/launcher-before-error-ids-20261110-221929.exe`.
- Rendered bilingual harness passes at 125%, 150% and 200%: reports under
  `out/i18n-error-ids-{125,live,200}/`. Error ID, translated explanation, original
  detail, complete Ctrl+C copying, Close and unchanged VFG notice timing pass.
  The 150% Korean error image was also visually inspected for readable ID,
  explanation, details and Close within the separate window.
- At 150%, the actual Small native Half TB generated-window session retains PID
  45296/session 1 through `ko/en/ko/en`, with submitted counts 12→18→25→31. Source,
  model, output window/layout and live lease remain the same; stop releases the
  lease and texture pool. These counts demonstrate continued output, not FPS.
- `out/i18n-error-ids-ux-final/report.json`: actual input checks pass for separate
  modal errors, Ctrl+C from text/button focus, Close/Esc/X and capture protection.
  The first run exposed lost raw status detail when a protected error could not
  appear. The fallback now retains it; a regression contract and rerun pass.

All rendered source labels are synthetic, and the native source is a test-owned
generated window. Test settings are temporary; clipboard data is restored. No
production language selection, private media or window-list contents are changed.

## Limits

No new language is shipped beyond Korean/English; the third language is a
temporary fixture. Adding a real language still requires translation and visual
review. RTL layout is not implemented. Native failure tables compile and validate;
separately provoking each pre-GUI MessageBox was not part of this run. A new
clean-machine portable package was not built; source and builders plus the local
EXE were updated. Existing portable/model folders were preserved. No rendering,
model or frame-timing algorithms changed, and this does not re-establish GPU
compatibility, sustained performance or physical stereo comfort.
