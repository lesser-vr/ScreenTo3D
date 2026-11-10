# oVDA resolution and mixed FP16 comparison — 2026-11-09

## Result and delivered scope

Retaining the 518x924 inference canvas and using encoder+spatial mixed FP16 is
the useful candidate. It passes the declared numerical quality budgets, reaches
the ~62.5 Hz source ceiling in the short native 4K test and lowers device-wide
GPU utilization. Reducing inference to 392x700 also lowers cost, but fails the
declared edge/depth/native-image budgets in several public scenes. It is retained
as a comparison candidate, not selected as a new default.

The ordinary oVDA allowlist, 518-resolution FP32 defaults and file precision are
unchanged. `scripts/run-ovda-resolution-trial.ps1` provides an explicit live GUI
comparison path, defaulting to the 518x924 mixed-FP16 candidate. It uses isolated
preferences/placement under `out/ovda-resolution-20261109/manual/<variant>` and
labels trial precision in the GUI. It retains the ordinary source selection and
non-commercial confirmation. File conversion in that GUI still uses the ordinary
FP32 path and is identified separately in help. The trial worker rejects other
model selections. No portable runtime or new model weights were distributed.

## Build, profiles and trust

All candidates use pinned c16 weights and upstream source:

- Source revision: `4173c24e22f528062a0cf8ae235c58a5d4376a74`.
- Weight SHA256: `ea531d53a1135a443bafcf106a175b26a6519c05ccc1e994d74e46159e14b7cb`.
- TRT 11.2.1.2, Torch 2.7.1+cu128, driver 621.14, RTX 5090; TF32 disabled.
- Low FP32 ONNX SHA256: `6a80992ced60e7eed21ff300bf714c97737b8e316ffb66d436fb41a18a5a4104`.

The existing `build_engine.py` can explicitly export 392x700 using the same
original positional interpolation folded into a fixed buffer. Every low FP32
depth and four new-cache outputs pass PyTorch atol=rtol=.001 on 32 self-fed public
frames. Cache topology is derived from the new patch grid; capacity remains 16.
The new graph then uses the established encoder+spatial recipe. Temporal blocks,
cache, depth head and floating I/O remain FP32; mask/position remain INT64.
This is mixed FP16, not a fully FP16 model/cache. TensorRT may fuse attention;
internal fused Softmax/accumulation precision is not independently certified.

| Variant | Inference canvas | Plan SHA256 | Plan bytes |
|---|---|---|---:|
| `fp32-current` | 518x924 FP32 | `7bd4916e0104a1306c99dd0bb5a37e8bf27aed0f8ac698b5f35f1076147b0e75` | 129355452 |
| `encoder-spatial` | 518x924 mixed FP16 | `394894301beee2302decaf43e7dd4912c043cae469a07f19f4848774a5eb0ec1` | 91370692 |
| `low-fp32` | 392x700 FP32 | `ac135d0bb63159ec0c98b1ea5f2907a8b1105161a682aa1b333d352eaad2f184` | 126550868 |
| `low-fp16` | 392x700 mixed FP16 | `1c4891befbded49c103730bcbf8d60ef7ac01547df3b6dcb876e5fa1b55cc6d8` | 86803228 |

`trial_runtime.py` changes the allowlist only within an explicit process-local
trial context. Paths, plan lengths/hashes and tensor signatures are checked before
deserialization; normal loading never accepts an arbitrary trial plan. Trial
backend/engine telemetry identifies mixed precision rather than claiming FP32
because floating I/O is FP32.

`TRIAL_CANVASES` permits the exported 392x700 geometry without adding it to the
normal model registry or default canvas selection. Source RGB/eyes retain their
dimensions. Trial inference aspect-fits into the canvas, with replicated padding
cropped before restoration; e.g. 16:9 content is 392x697, not stretched to 700.
The matching 518 canvas retains the pre-existing native transform. Thus this
tests the complete lower-profile path, including its small framing difference,
rather than claiming a mathematically isolated tensor-size change.
The input pixel count falls 42.67%; persistent cache falls 190857216 -> 108953600
bytes (42.91%). Resolution and cache precision are separate changes.

