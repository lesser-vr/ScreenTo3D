# Portable distribution slimming, 2026-11-11

This is a local, unreleased candidate from the dirty working tree based on
`71b9216419fbdf5ddef6ad17db011a625d6910b4`. The published `v1.0.0` tag and
`out/release-1.0.0/` artifacts were preserved. Candidate metadata retains version
1.0.0 and explicitly records `source_dirty: true`; this is not a second release.

## Changes and retained behavior

The ordinary desktop builder excludes development libraries, headers and CMake
files while preserving notices, runtime DLLs and importable Python modules. It
also removes unused Qt WebEngine. The measured exclusions are 909,125,641 bytes
of development files and 346,030,981 bytes of WebEngine files. Bytecode was already
excluded by the previous builder and is not counted as a new size saving.

The default build keeps TensorRT's common runtime and 244,992,624-byte PTX
resource in the app. Seven architecture resource DLLs, totaling 1,703,217,936
bytes, become pinned, deterministic sidecars. The GPU selects SM75/80/86/89/90/
100/120, with a full upstream compatibility pack for an unmapped architecture.
Only the required pack is installed. A supplied local runtime pack takes priority
even when an HTTPS origin is configured; remote installation remains explicit.
The full-runtime builder flag and source checkout's original SDK layout remain.

The trusted source catalog pins both archive and extracted file identities. A
pack is not trusted based on its own manifest. Installation reuses bounded,
cancelable reads and atomic publication. Workers verify the common PTX and
selected native resources before DLL search activation. Loader-registration
failure closes acquired handles and restores PATH. New errors have stable IDs
and Korean/English messages. Missing runtimes use the existing installation UI.

