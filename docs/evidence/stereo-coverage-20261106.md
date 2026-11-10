# Fractional silhouette coverage — 2026-11-06

Implemented the first priority from the wobble review using the user's strength
0.5 as the live comparison baseline. Global strength/convergence defaults are
unchanged. No new GUI option or model/precision change was introduced.

## Change and limits

The old subpixel reconstruction normalized the near-surface weights to one even
when that surface occupied only a tiny fraction of a destination pixel. At a
silhouette this made a nearly uncovered pixel fully opaque. The coverage mode
keeps the fractional weight and fills the remaining fraction from the nearest
locally visible farther source sample in the uncovered direction, searching at
most two source pixels and requiring a normalized-depth separation above 0.04.
The five same-surface samples retain their 0.01 depth tolerance. No extra image
buffers, CPU readback or frame history are added.

The numerical check also found an almost-integer failure: adding a tiny fraction
to a large pixel coordinate erased it, leaving an opaque pixel where coverage
should approach zero. Coverage mode subtracts integer coordinates first and
handles zero/tiny weight explicitly. The old subpixel diagnostic stays exact.

This is local edge extension, not recovered hidden geometry. Full coverage and
unresolved holes retain their previous behavior. Broad depth errors, slowly
changing surface estimates, wide disocclusions and gradual/ambiguous depth edges
are not solved. The next temporal/range changes require separate evidence.

Default `DEPTHSBS_STEREO_QUALITY=coverage` applies to live DA2 Small/Base CUDA
host/native output and the explicit VFG comparison. `subpixel` retains the prior
control, and `reference`, `anchor`, `stable` keep their prior diagnostic meaning.
RowFlow, stateful models and file/reference rendering are not promoted to this
new policy. Shared-layout DLLs were all rebuilt together and pinned.

## Analytic GPU validation

`v1/check_stereo_coverage_gpu.py` tests both eyes against independently calculated
pixel-area intersections of a foreground rectangle. Strengths 0.25/0.5/1/2 and
widths 1/2/7/500 give 16 configurations, with small fractional shifts and offsets
as close as 1e-7 to integer boundaries. The earlier implementation fails the
near-integer case; the final implementation passes.

- Maximum coverage/analytic difference is 0.001961, within 8-bit rounding.
- In the strength-0.5 sweep, the old edge changes from fully opaque to absent in
  one step; new coverage changes by at most 2/255 per tested step.
- Foreground coverage mass is preserved within 2.1/255, including one-pixel objects.
- Mixed colors occur only at analytically partial pixels in the two-layer fixture.
- A textured single plane matches independent linear interpolation within one RGB
  level. Smooth depth retains the previous result within one level, due to improved
  coordinate arithmetic. Zero disparity is exact.

This is a known-geometry test, not proof of estimated depth accuracy or comfort.

## Public rendering and integration

`v1/compare_stereo_coverage_public.py` uses Base FP16 and the exact same fresh raw
depth for old/new synthesis, three public clips, 90 frames each at 30 processed
frames/second, 1080p, strength 0.5. CUDA postprocessing is exercised; the optional
flat-border refinement branch is outside this diagnostic. Newly built `subpixel`
mode is bit-exact to the separately preserved old stable DLL for all 270 frames.

| Clip | Mean fraction of pixels changed by more than one RGB level | Maximum frame fraction |
|---|---:|---:|
| FloorballGame | 0.312% | 0.416% |
| OfficeWalk | 0.662% | 0.744% |
| ParkingGarage | 0.538% | 0.677% |

These quantify scope, not a perceptual quality score. Three comparison movies
decode all 90 frames. They show **cropped left-eye old/new views**, not stereo pairs.
The OfficeWalk largest-change still was inspected: major geometry and texture are
retained; existing disocclusion artifacts remain. No continuous binocular viewing
or normal-speed visual quality acceptance was performed.

The real `coverage` route also passes:

- Small GPU input: 27 preprocessing fixtures, 72 public/adapted host/native exact
  cases over landscape, portrait, ultrawide and 4K, including cuts/flat input.