The pinned optional GPU input DLL adds only the new profile guard:
`out/ovda-gpu-input-resolution/ovda_input.dll`, SHA256
`ef4fa57630fc1ab6eeeecac39bbf3927f57c4bde1afe0cb82875a50524b294a6`.
Build source SHA256 is
`be71b2a7d4eb3c99ee2fafb69397209eab0f9aed332e8240794ce4a76eaa7188`.
The older DLL remains an archived comparison control. Thirty prior-profile
RGB/BGRA/near-black/binary/random/pitched comparisons are bit-exact against it.
All four profiles pass 160 GPU/CPU preprocessing combinations (absolute tolerance
1e-5), plus invalid DLL/dtype/canvas/size/stream/thread rejection. Six sentinel
padding tests prove that padding does not enter restored low-profile depth.

## Declared quality comparison

`evaluate_resolution.py` fixes source frames, c16 self-fed histories, current
pixel EMA 0.5, causal range stabilization, guide radius 12, strength 0.5, GPU
preprocessing and native Half TB synthesis. It compares every variant to the
fresh FP32 control; no inference frames are inserted or skipped. Explicit common
cuts reset all models/renderers together. Source timestamps advance at 60 Hz.

The budgets were declared in the tool before evaluation:

| Candidate | Numerical budget |
|---|---|
| Same-canvas mixed FP16 | Worst case-mean raw MAE <=0.1% of FP32 P2/P98 span; native RGB MAE <=0.25/255; <=1% of pixels differ by >8 in any RGB channel |
| Low resolution | Dense normalized depth MAE <=0.02, edge MAE <=0.04; native RGB MAE <=2/255; <=5% of pixels differ by >8 |
| All | Additional low-RGB-motion eye-shift RMS <=0.1 pixel at 3840 eye width/strength 0.5 in each case; finite outputs and preserved ownership/geometry |

These are engineering comparison thresholds, not depth GT or a comfort standard.
The previous strict FP32 per-pixel/cache parity contract is not claimed for
precision or resolution changes. A failed quality budget excludes automatic
promotion; it does not prove that every user would reject that candidate.

The pinned UVG-VCM previews FloorballGame, OfficeWalk and ParkingGarage provide
180 frames each at 1280x720 and 90 each at scaled 3840x2160. OfficeWalk portrait
1080x1920, ParkingGarage ultrawide 3440x1440 and FloorballGame square 1024x1024 add
64 frames each: nine cases, 1002 source frames, four independent histories.
All trials fix the inference canvas at 518x924 or 392x700 even for unusual ratios;
this isolates the factor comparison from ordinary best-canvas selection.
Source hashes are retained in the JSON report.

Every frame checks 256x144 raw-depth observations and 32x32 samples of the actual
guided projection depth. Low-motion samples require RGB differences <=2 and a
7x7 eroded mask. Measurements exclude the first 16 updates; cached past occupancy
is tracked before inference. Samples can miss small objects, and still-color
regions can move in depth. Eye-shift conversion is the actual oVDA linear mapping.

Dense normalized-depth, edge and native-RGB metrics use 33 selected frames across
the cases (15/31/63/final where distinct). Each model is independently normalized
to its P2/P98 for depth-shape comparisons; raw errors separately retain scale/offset
differences. Edges are reference normalized gradients >0.01, dilated 5x5.
Every published native texture is read/released, including non-metric frames;
diagnostic readbacks/timing instrumentation are excluded from native FPS claims.

| Worst case-mean metric / worst sampled frame where noted | 518 mixed FP16 | 392 FP32 | 392 mixed FP16 |
|---|---:|---:|---:|
| Raw MAE, % reference span | 0.04910% | 6.78921% | 6.79320% |
| Dense normalized depth MAE | 0.000349 | 0.034215 | 0.034196 |
| Edge normalized MAE | 0.000601 | 0.069676 | 0.069723 |
| Native RGB MAE, 0–255 | 0.04171 | 4.34447 | 4.30857 |
| Pixels with RGB difference >8, worst sampled frame | 0.1567% | 20.0787% | 20.0905% |
| Additional low-motion eye-shift RMS, 4K pixels | 0.000153 | 0.047855 | 0.046982 |
| Declared comparison budget | Pass | Fail | Fail |

