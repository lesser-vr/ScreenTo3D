# Base FP16 default and Small precision review

2026-11-05. User explicitly selected the broadly converted FP16 candidate after
the [native FPS/spatial/temporal comparison](base-fp16-native-20261105.md).
This is an intentional precision/speed tradeoff, not a claim of FP32 numerical
parity or physical binocular acceptance. Selective FP16 was not promoted.

## Delivered Base change

Normal source-app Base live, explicit host/reference rendering and file conversion
now use mixed-FP16 TensorRT plans. Input/output, preprocessing, source-aspect
padding/cropping, depth postprocessing and native delivery keep their FP32
contracts. Resize, LayerNormalization and Softmax remain FP32 in the model graph.
No precision selector, implicit fallback, dependency upgrade or change to the
ordinary 30 Hz presentation target was added. A 60 Hz diagnostic target in the
earlier speed comparison is not a changed user default.

Both profile folders were installed beside the retained original FP32 folders;
no original engine was overwritten. The normal loader now selects `*-fp16` and
checks exact plan hash/size, runtime, GPU and FP32 tensor signatures. The backend
description and file-worker event report `tensorrt-fp16`; engine telemetry captures
the loaded hash/precision and explicitly records `io_precision=fp32`.

| Installed path below `out/da2-base-local/` | Bytes | SHA256 |
|---|---:|---|
| `518x896-fp16/model.plan` | 200603884 | `a8718fa657e73f7506ab71367e4ec2d4600338bb72a8d2c142c94e7ef0a86eb7` |
| `518x924-fp16/model.plan` | 200667716 | `0216c0493714c120ebe261d29eb10b3eadb52ca8fc5934192aa2dbf2570bd9bd` |

The 924 plan is the exact measured mixed candidate. The 896 plan was built using
the same conversion recipe and TensorRT 11.2.1.2, from the pinned FP32 ONNX
`ea4395b7864fbeb6c4819a469006166d559ed124a5e9511273e00484aab4beec`.
Its converted ONNX hash is
`a955082568d50df8b5e140ce0d62ab67beebcb8c25f9ffd87d067c8a027430e1`, identical to
the earlier 896 mixed graph; the new plan took 24.32s to build. Build result:
`out/base-trt-fp16-896-20261105/report.json`. A new build hash still requires
explicit validation/pinning; this is not a general artifact installer.

The test-only FP32 adapter and recent precision probes now explicitly select
retained FP32 controls, avoiding mislabeled comparisons after the default change.
The older app-check harness reports FP16-versus-FP32 error separately from its
functional pass and keeps the strict allclose assertion for FP32 runs.

## Completed checks

- 35 scoped unit tests: 11 Base geometry/loader/device ownership, 3 diagnostic
  loader integrity/restoration, 8 live backend routing and 13 desktop job checks.
- `out/base-fp16-default-parity-20261105`: 24 real-engine cases across 1080p,
  ultrawide, portrait and 4K, including cuts and flat-background refinement.
  Host/device raw depth is exact; GPU/CPU input SBS is exact; native texture/GPU
  host output is exact. Existing legacy CPU-post tolerances also pass unchanged.
  This compares paths using the same new FP16 engine, not FP16 against FP32.
- `out/base-fp16-default-lifecycle-20261105`: actual ordinary native app launch
  with no trial adapter; hide/restore, page restore, resize, fullscreen/Escape,
  stop/clear, restart/source loss, worker crash and preparation cancellation pass.
  Capture exclusion remains; cleanup asserts zero pools/nodes. The saved report's
  `native_delivery` snapshot is from running state, before the subsequent teardown
  assertions, and should not be interpreted as leaked final resources.
- `out/base-fp16-default-files-20261105`: ordinary file worker converts eight
  public frames each at 1056x608 H.264 and 1280x720 HEVC. Both profiles report
  `tensorrt-fp16`, FP32 I/O and the correct model shape. Full output decoding
  confirms eight frames at exactly double source width, with no source overwrite.
- Ruff E9/F and whitespace validation pass. No portable bundle was rebuilt;
  restart source GUI instances to use updated code. No commit/push was requested.

Prior FP32 continuous-playback evidence is not a new FP16 soak test. The earlier
924 FP16 spatial/temporal error limitations, licensing and hardware scope remain.
The 896 profile has functional parity coverage here, not a new sustained or
binocular-quality acceptance claim. RowFlow viewing remains deferred; no renderer
or physical quality promotion is inferred from choosing FP16.

## Small FP16 review

**Small already uses FP16; there is no missing half-precision switch to enable.**
The installed ONNX matches `models/da2-small/model-manifest.json` exactly:
49,642,442 bytes, SHA256
`2df6223f206b5164e21f664ace61dabeb9bb6a49b8b5a3e00510b4807d0f5b04`.
All 334 floating-point initializers are FLOAT16. Graph tensor types show FP16
inputs for 31 Conv, 72 MatMul and 12 Softmax nodes. Model input/output remain
FP32 at `(1,3,518,518)` / `(1,518,518)`. This is not the same graph/precision policy
as Base. Small uses the existing Apache-2.0 artifact; nothing was replaced.

The actual cached TensorRT 11.2.1.2 engine is 53,773,988 bytes, SHA256
`804f98ab5afd5c975cd873909b056968a13b89ee51bf78aa7330ff56e0ae99d9`.
Its runtime I/O is FP32 and execution produces finite depth. The cached engine's
inspector exposes layer names only, so no per-kernel accumulator-precision claim
is made; half-precision graph evidence is from its pinned source ONNX.

`v1/review_small_fp16.py` measured the existing engine with a fixed resident zero
input: ten warmups, sixty CUDA-event samples, **1.359ms median model GPU time**.
Transfers are outside events. This is not a matched model-quality comparison to
Base, whose input canvas and architecture differ. Artifact/type/timing output is
`out/small-fp16-review-20261105/report.json`.

Actual native Small/Performance output, public FloorballGame source process,
target 60Hz, six-second warmup and five six-second windows per resolution:

| Input / per eye | Median native FPS | Five-window range |
|---|---:|---:|
| 1920x1080 | 58.34 | 57.96–58.81 |
| 3840x2160 | 49.35 | 48.35–49.93 |

Both sessions pass the harness's stop/overload checks and end with zero pools/nodes.
Raw logs/environment are in `out/small-fp16-native-20261105/`, with `summary.json`.
As in the Base comparison, these count distinct Qt afterFrameEnd IDs and use an
enlarged 1080p public preview at 4K with a fitted output window, not physical scanout.

At 4K, sampled median worker depth/stereo/total intervals are 2.66/12.74/19.19ms;
the input color/copy bridge interval is 1.69ms. These overlapping/sample-based
intervals must not be added to the isolated 1.359ms model measurement. Small's
prepared-device inference returns after enqueue, whereas Base validates its
resized depth before returning. Thus some Small GPU inference wait is charged
to the following stereo interval; 12.74 versus Base's 9.76ms must not be read as
a pure stereo-kernel comparison. This timing-boundary difference was checked in
the follow-up explanation. Exact causal savings require a matched Small input-path
A/B, which has not been run. Small
still uses mapped host capture/RGB upload, unlike Base's current direct GPU input.
The next useful Small optimization targets that input path and full-resolution
SBS work. Re-converting its already-FP16 model is not a demonstrated speedup;
INT8/FP8 and different model/input shapes would require their own quality contract.
No Small precision or model change was made on the strength of this review.
