# Native restart, Base profiling and iw3 renderer comparison — 2026-11-05

## Result

1. Fixed the reproduced `Native texture wrapping failed` error when restarting
   native SBS at a different size. Six mixed-size sessions and the actual desktop
   hide/restore/resize/source-loss/crash lifecycle passed.
2. Separated Base GPU stages and tested a CUDA graph candidate without changing
   precision, model input or output arithmetic. Exact parity passed, but matched
   live output improved only 1.11% at 1080p and 0.59% at 4K, with overlapping run
   ranges. This does **not** establish a practical speed improvement. The candidate
   remains diagnostic and off by default.
3. Executed all three iw3 renderers on identical RGB/final-depth inputs. Some
   diagonal edges are smoother, but fine structures and occlusions have tradeoffs;
   all three cost more than the current renderer in this test. Keep the existing
   product renderer. No iw3 model is loaded by the normal application.

These results do not establish sustained 4K30/60, physical scanout, Owl3D or HMD
comfort. No new GUI controls, frame generation or precision change were added.

## Native output restart

The original benchmark failed on its second session, 1080p → stop → 4K, with
`Native texture wrapping failed`: `out/native-repro-20261105`. The fix makes the
output window retire graphics together with its nonpersistent scene graph:
`setPersistentGraphics(False)` next to `setPersistentSceneGraph(False)` in
`v1/depthsbs_app/desktop.py`. Native DLL hashes are unchanged.

Qt 6.10.2's [native texture wrapper][qt-texture] delegates to
`QQuickWindowPrivate::createTextureFromNativeTexture`; that function's null return
is its missing-window-RHI guard in [qquickwindow.cpp][qt-window]. The mixed
persistence settings and successful matched reproduction support the lifecycle
diagnosis; this is not a claim that every Qt restart failure has the same cause.

Evidence:

- `out/native-restart-fix-probe-20261105`: original two-size sequence passes.
- `out/native-mixed-restarts-20261105/runs.json`: same application process,
  1920x1080 → 3840x2160 → 1080x1920 → 3840x2160 → 1920x1080 → 3840x2160.
  All six sessions produce actual native output. Existing harness asserts zero
  live texture pools/nodes and release of the worker after every stop.
- `out/native-restart-graph-lifecycle-20261105/report.json`: Base with graph
  candidate enabled; output hide/restore, fullscreen/Escape, input resize,
  stop/restart, source minimize and owned-worker crash pass. Shutdown assertions
  verify zero pools/nodes. The report's main native snapshot is intentionally
  taken before stop and still contains its active pool/node.

The mixed-size run uses one-second observation windows as a regression test, not
a performance claim. The native output remains experimental; host output remains
the product default.

## Base stage cost and CUDA graph candidate

`v1/profile_base_stages.py` uses a pinned public FloorballGame frame, GPU input,
the unchanged FP32 TensorRT plan and native SBS pool. Six warmup iterations,
30 measured iterations per size; diagnostic output readback is outside timing.
CUDA events separate preprocessing, model execution and upscale. The finite check
includes its wait. This is an isolated probe, not capture/display throughput.

Baseline medians in milliseconds (`out/base-stage-profile-20261105/report.json`):

| Per eye | Input preprocessing | Model GPU execution | Upscale | Finite-check wait | Stereo host elapsed | Total host elapsed |
|---|---:|---:|---:|---:|---:|---:|
| 1920x1080 | 0.392 | 23.388 | 0.053 | 0.181 | 2.136 | 26.369 |
| 3840x2160 | 0.390 | 22.743 | 0.189 | 0.211 | 6.930 | 30.750 |

Both source sizes use the same 518x924 model canvas. Model execution is the main
isolated cost. The earlier live aggregate depth figure around 32ms also includes
capture/display contention and other work; it is not a pure-model ceiling.
Full host-output transfer remains an additional cost outside this native probe.

The candidate retains one fixed preprocessing allocation and one captured
TensorRT graph per engine. Input preparation, source-depth interpolation,
finite-output checks and the existing single pending-depth ownership remain on
the same stream. No silent fallback is used. Close resets the graph before engine
release, attempts cleanup after failures, and rejects the wrong owner thread.

- Diagnostic switch: `DEPTHSBS_BASE_GRAPH=1`; default `0`. Requires GPU input
  preprocessing. Invalid values are rejected.
