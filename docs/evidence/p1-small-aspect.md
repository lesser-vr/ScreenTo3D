# P1 DA2 Small rectangular-input experiment — 2026-09-09

## Decision

**Not selected for product integration.** HxW 392x700 did not show a speed benefit
in this bounded run, had a visible thin-object tradeoff, and did not pass every
predeclared numerical check. This rejects immediate promotion of this tested
candidate, not all aspect-preserving inputs or alternative preprocessing.
The product's existing 518x518 engines, loaders and rendering path are unchanged.

## Comparison contract

Same pinned DA2 Small ONNX weights, cubic uint8 RGB resize, float32 ImageNet
normalization, source frames, runtime and GPU; only model HxW changes from
518x518 to 392x700. The square preprocessing result was tested exactly against
`pipeline.preprocess`. The candidate is approximately 16:9 (0.45% ratio error),
not exact aspect preservation. Patch count is 1369 versus 1400 (+2.3%).

Input media: the original, checksum-pinned **3840x2160** public UVG-VCM
FloorballGame, OfficeWalk and ParkingGarage clips, six consecutive frames each.
Unlike the earlier P0 cost diagnostic, these are not enlarged 1080p previews.
Source hashes are in the reports and `public_test_media.SOURCES`. Attribution:
UVG-VCM, QoMEX 2026, CC BY 4.0; generated review images are resized and annotated
derivatives. See <https://tie-ultravideo.rd.tuni.fi/UVG-VCM/index.html>.

Each shape receives ten warmup calls at the first frame of each clip, then five
timed calls per frame; shape order alternates by frame. There are 90 timings per
shape, not 90 independent scenes or sustained live windows. Both engines remain
resident; runs execute sequentially. No unrelated GPU processes were terminated.
Preflight: RTX 5090, driver 616.64, 0% utilization, 4562 MiB GPU-wide memory.
Torch 2.7.1+cu128, TensorRT 11.2.1.2, one Torch CPU thread, ORT CPU oracle with
four intra-op threads. Engine build logs retain exact arguments.

Wall timing includes source RGB preprocessing, upload, inference, synchronization
and diagnostic depth readback. CUDA events cover only the TRT stream interval.
Neither includes capture, depth postprocessing, stereo synthesis, FG or scanout.
No per-eye/SBS output was produced; the product target remains 3840x2160 per eye /
7680x2160 Full SBS, not a geometry validated by this depth-only test.

## Results

Pooled medians in milliseconds, taken independently (do not add columns):

| ONNX storage / build | HxW | Preprocessing | TRT stream | Host wall |
|---|---|---:|---:|---:|
| FP16 graph, default TRT build | 518x518 | 3.732 | 1.407 | 5.947 |
| FP16 graph, default TRT build | 392x700 | 3.783 | 1.426 | 6.036 |
| FP32 graph, default TRT build | 518x518 | 3.651 | 3.297 | 7.744 |
| FP32 graph, default TRT build | 392x700 | 3.722 | 3.414 | 7.920 |

The observed rectangular wall differences are +1.5% and +2.3%, respectively;
short-run variation prevents treating these as a general slowdown estimate.
FP32 here describes the source graph; default TRT TF32 behavior was not disabled,
so it is not a strict IEEE-FP32 kernel experiment. It is also not a proposal to
replace the product's FP16 graph with a slower graph.

### Numerical checks

For the first frame of each clip/shape, reuse the existing reference-check budgets:
MAE <= .01, RMSE <= .015, max absolute <= .05, mean relative <= .01 and
correlation >= .999. These were not relaxed after observing failures.

- FP16 TRT versus FP32 ORT: **0/6 passed**. Both shapes exceed the max-error gate;
  ParkingGarage rectangular also fails the relative-error gate.
- FP16 TRT versus the **same FP16 ONNX** in ORT: **1/6 passed** (rectangular
  FloorballGame). Both baseline and candidate retain local numerical deviations;
  this cannot be attributed solely to a different source-graph precision.
- FP32-graph TRT versus FP32 ORT: **5/6 passed**. Rectangular ParkingGarage fails
  mean relative error (.05196), despite MAE .00128, max absolute .04649 and
  correlation .999999897. Relative error uses a 1e-6 denominator floor and is
  sensitive to near-zero depth; the failure is retained, not declared harmless.

These are new natural-frame checks, not evidence that an earlier gradient-only
reference result was false. Nor does high correlation certify depth or VR quality.

### Limited visual inspection

Inspected first-frame paired depth images for all three scenes in the FP16 run,
plus FloorballGame in the FP32-graph run. The previews share one 2%/98% display
range per pair (no independent contrast fitting), with source / square /
rectangular panels. Rectangular input changes room/car contours and foreground
depth placement, but the foreground floorball stick is much less represented;
the same tendency is visible in the FP32-graph preview. No consistent spatial
quality win is established by these few stills. Remaining stills, moving output,
thin-text/HUD cases, depth temporal behavior and binocular/HMD review are unreviewed.

## Provenance and reproduction

Build from the checksummed ONNX files in `out/models/da2-small` using the pinned
manifests in `models/da2-small`. Use a fresh experiment directory and the local
`trtexec.exe` with `--minShapes`, `--optShapes`, `--maxShapes` all set to
`pixel_values:1x3x518x518` or `pixel_values:1x3x392x700`, `--skipInference`, and
`--memPoolSize=workspace:2048`. Save as `small-518x518.plan` / `small-392x700.plan`.
Do not supply externally sourced serialized engines to this local-build diagnostic.
Then run `python v1/compare_small_aspect.py --directory <experiment-directory>`
in the prepared model environment; add `--model-precision fp32` only for engines
built from the FP32 graph. This flag records provenance, not an automatic cast or
an engine-authentication mechanism. Engine/source hashes are included in reports.

Local ignored output roots:

- `out/p1-small-aspect-20260909`: initial FP16 build/report and six review images.
- `out/p1-small-aspect-oracles-20260909`: same built engines; adds same-graph oracle.
  Report SHA256 `b16d60b3de3ee0e815fdb9cccc949b733ce25e6b9437a2ba73e633276059abf3`.
- `out/p1-small-aspect-fp32-20260909`: fresh FP32-graph builds and comparisons.
  Report SHA256 `8fe8ddac3ae392990dec78042f7d325908866fed9f6b81e81e010f8e738b50ea`.

Final reports were published after both engines closed. Three new CPU unit tests
and Python compilation passed. The experiment is isolated from the application;
no default, package, model allowlist or history policy changed, and no commit/push
was performed for this experiment. Distill Small A/B and temporal/occlusion work
have not been completed by this rectangular-input test.
