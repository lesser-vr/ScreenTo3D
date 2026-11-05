# MoGe-2 Small bounded test — 2026-09-19

## Initial 30-frame probe

Functional candidate, **not promoted**. Official PyTorch inference and the
existing paired CUDA SBS renderer completed 90 source frames per configuration,
360 Full SBS pairs total. No default, model allowlist, GUI, or packaged runtime
was changed. Existing unrelated GUI edits were preserved.

RTX 5090 / driver 616.64 / Windows WDDM / PyTorch 2.7.1+cu128, TF32 disabled.
Three discarded warmups followed by five measured repetitions of frame 0 for
each of three sources (15 timings/configuration). Wall time includes inference,
MoGe focal/shift recovery, inverse-depth conversion and CPU depth return. It
excludes source decode, image preparation and SBS rendering. The MoGe input is
already GPU resident; DA2's engine helper includes its small input upload.

| Configuration | Median ms | Min–max ms |
|---|---:|---:|
| DA2 Small, existing TensorRT FP32, 518x518 | 5.294 | 4.547–29.638 |
| MoGe-2 Small, PyTorch FP32, 1200 tokens | 22.544 | 22.397–24.885 |
| MoGe-2 Small, PyTorch autocast FP16, 1200 tokens | 13.585 | 13.432–15.350 |
| MoGe-2 Small, PyTorch autocast FP16, 1800 tokens | 16.589 | 16.475–16.900 |

This compares prepared implementations, not equal-runtime architecture speed.
The DA2 outlier is retained. No sustained throughput or end-to-end FPS claim.
TensorRT optimization for MoGe was not attempted. FP16 is upstream autocast with
FP32 postprocessing, not an all-half checkpoint or a precision-parity approval.

## Comparison contract and observations

Pinned UVG-VCM public FloorballGame, OfficeWalk and ParkingGarage sources, first
30 consecutive frames each. Source hashes are enforced by `public_test_media.py`.
Original RGB input and each eye are 3840x2160; combined output is 7680x2160.
MoGe receives a 700x392 cubic resize, then upstream token-grid resampling;
DA2 uses its existing 518x518 preprocessing. Thus internal resolution and
preprocessing intentionally differ. All cases share the Performance stereo
policy and independent per-model normalization/history, without frame reuse.
Metric depths are inverted; masked/nonfinite/nonpositive values become far-zero
inverse depth. An entirely invalid map is rejected. Three adapter tests passed.

The three frame-0 depth contact sheets were visually inspected:

- Floorball: major people/floor structure is present; the foreground stick is
  less preserved by MoGe, including at 1800 tokens, than by DA2 in this frame.
- Office: major desk/monitor/chair structure is present; MoGe boundaries appear
  smoother. This is not evidence of more accurate geometry.
- Parking: car/rail silhouettes differ; no ground truth establishes a winner.

No consistent quality advantage is established. Temporal absolute-change values
are diagnostic proxies only: no flow alignment or ground truth. Thirty frames
per scene are insufficient for flicker/cut robustness. SBS files were produced
with geometry checks, but no motion playback or fused headset review occurred.
Games/HUD, sky-heavy content, capture, native presentation and FG remain untested.

## Provenance and reproduction

- Application HEAD: `68b5bd0246d16db557e1dac246be9f09d1674ae9`, with prior GUI edits.
- Official source: https://github.com/microsoft/MoGe at
  `74fbce054ebed49800de42d0ad0e83495065719a`, clean checkout checked before use.
- Weights: https://huggingface.co/Ruicheng/moge-2-vits-normal at
  `26b477f41595707c5db6770294c0d1721e8ed4ed`.
- Weight SHA256: `79a16621928c2bf0ed04659218c55c01075e950507f40bb3332fb4c873d3e1dc`,
  140550416 bytes, verified against HF LFS metadata before weights-only loading.
- 35,103,656 parameters. Source MIT with bundled DINOv2 Apache-2.0; weight card
  states MIT. This is local evaluation, not redistribution clearance.
- `utils3d-moge` dependency pinned to
  `62f09d58509485564e24d5d9f6aac9ee9ebc0c37`. Extra dependencies installed only under
  `out/moge-python-deps`; no application environment packages were changed.
- Existing trusted DA2 engine and projection DLL verified by their pinned hashes.
- Raw report and images: `out/moge-small-20260919/report.json` and sibling files.
  Raw report records script hash, engine hash, source hashes and individual timings.

