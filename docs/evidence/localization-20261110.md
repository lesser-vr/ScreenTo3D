# Korean/English localization — 2026-11-10

## Implemented behavior

Product behavior is owned by [PRODUCT](../PRODUCT.md#desktop-experience). App
English source messages and QML `qsTr` calls use the bundled Korean Qt catalog.
The language choice uses `ui/language` in the existing DepthSBS settings namespace.
Only fixed bundled app/Qt catalogs are loaded. Unsupported language/catalog cases
fall back to English. Supported UI is LTR; a system region can format display
numbers without changing numeric protocol/settings values or eye order.

File rows now retain `queued/running/completed/cancelled/failed` states and expose
`stateLabel` independently. Capture stop completion uses an explicit flag.
Messages retain their template and scalar arguments, not native owners or
exception tracebacks. Bounded worker error payloads have a raw-text fallback;
malformed localization metadata cannot replace the original failure diagnostic.
Workers do not import Qt for translation.

## Validation

- 454 finished Korean catalog entries; no missing source entries or mismatched
  placeholders. `scripts/build-translations.py --check` validates sources; the
  same script compiles the `.qm` for the portable builder.
- `scripts/test-contracts.py --group cpu`: 419 passing tests, including missing
  catalogs, unsupported/system locales, region-number formatting, selection
  persistence, busy-session identity, malformed metadata, UTF-8 bounds, literal
  braces in process snapshots and exception-owner release.
- Runtime group: 26 passed. Additional desktop controller/preference tests: 24
  passed. Their settings use temporary INI files.
- Actual CPU FFmpeg success/cancel/encoder-failure cases for H.264 and HEVC pass,
  including output geometry, PTS, audio, full decode and previous-output retention.
- Qt QML lint/qmllint: eight changed files, 108 added/modified lines, no findings.
  Inline binding/lifecycle/wiring review found no additional actionable defects.
- Rendered bilingual source picker, live/file/settings screens and error copying
  pass at 125%, 150% and 200% scaling. A length-expanded checkbox label is also
  checked at the minimum settings width. App error Close text remains under app
  translation ownership when the standard Windows/Qt button text is cached.
- Full/Half SBS and Top-and-Bottom VFG notice layouts pass. Changing language
  updates a visible preparation message without restarting its hold/fade timer.
- Actual DA2 Small native Half TB, 60 FPS limit, owned generated 640×360-logical
  source: four `ko/en/ko/en` changes preserve the same worker PID, session, source,
  model, layout and output window. Submitted output counts advance 12→18→25→31.
  Stop releases the live lease and texture pool. These counts demonstrate progress,
  not an FPS or no-hitch performance benchmark.
- The Windows native launcher compiled successfully with bilingual pre-GUI errors
  and was copied to the local `ScreenTo3D.exe`; its prior executable was backed up
  under `out/`. The Korean catalog also loads from a Korean/spaced directory.

Local reports/screenshots are in `out/localization-final-{cpu,runtime}.json`,
`out/localization-final-media/`, `out/localization-final-{125,150,200}/` and
`out/localization-wrap-200/`. These are ignored test artifacts. The final rendered
harness uses synthetic window-list labels; native capture uses only its owned
generated window. User window contents and downloaded media are not published.

## Reproduction and limits

Run `v1/test_desktop_localization.py --output <new folder>` in the prepared Qt
environment; `--native` adds the actual Small native session. This is an explicit
owned-source test. The standard desktop launcher is the source-local entry point.

Old portable folders are not automatically replaced by source changes. The
portable build now validates/compiles catalogs before copying the app package;
a new clean-machine portable launch and separately triggered native failure-dialog
appearance were not tested here. Native file-dialog standard buttons can follow
Windows language. This work does not revalidate stereo comfort, every model/VFG
combination, other GPUs or long-session performance.
