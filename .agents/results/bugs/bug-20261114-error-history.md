---
oma-docs: skip
---

# Bug: Dismissed live errors had no persistent history

- Date: 2026-11-14
- Status: FIXED for reports delivered to the native error window
- Severity: MEDIUM (diagnostic loss)

## Cause and scope

LiveErrorDialog.showError only updated the native window. The launch log recorded uncaught startup errors/native output, but normal handled live/model errors were not written anywhere. The user had dismissed two start/playback errors; recent launch logs were empty and relevant Windows crash records were absent. Those past messages cannot be reconstructed by this change.

## Fix

Added a Qt/GPU-independent error journal called once from showError after formatting the message and before capture-protection/show handling. It records an offset-aware timestamp, stable error ID, localized message/title, available original details, exact displayed document, structured language-independent payload, app version, process ID and the launch-log basename. Closing/retranslating a dialog never removes or repeats the original report. Capture-protection rejection is recorded too.

The history is app-relative data/logs/errors.jsonl, rotated at 1 MiB to one errors.1.jsonl backup. Records are valid UTF-8 JSON, capped at 64 KiB, and marked truncated when oversized; error IDs remain intact. App-data link/path checks run before writes. A storage failure returns false, writes only a bounded identity warning to the existing stderr log when available, and never suppresses the original dialog. The feature has no successful-frame polling or log writes. It does not alter default file-worker stream redaction, startup logging, clipboard behavior, language selection or capture protection. Local diagnostic history is not uploaded; data/ remains excluded from application archives.

## Verification

- RED: a real Qt error dialog was dismissed/retranslated and the expected history file was absent (FileNotFoundError).
- GREEN: dismissal persistence, nested error IDs/details, localized displayed-text preservation, append/correlation timestamps, UTF-8 rotation, oversize/long error IDs, nonfinite/legacy arguments, storage failure and capture-protection rejection pass.
- Existing localization/clipboard test remains passing and its synthetic error is mocked out of production history. The standalone bilingual GUI fixture routes synthetic error history to its QA data.
- Native ScreenTo3D.exe host integration saved two simulated errors under out/error-journal-20261114/native-host-data/; repeated translation did not duplicate them. This used real Qt formatting with windows suppressed, not user input or production error injection.
- Full CPU suite: 607 tests, OK, one skipped because this account cannot create filesystem symlinks. Storage-failure and path-validation behavior are otherwise covered; no privilege change was attempted.
- User-facing Korean/English portable instructions and PRODUCT documentation include location, retention and scope.

## Evidence / remaining scope

Ignored local evidence: out/error-journal-20261114/red.log, cpu-tests.log, native-host-report.json, native-host-data/logs/errors.jsonl. The two original user errors remain unknown. Source changes are local; no commit/push or public release replacement was requested. A new genuine error is needed to investigate that original playback issue.