```powershell
$env:PYTHONPATH='v1;out/moge-source;out/moge-python-deps;out/v1-python-deps;out/capture-python-deps'
& out/vda-oracle-env/Scripts/python.exe v1/evaluate_moge_small.py --output out/moge-small-new-run --frames 30
& out/vda-oracle-env/Scripts/python.exe -m unittest discover -s v1/tests -p test_moge_adapter.py
```

## Six-second motion follow-up — 2026-09-19

**Selected action: retain DA2; do not promote this MoGe FP16/1200 configuration.**
The bounded follow-up found no consistent visual advantage and higher
flow-aligned normalized-depth residuals in all three scenes. This does not reject
other token counts, precision recipes, temporal processing or MoGe variants.

Same pinned media/models as above, first 360 consecutive frames of each source:
1,080 unique RGB frames, independently inferred by each model, 2,160 SBS pairs.
Six HEVC videos are each 7680x2160, 360 frames, exact 60/1 rate (six seconds), with
no audio. Every video passed frame/geometry/rate checks plus a complete FFmpeg
`-xerror` decode before final publication. No frame reuse or interpolation.

The pipeline is the same **host** StereoSynthesizer used in the initial probe,
with paired CUDA projection, not the production all-GPU postprocessor. Same
Performance policy: strength 1, divergence .018, convergence .45, temporal alpha
.55, guide radius 4, transition .008; separate per-model normalization/history.
Its roughly 363–387 ms processing medians include slow host processing and run
alongside recording. They do **not** describe the production live path. The 60fps
file timestamps are not a real-time processing claim.

### Temporal diagnostic

For each of 359 adjacent-frame pairs per scene, compute backward Farneback flow
on 350x196 RGB-derived gray frames; warp the previous normalized/EMA depth to the
current frame. Retain in-bounds pixels with gray residual below 20/255. Report
mean absolute depth residual over those pixels, then average over frame pairs.
This samples pre-guidance normalized depth, not rendered SBS disparity.

| Scene | DA2 mean residual | MoGe mean residual | MoGe / DA2 | Retained pixels, mean |
|---|---:|---:|---:|---:|
| FloorballGame | .003100 | .007823 | 2.52x | 97.12% |
| OfficeWalk | .010565 | .018956 | 1.79x | 89.63% |
| ParkingGarage | .003846 | .005538 | 1.44x | 96.95% |

This is **not a depth accuracy score or a measured perceptual flicker ratio**.
Flow errors, occlusions, true geometry change, normalization and smoothing all
affect it; the photometric filter is not an occlusion oracle. No ground truth,
forward/backward flow-consistency test or scale/FOV cause attribution was used.
Nevertheless, these results do not support a temporal-stability improvement.

### Visual evidence and remaining gate

Depth sheets at frames 0/120/240/359 and selected native-pixel eye crops were
inspected across the scenes. Sports sticks remain less distinctly represented in
MoGe at multiple times. Office/parking major structures are recognizable in both,
with changed smoothness and boundaries, but no established consistent winner.
This is sampled visual review, **not continuous playback or fused HMD review**.
Six seconds per scene is longer than the initial probe but not a long-session,
scene-cut, game/HUD or VR comfort qualification.

Artifacts in `out/moge-small-motion-20260919/`:

- `report.json`: every frame, source/model hashes, timings, video hashes, 2,160
  completed pairs and host/device transfer telemetry.
- `review-summary.json`: per-scene proxy means/medians/P95 and preview metadata.
- `review.html`: local playback page, labeled DA2 left / MoGe right. Preview
  videos show **each model's left eye**, scaled to 960x540, side by side at 60fps;
  these are not stereo files. Links expose the six original Full SBS videos.
- `*-sequence.jpg`: seven timestamps of native-pixel left/right eye crops.

Three browser-compatible H.264 previews passed geometry/frame-count checks.
Adapter (3), encoder cleanup (3), and review sequence validation (4) tests passed.
The runtime report records the executed script hash; afterward only the success
status assignment was moved after final publication, without numerical changes.

```powershell
$env:PYTHONPATH='v1;out/moge-source;out/moge-python-deps;out/v1-python-deps;out/capture-python-deps'
& out/vda-oracle-env/Scripts/python.exe v1/evaluate_moge_small.py --output out/moge-motion-new-run --frames 360 --motion
& out/vda-oracle-env/Scripts/python.exe v1/review_moge_motion.py --directory out/moge-motion-new-run
```

No application backend, model defaults, GUI or package changed. No commit/push.
User playback/headset review remains available through the retained videos;
current evidence does not justify investing in default integration or promoting
the model merely because TensorRT might reduce inference time.