Lower-resolution raw differences partly include learned scale/offset changes,
but the independently normalized edge/depth and actual SBS differences also grow.
It therefore cannot be justified as a parity-preserving speed optimization.
Mixed FP16 at retained resolution stays much closer to FP32 in these samples.
Normal-speed binocular/Owl3D acceptance is still unmeasured.

Valid artifact: `out/ovda-resolution-20261109/quality-r3/report.json`, plus saved
native Half TB previews. `quality` stopped before usable comparison on a missing
diagnostic ctypes signature. `quality-r2` stopped because unmeasured texture slots
were not released. Both diagnostic harness faults were corrected; their partial
outputs are not quality evidence and production handoff was not changed.

## Actual capture to native output

`benchmark_precision_live.py --resolution-comparison --layout half-tb --windows 3`
uses owned public FloorballGame playback with a 16 ms timer, actual WGC GPU capture,
current oVDA filtering/history and native texture output. Output is uncapped,
VFG off. At each source size it runs all four variants and then reversed order,
three seconds warmup and three 3-second windows per session: six windows per
condition. No other GPU diagnostic runs concurrently.

| Source size | Inference | Native output FPS | Device-wide GPU utilization |
|---|---|---:|---:|
| 1920x1080 | 518 FP32 | 59.06 | 85.90% |
| 1920x1080 | 518 mixed FP16 | 62.35 | 43.26% |
| 1920x1080 | 392 FP32 | 62.46 | 45.48% |
| 1920x1080 | 392 mixed FP16 | 62.51 | 30.90% |
| 3840x2160 | 518 FP32 | 46.16 | 86.95% |
| 3840x2160 | 518 mixed FP16 | 62.42 | 64.55% |
| 3840x2160 | 392 FP32 | 62.40 | 66.69% |
| 3840x2160 | 392 mixed FP16 | 62.43 | 50.45% |

The optimized paths reach this source's ~62.5 Hz ceiling, so the results do not
measure their maximum possible FPS. GPU utilization is NVML device-wide, including
public-source playback and desktop; it is not isolated model utilization. Output
FPS counts distinct native submissions, not display scans. All timed windows keep
15 cached past frames/full context, have no gap/cut resets and retain zero input
H2D bytes. Normal small metadata/diagnostic readbacks remain.

Median TRT stream intervals in the 4K matched quality replay are about 16.1 ms
for 518 FP32, 6.2 ms for 518 mixed FP16, 6.7 ms for 392 FP32 and 4.0 ms for
392 mixed FP16. These intervals exclude capture/rendering and include possible
host enqueue gaps; only the native test above supports end-to-end output claims.
Artifact: `native/report.json`.

## Lifecycle, reproducibility and limits

Actual QML tests pass for both mixed FP16 candidates: real WGC start, input resize
across landscape/portrait/square/profile boundaries, output movement between
PG32UCWM and Owl3D Shift, F11/Esc, minimize/continue, X/button stop, restart
placement and preparation cancellation. Stops leave no native pools/nodes.
The trial wrapper also isolates preferences from normal user selection storage.
Artifacts: `gui-fp16/lifecycle/report.json` and `gui-low-fp16/lifecycle/report.json`.
Seven affected geometry/allowlist/binding unit tests pass.

Builds and checks are reproducible from the pinned local prerequisites:

```powershell
# Run in the prepared oVDA Python environment described in docs/models/ovda.md.
python experiments/ovda/build_engine.py --height 392 --fold-position --input out/public-live-default/FloorballGame.mp4 --output out/ovda-resolution-20261109/low-fp32
python experiments/ovda/precision_trial.py --low-resolution --spatial-only --output out/ovda-resolution-20261109/mixed
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-ovda-input.ps1
```

Build directories must be new; normal artifact/hash checks remain enforced.
Graph/plan build records, preprocessing and padding controls are under
`out/ovda-resolution-20261109/`; the new native input build manifest is under
`out/ovda-gpu-input-resolution/`. No commercial clearance, other-GPU support,
physical comfort, long-session drift or release packaging is established here.
