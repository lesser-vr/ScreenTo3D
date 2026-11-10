# oVDA uniform-background FPS collapse — 2026-11-10

## Finding

The reported black-background/central-object slowdown is reproduced on the
user-supplied OLED test video's 01:04 transition into the flower shot. The main
bottleneck is the existing full-source-resolution CPU uniform-backdrop refinement,
activated by uniform border colors in Video Quality. The adopted mixed-FP16 model
still infers in roughly 7–9 ms in the slow condition. No product default, model,
precision, cache guard or correction behavior was changed by this investigation.

`LiveGpuCandidate.needs_background()` accepts a border if >=98% of pixels lie
within the configured color tolerance of its median. Video Quality enables
`flat_background_refinement`, including oVDA. With the flower on black, this
activates a costly path inside the normal GPU/native renderer:

1. Allocate/read back the full normalized/guided FP32 depth.
2. Read the full RGB image back through `GpuFrame.to_host()`.
3. Run `stereo.refine_flat_background()` on the CPU: color mask, border-connected
   background components, foreground components, per-component depth aggregation,
   distance transform, rim blending and background depth median.
4. Upload the corrected FP32 depth for native projection.

This is one conditional CPU depth-correction stage within a GPU renderer, not a
switch of the entire renderer to its CPU implementation. It accepts any uniform
backdrop color; black is a common trigger, not a special model mode.

## Exact local scene and ablation

The supplied file probes as 3840x2160, AV1, 10-bit BT.2020/PQ, 60/1, duration
582.616667 seconds. Its name includes 8K, but the tested downloaded stream is 4K.
The original file is preserved. Only authorized local derivatives were created
under `out/ovda-black-scene-20261110/`; they are not public corpus material.

FFmpeg extracted 64.0–67.0 seconds, converted PQ to linear light, used Hable
tone mapping, then converted to BT.709 SDR/H.264. The first ~0.4 seconds contain
the lava scene; the flower is present from ~65 seconds onward. `lava.mp4` uses
the first 0.4 seconds; `flower.mp4` uses 65.2–66.7 seconds. The contact sheet
confirms the requested transition. This is an explicit SDR reproduction, not
certification of the original player's HDR tone mapping or scanout behavior.

`analyze_uniform_background.py` uses the ordinary adopted oVDA plan, WGC GPU
capture, native Half TB, strength 0.5, VFG off, output uncapped. An owned Qt source
plays the derived clip with a 16 ms timer. Lava is a nonuniform-border control.
The flower ablation changes only `flat_background_refinement` in the diagnostic
worker. ON/OFF/OFF/ON session order gives four 3-second measurement windows per
condition and size, after a 2-second warmup. All sessions release their pools and
nodes. Preferences/placement are isolated.

| Source/window size | Background correction | Native output FPS | Inference ms* | Background stage ms* |
|---|---|---:|---:|---:|
| 1920x1080 flower | ON, normal | 13.46 | 8.09 | 58.72 |
| 1920x1080 flower | OFF, diagnostic | 39.22 | 6.60 | ~0 |
| 3840x2160 flower | ON, normal | 2.99 | 8.59 | 306.70 |
| 3840x2160 flower | OFF, diagnostic | 29.03 | 6.51 | ~0 |

*Stage columns average per-window medians of sampled distinct worker updates.
They are wall intervals, not isolated GPU kernel times. The background interval
also includes full RGB host readback. Native FPS counts distinct submissions,
not physical display scans. The 4K-decoded Qt source and desktop capture/presentation
also constrain these runs; OFF rates are not maximum possible oVDA performance
or a promise to match this exact rate in the user's player.

The lava control has no background-stage work (median <=0.0003 ms) or full-frame
input transfers, although its source/decode/presentation throughput is also
limited. The same flower scene recovering when only correction is disabled,
together with the stage timing and transfer counters, identifies the conditional
correction as a causal bottleneck independently of HDR/AV1 playback overhead.

## Transfers, CPU profile and temporal consequence

For 1080p with correction, measured H2D is 8294400 bytes/frame and D2H is
14536276 bytes/frame; with correction disabled H2D is zero and D2H is 3076 bytes.
At 4K, H2D is 33177600 bytes/frame and D2H is 58099876 bytes/frame. The dominant
payload is 3-byte RGB + 4-byte depth D2H and 4-byte corrected depth H2D: about
91.24 MB per 4K frame, before small metadata. The CPU also creates and scans
multiple full-frame masks/labels/depth intermediates on every accepted frame.

An isolated profile of three actual flower frames per size confirms that the
refinement itself is expensive without source/capture competition: mean CPU
function time ~46 ms at 1080p and ~201 ms at 4K. At 4K, approximately 119 ms per
call is attributed to the refinement function's own array expressions/indexing/
aggregation, ~23 ms to `isin`, ~10 ms to distance transform and ~10 ms total to
the two connected-component calls. Thus connected components alone are not the
whole cost. Profile numbers include instrumentation and are not live output FPS;
the ~307 ms live background interval includes readback and concurrent-source costs.

At normal correction ON, all measured flower windows have full-context fraction
zero. In 1080p, 157 gap resets occur across the four 3-second windows; at 4K, 35.
The correction delay exceeds the existing <=one skipped update/<=50 ms history
contract, so cache history repeatedly resets. Disabling correction raises measured
full-context occupancy (~74% at 1080p/~66% at 4K in this fixture). This explains an
additional temporal-stability risk; no binocular quality change is asserted.

## Improvement direction and scope

Prioritize eliminating the full-frame CPU roundtrip and repeated high-resolution
array work. A GPU-resident or reduced-resolution mask/refinement candidate should
be evaluated on this flower's thin hairs/rim, background depth and temporal output.
Disabling correction is a useful ablation, but changes depth behavior and is not
treated here as a parity-preserving fix. Raising the cache-gap allowance would
not remove the measured processing bottleneck.

Artifacts: `out/ovda-black-scene-20261110/native/report.json`, `summary.json`,
`cpu-profile/report.json`, CPU `.pstats`/text reports and local scene derivatives.
The diagnostic fixture now accepts an explicit `Path` clip in addition to named
public fixtures. Production application code and defaults are unchanged.
