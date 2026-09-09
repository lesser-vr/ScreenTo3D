# P1 Distill Any Depth Small — controlled first comparison, 2026-09-09

## Decision and scope

**Retained for further evaluation, not selected as the product default.** The
official Small checkpoint loads strictly into the reviewed DA2 Small depth
architecture, exports at 518x518, and its FP32 TensorRT output passes bounded
numerical checks. The first controlled stereo comparison establishes feasibility,
not superiority over iw3, the current FP16 live product or another depth model.

The initial P0/P1 work was committed as `8358820`; the diagnostic files and this
record were created subsequently. No application binding, default, model allowlist,
package or temporal policy changed. No push was performed.

## Artifact and source trust

- Official source: [Distill-Any-Depth at
  `6d8f415392eafb49c96a38cc4dedbd09a1607f50`](https://github.com/Westlake-AGI-Lab/Distill-Any-Depth/tree/6d8f415392eafb49c96a38cc4dedbd09a1607f50).
  Its README links the original `small/model.safetensors` checkpoint, rather than
  the separately converted Transformers checkpoint. Source license is MIT.
- Weight repository revision: `38095a41cca1e28a28e8bb6372c68df721455a2d`,
  `xingyang1/Distill-Any-Depth`, `small/model.safetensors`, 99,165,428 bytes,
  SHA256 `56a173c0e1b5045bf6296a5c1fb16eace0bbde2eddc24b37532cb1774ac09caa`.
  The [pinned model card](https://huggingface.co/xingyang1/Distill-Any-Depth/blob/38095a41cca1e28a28e8bb6372c68df721455a2d/README.md)
  labels the weights Apache-2.0. This local comparison does not bundle them for release.
- Both local source checkouts are revision-pinned and checked clean before use.
  All 11 common Python backbone/helper files match the existing pinned DA2 source
  byte-for-byte; the fusion builder, convolution block and DPT head match as ASTs.
  Reviewed `DepthAnythingV2` differences are hub mixin support, an unused shape
  unpack, and returning auxiliary features plus an unsqueezed depth tensor.
  The experiment uses the existing DA2 depth-only class, excluding hub/demo code
  and auxiliary features. Strict state loading succeeds; 24,785,089 parameters.
- `safetensors==0.6.2` was installed only in `out/distill-python-deps`. No
  Transformers, Diffusers, hub remote code, xFormers or Detectron2 was installed
  or executed. Serialized engines were built locally from the verified export.

## Controlled comparison contract

Original checksum-pinned UVG-VCM FloorballGame, OfficeWalk and ParkingGarage,
3840x2160 at 60 fps, first 30 contiguous frames per clip (0.5 seconds each).
Source/derivative attribution: UVG-VCM, QoMEX 2026, CC BY 4.0;
<https://tie-ultravideo.rd.tuni.fi/UVG-VCM/index.html>. Source hashes are in the report.

Both models use the product's RGB cubic-uint8-resize/ImageNet normalization at
518x518. This deliberately compares a model replacement at the existing input
contract, not the official demo's 700x700 preprocessing. The baseline is the
pinned FP32 DA2 ONNX, not a claim that the installed FP16 product uses FP32.
Both engines are FP32 with TensorRT TF32 explicitly disabled. Torch oracle TF32
is also disabled. FP16 cost/quality is not established by this run.

The same Performance stereo policy, source-resolution CPU guide/normalization/EMA
and pinned paired CUDA projection are used for both. History and percentile
normalization are independent per model; no model frame reuse occurs. This is a
controlled reference renderer, **not the optimized native live GPU renderer**.
Every generated pair was checked as 7680x2160 Full SBS, 3840x2160 per eye.

RTX 5090, driver 616.64, Torch 2.7.1+cu128, TRT 11.2.1.2. One Torch CPU thread,
four ORT oracle intra-op threads. Both engines and the Torch oracle remain resident;
model order alternates per frame. Ten warmup calls/model at each clip start.
No desktop/private capture, unrelated-process termination, recording, FG or
headset session was performed. Saved outputs are public-media PNG review stills.

## Executed results

- **180 stereo pairs**: 90 unique source frames through two models. This is not
  180 unique source frames and not sustained real-time throughput.
- **12/12 numerical checks passed**: first and last frame of each clip/model,
  per-pixel `allclose(atol=.001, rtol=.001)`. Distill reference is the loaded
  Torch model; DA2 reference is pinned FP32 ONNX in CPU ORT. Maximum absolute
  difference across all checks: **0.00017238**. All rendered depths were finite.
- Three new CPU tests cover per-pixel gate failure, invalid output rejection and
  visible image-write failure. Python compilation passed.
- All owned CUDA projection/engine/oracle resources were closed before final
  report publication. After process exit, GPU-wide utilization/memory returned
  to 0% / 4562 MiB in the sampled check; this is not a leak soak.

TRT stream P50 in ms (30 samples/model/scene; no general speed claim):

| Scene | DA2 FP32 | Distill FP32 |
|---|---:|---:|
| FloorballGame | 4.348 | 4.476 |
| OfficeWalk | 4.613 | 4.501 |
| ParkingGarage | 4.625 | 4.517 |

Inference plus diagnostic upload/readback wall medians were 5.24–5.62 ms;
source preprocessing is outside this interval. Reference stereo host medians
were 322.5–334.1 ms, dominated by the deliberately unfused reference path.
Do not substitute these for the product's live stereo performance, sum these
separate medians into a supported rate, or compare them directly with the earlier
FP16/default-TF32 aspect experiment as if conditions were matched.

Median consecutive-frame normalized/EMA depth-change MAE, an unsigned proxy:

| Scene | DA2 | Distill |
|---|---:|---:|
| FloorballGame | .003970 | .003838 |
| OfficeWalk | .008445 | .007809 |
| ParkingGarage | .000883 | .000673 |

Less change can also mean smoother, less accurate or lagging depth. These values
do not establish reduced flicker, better motion handling or ground-truth accuracy.
This run contains no deliberately inserted scene cuts or long motion sequences.

## Follow-up precision probe (2026-09-09)

Two isolated ONNX conversion recipes were built from the validated fixed FP32
export. Both keep float32 I/O and block FP16 conversion for Resize,
LayerNormalization and Softmax. The `fp16-head` recipe additionally blocks
non-depth-head nodes. TF32 remains disabled. This is the converter's block-list
recipe, not proof that every encoder intermediate stays FP32: the resulting
head-policy graph contains 946 Cast nodes. An inspection found all 174 matched
non-head float32 initializers unchanged and inspected encoder Conv/MatMul inputs
float32, but cast boundaries can still quantize intermediate activations.

Each recipe used six contiguous original-4K frames from each of the three public
clips: 18 unique frames, five timed calls/frame, five warmup calls at clip starts.
The unchanged per-pixel Torch FP32 reference budget was atol=.001, rtol=.001.

| Recipe | Numerical checks passed | Worst absolute error | Worst frame MAE | TRT interval P50 |
|---|---:|---:|---:|---:|
| FP16 eligible graph | 0/18 | .164255 | .003583 | 1.488 ms |
| FP16 head block-list | 0/18 | .084383 | .002332 | 1.602 ms |

**Neither recipe is selected.** These are precision-preservation gate failures,
not an established perceptual defect or a ban on FP16 under a separately declared
quality contract. The earlier FP32 timing used different surrounding work, so
the intervals above do not establish a matched speedup or live FPS. No threshold
was relaxed and neither engine was passed on as a qualified model for longer
motion comparison. Longer motion/FP16-native acceptance is still pending; the
previously validated FP32 path remains available as a reference.

The precision probe closed each engine and the Torch model before report
publication. Two graph-ordering/rejection tests were added; all five Distill
diagnostic unit tests and Python compilation passed. Local artifacts are in
`out/p1-distill-precision-20260909`; `report.json` SHA256 is
`65333a6f27391f72e7126a45a8aba91485c85f93460456c701e0379dcab4f24f`.
Reproduce with `v1/distill_precision_probe.py --output <fresh-directory>` in the
same prepared environment. Reports contain graph/engine hashes, per-frame errors
and timing samples; they do not authorize production artifact loading.

## Limited visual review

Inspected first-frame depth comparisons for FloorballGame and OfficeWalk, plus
native-pixel first-frame left/right crops from all three scenes. Distill preserves
the foreground floorball stick at this square input, unlike the earlier rejected
rectangular-input example, but the current square DA2 also represents it. Room
object depth placement changes; the final stereo crops show only modest local
differences. No consistent winner can be selected from these stills.

The review crops show both eyes separately, not fused binocular perception.
Full-frame last-frame stills, motion playback, thin HUD/text, scene cuts and
OpenVR/Desktop+/Quest 3 perception/comfort remain unreviewed. Before promotion,
a practical precision/runtime comparison and a longer matched motion/stereo
comparison are needed. Temporal/occlusion algorithm work remains separate.

## Local artifacts and reproduction

`out/p1-distill-small-20260909` contains `export.json`, the verified fixed-518
ONNX, local engines, build logs, and `comparison/` with 12 full-resolution SBS
PNGs, six depth overview PNGs, three eye-crop sheets and the report.
`comparison/report.json` SHA256:
`c61666e6130ff9f640a3a5888ed3a7380cec16e00c7839c1fe48213430172627`.
These are ignored local artifacts, not release assets. The initial static-build
failure log is retained: explicit dynamic-shape arguments were rejected for the
fixed export; the corrected build omitted those arguments, without graph changes.

Use the prepared GPU Python environment with `out/distill-python-deps` appended
to its module path. Run `v1/distill_small_experiment.py --output <fresh-directory>`.
Build the candidate ONNX as `distill-small-fp32.plan` with local `trtexec`,
`--noTF32 --skipInference --memPoolSize=workspace:2048` (no dynamic-shape flags).
Build the pinned baseline FP32 ONNX as `da2-small-fp32.plan` with the same flags
and all min/opt/max `pixel_values:1x3x518x518` because that graph is dynamic.
Then run `v1/compare_distill_small.py --directory <directory> --frames 30`, followed
by `v1/review_distill_small.py --directory <directory>/comparison` if eye crops
are needed. Never use externally supplied serialized engines in this diagnostic;
the report hashes record the controlled local build, not authentication of arbitrary
third-party engines. A partial report is not a completed result.

## Longer GPU-postprocessor comparison (2026-09-09)

The validated FP32 pair was subsequently evaluated with
`v1/distill_gpu_motion.py`: three original-4K public clips, first 360 frames/six
seconds each, both models. **1,080 unique source frames, 2,160 rendered SBS pairs**,
six HEVC videos. Each eye is 3840x2160; combined SBS is 7680x2160 at encoded 60Hz.
All six files decoded to the expected 360 frames and exact combined geometry.
Encoded rate is a timestamp contract, not processing throughput.

Both pinned, locally built engines use FP32 with TF32 disabled. The actual
`LiveGpuCandidate` Performance GPU postprocessor, guide, normalization/history
and paired projection are used, followed by **host SBS readback** and NVENC
recording. No WGC, native Qt texture presentation, headset or private capture.
Six first-frame host/device preparation comparisons passed the .001 absolute /
.001 relative per-pixel budget. Sixteen warmup calls precede each clip/model,
then history resets. Model order alternates between clips, not between frames.

Processing wall P50 (ms), 360 samples per cell:

| Scene | DA2 FP32 | Distill FP32 |
|---|---:|---:|
| FloorballGame | 36.765 | 36.620 |
| OfficeWalk | 36.827 | 37.178 |
| ParkingGarage | 35.944 | 36.021 |

Intervals cover inference and GPU render/host readback; source decode, RGB
conversion and encoder writes are outside them. Encoder GPU contention may still
affect timing. This is not a native-live rate measurement, no clear speed win,
and not a matched benchmark against the FP16 installed default.

`v1/review_distill_motion.py` decoded all six recordings and generated 384x384
native-pixel eye crops at frames 0/60/120/180/240/359. All three sheets were
inspected (viewer resized the sheet): foreground leg/stick, furniture/cables/chair
and vehicle detail remain present in both candidates. Chair/foreground boundary
distortion remains visible in both. The sampled crops do not establish a
consistent winner or binocular comfort. They are **not motion playback**, and
do not establish ghosting-free output. Thin HUD/text, games, cuts and actual
OpenVR/Desktop+/Quest 3 review remain unpassed. This longer bounded experiment
supersedes the earlier statement that no longer GPU motion sequence was run,
but does not supersede the visual/VR limitations.

Decision: retain Distill FP32 as an experimental reference; do not replace the
product model. The two FP16 recipes remain rejected under their preservation
contract. P1's bounded comparison branch ends without promotion, not with a
claim that all perceptual acceptance is complete.

Completed run: `out/p1-distill-gpu-motion-run2-20260909/report.json`, SHA256
`14a87f439d4dbf06fcdeff10ac6d877980c403acc69ab53b6cdc89c27a157be6`.
The report records engine/video/DLL/script hashes and all timing rows. The first
attempt stopped before GPU initialization because dependency access was denied;
the second used the existing dependency environment with approved access.
No new CUDA package was installed.

Owned engine, GPU postprocessor and encoder resources were closed before final
video names/report publication. Subsequent diagnostic hardening guarantees the
encoder is waited on even if its input close raises BrokenPipeError, and makes
review-image write failures visible. Three mock cleanup tests cover broken pipe,
failure cleanup and timeout/kill/wait. These are failure-path unit tests, not a
hardware failure soak; the successful GPU run predates that hardening and retains
its original script hash. Eight Distill tests plus seven temporal tests passed.
