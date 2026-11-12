# Separate public Base/VDA distribution, 2026-11-12

The user approved the separate-model distribution proposal. The new public
[ScreenTo3D-Models repository](https://github.com/lesser-vr/ScreenTo3D-Models)
and [packs-2026.11.1 release](https://github.com/lesser-vr/ScreenTo3D-Models/releases/tag/packs-2026.11.1)
are published. Repository ID: `1455000984`; release ID: `442644930`;
documentation commit: `a3715fd89356cb31b656660354eb563174d64f3e`.

The existing source repository remains private, its app release is unchanged,
and no source-worktree commit/push was performed. The public model repository
has its own initial documentation commits, required to publish its model tag.
No existing repository history was copied into it.

## Public artifacts and provenance

Only these four release attachments were published:

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| `da2-base-onnx-v1.zip` | 392,348,171 | `61bf0969e59e0b098ad4f968522b990d844ff7e4a0654dd82bbadfcd6b054731` |
| `vda-small-onnx-v3.zip` | 363,291,834 | `b4e68c45328e37b601c95f1d06a024c41c510c6c980ba2fcdec5b1030603778f` |
| `model-manifest.json` | 5,742 | `b18f720966726fe09e382ffc26864512f4555565ffa8cd03631bf4bfff9572ac` |
| `SHA256SUMS.txt` | 700 | `0cb77d447d8fe6d3d422195430b6cf1a5a09aec0970ca85f94ceee94f3041a3e` |

Each server-reported size/digest matched the local reviewed artifact before
publication (`out/public-model-release/published.json`). Documentation in Git
contains model cards, separate license texts, manifest/checksums and a bilingual
README; no large binaries were committed to its Git history. Existing model ZIPs
are byte-identical to their previous pins, so valid installed engines/downloads
remain reusable. Added external provenance did not change model pack hashes.

Public staging verifies archive hashes and an exact member allowlist, then checks
individual ONNX hashes. Packs contain ONNX, small numeric reference arrays and
model-specific notices; no app source, input videos, prebuilt GPU engines or
NVIDIA runtime files were published. Manifest provenance includes original
source/weight revisions, conversion script hashes, precision/profiles and the
declared local validation environment. The source worktree is explicitly recorded
as dirty, rather than claiming the current Git commit fully reproduces its bytes.

Base retains CC BY-NC 4.0; VDA Small retains Apache 2.0. Public model cards
preserve upstream links, modification and non-endorsement notices. CC license text
was fetched from SPDX's standard license list because the Creative Commons plain
text endpoint returned HTTP 403; canonical CC license links remain in the card.
VDA license text is preserved from the recorded upstream source. No project-wide
MIT/Apache grant was applied to the mixed-license model repository.

## Application behavior and packaging

The default builder includes Small and the UI; Base/VDA come from the fixed
`packs-2026.11.1` public release. A distributor override changes only the HTTPS
origin, never app-owned archive/graph pins. Optional `--bundle-models` preserves
the existing verified offline layout. Merely selecting a model does not download
it; explicit Start/Install drives the shared setup flow and local engine build.
Failed/cancelled setup drops task continuation, and cached originals are hash
verified before reuse. Official TensorRT/CUDA, FFmpeg and VFG sources are unchanged.

Packaging anonymously probes all four runtime and both model archives before
creating assets. A public-model build rejects accidental bundled packs and the
legacy `--packs` request, avoiding redundant optional-model ZIPs.

Final app: `out/public-model-desktop/ScreenTo3D-1.0.0/ScreenTo3D.exe`.
Final ZIP: `out/public-model-desktop/assets/ScreenTo3D-1.0.0-windows-x64.zip`.
App: **428,890,286 bytes**, 3,247 files. ZIP: **182,773,613 bytes**
(182.8 MB / 174.3 MiB), compared with the preceding bundled-model ZIP's
822,256,200 bytes: **77.77% smaller**. ZIP SHA-256:
`d9adb8993a13fe3b5b75abd81e12e5382e97d8e30eec0f4e035fcf643283dc99`.
There is one app ZIP and no duplicate model archive in its asset set.

## Verification

- Core/platform/profiles/Qt: **416 passed**, no skips
  (`out/public-model-contracts.json`). File-controller tests: **23 passed**
  (`out/public-model-controller.log`). Existing cache tests cover interrupted
  transfers, exact-range resume, ignored-range restart, cancellation, corrupt
  cache/hash rejection and retry bounds.
- Both public model ZIPs were actually downloaded anonymously from their fixed
  release URLs with full size/SHA-256 verification. The same full check reverified
  cached publisher originals (`out/public-model-full-downloads.json`). No token
  is passed by the download implementation. A live HTTP Range probe returned
  206 with the expected total sizes for both model archives.
- Four Korean/English model-setup renders at minimum width passed without QML
  warnings; screenshots were inspected for readable size/license/action text
  (`out/public-model-setup-ui/report.json`). These are fixture states, not network
  progress recordings.
- Final ZIP checksum extraction into a new directory passed. Qt static/delay
  imports: **121 binaries**, no missing Qt dependency
  (`out/public-model-dependencies.json`).

- Fresh packaged setup with isolated model/engine caches successfully built
  Small, Base's two and VDA's four engines. Each model converted a generated
  12-frame 320x180 Half Top-and-Bottom clip, retained audio, and passed full
  decoding (`out/public-model-first-use-qa/report.json`). This GUI run reused
  the full-hash-verified archives downloaded by the preceding anonymous check;
  it did not download a second copy of every model/runtime. It explicitly
  required remote public model sources and no bundled Base/VDA packs.
- Final read-only verification confirmed public model release metadata and
  anonymous manifest/checksum downloads, source/Small hashes in the extracted
  app, no bundled Base/VDA, and the unchanged private source repository
  (`out/public-model-delivery-verified.json`).
- Extracted `ScreenTo3D.exe` showed its owned main window under a Windows-only
  PATH and closed normally with exit code 0
  (`out/public-model-extracted-launcher.json`).

These are short functional checks on Windows/RTX 5090, not new long-session,
other-GPU or physical stereo quality acceptance.