- Stage instrument switch: `DEPTHSBS_BASE_STAGE_PROFILE=1`; default off.
- `out/base-graph-parity-20261105/report.json`: 24 real-engine cases across 1080p,
  ultrawide, portrait and 4K, including cut and background-refinement cases.
  Raw depth, CPU/GPU-input SBS and GPU-host/native SBS are exact. The existing
  legacy CPU-post comparison stays within its pre-existing tolerance.
- Scoped device tests cover foreign token completion, shape/device/stream/epoch
  rejection, invalid graph configuration, wrong-thread cleanup and injected
  synchronization/graph-release failures. Six tests pass.
- `out/native-profile-iw3-unit-20261105.log`: final 21 selected device/profile,
  live routing and native transport tests pass; changed Python files pass scoped
  Ruff error/name checks and the working diff has no whitespace errors.
- `out/base-stage-graph-profile-20261105/report.json`: isolated graph measurements.

Matched live benchmark: RTX 5090 / driver 621.14, Qt 6.10.2, TensorRT 11.2.1.2,
public FloorballGame in an owned separate source process, native output, target
60Hz, six-second warmup and five six-second windows for each size/path. On and off
are separate sequential runs, not a randomized sustained trial.

| Per eye | Graph off median output fps (range) | Graph on median output fps (range) |
|---|---:|---:|
| 1920x1080 | 32.15 (31.98–32.66) | 32.51 (32.34–32.82) |
| 3840x2160 | 23.86 (23.67–24.03) | 24.00 (23.86–24.03) |

Data: `out/base-graph-live-off-20261105/`, `out/base-graph-live-on-20261105/`,
`out/base-graph-live-summary-20261105.json`. Commands explicitly set the graph
environment variable before spawning workers; those initial environment manifests
predate the new graph metadata field. The harness now records both graph/profile
flags and the desktop lifecycle source hash for future runs. Counts are distinct
Qt afterFrameEnd IDs, not physical display refresh. 4K input is an upscaled 1080p
public excerpt, processed as 7680x2160 Full SBS in a fitted output window.

## iw3 comparison contract and provenance

Harness: `v1/compare_iw3_renderers.py`. Separate clean source checkout:
`out/iw3-render-source-20261105`, nunif commit
`0d3d92c8f4396da564c44524b6390ee5c76b9668`. Exact source revision and clean status
are checked before import. Only the required model modules are imported; no depth
model hub or automatic download is invoked. The existing reference checkout is
unchanged. Official [model factory][iw3-factory] and [warp code][iw3-warp] are used.

| Candidate | Official release file | SHA-256 |
|---|---|---|
| RowFlow v3 symmetric | `iw3_row_flow_v3_sym_20250628.pth` | `b61518f9c83e1f0c19d8a8844dbe5304e5f47bfb65928d5bb74256c1640186a0` |
| RowFlow v3 | `iw3_row_flow_v3_20250627.pth` | `2e4daa14a72a5f751ffff489c1809ce2c4c6aea6191d47f67f2f72afe4ef612a` |
| MLBW small, two layers | `iw3_mlbw_l2s_d1_20250627.pth` | `d66467d9b055bf7ca651aeb24d11d2ccc9ad447d040a5b3e455962821c891e28` |

Files come from `https://github.com/nagadomi/nunif/releases/download/0.0.0/`, are
hash checked and loaded with `torch.load(weights_only=True)`, strict state dicts.
Source is [MIT][iw3-license]; the readme describes synthetic training for RowFlow.
No separate model license grant was found in the checkpoint metadata. Local
evaluation is not clearance to bundle model files commercially. Base's existing
CC-BY-NC-4.0 restriction remains. Models are outside the product distribution.

All methods receive the same RGB and final Base depth after the existing
normalization/history/guide/background policy. Sixty consecutive 60Hz frames each
from FloorballGame, OfficeWalk and ParkingGarage: 180 natural frames total.
The public corpus hashes are checked; UVG-VCM/Tampere CC BY 4.0 attribution is in
the JSON and `v1/public_test_media.py`. Natural video has no ground-truth stereo.

The synthetic layered scene has exact target eyes: stationary background,
eight-pixel foreground shift, text and thin bars. Revealed background is scored
separately because no monocular renderer sees the originally hidden texture.
This single fixture is a diagnostic, not a universal quality ranking.

