# Bundled models, official downloads and VDA validation, 2026-11-12

Local, unreleased candidate over `b3b76868eb9348c9a74228591a8521acf417eaaa`.
No commit, push, repository-visibility change or remote release replacement was
performed. Tests below ran on Windows with RTX 5090; they do not establish other
GPU support or physical stereo quality acceptance.

## Installation and distribution

The app includes DA2 Small and the verified Base/VDA ONNX archives. Base's pack
is 392,348,171 bytes; VDA's is 363,291,834 bytes. Engine compilation remains local
to the user's GPU. Common TensorRT/CUDA, selected GPU resources, FFmpeg and
optional VFG use fixed original publisher URLs rather than private release
attachments. All four upstream artifacts were downloaded in full and SHA-256
verified (`out/upstream-full-downloads.json`).

| Original archive | Bytes | Pinned version |
| --- | ---: | --- |
| TensorRT CUDA 13 Windows libraries | 1,957,705,017 | 11.2.1.2 |
| CUDA runtime | 3,093,656 | 13.1.80 |
| FFmpeg shared build | 97,261,187 | 9.0.1 |
| NVIDIA VFX wheel | 435,809,365 | 0.2.0.0 |

Exact URLs, sizes and full hashes are owned by
`v1/depthsbs_app/upstream_sources.json`. Cache reuse performs a fresh full hash
check. Interrupted partial files use validated ranges, and ignored ranges restart
safely. Retries and per-artifact process locks are bounded. TLS downgrade, wrong
length/hash, unsafe paths and corrupt payloads are rejected. Runtime and GPU
resource installation reuse the same original TensorRT archive.

The official wheel and SDK have different signed DLL bytes. All 11 differing
DLLs matched after excluding only PE checksum, certificate-directory entry and
Authenticode certificate table (`out/upstream-pe-comparison.json`). Installation
accepts explicitly pinned full hashes for these variants; it does not normalize
or modify binaries. Original-derived payload inventories passed
(`out/upstream-payload-qa/report.json`).

Packaging checks anonymous HTTPS availability and archive prefix/length for all
four fixed sources before writing final assets. The full-hash pre-release command
also passed using cached originals (`out/upstream-pre-release-check.json`). The
production embedded interpreter independently passed all four anonymous probes
(`out/official-embedded-network.json`). These bounded probes are availability
checks, not a promise of future uptime or a full remote hash check on each build.

## VDA engine reference rejection

The reported `E_ENGINE_OPTIMIZATION` NumPy mismatch was reproduced during fresh
packaged setup. A captured rejected 518x896 candidate failed the former
per-element intermediate-cache tolerance while its final-depth reference samples
passed. The captured cache's maximum tensor-relative RMSE was 0.6325%; its
maximum error normalized by reference tensor RMS was 2.116%. Retrying alone did
not reliably solve the problem. Neither directory layout nor the official DLL
signature variant was established as the numerical cause.

The explicit `vda-fp16-cache-v1` contract permits intermediate `*_new_cache_*`
tensors to pass either the existing pointwise comparison or both of these bounds:
relative tensor RMSE <= 1%, and maximum absolute error/reference RMS <= 3%.
Shape and finite-value checks remain mandatory. Final-depth acceptance remains
`atol=rtol=0.001`; Base's tolerance remains unchanged. A contract failure allows
one bounded candidate rebuild, followed by the same checks. Receipts record the
contract and attempt count. Failure diagnostics use localized
`E_ENGINE_REFERENCE_MISMATCH` or `E_ENGINE_REFERENCE_SCHEMA` rather than an
unknown-error NumPy dump.

The rejected candidate was compared with the baseline on 48 frames of public
FloorballGame video, using independent 42-entry histories. Maximum full-depth
relative RMSE was 0.03653%, and maximum depth-span-normalized MAE was 0.01682%
(`out/vda-candidate-sequence.json`). The largest raw depth difference was 0.16321;
up to 1.0125% of pixels in one frame exceeded the former pointwise depth
threshold. Thus these measurements do not demonstrate pixel identity or visual
SBS equivalence. They provide a bounded numerical observation for this candidate,
not a universal quality guarantee for every future tactic or GPU.

The small synthetic regression fixture and provenance are repository test
inputs in `v1/tests/fixtures/vda-fp16-candidate-896.*` (no video, weights or
executable engine). Tests accept the observed cache variant while rejecting
excess bias, zero cache, sparse spikes, changed final depth, NaN and invalid
signatures. Generic strict-reference and bounded-retry tests remain.

## Verification and final artifact

- Core/platform/Qt: **318 passed**, including download integrity/resume/retry,
  cache ownership, setup cancellation and engine-reference regression checks
  (`out/official-complete-contracts.json`). File controller: **23 passed**
  (`out/official-controller-final.log`).
- Fresh isolated packaged setup built Small, Base and VDA engines and converted
  12 frames of 320x180 Half Top and Bottom output per model, retaining audio;
  full output decoding passed (`out/official-complete-qa/report.json`). Setup
  reused previously full-hash-verified original archives rather than downloading
  another 2 GB during the GUI run. This is a short functional check, not a
  long-session performance or physical display test.
- Four Korean/English narrow setup fixture renders passed with no QML warnings;
  screenshots were inspected (`out/official-setup-ui/report.json`). Fixture
  progress illustrates resume copy; it is not an actual network progress capture.
- Static/delay Qt imports: **121 binaries**, no missing dependency
  (`out/official-complete-dependencies.json`).
- Final checksum extraction into a new directory and launch/normal close of its
  EXE with a Windows-only PATH passed
  (`out/official-complete-final-launcher.json`).

Final app: `out/official-complete/ScreenTo3D-1.0.0/ScreenTo3D.exe`.
Final ZIP: `out/official-complete/final-assets/ScreenTo3D-1.0.0-windows-x64.zip`.
ZIP size **822,256,200 bytes** (about 822 MB / 784 MiB); unpacked app
**1,184,529,305 bytes**, 3,248 files. ZIP SHA-256:
`1b4b5d5e7678741aa03f041187a12e82e4d077d8400f3053ee0e1acb8cd0527b`.

Public GitHub download feasibility was researched separately in
[the public-distribution report](github-public-downloads-20261112.md).
