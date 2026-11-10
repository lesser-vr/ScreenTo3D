# oVDA additional pixel EMA tuning — 2026-11-09

## Delivered change

The source live oVDA adapter now supplies `temporal_depth_alpha=0.5`. Its original
`temporal_alpha=0.18` remains the depth-range EMA. The shared worker applies the
immutable model override before constructing the renderer; diagnostics use the
same resolver. File modes leave the new optional field unset. Other live models,
guide radius, motion/depth gates, model precision, source geometry, strength and
the short-skip policy are unchanged. No GUI setting was added.

The existing CUDA postprocessor used one coefficient for both range and pixel
EMA. Raising that coefficient would mix two changes. An optional internal pixel
argument now separates them; the existing exported signatures and default behavior
remain compatible. Only a new source-only oVDA bridge was built/installed; the
shared production CUDA DLLs and their pins were not replaced.

`LiveSourceGpuCandidate` lazily creates the bridge only for an explicit oVDA pixel
override. The bridge validates its native hash and borrowed-layout identity,
uses the owner stream and holds a weak renderer reference. It adds no buffers or
per-frame readback. Failed bridge setup closes its context before publication.
The CPU live reference also separates the two coefficients; ordinary file policy
defaults remain the same.

## Native provenance and compatibility

Build: `scripts/build-ovda-postprocess.ps1`, CUDA 13.1.80, MSVC 2022,
`--fmad=false`, SM120 plus compute_75 PTX, matching portable guide flags. The new
bridge includes the common implementation, but the LiveDepth structure has no
new fields. Native pool/lease/stream ownership and failure fences remain owned
by the existing renderer.

- Bridge DLL SHA256: `da3a065477429ce271382739a83bccea0d52dfd6222fefeafbc55d10f35c69c6`.
- Bridge source SHA256: `802a835c53e3e4b8a47c8e7a7e3960f1e5ed29da49bdb37bcf18bb1cb00542cd`.
- Common live-depth source SHA256: `814b883ecac1f71c8b8b06cc838b77d8bcb237e12fee347193b1f7a01d6ab43f`.
- Borrowed layout validation identity:
  `0394a7b790c92db37aaa49190e213edc65914e79625f03d38d62cf3c2911da85`.

Manifest: `out/ovda-postprocess/build-manifest.json`. This optional NC-SA runtime
is not added to portable distributions or generalized to another GPU.

## Declared comparison contract

`evaluate_pixel_ema.py` compares legacy and independent pixel EMA weights
0.18/0.5/0.75/1.0. All postprocessors consume the exact same pending model depth
on its owner stream; a real completion is deferred only in this explicit
multi-consumer diagnostic, until every postprocessor has finished. Product
completion and resource lifetime behavior are unchanged.

The contract, declared in the script before evaluation, requires:

1. Independent 0.18 exactly matches legacy normalization, smooth depth and native
   pixels; all weights have identical pre-EMA normalization and range endpoints.
2. The synthetic step response improves.
3. In every natural case, additional low-RGB-motion eye-shift RMS stays within
   0.1 pixel when scaled to 3840-pixel eye width, strength 0.5. This is an engineering
   subpixel budget, not a perceptual comfort threshold.

## Results

A 512x288 native fixture holds RGB constant and changes a central raw-depth region
from 0.45 to 0.49 after 36 settled updates, keeping the percentile endpoints and
motion gates controlled. The region's step remains below the bypass threshold.
Ninety-percent response takes:

| Pixel EMA | Updates to 90% step response |
|---|---:|
| Legacy / independent 0.18 | 12 |
| 0.5 | 4 |
| 0.75 | 2 |
| 1.0 | 1 |

This is additional-EMA response, not measured game latency or a model's own
temporal delay. The 72 fixture frames also pass exact legacy/0.18 compatibility.

