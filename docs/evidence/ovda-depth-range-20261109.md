# oVDA source-time depth-range stabilization — 2026-11-09

## Delivered behavior and implementation

Live oVDA now enables `stabilize_depth_range` in its model adapter, independently
of pixel EMA 0.5. It keeps c16/FP32, the accepted input sequence, short-skip policy,
guide radius 12, strength, motion gates and output geometry. Other models and
ordinary file defaults do not enable this tracker. No user option was added.

Current raw P2/P98 remains the range observation. A 2%-of-span endpoint deadband
suppresses small changes; source-time exponential response uses 0.05 seconds for
expansion and 0.5 seconds for contraction. Cuts, source/geometry changes and clock
discontinuities adopt a fresh range. This is causal and never locks the first
frame's range forever. The existing `temporal_alpha=0.18` value is the legacy
fallback coefficient, not the active stabilized range response.

1024 raw FP32 anchors (4 KiB) support robust affine transport into the current
model's units. A 3x3 RGB neighborhood must change by at most four byte levels.
The two-pass fit requires at least 96 anchors, normalized variance >=0.005,
gain 0.8–1.25 and offset magnitude <=0.15. The second pass retains >=80% of initial
anchors within residual 0.025 and requires RMS residual <=0.015. Rejected fits
leave the previous range in place before ordinary time-based adaptation.
Raw anchors avoid treating the range/pixel filter's own lag as model scale drift.

The optional oVDA bridge replaces the existing percentile endpoint kernel with
one same-stream kernel. No extra production readback, wait or per-frame
allocation is added. It borrows the unchanged LiveDepth layout and keeps a weak
renderer reference. Its anchor tensor is released after native context teardown
fences the owner stream. CPU live reference rendering uses `depth_range.py` with
the same clock/response and clears pixel history after clock discontinuities.

## Provenance and comparison contract

Build: `scripts/build-ovda-postprocess.ps1`, CUDA 13.1.80/MSVC 2022,
`--fmad=false`, SM120 plus compute_75 PTX and the established portable guide flags.
Only the source-only optional bridge was rebuilt; shared production CUDA DLLs
and the native context layout were not replaced.

- New DLL: `out/ovda-postprocess-range/ovda_postprocess.dll`, SHA256
  `b4873fc3b2b479a825526b1a3fd397e4b255ca1ecc3b3ddbfeec442763372629`.
- Bridge source SHA256:
  `6291ce02fda4d006d69de15c7937eec11b8a2453c665b115ba35d759df2fb745`.
- Included common source SHA256:
  `f0c4e8e369982c07f11310fda101985f8aa8e31353c84781cbf80da1522dac3a`.
- Borrowed layout identity remains
  `0394a7b790c92db37aaa49190e213edc65914e79625f03d38d62cf3c2911da85`.
- Old pixel-EMA-only DLL retained as comparison control:
  `out/ovda-postprocess/ovda_postprocess.dll`, SHA256
  `da3a065477429ce271382739a83bccea0d52dfd6222fefeafbc55d10f35c69c6`.

`evaluate_depth_range.py` feeds the same pending raw depth to old legacy, new
legacy and new stabilized renderers; pixel EMA is fixed at 0.5. Only this
multi-consumer diagnostic defers one real completion until all consumers finish.
The application retains its ordinary completion contract. Requirements:

1. Old/new legacy normalized depth, smoothed depth, bounds, shifts and native
   RGBA output are exact; this is a compatibility control, not a requirement for
   the intentionally changed stable path.
2. Stabilized native bounds match the independent CPU reference within 2e-6
   absolute/relative tolerance; synthetic tail noise and model affine drift
   cause less middle-surface variation; new range content recovers and cuts
   adopt the new observation immediately.
3. Additional low-RGB-motion eye-shift RMS must stay <=0.1 pixel in each public
   case, scaled to 3840 eye width/strength 0.5. This is an engineering budget,
   not a perceptual comfort threshold.
4. A follow-up saturation audit, declared before that audit, limits the increase
   in pixels losing >0.05 of the current frame's P2/P98 normalized span to
   0.5 percentage point in the two audited conditions.

## Synthetic and natural results

Four 512x288 fixtures each run 180 frames. Native/CPU bound error is at most
5.11e-15. With an initial common range and endpoint-only oscillation after 30
frames, middle-surface standard deviation falls 0.000393 -> 0. For global raw
affine drift it falls 0.000462 -> 1.30e-8. These are normalized-depth response
proxies, not ground-truth accuracy. A new near/far object is within 0.06 raw units
of the expanded endpoints after ten updates (~167 ms). After removal, endpoints
return within 0.025 of current P2/P98 in 1.5 seconds. A flat-depth cut adopts
0.7/0.7 immediately and all output stays finite.

The first exploratory tail fixture started at an extreme noisy endpoint, so its
initial recovery dominated the statistic and failed the jitter criterion. The
valid fixture initializes both paths from the same unperturbed range before
adding endpoint noise. It tests noise rejection separately from cold-start
recovery; the algorithm was not changed to fit that fixture.

