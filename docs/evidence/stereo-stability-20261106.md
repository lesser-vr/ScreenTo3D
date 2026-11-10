# Live DA2 stereo stability — 2026-11-06

The user reported substantial benefit from the LR correction but residual wobble
and focus discomfort compared with Owl3D Live 3D. This change implements two
independent improvements informed by that investigation; it does not reproduce
Owl3D's proprietary renderer or establish equivalent viewing comfort.

## Promoted behavior and comparison contract

- DA2 Small/Base retain normalization/EMA history across ordinary latest-frame
  capture replacement. Sequence and source timestamp must advance, with a maximum
  100 ms source interval. Start/resize/cut, replay, invalid/backwards time and a
  longer pause still reset. Stateful/every-frame models keep strict semantics.
- Live CUDA host/native/VFG output reconstructs fractional shifts using triangle
  weights around the existing near-surface owner. At most five source pixels are
  considered, rejecting neighbors differing by more than 0.01 normalized depth.
  Existing hole filling remains. This helps within-surface sampling; it does not
  solve motion-warped depth, all silhouettes or disoccluded content.
- The default diagnostics are `DEPTHSBS_DEPTH_HISTORY=continuous` and
  `DEPTHSBS_STEREO_QUALITY=subpixel`. Explicit `legacy` history and `reference`
  quality provide an old-policy control. These are developer comparison controls,
  not new GUI options. Model precision, strength, convergence and file/reference
  rendering are unchanged. The live temporal/rendered pixels intentionally change.
- Every real reset also invalidates VFG pair history. The wrapper forwards the
  new source-time arguments, and ordinary coalescing no longer appears as a reset.

## GPU correctness and bounded cost

`v1/check_stereo_stability_gpu.py` uses known continuous translations independently
of the implementation. In 41 positions from 0 to 2 px, two eyes, the maximum red
marker centroid error is 1.0 px with reference coverage versus 0.001961 px with
subpixel reconstruction. Zero shift retains random texture exactly. Red foreground
over blue background has no mixed-color surface bleed in the generated fixture.
These checks concern the supplied geometry, not estimated depth correctness.

At 17x16, 256x72, 1920x1080 and 3840x2160:

- Reference mode matches the separately retained, correct-LR DLL exactly.
- Small's rebuilt DLL matches the common depth DLL in both projection modes.
- Native and VFG-original RGBA exactly match host RGB; alpha remains 255.
- Sparse GPU depth samples exactly match independent CPU sample coordinates.

Alternating modes, 4 warmup plus 10 measured repetitions per mode, using the
production parallel resolver: median GPU projection interval is 0.245→0.284 ms
at 1080p and 1.434→1.650 ms at 4K. These timings exclude capture, inference,
presentation and physical display; they are not a live FPS claim.

`v1/check_stereo_geometry_gpu.py` additionally passes all six LR geometry/native/
VFG-publication cases. `v1/test_small_gpu_input.py --quality subpixel` passes 27
resize fixtures and 72 public/adapted samples over 1080p, ultrawide, portrait and
4K: preprocessing, raw depth and host/native output are exact across the Small
CPU/GPU input routes. `experiments/vfg/check_native_bridge.py --quality subpixel`
passes six real Base FP16 original/native comparisons and generates a VFG frame
at both 1080p and 4K. The optional RowFlow eager geometry check remains correct;
its direct binocular quality review is still deferred.

## Identical-inference public comparison

`v1/check_stereo_history_public.py` uses three hash-verified UVG-VCM previews,
90 Base FP16 inferences per clip, selecting every second frame from 3 seconds of
60 Hz source content. Both history policies receive the same raw inference and
RGB. A forced midpoint cut checks exact reinitialization. Each clip has 90 legacy
resets versus 2 continuous resets. Cut results are exact between the policies.

The temporal metric is mean depth difference after DIS motion alignment on
photometrically consistent pixels. It is a proxy without depth ground truth;
lower error alone cannot rule out temporal lag or oversmoothing.

| Clip | Legacy depth MAE | Continuous depth MAE | Change |
|---|---:|---:|---:|
| FloorballGame | 0.002264 | 0.002312 | +2.2% |
| OfficeWalk | 0.010149 | 0.008671 | -14.6% |
| ParkingGarage | 0.001634 | 0.001224 | -25.1% |

