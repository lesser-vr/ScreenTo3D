# Qt/TensorRT deployment pruning, 2026-11-11

Local unreleased packaging change on the existing dirty working tree. Model
graphs, precision, algorithms, stereo defaults and retained inference/native
binaries are unchanged. Previous candidates, user caches and the public 1.0.0
release are preserved. No commit/push is part of this work.

## Result

| Scope | Source-pruned candidate | Qt/TensorRT-pruned candidate |
|---|---:|---:|
| App bytes | 1,523,539,309 | 1,350,538,768 |
| App files | 4,667 | 3,250 |
| App ZIP bytes | 778,370,865 | 713,331,657 |
| PySide6 tree bytes | 302,887,488 | 167,007,506 |
| Common TensorRT directory bytes | 724,089,794 | 686,960,754 |

`out/qt-trt-pruned/inventory.json` records 1,418 removed files: Qt 1,415 files /
135,879,982 bytes and TensorRT three files / 37,129,040 bytes. All 50 license and
notice files are byte-identical. The new Qt profile adds one application file;
net app saving is 173,000,541 bytes, versus 173,009,022 removed payload bytes.
The app ZIP saves 65,039,208 bytes (8.4%). GPU-resource and optional-model ZIPs
are unchanged. The app plus SM120 resource ZIP totals 985,348,518 bytes; other
GPUs need their selected resource. Generated engine caches are additional.

The builder produced `out/qt-trt-pruned/ScreenTo3D-1.0.0/` and the normal release
packager produced `out/qt-trt-pruned/assets/`. For local storage, byte-identical
binaries were hardlinked from the previous preserved candidate. Python/config
files were copied and the native launcher was rebuilt. Normal hash checks,
translation compilation and exclusion callbacks still ran.

## Dependency selection

- The bundled PySide6 version is **6.10.2**. The trusted profile is
  `v1/depthsbs_app/qt_portable_profile.json`; mismatched versions and missing
  required bindings/libraries fail before assembly. Direct Python/QML imports
  also have a core contract so future app changes cannot silently use an
  explicitly excluded module.
- Actual app initialization, both languages, all main pages and an owned native
  file dialog were traced in `out/qt-runtime-trace/report.json`. The SDK's
  `qmlimportscanner.exe -rootPath v1/depthsbs_app/qml -importPath
  out/gui-python-deps/PySide6/qml` produced `out/qt-qml-imports.json`. PE normal and
  delay imports of the retained bindings, plugins, QML libraries and native
  output library formed `out/qt-profile-pe-edges.json`.
- The profile retains eight Python bindings and 36 root Qt DLLs. QtOpenGL is
  indirectly imported by QtQuick even though app sources do not import it.
  QtWidgets, network/TLS, image formats including SVG/PDF, input contexts,
  scanner-reported optional control styles, virtual keyboard, translations,
  software OpenGL and shader tools remain. 57 unused QML module roots, unused
  Python bindings/root DLLs, unrelated plugin families and Qt development tools
  are excluded. This is dependency pruning, not a rendering-backend change.
- TensorRT's `nvinfer_lean_11.dll`, `nvinfer_dispatch_11.dll` and
  `nvinfer_vc_plugin_11.dll` are omitted. Current local engines use the full
  runtime without version-compatible engine flags. Full inference, standard
  plugins, ONNX parser, common PTX, CUDA runtime and architecture resources stay.
  Both split and full-runtime builds use the same three-file exclusion. A future
  engine-format/version-compatibility change needs this rule revisited.

Qt deployment requires both binary and QML/plugin dependencies; a direct import
search alone is insufficient. See [Qt's Windows deployment documentation](https://doc.qt.io/qt-6/windows-deployment.html).
The tested SDK and dependency inputs here are specifically 6.10.2.

## Validation

- `out/qt-trt-core.json`: 121 GPU/Qt-free core contracts pass, including required
  module/plugin/fallback retention, unused component pruning, SDK rejection,
  direct app imports and license exceptions.
- `out/qt-trt-dependencies.json`: `scripts/check-portable-dependencies.py` scans
  121 retained Qt/native binaries, with no missing static/delay Qt imports.
  Dynamic loads require the following independent runtime checks.
- `out/qt-runtime-trace-pruned/report.json`: the pruned app loads the same Python
  Qt modules and Qt DLL filename set as the previous candidate through the
  bilingual pages and file-dialog scenario, with no QML warnings.
- `out/qt-trt-ui-qa-3/report.json`: both languages open all three live dropdowns
  and the deployed help component, show the separate native error window, invoke
  its Ctrl+C handler and Close, and retain the main window. Help is opened
  programmatically, not claimed as a physical-hover check; the clipboard sink is
  mocked so no user clipboard data changes. Initial test harness attempts exposed
  a Python converter limitation for `QQuickPopup*` and focus-dependent tooltip
  behavior; the final harness uses QML evaluation/component opening. No app fix
  was needed. There are no QML warnings.
- `out/qt-trt-desktop-qa/report.json`: Windows-only PATH and another empty cache
  build a fresh Small engine, render native Half TB, switch languages in the same
  session, release native pools and convert two queued owned inputs with frame,
  geometry and audio checks.
- `out/qt-trt-model-qa/report.json`: actual packaged Base/VDA installers build
  and numerically validate two/four new engines in that fresh cache; both complete
  a 12-frame conversion with decoded frame count, geometry and audio checked.
- `out/qt-trt-live-qa/report.json`: native Small/Base/VDA each submit at least 30
  frames from an owned generated input. Small/Base each toggle VFG on/off twice
  and resume frame submission; all stop with zero live native pools. The Small
  observation is two seconds, not a new long-duration performance measurement.
- `out/qt-trt-file-matrix/report.json`: Small, Base, VDA streaming and VDA centered
  five-frame paths each convert a real owned input with VFG, Half TB, 24 expected
  frames at 48 FPS, matching audio/duration and complete decode. The native VFG
  SDK is installed in a separate isolated test cache, not bundled in the app.
- `out/qt-trt-pruned-delivery/report.json`: the final ZIP and only SM120 resource
  ZIP pass the distributed checksum-verifying extractor into a new directory;
  all 3,250 app entries satisfy the pruning policy. Representative extracted
  EXE, Python, FFmpeg and native-memory files match the candidate. The extracted
  EXE opens its main window and exits normally with Windows-only PATH in
  `out/qt-trt-launcher.json`.

Runtime tests clear development Python/Qt/CUDA environment paths and use the
embedded interpreter and owned generated sources. Actual GPU tests use RTX 5090;
they do not certify other GPU models or a clean Windows installation. Unchanged
model/native binaries retain the earlier
[numerical and 4K evidence](native-cuda-memory-20261111.md); this packaging work
does not establish a new throughput or image-quality gain.
