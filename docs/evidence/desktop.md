# Desktop and output controls

Historical evidence by recorded checkpoint. Current support is in
[implementation status](../implementation-status.md).

## Records

- [unified-gui-results-2026-09-05](#record-result-unified-gui-results-2026-09-05)
- [unified-gui](#record-result-unified-gui)
- [output-geometry-feedback](#record-plan-output-geometry-feedback)
- [unified-gui-foundation](#record-plan-unified-gui-foundation)

<a id="record-result-unified-gui-results-2026-09-05"></a>
## unified-gui-results-2026-09-05

Checkpoint date recorded in source: 2026-09-05.

> Date: 2026-09-05. Scope: local source GUI steps 1-3, not V2 live completion.

### Environment

> - Windows reference workstation, RTX 5090, driver 616.56.
> - Prepared Python 3.13 environment, PySide6 / Qt 6.10.2 in separate target folder.
> - Existing TensorRT 11.2.1.2, validated local models and CUDA stereo unchanged.
> - Actual Qt renderer: `GraphicsApi.Direct3D11` on both main and output windows.
> - Default 1180x800 and minimum 980x700 logical windows, host 150% scaling.

### Results

> | Gate | Result | Local evidence |
> |---|---|---|
> | Four-model GUI conversion | Pass: original 1056x608 / 124 frames, Full SBS 2112x608 | `out/desktop-gui/da2-h264-01`, `base-01`, `vda-01`, `ovda-hevc-01` |
> | H.264 / HEVC media | Full decode passes; original 124 video frames, AAC 32000 Hz stereo, video 5.166667 s, audio 5.152 s | Same directories, converted.mp4 and report.json |
> | Main + separate fullscreen output | D3D11, enter/exit fullscreen, no QML warnings | `out/desktop-gui/final-click-01` screenshots and report.json |
> | Actual convert-button mouse click | Pass; output exists and success shown after worker exit | `out/desktop-gui/final-click-01` |
> | Console-free pythonw path | Pass; child uses python.exe and JSON pipes | `out/desktop-gui/pythonw-01` |
> | Immediate cancellation | Pass, no falsely completed output | `out/desktop-gui/cancel-01` |
> | Invalid oVDA engine installation | Visible error, no output, controls restored | `out/desktop-gui/error-01` |
> | Real lifecycle / prior output preservation | Immediate cancel, processing cancel, close cancel, invalid engine all preserve sentinel and clean temporary ownership | `out/desktop-gui/lifecycle-01/report.json` |
> | Retry after error / four modes | Performance, Balanced, Video Quality, Offline Quality all complete with DA2 Small in same GUI session | `out/desktop-gui/lifecycle-01` |
> | Python regression | 132 tests pass, including 12 new pure job-policy tests | unittest discover v1/tests |
> | Qt controller regression | 12 tests pass: queue limit, license reset, locked settings, ownership, failure/success/close boundaries | v1/test_desktop_controller.py |
> | Process-tree / C++ regression | 7 process-tree cases and CTest pass | scripts/test-process-tree-memory.ps1, scripts/dev.ps1 |
> | Static checks | Ruff check and format check pass for 8 added Python files; git diff --check passes | Ruff 0.14.14, isolated out/gui-dev-deps |

> Screenshots were visually inspected. Fixed initial empty model/mode labels,
> low-contrast progress styling, retained Qt plugin DLL search-path ownership,
> QML teardown ordering and pythonw child stdout behavior during verification.
> Tests are repeatable via [desktop.md](desktop.md#record-result-unified-gui); use fresh evidence directories.
> Reports contain explicitly selected local test paths; review before sharing.

### Not demonstrated

> - Screen capture, real-time SBS, native CUDA/D3D texture sharing or zero-copy.
> - Presentation latency, 1080p60, HDR, direct headset / OpenXR output.
> - Other GPUs, clean-machine installation or redistributed Qt/model packaging.
> - One-hour stability, VR playback, abrupt native device-loss recovery.
> - Automated queue execution or simultaneous live/file processing.

> The output-window button renders generated LEFT/RIGHT geometry only and is
> labelled accordingly. File results are opened in the user's default media player;
> the new shell does not yet embed arbitrary video playback. Long-running native
> operations can delay cooperative cancellation. The lease coordinates this GUI's
> workers, not unrelated GPU programs or legacy app instances.


<a id="record-result-unified-gui"></a>
## unified-gui

Checkpoint date recorded in source: 2026-09-05.

> Status: Accepted for source GUI foundation, 2026-09-05.

### Choice

> Qt Quick / QML with PySide6 6.10.2 is selected for the shell. It reuses Python
> worker contracts without adding a browser/server bridge, supports GPU-rendered
> scenes and separate windows, and permits a future native Qt scene-graph adapter.
> Keep the legacy Tk GUI and portable launchers unchanged. Widgets are used only
> for native file/confirmation dialogs; QML owns the designed application surface.

> Considered alternatives: keeping Tk would minimize dependency changes but still
> require a different GPU presentation surface; a web shell introduces an additional
> local IPC/runtime boundary; a full native Windows rewrite would duplicate the
> current worker integration. No speed advantage is claimed from these comparisons.

> Primary references:
> - [Qt for Python setup](https://doc.qt.io/qtforpython-6/gettingstarted.html)
> - [Qt graphics API and native resource boundary](https://doc.qt.io/qt-6/qsgrendererinterface.html)
> - [Qt for Python licenses](https://doc.qt.io/qtforpython-6/)

> The installed wheels are pinned in `v1/requirements-gui.txt` and isolated under
> `out/gui-python-deps`, not installed into the model environment. Preserve Qt /
> PySide / Shiboken notices and applicable source/relink obligations when packaging;
> local use is not redistribution clearance. No public release in this change.

### Verified graphics spike

> `v1/test_desktop_gui.py` opens the real QML shell on Windows, asserts actual
> `GraphicsApi.Direct3D11`, renders generated left/right geometry in a second
> window, enters/exits fullscreen, and captures window pixels. Main window tested
> at 1180x800 and 980x700 logical pixels (host scale 150%). Screenshots are under
> `out/desktop-gui/`. QML runtime warnings must be empty including destruction.

> This proves Qt scene rendering and window behavior only. There is **no capture,
> CUDA output texture import, cross-process shared D3D resource, zero-copy proof,
> HDR validation or measured capture-to-present latency**. QQuickWindow.grabWindow
> is test-only readback, never the proposed production frame transport.

> Next native adapter spike must own the D3D device/texture and fences explicitly,
> select same-adapter CUDA interop, bound texture slots, handle resize/device loss,
> and report copies and presentation timestamps. Do not send live raw frames over
> the file worker JSON channel. Failure of that spike can revise the preview adapter
> without rewriting the shell or file pipeline.

### Boundaries

> QML -> DesktopController -> immutable Job + exclusive ProcessingLease -> QProcess
> -> desktop_worker -> existing run_worker / convert_video / validated bindings.

> - GUI never imports TensorRT, torch, OpenCV or engines.
> - Worker stdout is bounded JSON event transport. Partial lines are retained;
>   lines/buffers above 256 KiB are discarded, native stderr is drained, not stored.
> - Queue holds <=32 path records, not video pixels. One selected job executes;
>   no automatic next item. Settings freeze while the lease is owned.
> - Setup uses a separate read-only process and the same lease. oVDA keeps original
>   install checks; other models check inventory/profiles, not engine execution.
> - Source launcher uses pythonw; children explicitly use python.exe with captured
>   pipes so JSON output is available without a console window.
> - Cancellation marker is unique per job and never unlinked on worker startup.
>   Close waits for cooperative cleanup. No forced termination is implemented.
> - Complete JSON alone is not success; normal zero exit and final file required.
> - QML engine is destroyed before its Python context owner to prevent teardown
>   callbacks referencing deleted objects.

### Launch and verification

> Double-click `Run-DepthSBS.cmd`. It uses the prepared local model environment and
> known local resources; this is not a standalone redistributable installer.

> PowerShell development commands (from repository root):

> ```powershell
> & out/vda-oracle-env/Scripts/python.exe -m pip install --target out/gui-python-deps -r v1/requirements-gui.txt
> $env:PYTHONPATH = "$PWD/v1;$PWD/out/gui-python-deps;$PWD/out/v1-python-deps"
> & out/vda-oracle-env/Scripts/python.exe v1/test_desktop_controller.py -v
> & out/vda-oracle-env/Scripts/python.exe -m unittest discover -s v1/tests -p test_desktop_jobs.py -v
> & out/vda-oracle-env/Scripts/python.exe v1/test_desktop_gui.py --output out/desktop-gui/new-run --input 'path/to/clip.mp4'
> ```

> Use a fresh output directory. `--model`, `--codec hevc`, `--cancel`, and `--error`
> select local test cases. `--error` uses an invalid oVDA engine folder; it does not
> inject device loss. Tests do not certify long-duration reliability or VR playback.


<a id="record-plan-output-geometry-feedback"></a>
## output-geometry-feedback

Checkpoint date recorded in source: 2026-09-05.

> Implemented input/per-eye/SBS geometry after the worker start event, completion
> counts from worker telemetry and a persistent no-add/no-remove explanation.
> Repeated jobs clear previous results; legacy completion events remain supported.
> Actual Tk construction/event/command tests pass via `v1/test_vda_gui.py`, including
> zero applied / 124 bypassed, old events and unchanged model defaults. Diff
> whitespace check passes. Renderer behavior is unchanged; no GPU rerun or portable
> rebuild was needed. Visual layout at alternate Windows display scaling is not
> certified by these construction tests.


<a id="record-plan-unified-gui-foundation"></a>
## unified-gui-foundation

Checkpoint date recorded in source: 2026-09-05.

### Decisions

> - Existing dirty work belongs to prior development and is preserved.
> - Use a separate source launcher; no implicit migration of older launchers.
> - Live remains visibly unavailable; test pattern output is not live capture.
> - No hidden CPU/model/codec fallback and no automatic model downloads.
> - Future live workers must acquire the same exclusive processing lease.

### Progress

> - [x] Verify repository and existing worker interfaces.
> - [x] Product contract and roadmap updated.
> - [x] GUI graphics spike and technology decision recorded.
> - [x] New shell and file conversion connected.
> - [x] Tests and evidence recorded.

### Evidence and handoff

> See [desktop.md](desktop.md#record-result-unified-gui-results-2026-09-05): four real models, H.264/HEVC decode/audio, D3D11 and fullscreen, console-free launch, actual button click, prior-output cancellation/error preservation and four-mode retry pass. 132 Python + 12 Qt controller tests, 7 process-tree cases, CTest and static checks pass. No release was produced. The current output window uses generated geometry only, not CUDA/D3D imported video textures.