The content-plane candidate uses a central sparse-depth quantile, deadband,
one-second response and 0.06 normalized-depth/second limit, resetting at a cut.
It is available only via explicit `anchor` or `stable` diagnostic quality.
It is **not promoted**: ParkingGarage's central absolute disparity falls from
7.10 to 4.37 px, but whole-image P95 absolute disparity rises from 24.61 to 32.83 px
(+33.4%). OfficeWalk similarly increases whole-image P95 by 4.5%. A future content
anchor needs scene-wide disparity budgeting and binocular review, not just a
better center statistic. The default subpixel mode has no sparse-depth readback.

Public media: Ultra Video Group/Tampere University, UVG-VCM, CC BY 4.0; compressed
1080p previews from the 4K source. Exact source hashes, modification details and
attribution are retained by `v1/public_test_media.py` and the output report.

## Actual native execution

RTX 5090, Base TensorRT mixed FP16 with FP32 I/O, 3840x2160 source and 7680x2160
Full SBS, unlimited output, owned public FloorballGame source. The output window
is fitted for the test; this is Qt completion, not physical scanout or an Owl3D
binocular acceptance test. Baseline uses legacy/reference, improved uses
continuous/subpixel. Sequential short runs are not a statistical performance
qualification. Each has 2 seconds of warmup and three 3-second windows.

| Path | Median native FPS | Median of interval P50 source-to-Qt age | Resets at last measured snapshot |
|---|---:|---:|---:|
| Previous policy, correct LR | 55.86 | 21.74 ms | 254 (start 1, gap 253) |
| Continuous history + subpixel | 54.81 | 22.71 ms | 2 (start 1, gap 1) |

The observed FPS difference is -1.87%, with approximately +0.97 ms source age.
Source paint supply is about 78 versus 75 FPS, so the numbers should not be used
as a controlled GPU-only comparison. The independent projection timing above
isolates a roughly 0.22 ms 4K cost under its synthetic input.

The explicit Medium VFG run uses two 3-second windows: native output 77.08/77.65
FPS, fresh SBS 38.54/38.66 FPS, original source-to-Qt P50 40.49/40.75 ms. A generated
frame's oldest input is about 54 ms old. VFG still trades fresh-frame rate and
latency for output cadence. It is not the normal app default.

Default and VFG runs both pass hide/restore, resize, stop, restart and preparation
cancellation. Native pools/nodes are zero after stop. VFG create/close counts
balance across resize and restart. No user-selected source or private frame was
recorded. The benchmark source activation affects only its owned test window.

Early attempts, including the old-policy control, received only about 4 FPS from
capture despite 80+ source paints/second. They were excluded from performance
comparison. Later capture supply recovered; the cause was not established. The
timestamp bound was not weakened to accommodate those attempts. The folder named
`final-vfg` was accidentally run without the VFG flag; its report correctly says
`vfg:false` and it is not VFG evidence. The actual VFG run is `final-vfg-enabled`.

## Checks, artifacts and limits

236 core/platform/profile contracts pass. A final targeted run of screen-plane,
Small ownership and VFG timing tests passes 12 tests. Ruff E9/F and whitespace
checks pass. Test records are under `out/stereo-stability-20261106/`:

- `contracts.json`, `geometry.json`, `subpixel.json`, `public-history.json`
- `small-subpixel/report.json`, `native-bridge-subpixel/result.json`
- `final-baseline/report.json`, `final-improved/report.json`
- `final-native-smoke/report.json`, `final-vfg-enabled/report.json` and worker reports
- `rowflow-geometry.json`

Fresh binaries are isolated from the prior outputs; Python consumers verify SHA256:

| Artifact | SHA256 |
|---|---|
| `out/live-depth-stable/live_depth.dll` | `5237760648814414a0662330d101a77de3bfa4b6745dd7d6e78026b41c0e1f9b` |
| `out/small-input-stable/small_input.dll` | `786d8e562641b4d8d31f83e6862b8f722e433e2e86841e3a781c97015f799d7e` |
| `out/live-texture-stable/live_texture_runtime.dll` | `6f8e4bb1e5f196724344c5c58f2806c349d6a9e762cec4bcaadb4a23197a922d` |
| `out/vfg-native-bridge-stable/vfg_native_bridge.dll` | `9ae1c78173ee27e9a3b6e9f81de34fa0e9ed83d9de858ebdd4c91d47f2899114` |
| `out/rowflow-bridge-stable/rowflow_bridge.dll` | `4a684b609d526b682c59f17e12695f373ebb6b20d0b201933e8b685f42c0ea81` |

Full application restart loads the revised modules. Tests establish functional
behavior and bounded measurement, not user comfort, parity with Owl3D Live 3D,
long-session game performance or public package availability. Physical viewing
of motion, silhouette wobble, near/far transitions and occlusion remains open.