- Base/VFG: six exact original/native cases at 1080p and 4K, plus SDK generation
  at each size. Both modes use the same reconstruction before interpolation.
- 236 core/platform/profile contracts; Ruff E9/F and whitespace checks.

## GPU cost and actual native runs

An isolated alternating benchmark compares the preserved old stable binary,
new binary in subpixel mode and new coverage mode on one stream. Six warmup and
21 measured repetitions per case, rotating order, strength 0.5:

| Input | Old binary GPU projection | New subpixel | New coverage |
|---|---:|---:|---:|
| 1920x1080 | 0.288 ms | 0.301 ms | 0.302 ms |
| 3840x2160 | 1.654 ms | 1.668 ms | 1.667 ms |

These synthetic scene times include projection/linear RGBA packing, not model,
capture, SDK generation or display. Small differences are not statistical proof
of a precise cost and are not live FPS claims.

Actual owned public WGC input 3840x2160 / Full SBS 7680x2160, Base FP16, strength
0.5, unlimited output, fitted Qt output, 2-second warmup:

| Mode | Windows | Median native FPS | Fresh SBS FPS | Original source-to-Qt P50 |
|---|---|---:|---:|---:|
| New binary, prior subpixel policy | 3 x 3 s | 24.26 | 24.31 | 45.77 ms |
| Coverage A | 3 x 3 s | 24.22 | 24.22 | 47.34 ms |
| Coverage B, Medium VFG | 2 x 3 s | 38.29 | 19.15 | 82.09 ms |

B adds approximately 19.15 generated frames/second. Its extra GPU work and ordered
pair publication increase output cadence while reducing fresh throughput and
increasing latency. This reproduces the user's observation qualitatively; it does
not measure the user's game/session directly or claim that B preserves A's fresh
FPS. B's oldest contributing input is about 108 ms old in this run.

Current control and candidate whole-path rates are below earlier 55/77 FPS tests.
The cause was not isolated. Source painting was about 71–74 FPS; processing and
source age were higher in both policies. Do not attribute the whole difference to
the new coverage stage or compare the earlier absolute rates as matched trials.
The preserved-binary alternating test above bounds only the isolated projection.

Coverage A and B both pass hide/restore, resize, stop, restart and preparation
cancellation. Stopped native pools/nodes are zero; VFG create/close counts balance.
Measurements are Qt completion, not monitor scanout or general 4K60 support.

## Artifacts and pins

Under `out/stereo-coverage-20261106/`: `geometry.json`, `gpu-cost.json`,
`public/result.json` and public previews, `small/report.json`,
`native-bridge/result.json`, `contracts.json`, and `live-before`, `live-after`,
`live-vfg` reports/worker logs. Public media is the existing hash-verified
UVG-VCM corpus, CC BY 4.0; full attribution and preview modifications are embedded
in the report. No personal source or frame was recorded.

| Artifact | SHA256 |
|---|---|
| `out/live-depth-coverage/live_depth.dll` | `dfa9b515c5e078fb1befa9e37ad8ef7ec555a68828bf7f5dbd7e545f3e42171a` |
| `out/small-input-coverage/small_input.dll` | `c47a078e0cb870230cb37eb08c436dbdf7e3f0733cbba11a63c857d50e0da765` |
| `out/live-texture-coverage/live_texture_runtime.dll` | `e6bd639313304a282e1b4078024aab294abf0c820ad4675c1c9c4545bfb86191` |
| `out/vfg-native-bridge-coverage/vfg_native_bridge.dll` | `46b1f792dba13c1aa46bda163037bd241f63f216b1cff55dea31cc727ca756c4` |
| `out/rowflow-bridge-coverage/rowflow_bridge.dll` | `4bc5d66a80f6f8bbf7e8dcb19b3f7f1ab8b5d6b45629d0cd9812205b0f082081` |

A full app restart loads the new modules. User viewing on Owl3D at strength 0.5
remains the acceptance check for the practical benefit; equality to Owl3D Live 3D
quality has not been established.