Geometry calibration discovered opposite returned eye naming. iw3's returned
eyes are swapped to preserve DepthSBS's current eye order. Divergence is
`100 * 0.026 = 2.6`, convergence `.45`, both eyes, one warp step, no mapper or
screen-border forcing. Constant-plane expected shifts are −9.984/+9.984 pixels;
all methods are within 1.5 pixels (current integer projection is −10/+9, learned
methods approximately −9.82…−9.92 / +9.85…+9.88). The uncorrected first attempt
failed this assertion and is not used as comparison evidence.

Learned rendering uses upstream AMP FP16 with RGB/depth FP32; TF32 disabled.
This is an intentional new renderer comparison, not numerical parity. Rendering
depth stays at source resolution. Upstream's optional `--stereo-width` reduction,
TensorRT conversion, compilation and inpainting are not evaluated here.

## Rendering cost and visual result

Three warmups and ten samples per method/size. CPU-in/out latency includes host
inputs and host eye outputs for every renderer. iw3 GPU-resident timing excludes
those transfers and is a separately labeled boundary. The current reference
adapter is the pinned CUDA paired forward-zbuffer renderer; these CPU-in/out
figures are not the product's GPU-resident native transport cost.
The CUDA adapter returns two uint8 eye arrays; the iw3 wrapper also packs its
float eye tensors into one uint8 SBS array for readback. That packing/layout cost
is included in the iw3 CPU-in/out figure; these are adapter costs, not isolated
kernel speed comparisons.

| Renderer | 1080p CPU-in/out ms | 4K CPU-in/out ms | 4K iw3 GPU-resident ms |
|---|---:|---:|---:|
| Current CUDA | 5.95 | 34.57 | — |
| RowFlow v3 symmetric | 7.35 | 45.77 | 27.49 |
| RowFlow v3 | 10.00 | 72.76 | 54.58 |
| MLBW small | 10.80 | 67.60 | 49.36 |

4K timing uses the last ParkingGarage RGB/depth upscaled to 3840x2160, shared by
all methods; it is not a native-4K quality test. The 1080p timing frame is the first
FloorballGame frame. No capture, model inference or GUI is in renderer timing.

Synthetic RGB mean absolute error, 0–255 scale:

| Renderer | Whole frame | Previously visible region | Newly exposed background |
|---|---:|---:|---:|
| Current CUDA | 0.279 | 0.221 | 5.447 |
| RowFlow v3 symmetric | 1.289 | 1.254 | 4.482 |
| RowFlow v3 | 1.246 | 1.073 | 16.653 |
| MLBW small | 1.436 | 1.197 | 22.643 |

Inspected original-pixel synthetic, FloorballGame and OfficeWalk still crops.
Learned warps smooth the floor's diagonal line compared with the current jagged
projection. The symmetric model can weaken thin bars and round/stretch object
edges; learned interpolation also softens fine structures. OfficeWalk differences
are modest at the inspected crop. Better synthetic disocclusion score for the
symmetric method coexists with worse visible-region error. This supports keeping
the current renderer while retaining these artifacts for future comparisons.

Artifacts under `out/iw3-render-comparison-calibrated-20261105/`:

- `report.json`: calibration, model hashes, all timing samples and synthetic metrics.
- `synthetic-comparison.png`, `synthetic-truth.png`, `*-synthetic.png`: exact-pixel
  comparison, ground truth and full eyes.
- Each source directory contains `source.png`, `depth.npy`, each full renderer
  PNG, `detail.png`, `overview-correct-aspect.png`, and `comparison-h264.mp4`.
  These videos contain the same 60 frames at 60Hz; no interpolation. H.264 previews
  were derived from the initial comparison export with corrected per-eye display
  aspect and labels. The harness also now creates correct-aspect previews directly.

Image inspection is complete for the named stills. Videos were generated and
decoded for export, but continuous normal-speed binocular/HMD review was not
performed. No claim about reduced eye strain or temporal quality is made.

[qt-texture]: https://github.com/qt/qtdeclarative/blob/v6.10.2/src/quick/scenegraph/coreapi/qsgtexture.cpp
[qt-window]: https://github.com/qt/qtdeclarative/blob/v6.10.2/src/quick/items/qquickwindow.cpp
[iw3-factory]: https://github.com/nagadomi/nunif/blob/0d3d92c8f4396da564c44524b6390ee5c76b9668/iw3/stereo_model_factory.py
[iw3-warp]: https://github.com/nagadomi/nunif/blob/0d3d92c8f4396da564c44524b6390ee5c76b9668/iw3/backward_warp.py
[iw3-license]: https://github.com/nagadomi/nunif/blob/0d3d92c8f4396da564c44524b6390ee5c76b9668/LICENSE
