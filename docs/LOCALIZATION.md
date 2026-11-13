# Maintaining languages and errors

Language definitions live in `v1/screento3d_app/translations/languages.json`.
Each entry specifies its stable code, native display name, BCP-47 locale,
bundled catalog basename and optional Qt standard catalogs. The default language
provides English source fallback without a catalog. Only bundled basenames are
accepted; user-selected or remote translation files are not loaded.

To add a language:

1. Add its definition to `languages.json`, for example code `de`, name `Deutsch`,
   locale `de-DE`, catalog `screento3d_de`, and Qt catalogs `qtbase_de` /
   `qtdeclarative_de` when available.
2. Run `python scripts/build-translations.py --update`. Translate the unfinished
   entries in the generated `.ts` file. The current Korean catalog is a reference.
3. Run `python scripts/build-translations.py`. It validates every registered
   catalog, compiles `.qm` files and regenerates `native/launcher/generated_i18n.h`.
   Release builds reject missing, empty or unfinished translations, duplicate
   entries and mismatched formatting parameters. `--check` validates without Qt
   and detects a stale generated native table.
4. Build the launcher and portable app using the normal scripts. The launcher
   builder regenerates its table with `--native-only`; the portable builder
   compiles and includes the registered catalogs. Include changed registries,
   `.ts` / `.qm` files and the generated header in review.
5. Check rendered text, minimum sizes, keyboard input and DPI behavior in the new
   language. Source registration alone is not visual or RTL validation.

The picker, locale selection, Qt catalog loading and native table generation
need no language-specific source changes. The saved explicit choice wins over
Windows. System default follows the first preferred Windows UI language on app
startup, matching its full tag then its base language; an unsupported language
falls back to the registry default. UI layout remains LTR and eye order stays
unchanged. System regional number formatting remains independent of machine
messages, filenames and model inputs.

## Error identity and translation

Application errors use semantic IDs from `translations/errors.json`, for example:

```python
from .messages import ErrorMessage as E
raise RuntimeError(E('E_OUTPUT_FRAME_DELIVERY', v0=driver_result))
```

Each definition owns its English template, a parameter-free public explanation,
compatibility category and optional native-launcher flag. Add an ID for a new
failure meaning, and keep that ID when rewording its explanation. IDs must not
derive from line numbers or a hash of the text. Retain old IDs while an existing
worker or support report may still reference them.

After adding a definition, run `--update` and translate its `Errors` and
`PublicErrors` entries. The Qt translation **source is the ID**; `extracomment`
documents the English meaning. Parameters in the translated text must match the
definition. Ordinary progress and QML labels continue to use source-text keys.

An `ErrorMessage` transports ID, scalar/nested-message parameters, detached opaque
details and a public flag, without Qt imports or retaining exception tracebacks.
Use `details=` for third-party diagnostics that must remain unchanged. Worker
mailboxes have a fixed byte budget: oversized strings are shortened while ID and
valid metadata survive. Extremely small buffers fall back to ID-prefixed text.
Unknown valid IDs retain their identity/details and display a generic explanation;
malformed metadata remains a bounded original diagnostic.

The error dialog localizes at display time, so an open error changes language
without rerunning the failed operation. It shows ID, explanation and details;
Ctrl+C copies everything. Default file-worker events contain the same error ID
and only the parameter-free public explanation. Private parameters, exception
text and cleanup notes are included only with explicit detailed errors. The
media-tool compatibility adapter still maps older English diagnostic prefixes
to registered IDs; typed application errors bypass wording classification.

Native launcher errors are a subset marked `native: true`. The generator emits
their language table and IDs; do not hand-edit the generated header. Native
diagnostic paths and Windows result codes are appended separately from the
localized explanation.
