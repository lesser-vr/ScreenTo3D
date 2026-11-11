# File workspace, queue and completion shutdown — 2026-11-11

Product behavior is owned by [PRODUCT](../PRODUCT.md#desktop-experience), with
ownership boundaries in [ARCHITECTURE](../../ARCHITECTURE.md).

## Implemented scope

All file controls are expanded; the shared header omits its settings button in
file mode. Fresh file settings use Balanced/DA2 Base and Half TB. Live retains
Small, and existing saved user choices are not overwritten. The model label marks
the appropriate per-workspace default. Automatic pending output names track
`Full_SBS`, `Half_SBS`, `Full_TB` and `Half_TB`; existing files, completed paths and
manually chosen output names are preserved.

Start preflights all pending/retry entries, validates input/output aliasing and
asks once about existing destinations. It snapshots the queue's settings and
retains the exclusive file lease across worker cleanup and the next launch.
Late unapproved output collisions fail visibly. Completion still requires the
worker's completion event, clean exit, no error event and published file. Cancel,
failure or app close stops subsequent submissions. Only owned QProcess callbacks
matching the current process can update job state.

Completion shutdown is explicit, unsaved and off on launch. Whole-queue success
starts an app-owned monotonic 30-second countdown with a visible cancel action.
It owns the processing lease until cancellation or request completion, and brings
the file view forward. No OS command is scheduled before the countdown expires.
At expiry, an asynchronous QProcess uses the trusted Windows system executable
with `/s /t 0 /d p:0:0`, without `/f`. The delay is kept inside the app because a
positive OS timeout implies forced application closure. See
[Microsoft shutdown command documentation](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/shutdown).
Request delivery and completed OS shutdown are separate outcomes; applications
may block an ordinary shutdown. Failed requests retain converted outputs and
surface a stable translated error ID.

## Verification

- `out/file-queue-cpu-final.json`: 439 CPU/Qt contracts pass, including all four
  filename formats, reserved-name collisions, input/output aliasing, countdown
  timing/cancel, busy gating, request failure and trusted non-forcing command
  construction. The separate minimum-dependency CI core subset passes 99 tests
  (`out/file-queue-core-ci.json`).
- Additional desktop-controller and preference suites pass 21 + 10 checks.
  Queue tests cover retained lease, fixed settings, failure/cancellation,
  output appearance between jobs, complete-output path retention, custom names,
  all-success shutdown gating and app-close cancellation.
- `out/file-queue-real/report.json`: actual desktop QProcess workers use default
  Base/Half TB on two generated 320x180, 24-fps, half-second videos with audio.
  Success progresses queued/queued → running/queued → completed/running →
  completed/completed. Both `_Half_TB.mp4` outputs contain 12 frames, the expected
  geometry and audio, and fully decode. Source hashes remain unchanged.
- The same actual-worker harness verifies immediate cancellation and invalid-media
  failure. Both leave the second job queued without output; failure also disarms
  an explicitly selected completion-shutdown option.
- `out/file-queue-ui-{150,200}/report.json`: bilingual minimum-size rendered checks
  pass for expanded options, hidden file settings icon, black-bar help, the
  default-off shutdown checkbox, visible countdown and actual-pointer cancellation.
  Images of both languages and the Korean countdown were inspected at 150%.
- General actual-input desktop UX checks and QML/qmllint review pass. Catalog
  validation covers 139 error IDs and 753 Korean entries. No processing defaults
  other than fresh file model/mode were changed.

## Reproduction and limits

Use the prepared GUI/GPU environment and run:

```powershell
python scripts/test-contracts.py --group cpu --report out/new-file-contracts.json
python -m unittest discover -s v1 -p test_desktop_controller.py
python -m unittest discover -s v1 -p test_desktop_preferences.py
python v1/test_desktop_file_queue.py --media-tools <ffmpeg-folder> --output <new-folder>
python v1/test_desktop_localization.py --output <new-folder>
python v1/test_desktop_ux.py --output <new-folder>
```

Tests use temporary settings and generated media. All tests that can arm shutdown
inject a forbidden/stub command or process factory; no real OS shutdown was
performed. Actual shutdown permission, saving/blocking applications and the OS's
final power transition remain untested. The video test checks bounded functional
conversion, not sustained FPS, visual quality or other GPU compatibility. Existing
portable packages are not rebuilt by source changes.
