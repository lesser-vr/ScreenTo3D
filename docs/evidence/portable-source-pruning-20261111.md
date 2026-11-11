# Portable development-source pruning, 2026-11-11

Local unreleased packaging-only change on the existing dirty working tree.
`portable_package.py` now excludes `.c`, `.cc`, `.cpp`, `.cxx`, `.cu`, `.pyx`,
`.pxd` and `.pxi` files from packaged dependencies. License/copyright/notice
exceptions retain priority. DLL/PYD, Python, QML and other runtime data rules are
unchanged. Repository/development sources and previous candidates are preserved.

The ordinary desktop builder produced
`out/source-pruned/ScreenTo3D-1.0.0/`. For local storage only, byte-identical binary
files were hardlinked from the previous immutable candidate; source/config files
were copied. The builder's normal exclusion callback and artifact validation
still ran. The storage inventory is `out/source-pruned/build-storage.json`.

## Measured results

| Scope | Previous candidate | Source-pruned candidate |
|---|---:|---:|
| App bytes | 1,648,735,237 | 1,523,539,309 |
| App files | 4,793 | 4,667 |
| App ZIP bytes | 788,372,541 | 778,370,865 |

`out/source-pruned/inventory.json` confirms exactly 126 dependency source files
removed (125,196,005 bytes), no additional paths, and all 50 license/notice files
byte-identical. The only changed retained files are the pruning policy module,
build manifest and newly compiled launcher. All retained runtime binaries other
than that launcher match the prior candidate. The ZIP saving is 10,001,676 bytes;
installed-file and download savings have different scales because source text
compresses well. GPU-resource packs, model graphs/precision and user GPU engine
generation remain unchanged. Generated caches are not part of these app sizes.

## Validation and limits

- `out/source-prune-core.json`: 117 core contracts pass. New coverage checks all
  eight source suffixes, case handling, runtime-module retention and license
  exceptions without importing CUDA or Qt.
- `out/source-prune-desktop-qa/report.json`: the embedded interpreter with a
  Windows-only PATH and another empty isolated user cache builds a new Small
  engine, produces native Half TB, switches Korean/English in the same worker,
  releases texture pools and converts two real queued inputs with expected
  decoded frames/geometry/audio. No QML warnings occur.
- `out/source-prune-model-qa/report.json`: fresh Base and VDA installs build and
  numerically validate two and four engines respectively using the packaged
  interpreter without development sources. Both then complete a real 12-frame
  conversion with decoded audio, geometry and frame count verified.
- `out/source-pruned-delivery/report.json`: actual final app ZIP plus only the
  selected SM120 ZIP pass the distributed checksum-verifying extractor into a
  new directory; 4,667 disjoint application entries satisfy the pruning policy.
  Representative extracted native/application/media files match the prepared app.
  `out/source-prune-launcher.json` confirms the extracted native EXE opens its
  owned main window and exits normally with isolated PATH. The extracted
  interpreter repeats the native/queue checks in `out/source-prune-delivery-qa/`.
- Unchanged algorithms, runtime DLL/PYD files and model graphs retain the prior
  [native CUDA numerical/4K evidence](native-cuda-memory-20261111.md). This source
  exclusion does not introduce a new quality or throughput claim.

Only owned generated media/window sources are used. Actual GPU tests use RTX
5090; this is not clean-machine or other-GPU certification. The public 1.0.0 tag
and release artifacts are unchanged. No commit/push is part of this work.