FFmpeg changes from duplicated full static executables to the same-version full
shared Gyan 9.0.1 build. Files used by the app shrink from 444,255,744 to
234,828,598 bytes, including shared DLLs and preserved notices. Preparation pins
the official archive to 97,261,187 bytes and SHA-256
`6fd54b3b4f49117a307877b570f5e1659090f178973298658b41f5c559b5b5ab`.
Prepared executables/DLLs are checked against that authenticated archive, with
unexpected files rejected. Sources: [Gyan build overview](https://www.gyan.dev/ffmpeg/builds/)
and [9.0.1 release](https://github.com/GyanD/codexffmpeg/releases/tag/9.0.1).

## Models and runtime scope

DA2 Small FP16 ONNX remains the only bundled depth weight: 49,642,442 bytes,
SHA-256 `2df6223f206b5164e21f664ace61dabeb9bb6a49b8b5a3e00510b4807d0f5b04`.
Its engine is still created on the user's GPU. Base and VDA remain optional
verified ONNX packs (392,348,171 and 363,291,834 bytes); VFG remains an optional,
default-off NVIDIA download. No oVDA, ZipDepth or device-specific engine plans
were added to the main app. Model algorithms, quality policy and precision did
not change. Torch remains a production runtime dependency.

## Measured package sizes

All figures are decimal bytes/GB; installed engine caches are separate.

| Scope | Original 1.0.0 | Local candidate |
|---|---:|---:|
| Application files | 9,730,850,006 | 6,563,125,196 |
| Application file count | 18,542 | 9,388 |
| Application ZIPs, total | 5,797,809,149 | 3,944,459,156 |
| Application ZIP parts | 4 | 3 |
| Additional selected SM120 ZIP | Included in original runtime | 272,016,861 |
| App + selected SM120 download | 5,797,809,149 | 4,216,476,017 |
| Optional Base/VDA outer ZIP | 639,483,103 | 639,483,103 |

The app shrinks 32.6% before compression. Downloading the app plus the selected
SM120 resource shrinks 27.3%. The app ZIP alone shrinks 32.0%. Seven architecture
ZIPs and the full compatibility ZIP are exported for distribution; users do not
need to download all eight. Summing every alternative pack is not a comparison
of a single user's download. The local candidate and full asset inventory are
`out/lean-complete/ScreenTo3D-1.0.0/` and `out/lean-complete/assets/`.

## Verification

- `out/lean-cpu-complete.json`: 468 CPU/Qt contracts pass, including runtime
  archive corruption, cached-DLL modification, layout validation, required
  architecture selection, explicit remote installation and local-sidecar priority.
- `out/lean-core-final.json`: the Qt/GPU-free core subset passes 114 tests.
  This subset overlaps the CPU total; it is not an additional 114 unique tests.
- Translation validation passes 772 Korean entries and 145 stable error IDs.
  QML lint and qmllint report zero findings on four changed lines. Inline A1–A7
  review traced installation-needed bindings, utility-window navigation,
  busy/lease guards, card ownership and file/live preflights; no findings.
- `out/lean-runtime-first-use-qa/report.json`: an empty, isolated user cache
  installs only the SM120 resource and builds a new Small engine, then produces
  real native Half TB output. Switching languages keeps the worker running.
  Stop releases its texture pools; two actual Small file workers decode to the
  expected frames and audio.
- `out/lean-model-first-use/report.json`: Base builds and validates two engines
  in 61.4 seconds; VDA builds and validates four in 136.7 seconds. Each converts
  a 12-frame owned input with audio. These are first-install timings on this
  host, not processing FPS or timing guarantees.
- `out/ffmpeg-shared-parity.json`: all 553 decoders, 241 encoders, 367 demuxers,
  184 muxers, 579 filters and 268 pixel formats match the old tools. Decoded RGB
  hashes match. `out/lean-shared-media/report.json` verifies actual H.264/HEVC
  decoding, timestamps, audio where applicable, and preservation of previous
  outputs on cancellation/encoder failure, plus the uniform-background fixture.
- `out/lean-complete-qa/report.json`: the final builder's embedded Python runs
  real native Small Half TB, live language switching, cleanup and two sequential
  real file workers with decoded geometry/frame counts/audio verified. PATH and
  user cache are isolated; only an owned generated window is captured.
- `out/lean-missing-runtime-ui-3/report.json`: real rendered Korean/English
  live/file installation cards show the required SM120 pack, 272 MB and NVIDIA
  terms; the primary live button opens the separate settings window. No download
  starts from navigation. Missing-origin/network behavior is injected; no remote
  server is certified by this test.
- `out/lean-extractor-fixture/report.json`: disjoint multi-ZIP extraction and
  byte-exact opaque runtime ZIP copying pass. Existing destinations, application/
  runtime checksum failures, duplicate resource assets, traversal and duplicate
  application entries are rejected before creating the destination.
- `out/lean-complete-delivery/report.json`: the actual final three app ZIPs and
  only the SM120 sidecar extract successfully with the distributed PowerShell
  helper. All 9,388 application entries are disjoint and satisfy the pruning
  policy, including license exceptions. Representative extracted launcher,
  application code, FFmpeg and Torch CUDA DLL hashes match the built app.
- `out/lean-delivery-qa/report.json`: that extracted app, with a second empty
  isolated cache and only the selected sidecar present, installs SM120, builds
  a fresh Small engine and passes real native Half TB, in-session language
  switching, texture-pool cleanup and two sequential conversions with audio.
  `out/lean-delivery-launcher.json` separately confirms that the extracted native
  EXE shows its owned main window and exits normally with an isolated PATH.

## Separate Torch-free GPU-memory experiment

`experiments/native_gpu_runtime/` is not registered as a production backend.
The probe forbids importing Torch and runs owned WGC capture → native BGRA/RGB →
the existing Small GPU preprocessor → TensorRT → existing detail stereo kernels
→ the native Half TB texture pool. CUDA memory and the engine stream remain
explicitly owned; closed buffers reject access.

`out/native-gpu-runtime-proof/native.json` passes 16 frames without importing
Torch. `parity.json` compares those exact captured RGB frames against the ordinary
Torch-backed path at default strength 0.5 and a fixed 60 Hz fixture clock. Every
RGBA pixel matches exactly on all 16 frames, including odd-height Half TB packing.

Diagnostic RGB/output readbacks are deliberately enabled for comparison. This
does not establish throughput, physical/Qt presentation, completed-frame reuse,
long-session stability, or Base/VDA/VFG parity. The experiment supports further
native-memory work; it does not justify removing Torch from the normal package.

## Evidence limits

Actual GPU tests used RTX 5090. Architecture mapping and pinned sidecar generation
are checked for other supported resource names; other GPUs and clean machines
were not physically tested. No new sustained-FPS, monitor/VR quality or device-loss
claim is made. Existing runtime/driver/license restrictions remain applicable.
No commit, push or release replacement is part of this local candidate.
