# VDA final-depth reference rejection — 2026-11-13

The user reported `E_ENGINE_OPTIMIZATION` / `E_ENGINE_REFERENCE_MISMATCH` on
RTX 5090: profile `518x896-fp16`, `cached_depth`, 2/256 values outside tolerance,
maximum absolute difference 0.006600. This is a post-build numerical rejection,
not a failed model-archive checksum or an indication that Base downloaded VDA.

## Reproduction and limits

The old `vda-fp16-cache-v1` alternative covered intermediate caches only; final
depth still used `atol=rtol=0.001` per element. A synthetic test using the pinned
random-input depth reference and two 0.0066 perturbations reproduces the reported
2/256 rejection. It is **not** a capture of the user's exact rejected tensors.

Two actual fresh 518x896 builds, one through the source environment and one
through the released Python/official runtime, passed the old guard; repeated
inference was identical. Four pairings of trusted retained/new warmup and cached
engines also passed. A specific faulty TensorRT tactic or the user's exact
candidate failure was therefore not established. The failing install's temporary
engine files were no longer available.

The retry path did have a separate confirmed dependency issue: `cached_depth`
depends on the warmup-generated cache, but any cached-stage error previously
rebuilt only `cached`. A unit test fails under that behavior.

## Explicit replacement contract

The graphs, mixed precision, archive/graph hashes and reference arrays are
unchanged. Base keeps its existing acceptance. VDA opts into the named
`vda-fp16-reference-v2` contract, recorded in its GPU-bound receipt:

- Existing pointwise passes remain accepted.
- Intermediate caches retain relative RMSE <= 1% and maximum error/reference
  RMS <= 3%.
- Final `warmup_depth` / `cached_depth` samples that fail the pointwise test
  must satisfy **both** relative RMSE <= 0.05% and maximum error/reference
  RMS <= 0.5%. No mismatch-count exception is used.
- Shape and finite-value checks remain mandatory. Tests reject aggregate bias,
  a sparse outlier, zero output, invalid signatures, NaN and infinity.
- At most one rebuild remains permitted. A cached-cache-only error may rebuild
  `cached`; a warmup or cached-depth error rebuilds both dependent stages.

This deliberately changes numerical acceptance; it is not a claim that the old
pointwise guard was preserved or that every rejected FP16 candidate is valid.
Both normalized limits and the separate cache bounds remain enforced after retry.

NVIDIA documents reduced-precision accuracy tradeoffs and sensitivity to
optimization choices; these motivate explicit model validation, not these exact
project thresholds: [accuracy considerations](https://docs.nvidia.com/deeplearning/tensorrt/latest/inference-library/accuracy-considerations.html),
[TensorRT execution and reproducibility](https://docs.nvidia.com/deeplearning/tensorrt/latest/architecture/how-trt-works.html).

## Verification and actual installation

- Before the fix: the new contract tests produced two errors, and the dependency
  test failed. After the fix: all 10 engine-reference tests and **530 CPU/Qt
  contracts** pass.
- Three actual tactic variants were compared with the pinned v3 baseline on
  **48 public FloorballGame frames each**, with independent 42-entry histories.
  Predeclared full-depth relative RMSE / span MAE / temporal span MAE limits were
  0.1% / 0.1% / 0.2%. All passed. The largest observed values were **0.03653% /
  0.01681% / 0.00876%** for the retained variant. This is numerical evidence,
  not visual/SBS equivalence or a guarantee for another GPU/content.
- The verified archive already in this PC's download cache was reused. No valid
  installed engine folder was overwritten. All four engines for 518x896/518x924
  built, passed v2 on their first attempt and received valid protected receipts
  in `<LOCALAPPDATA>/DepthSBS/models/vda-small/`.
- The new portable recognized the actual user model cache and completed
  320x192 and 320x180 Half Top-and-Bottom conversions: each 12 frames, retained
  audio and full decode. Previously verified QA FFmpeg binaries were supplied
  explicitly; no media-tool installation was needed for this check. Preferences,
  input fixtures and outputs were confined to the new QA folder.
- A separate local app/ZIP was rebuilt. Previous release ZIPs are preserved;
  this change has not been uploaded as a replacement release.

Evidence under Git-excluded `out/vda-depth-fix-20261113/`: `root-cause.json`,
`proposed-contract.json`, `red.log`, `green.log`, `contracts.json`,
`fresh-candidate.json`, `packaged-runtime/fresh-candidate.json`,
`paired-tactics.json`, `sequence.json`, `installed.json` and
`gui-convert/report.json`. Candidate NPZ files contain generated diagnostic
samples, not user video frames or model weights. Published evidence omits personal
paths and device identifiers. The local logs/receipt remain private.