Checksum-verified FloorballGame, OfficeWalk and ParkingGarage use 180 frames at
1280x720, 120 at 720x1280 and 90 at scaled 3840x2160: 1170 public model outputs.
The fixture clock advances at a declared 60 Hz; this is a matched sequence
comparison, not real-time playback timing. Model/cache input is identical across
renderers. Public-source hashes are in each JSON report. The low-motion mask uses
RGB change <=2 byte levels and 7x7 erosion; statistics exclude eight initial
updates. Still-color pixels may contain real depth movement, so this measures
variation rather than pure noise.

| Size | Clip | Legacy RMS | Stable RMS | Reduction |
|---|---|---:|---:|---:|
| 1280x720 | FloorballGame | 0.06355 | 0.06216 | 2.2% |
| 1280x720 | OfficeWalk | 0.27200 | 0.20226 | 25.6% |
| 1280x720 | ParkingGarage | 0.04854 | 0.04733 | 2.5% |
| 720x1280 | FloorballGame | 0.11534 | 0.10718 | 7.1% |
| 720x1280 | OfficeWalk | 0.28311 | 0.21915 | 22.6% |
| 720x1280 | ParkingGarage | 0.03551 | 0.03124 | 12.0% |
| 3840x2160 | FloorballGame | 0.06300 | 0.06004 | 4.7% |
| 3840x2160 | OfficeWalk | 0.27364 | 0.18996 | 30.6% |
| 3840x2160 | ParkingGarage | 0.04180 | 0.04102 | 1.9% |

All nine meet the variation budget. The old/new legacy control is exact on all
1890 synthetic/public frames. Product routing matches explicit stabilized native
output exactly on 720 more fixture frames; close releases the anchor tensors.
An isolated 48-frame pixel-EMA check still passes, including six invalid weights
and corrupt-DLL setup cleanup. Thirty-eight affected unit checks pass: range
parameters/clock/response/reset, model policies/diagnostics, file defaults,
CPU reference, source renderer and live reset boundaries.

Saturation is a tradeoff of retaining a small endpoint deadband. At 720p
ParkingGarage, clamped pixels grow 4.18% -> 6.66%, although low-motion RMS falls
2.5%. A diagnostic raw-depth readback measures the actual lost normalized span:
neither path loses >0.05 beyond the current-frame P2/P98 contract in that condition
or the audited 4K OfficeWalk case (270 additional frames). This does not establish
that arbitrary scenes cannot lose detail. The initial short 4K OfficeWalk sample
showed more saturation; its 90-frame window instead falls 4.07% -> 2.99%.

Artifacts under `out/ovda-depth-range-20261109/`:

- `comparison-long/report.json`: four fixtures and nine longer public cases.
- `comparison-r2/report.json`: earlier valid shorter public windows.
- `clipping-audit/report.json`: the two extra diagnostic saturation checks.
- `product-integration/report.json`: product parity and anchor cleanup.
- `bridge-errors.json`: isolated pixel override and failed setup cleanup.
- `../ovda-postprocess-range/build-manifest.json`: native build provenance.

## Runtime validation and limits

`benchmark_precision_live.py --range-comparison --layout half-tb --windows 3`
uses an owned FloorballGame source with a 16 ms timer, actual WGC GPU capture,
oVDA and native Half TB output, VFG off and output uncapped. The same freshly
built FP32 control plan is used in both paths (SHA256
`7bd4916e0104a1306c99dd0bb5a37e8bf27aed0f8ac698b5f35f1076147b0e75`).
Each size uses legacy/stable/stable/legacy session order, three seconds warmup
per session and three 3-second measurement windows: six windows per condition.
No other diagnostic GPU workload runs concurrently.

| Source size | Legacy output FPS | Stable output FPS | Legacy GPU | Stable GPU |
|---|---:|---:|---:|---:|
| 1920x1080 | 59.20 | 59.32 | 85.62% | 86.14% |
| 3840x2160 | 46.32 | 46.23 | 87.14% | 87.33% |

These short differences do not establish a meaningful throughput change.
All measured windows retain 15 cached past frames/full context and have no
gap/cut resets. Input H2D stays zero; existing small diagnostic/control readbacks
remain. NVML utilization is device-wide and includes the source/desktop, not
the model alone. FPS counts distinct native output submissions, not physical
display scans. Hardware: RTX 5090, driver 621.14, Torch 2.7.1+cu128, TRT 11.2.1.2.
Artifact: `native/report.json`.

Actual QML testing passes start, oVDA inference, live input resize across
landscape/portrait/square/profile boundaries, output movement between PG32UCWM
and Owl3D Shift, F11/Esc, minimize/continue, X stop, placement on restart, button
stop and preparation cancellation. Output sizes follow actual WGC ContentSize,
including Windows' odd-size rounding. Native pools/nodes are empty after stops.
Artifacts: `gui/report.json` and associated generated-source screenshots.

This tuning does not establish perceptual comfort, normal-speed
binocular visual acceptance, long-session drift, ground-truth accuracy or general
GPU compatibility. oVDA remains a source-only non-commercial integration and is
not added to the portable distribution by this task.
