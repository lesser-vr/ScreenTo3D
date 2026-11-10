# Stereo output packing, 2026-11-09

Full SBS, Half SBS, Full Top-and-Bottom and Half Top-and-Bottom use a shared
packing contract. Full-resolution stereo synthesis and depth inference remain
unchanged. Native publication writes directly to the final-sized texture.
Host/file output packs RGB arrays before publication/encoding. VFG retains
full-resolution SBS interpolation buffers and packs the completed result.

Half modes average pixel pairs with integer round-half-up. An odd final pixel
is replicated. Left eye is left/top. Sampling never crosses the eye boundary.
Overlay coordinates follow the packed eye regions, including inverse text-axis
scaling for Half playback.

## Correctness

- Production GPU packing versus CPU reference was bit-exact for all formats at
  per-eye 17×19, 1920×1080 and 3840×2160, including arbitrary alpha.
  Results are in out/stereo-layout-gpu-final.json.
- Actual Base native GUI sessions passed for all formats, including dimensions,
  F11/Escape, overlay on/off, minimize/restore, close, restart and cancellation.
  Results are in out/stereo-layout-gui-{full-sbs,half-sbs,full-tb,half-tb}/.
- VFG Half Top-and-Bottom and host Full Top-and-Bottom passed the same checks in
  out/stereo-layout-vfg-half-tb/ and out/stereo-layout-host-full-tb/.
- VDA Full Top-and-Bottom passed actual native output, fullscreen, restart and
  cancellation in out/stereo-layout-vda-full-tb/. Updated source and portable
  ScreenTo3D.exe both opened and closed normally.
- A 12-frame public excerpt at 320×180 converted through the desktop worker with
  CUDA rendering and H.264. FFprobe confirmed 12 decoded frames for 640×180,
  320×180, 320×360 and 320×180 respectively. Outputs and telemetry are in
  out/stereo-layout-files/.
- Unit checks cover packing, odd edges, eye order, descriptors, native transfer,
  file jobs, encoder limits and pipeline lifecycle.

## Native output measurements

RTX 5090, Small/Performance, VFG off, native output, unlimited presentation.
The prepared public FloorballGame preview is decoded in an owned process and
painted at a physical capture raster of 3840×2160. Its underlying preview is
1920×1080, enlarged for this test. This tests 4K processing and output.
Each format used six seconds of discarded warmup followed by five six-second
windows. Output FPS counts distinct native Qt afterFrameEnd IDs. GPU readings
are device-wide 1-second samples within those windows, including desktop/source.

| Format | Output pixels | Output FPS median [range] | GPU usage median | GPU memory median |
|---|---|---|---|---|
| Full SBS | 7680×2160 | 62.44 [62.26–62.44] | 42% | 4129 MiB |
| Half SBS | 3840×2160 | 62.44 [62.28–62.47] | 43% | 4034 MiB |
| Full Top-and-Bottom | 3840×4320 | 62.45 [62.34–62.46] | 42% | 4130 MiB |
| Half Top-and-Bottom | 3840×2160 | 62.44 [62.29–62.47] | 42.5% | 4034 MiB |

Source painting medians were 62.24–62.33 FPS. This input-limited comparison
does not establish maximum rendering throughput. Half modes reduced device
memory by approximately 95 MiB, consistent with three output-sized RGBA textures.
GPU usage ranges overlapped. Median power was approximately 201–203 W.
A material GPU load, power or FPS improvement was not established.
Per-eye generation/inference cost and fullscreen Qt framebuffer size are retained.

Raw results are in out/stereo-layout-final-{full-sbs,half-sbs,full-tb,half-tb}/.
The combined summary is out/stereo-layout-summary.json. The first three
environment files' legacy texture-runtime hash field points to an older
diagnostic DLL. The actual production runtime used for all four runs is pinned
in portable_cuda.py as
e1081f3c50dfe56cef0dcff79c4e7e568e8830e8299b1e7e616f9dec4898a597.

An earlier comparison in out/stereo-layout-bench-* stopped at an obsolete
overload probe. Slowing only health polling did not slow event-driven delivery.
The benchmark now suppresses frame-ready/deadline wakeups only during its bounded
overload probe. The final four runs passed that probe.

Playback devices must select the matching stereo format. Owl3D decoding,
restored-eye sharpness and stereo comfort require user device review.
