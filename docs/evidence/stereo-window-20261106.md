# Left/right screen-edge protection — 2026-11-06

## Delivered behavior

The prepared-local Small/Base CUDA live default is now `window`, including the
existing range/coverage/motion correction and the A/B/Small VFG launchers. It adds
a thin floating stereo window when crossed-disparity foreground is clipped by
the left or right image boundary. No extra UI option; strength still defaults to
0.5. Restart the application to load the new native modules.

The left eye gets a left-edge mask, and the right eye a right-edge mask. This
places the apparent frame in front of the clipped foreground. It preserves
coordinates/depth, center stereo and image dimensions by deliberately hiding a
small edge strip. The technique and eye/edge convention are described in the
[SMPTE stereoscopic glossary](https://pub.smpte.org/pub/eg2061/eg2061-2016.pdf) and
[Autodesk floating-window documentation](https://help.autodesk.com/cloudhelp/2022/ENU/Lustre-UG/files/Stereoscopy/Lustre_UG_Stereoscopy_Using_the_Floating_Window_html.html).
This is an independent implementation, not copied Owl3D code or a claim about
Owl3D's internal behavior.

Only left/right edge violations are addressed. Top/bottom clipping, scene-wide
disparity budgets and physical eye comfort remain separate. Edge HUD/text can be
partially hidden by the mask. At high strength, the width cap can leave residual
violations rather than hide a large part of the image. Direct Owl3D acceptance
and sustained generated-frame quality remain unverified.

## Implementation and comparison contract

- From the actual projection depth, find positive left-eye shifts `s` for which
  source `x < s` or `width-1-x < s`. Reduce the maximum `2*s` independently on each
  side, capped at 1.5% of one eye's width. The common shift kernel performs the
  reduction on the GPU; it does not change any shift or depth.
- Immediate expansion; release uses `max(target, previous*exp(-dt/0.20))` with
  source time. Widths below 0.01px become zero. Cuts, time reversal, >100ms gaps
  and resize reset state. A one-pixel fractional coverage edge avoids integer
  stepping. No lookahead is added to the existing live path.
- Shared host/native/VFG original-frame projection applies the mask after stereo
  reconstruction. Four GPU floats and two host timing fields are owned by the
  existing renderer. Normal rendering adds no host pixel/depth readback.
- All allocators and consumers of the appended `LiveDepth` layout were rebuilt
  and pinned in separate `*-window` output directories. Previous binaries remain.
  RowFlow is not opted into the correction; its bridge was rebuilt for layout
  compatibility. Model artifacts/precision, capture policy and output limits are
  unchanged.
- VFG snapshots two widths on the GPU alongside each original RGBA buffer and
  swaps both buffer pairs together. After interpolation, it reapplies the larger
  of the two source masks before recording the generated frame's ready timestamp.
  This requires four additional GPU floats and a bounded edge kernel; no source
  image readback or source RGBA mutation.

This is an intentional visibility change. The comparison contract is exact
baseline pixels outside the declared mask, exact projection geometry/depth,
correct left/right mask side, bounded widths and source-time/reset behavior.
It does not claim pixel equality inside the deliberately masked strip or a
measured reduction in physical eye strain.

## Tests and results

105 synthetic cases: 64x32, 1920x1080, 3440x1440, 1080x1920 and 3840x2160;
strength 0.25/0.5/2; screen/far/near planes, left/right clipped foreground, centered
foreground and a one-pixel near object. Independent CPU mask/target calculations
match GPU output exactly (target tolerance 0.00002px). Disabled projection stays
bit-exact to the prior range DLL. Screen/far/centered-foreground cases remain
unchanged. Every non-mask output pixel is exact, so no coordinate bending or
central disparity compression is introduced.

Immediate expansion, cut reset, invalid interval rejection and half-second
release at 30/60/120Hz pass. Released widths agree within 0.000001px across rates.
The existing motion-history synthetic tests also pass with the rebuilt layout,
including depth-jump/newly-visible rejection and time discontinuities.

Public comparison: three existing attributed UVG-VCM clips, each 30 observations
from the first 90 at nominal 20Hz, Small and Base, 1920x1080, strength 0.5.
Each pair shares the same inference and range+motion depth. All 180 pairs match
the independent mask oracle and preserve all outside-mask pixels exactly.

| Model / clip | Maximum left / right mask, px | Mean changed SBS pixels |
|---|---:|---:|
| Base / Floorball | 13.73 / 13.51 | 0.726% |
| Base / Office | 13.73 / 0 | 0.251% |
| Base / Parking | 13.61 / 13.73 | 0.729% |
| Small / Floorball | 9.50 / 9.50 | 0.518% |
| Small / Office | 9.50 / 0 | 0.193% |
| Small / Parking | 9.50 / 9.50 | 0.521% |

The maximum actual width here is about 0.72% per eye for Base and 0.50% for Small,
below the 1.5% cap. Fractions count changed RGB pixels, not lost stereoscopic
information or perceived improvement.

VFG initially reintroduced up to 20/255 RGB into an originally black right border
at 1080p. That version was not accepted as the finished VFG path. The final
post-interpolation repair passes Base/Small 1080p and 4K: protected columns are
exact black. Base uses 13/13 columns at 1080p, 27/26 at 4K; Small uses 9/9 and
19/19. Six original/native comparisons per model remain exact. This checks those
bounded generated samples, not all temporal binocular artifacts.

Other completed checks:

- 243 CPU contracts and 12 VFG comparison/timing tests pass.
- 27 Small preprocessing fixtures and 72 host/GPU/native cases pass over four
  aspect/size configurations with the new default selected on both paths.
- Actual Base A and final Small VFG GUI checks pass Start, strength 0.5,
  selected-model guard, two-screen movement, fullscreen, hide/restore, protected
  controls/capturable output, cross-process recapture rejection, stop/restart and
  zero native pools/nodes after cleanup. Only owned public video was captured.
- RowFlow bridge receives exact RGB and refined depth through the rebuilt
  borrowed layout; its learned model/compiled performance was not rerun.
- Scoped Ruff and whitespace checks pass. No commit or push was performed.

## Cost measurement

Alternating enabled/disabled native projection/publication, identical analytic
near depth and public RGB, twenty warm samples per condition, diagnostic consumer
readback outside the measured interval:

| Source | Disabled median | Enabled median |
|---|---:|---:|
| 1920x1080 | 0.4310ms | 0.4332ms |
| 3840x2160 | 1.8467ms | 1.8461ms |

The differences are at measurement-noise scale; they are not evidence of a speedup
or a guaranteed zero cost. Intervals include enqueue gaps. Capture, inference,
VFG post-interpolation repair and actual panel scanout are not measured by this
isolated comparison. No new full-app FPS support claim is made.

## Reproduction / artifacts

- `v1/check_stereo_window.py --output <json>`: synthetic independent oracle.
- Same script with `--model base` / `--model small`: public pairs.
- Same script with `--benchmark`: isolated native delivery comparison.
- `v1/test_small_gpu_input.py --quality window --output <new-directory>`.
- `experiments/vfg/check_native_bridge.py --quality window --model da2-base`
  or `da2-small`, plus `--output <new-directory>`: original/native/generated mask checks.
- Existing comparison GUI checks use the default `window` mode.
- Explicit `DEPTHSBS_STEREO_QUALITY=motion` selects the pre-window diagnostic
  control. Normal launchers require no setting change.

Data: `out/stereo-window-20261106/` contains `synthetic.json`,
`{base,small}-public.json`, `benchmark.json`, `cpu.json`,
`small-parity/report.json`, `{base,small}-generated-final/result.json`,
`base-gui/smoke.json`, `small-vfg-gui-final/smoke.json`, `motion-regression.json`,
and `rowflow-layout.json`. Public attribution is embedded in the public results.

Build procedures: `scripts/build-live-depth.ps1`, `scripts/build-small-input.ps1`,
`scripts/build-live-texture-projection.ps1 -OutputName live-texture-window`
(also `rowflow-bridge-window`), `scripts/build-live-motion.ps1` and
`experiments/vfg/build-native.ps1`. Final pins:

| Module | SHA256 |
|---|---|
| Base layout | `141985fed439632197b907f50d34d9962b08fa6f36871e6221c3acc52d6e0fef` |
| Small layout | `2a6f0ff06e277d8d2cc9d7ceb65c84e54b2b4fe0d33009c2e8e4f205e28feca7` |
| Native texture | `8300b2f12c67a2d37c202f36453e04492e7a9cf17325f5bf5ff29e6ec66e156d` |
| Motion | `fff169493ca1231f0eba18ae0be5afc45d37c338929231eacf8cec559785d7f6` |
| VFG | `c7b773f98bb529439ce900a80b942eecd575d9138c2d40df48c989a0ca971f41` |
| RowFlow layout bridge | `01cd7538f52112f078e00bfb224a8b6a536403a55b217c54b1c69cad427b8e3a` |
