# OMA review fixes, 2026-11-12

The user authorized fixing the three findings in
[the OMA QA review](oma-qa-project-review-20261112.md). All three are fixed in the
current source and local prepared EXE folders. Existing ZIPs and remote releases
were not rebuilt/replaced; no commit/push was performed. The `oma-debug` skill's
reproduce/fix/regression procedure was used. This record follows the project's
existing `docs/evidence/` convention rather than creating a duplicate OMA bug tree.

## Short audio and truthful final-media publication

The previous unconditional `-shortest` mux truncated a 48-frame, 2-second video
to 5 frames when its audio was only 0.25 seconds. `mux_video()` now adds audio
padding and `-shortest` only when an audio track exists. Finite video determines
the mux boundary; long audio is clipped there and no-audio input stays complete.

`verify_output()` reads MP4 sample metadata with FFprobe before replacement,
checking video sample count, dimensions and finite duration against the emitted
frame timeline. It does not decode the whole completed video again. Missing,
invalid or mismatching metadata fails with the existing localized `E_AUDIO_MUX`,
preserves any previous destination and emits no success. A regression covers
final-validation failure after mux as well as count/geometry/nonfinite-time errors.

Real FFmpeg 9.0.1 tests with short, long and no audio each retain **48 frames /
2.0 seconds**. The production decode/stereo/NVENC/mux path also retains those
48 frames and audio. This specific test uses constant synthetic depth instead of
model inference so that the media regression is independent of a model's output.
Evidence: `out/oma-fix-media-runtime-final/report.json`.

## FFmpeg log backpressure and cancellation

`media_process.py` explicitly owns each file-job child. Stderr is consumed from
process start into a bounded tail (at most 64 KiB), preventing the decoder and
main worker from waiting on opposite full pipes. FFprobe/mux stdout metadata is
bounded at 4 MiB; overflow is rejected rather than silently truncated and parsed.
The same ownership applies to initial probe, decode, encode, mux and final probe.

A 50 ms cancellation watcher can kill only children registered by that job,
releasing blocked raw reads/writes and process waits. The normal path has no
per-frame cancel polling thread allocation. Process/reader cleanup is bounded;
cleanup failures are attached to the primary error or fail the job. Failure to
reap a child is not marked as successful cleanup. Cancellation during pipe failure
is reported as cancellation. The watcher and children are retired before output
replacement, so later cleanup cannot turn a published file into a failed job.
Media-tool/pipe failures have localized error ID `E_MEDIA_PROCESS`.

Hermetic OS-pipe tests exercise 300 KB of stderr, bounded tail retention, blocked
read/write cancellation, probe/mux wait cancellation and metadata overflow; they
assert child reaping and reader termination. The earlier real corrupted H264 case
now rejects in about **0.09 seconds**, preserving the previous output and removing
owned temporary files. It finishes before cancellation is requested, so this is
recorded as corrupt-input rejection, not as a cancel pass. A separate paced actual
FFmpeg command receives a cancel marker at 0.2 seconds and completes cancellation
with all owned children reaped in about **0.20 seconds total**. These measured
times describe these short fixtures, not a universal deadline for GPU inference.

## Logical work-area fitting

The previous file minimum height of 620 placed the conversion button's bottom at
y=600 in a 960x522 work area. `control_geometry()` now fits both the complete
decorated window and its minimum dimensions into the available work area.
Desktop/QML workspace switching uses this helper for live/file/settings controls;
screen, DPI and available-work-area notifications trigger refitting. In a normal
work area, preferred sizes/positions remain unchanged. Output-video geometry and
stereo packing are unaffected.

Actual Windows Qt at process-local DPR 4.0 now produces an 860x511 client window
and button bottom **y=502**, within the 522-pixel logical work area. Repeated
file/live/file/settings/file transitions fit their complete window frames and
produce no QML warnings. The rendered file screen was inspected; settings scroll
while bottom actions remain visible. At normal DPR 1.5 / 2560x1392 the file size
remains 860x740. OS display settings and user preferences were not modified.
Evidence: `out/oma-fix-control-workarea-final/report.json` and
`out/oma-fix-control-normal/report.json`.

## Verification and local app

- **525 CPU/Qt contracts passed**, including new media-pipe and final-video
  regressions and small-work-area frame/minimum-size checks
  (`out/oma-fix-contracts-final.json`). File controller: **23 passed**
  (`out/oma-fix-controller.log`). Focused checks were repeated for subsequent
  bounded-reader cleanup and work-area notification changes.
- The translation catalog validates **155 error IDs / 813 translations / two
  languages** (`out/oma-fix-translations.log`).
- The unchanged native launchers' Python/QML/catalog files were refreshed in
  `out/public-model-desktop/ScreenTo3D-1.0.0` and its `extracted/ScreenTo3D-1.0.0`
  folder. Their source identity manifests were updated. This did not rebuild the
  native EXE, create a new ZIP or publish an app release.
- The updated packaged interpreter completed **Small, Base and VDA** conversions:
  each had 12 frames, 320x180 Half Top-and-Bottom, retained audio and passed full
  decode (`out/oma-fix-packaged-models/report.json`). It deliberately reused the
  previously validated QA engine/runtime cache. This is not fresh model/engine
  validation and no model graph or inference precision was changed.
- The updated local extracted EXE launches under a Windows-only PATH, shows its
  owned main window, and closes normally with exit 0 (`out/oma-fix-launcher.json`).

Durable reproduction commands (use the prepared Python/PYTHONPATH or packaged
interpreter as appropriate):

```powershell
python scripts/test-contracts.py --group cpu --report out/fix-contracts.json
python v1/test_media_runtime.py --ffmpeg <ffmpeg.exe> --output <new-output-folder>
python v1/test_control_workarea.py --scale 2.666666666666667 --output <new-output-folder>
```

The original review's FAIL verdict is retained as historical evidence. These
fixes do not certify long-session/device-loss behavior, other GPUs, NVDA access
or physical Owl3D/VR stereo quality. Local prepared apps must be restarted to
load the updated modules.
