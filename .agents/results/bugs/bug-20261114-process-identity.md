---
oma-docs: skip
---

# Bug: GUI and processing tasks appeared as Python in process managers

- Reported/fixed locally: 2026-11-14
- Status: FIXED locally; public release replacement not requested
- Severity: LOW (process identity / user experience)

## Cause

The branded outer launcher started the official `pythonw.exe`. Window/taskbar identity does not change the actual process image or its PE file description. Multiprocessing children also used that interpreter, so a branded shortcut/window still left Python-named GUI/work processes.

## Change

Added a small native GUI-subsystem `ScreenTo3D.exe` host next to the unmodified pinned CPython runtime. The outer launcher starts this host. It loads only the adjacent `python313.dll` with explicit DLL-search flags and delegates to `Py_Main`; Python modules, model/runtime paths and normal app-relative data settings remain unchanged. `sys.executable` is the host, so normal multiprocessing and QProcess workers inherit the same process identity.

The host and launcher share the approved icon and `FileDescription=ScreenTo3D`. Inherited pipes are usable without a console window. The host explicitly enables UTF-8, including isolated children that ignore environment encoding settings. Original `python.exe`/`pythonw.exe` files remain intact for developer/legacy entry points. Experimental scripts that deliberately invoke their own external Python environment may still show Python; the normal desktop GUI and its application workers use the branded host. External tools such as FFmpeg retain their own names.

The host avoids STL DLL dependencies: only Windows/system CRT APIs and the VCRUNTIME already supplied by embedded CPython are required. The first host prototype imported MSVCP140.dll; inspection detected that extra clean-machine dependency and it was removed before installation. A PE import check now rejects any non-system dependency missing beside the host. No extra runtime installation is needed for this change.

The portable builder bundles both launcher and host and records the host hash. `build-desktop-launcher.ps1 -InstallSource` installs both into a prepared source checkout after the app is closed. The developer desktop launch script uses the branded host too.

## Validation

- Native source/portable host checks: PE product description and GUI subsystem, dependency closure, UTF-8 stdin/stdout/stderr, actual spawned-worker executable image, QProcess JSON, exit codes, invalid arguments, relocated Korean/space paths and quoted arguments, adjacent-runtime failure.
- An isolated Unicode-path test exposed locale-dependent output before explicit UTF-8 mode; the corrected host passes both source and portable tests.
- Real Qt GUI loads from the final portable package; app name/window title are ScreenTo3D and icon is present.
- Real generated-input DA2 Small native GPU output: final installed GUI and GPU-worker images are both ScreenTo3D.exe, at least 8 frames, clean retirement. This is a lifecycle check, not a performance/visual-quality benchmark.
- Real file conversion queue with generated media: two successful Half-TB conversions, cancellation and failure scenarios pass; JSON communication, frame/audio validation and next-file progression succeed. Real Windows shutdown is blocked by the test.
- CPU suite: 598 passed. `git diff --check` passes.
- User closed the live app before installation. Restarted source launcher PID 25340 and GUI PID 41540 were verified via Windows process metadata as ScreenTo3D.exe. Existing models and preferences were not moved or deleted. User may restart live 3D from the normal source selector.

## Evidence

Local ignored evidence under `out/process-identity-20261114/`: final-source-host/report.json, final-portable-host/report.json, portable-gui-report.json, file-queue/report.json, gui-live-installed/report.json, cpu-tests.log and installed.json. Full private QA portable build is under portable-final/ScreenTo3D. No screenshot-based Task Manager UI acceptance was claimed; actual Windows executable paths and file descriptions were checked.

## Remaining scope

Public release ZIP replacement, signing and commit/push were not requested. This change identifies processes; it does not change depth models or claim FPS improvements.

## References

- https://docs.python.org/3.13/c-api/init.html
- https://docs.python.org/3.13/using/windows.html
- https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/open-osfhandle?view=msvc-170
