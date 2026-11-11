# First-use desktop components, 2026-11-11

Local implementation on the existing dirty working tree. The desktop builder's
default now separates the common TensorRT/PTX/CUDA runtime and full shared
FFmpeg/FFprobe from the application. Small ONNX, the embedded Python/Qt UI,
native modules and model policies remain. Original release files and previous
candidates are preserved; no commit, push or publishing was performed.

## Measured artifacts

| Scope | Previous candidate | First-use candidate |
|---|---:|---:|
| App bytes | 1,350,538,768 | 428,866,502 |
| App ZIP bytes | 713,331,657 | 182,759,785 |
| App files | 3,250 | 3,240 |

App-file saving is 921,672,266 bytes (68.2%); app-ZIP saving is 530,571,872 bytes
(74.4%). These exclude installed caches and selected architecture resources.
Moving files to first-use installation does not reduce their eventual installed
size or eliminate the download needed to use those features.

- `tensorrt-11.2.1.2-core-v1.zip`: 438,176,196 bytes,
  SHA-256 `361cc4a5fe508930689d5541e4ace62b57b28c8dcbaf6a8d33883e3843c99060`.
  Contains full inference, standard plugins, ONNX parser, common PTX, pinned CUDA
  13.1 runtime, builder-layout data and NVIDIA license texts.
- `ffmpeg-9.0.1-shared-v1.zip`: 92,456,432 bytes. Contains the same full shared
  FFmpeg/FFprobe binaries, provenance and notices as the preceding candidate.
  Its archive and every file have trusted pins in `desktop_runtimes.json`.
- Existing GPU-resource and optional-model packs are unchanged. The app plus
  both component ZIPs and SM120 ZIP is 985,409,274 bytes. A live-only installation
  need not fetch the media component. Local original packs remain user-owned.

Final candidate: `out/first-use-final/ScreenTo3D-1.0.0/`; archives and extraction
tools: `out/first-use-final/assets/`. The native launcher was rebuilt. Other
retained binaries are byte-identical to the preceding tested candidate. Immutable
binary files and sidecars were hardlinked for local storage; app sources were
copied and normal builder validation ran. The normal component builder rebuilt
both pinned archives byte-identically in `out/component-packs-rebuild/`.

## Ownership and setup

`desktop_runtimes.py` resolves only explicit deferred-layout markers or the
versioned managed cache. It verifies the complete expected file inventory and
hashes before executable loading. Resolution performs no network requests.
`optional_models.py` reuses bounded downloads, HTTPS redirect checks, exact
archive size/hash, contained extraction, cancellation and atomic publication.
Components never invoke model optimization. Space checks include compressed and
expanded component bytes. Existing cache collisions must also validate payloads.
TensorRT DLL search directories and media paths are explicit; ambient developer
installations are not substituted.

`ModelDownloads.ensure` sequences required components after an explicit Start or
model-install action under the existing shared lease. Successful setup hands
control directly to the original task. Cancellation/failure clears continuation;
an explicit subsequent installation does not resurrect it. A live source or
processing selection changed while waiting requires another Start. Standalone
model installation does not start capture. The separate protected setup window
uses existing theme tokens and native Close; cancellation remains available.
Component descriptions/actions explicitly track language changes. Its minimum
height follows content so progress and Close fit at 380 logical-pixel width.

Local original packs under adjacent `runtime-packs/` take precedence over the
configured `--model-origin` HTTPS address. This local candidate has no public
origin configured and uses adjacent packs. Online code is exercised with a
controlled HTTPS-response fixture, including redirect downgrade rejection;
actual public CDN transfer has not been tested or published. Missing origin
shows a separate error and supports choosing the original pack from a file.
`--bundled-components` retains common/media in the application;
`--full-runtime` also retains all architecture resources for offline delivery.
The release manifest/extractor recognize component-runtime ZIPs as opaque
sidecars, copying only supplied packs beside the app after checksum verification.

## Validation

- `out/first-use-contracts.json`: 267 core/profile/Qt contracts pass. New tests
  cover incomplete/tampered payloads, pinned HTTPS responses and insecure
  redirects, corrupt/cancelled install cleanup/retry, local-pack precedence,
  ordered setup, no task after cancel/failure/close, and synchronous lease handoff.
  Translation compilation validates 149 error IDs and 787 translations.
- `out/first-use-qt-dependencies.json`: 121 retained Qt/native binaries have no
  missing static/delay Qt imports. Final size-only QML adjustment adds no imports.
- `out/first-use-desktop-qa/report.json`: embedded interpreter with Windows-only
  PATH and an empty isolated cache opens the real app, cancels the actual core
  installation without publishing or capturing, retries, builds Small's engine
  and automatically starts the selected native Half TB session. Language changes
  preserve the worker. Stop releases all native pools. Media is still absent
  after live use; starting a two-input file queue installs it and then completes
  both conversions. Decoded geometry, 12 frames per file and audio are checked.
- `out/first-use-model-qa/report.json`: the cached common runtime builds and
  numerically validates two fresh Base and four VDA engines. Both then convert
  12-frame inputs with expected geometry/audio and complete decode.
- `out/first-use-live-qa/report.json`: native Small/Base/VDA each submit over 30
  frames; Small/Base each toggle VFG on/off twice and continue producing frames.
  Every stop releases all pools. This is a functional check, not a new FPS or
  long-duration stability measurement.
- `out/first-use-vfg-files/report.json`: real Small, Base, VDA streaming and VDA
  centered five-frame conversions with VFG produce expected 24-frame, 48-FPS Half
  TB output with original duration/audio and complete decode. NVIDIA SDK data is
  in a separate test cache, not the application archive.
- `out/first-use-recovery-qa/report.json`: an unconfigured-origin error, injected
  network failure and original-file installation use the actual Qt adapter/error
  windows. Failure publishes nothing and does not resume capture. Explicit file
  recovery succeeds while the original continuation stays cancelled. English and
  Korean descriptions update while the setup window remains open.
- Rendered real setup/progress screens in `out/first-use-desktop-qa/` and recovery
  screens in `out/first-use-recovery-qa/` were inspected. Narrow progress-state
  captures in `out/first-use-layout-active-final/` confirm all controls fit.
  Mechanical design scans report no findings. This is implementation/visual QA,
  not user acceptance.
- `out/first-use-final-delivery/report.json` records actual final app ZIP plus
  only the common/media/SM120 packs passed through the checksum-verifying
  distributed extractor. Representative extracted files match the candidate.
  `out/first-use-final-launcher.json` records extracted EXE launch and normal exit
  with isolated PATH and no installed runtime in its test cache.

The full GPU/queue/recovery checks ran before the final content-based minimum-
height adjustment. Build manifests confirm that `RuntimeSetup.qml` is the only
application-source difference; numerical code and all inference/native binaries
are unchanged. Narrow rendering and final extraction/EXE checks ran on the final
candidate. Earlier numerical/4K evidence remains applicable; no new throughput or
quality improvement is claimed. Only generated owned sources were captured.
Actual GPU testing is RTX 5090 only, not clean-machine or other-GPU certification.