The checksum-verified FloorballGame, OfficeWalk and ParkingGarage clips use
1280x720/64 frames, 720x1280/48 frames and scaled 3840x2160/20 frames each:
396 public model-depth frames and five independent native postprocessors.
Model/cache history, range response and input sequences are fixed across weights.
Every frame passed exact range/pre-EMA identity, plus legacy/0.18 smooth/native
pixel parity. Thus the legacy bridge control covers 468 synthetic/public frames.

After eight initial updates, the low-RGB-motion mask requires RGB differences
at most two byte levels and a 7x7 erosion. RMS temporal changes in actual native
eye shift are accumulated on that mask. A still-color region can contain real
depth change, so this is a variation proxy rather than pure noise. The tracking
proxy measures smooth-depth versus the current normalized model depth, scaled
to the corresponding eye shift before guide filtering.

| Pixel EMA | Worst additional low-RGB-motion RMS, 4K eye pixels | Budget |
|---|---:|---|
| 0.5 | 0.07281 | Pass |
| 0.75 | 0.13684 | Exceeds 0.1 |
| 1.0 | 0.21234 | Exceeds 0.1 |

Weight 0.5 is the fastest-response candidate passing every case. Its EMA tracking
RMS falls 58.3–70.9% relative to 0.18. This is closer tracking of current model
depth, not an accuracy improvement against ground truth. Small variation can
increase; physical comfort and normal-speed visual acceptance are not established.

Valid artifact: `out/ovda-pixel-ema-20261109/comparison-r2/report.json`.
The initial `comparison` run stopped before frame evaluation because the diagnostic
used the wrong snapshot export name. It contains no comparison result.

## Product routing and error checks

`check_pixel_ema_integration.py` verifies 48 additional native fixture frames:
the product policy's 0.5 output equals the explicit comparison renderer exactly,
and product 0.18 matches legacy while range endpoints stay identical. It also
checks a cut/reset, six invalid weights and corrupt-DLL cleanup. Artifact:
`out/ovda-pixel-ema-20261109/integration.json`.

Thirty-four affected unit checks pass, including live model resolution/diagnostics,
unchanged file defaults, CPU reference separation, backend cadence, geometry and
pixel contracts. Actual GUI start, input resizing across landscape/portrait/square,
both-monitor movement, fullscreen, stop/restart and preparation cancellation pass:
`out/ovda-pixel-ema-20261109/gui/report.json`.

## Actual native throughput

RTX 5090, driver 621.14, Torch 2.7.1+cu128 and TensorRT 11.2.1.2. Both variants use
the same current-device FP32 518x924 control plan (SHA256
`7bd4916e0104a1306c99dd0bb5a37e8bf27aed0f8ac698b5f35f1076147b0e75`), GPU capture,
fixed buffers, continuous short-skip policy, Half TB, strength 0.5 and VFG off.
App output is unlimited for measurement; the user's default setting is unchanged.
An owned FloorballGame window advances on a 16ms timer. 4K scales this public source.

At each resolution, session order is .18/.5/.5/.18. Each session discards three
warmup seconds, then measures three adjacent three-second windows: six windows
per condition. Native FPS counts distinct submissions, not physical scanout.
GPU samples are device-wide and include playback/desktop and other clients.

| Input | Pixel EMA | Median native FPS (range) | Mean GPU |
|---|---|---:|---:|
| 1920x1080 | 0.18 | 58.65 (58.44–59.04) | 85.69% |
| 1920x1080 | 0.5 | 58.95 (58.73–59.51) | 85.36% |
| 3840x2160 | 0.18 | 46.12 (45.66–46.47) | 86.71% |
| 3840x2160 | 0.5 | 46.40 (46.09–46.65) | 86.64% |

These short runs show essentially unchanged throughput, not a material FPS
optimization. All timed inferences use full c16 context; all eight sessions stop
with zero live native pools/nodes. Artifact:
`out/ovda-pixel-ema-20261109/native/report.json`. Reproduce with
`benchmark_precision_live.py --ema-comparison --windows 3 --layout half-tb
--output <new-directory>`. Longer sequences, other GPUs and physical-display
comfort remain separate checks.
