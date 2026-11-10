# Half-resolution stereo synthesis, 2026-11-09

The published implementation uses half-height eye synthesis for native CUDA
Half Top-and-Bottom with VFG off. Half SBS retains full-resolution eye synthesis.
File conversion, host delivery, VFG and RowFlow continue to pack completed eyes.

Full-resolution depth inference, temporal/range/motion history, contour-adjusted
disparity and floating-window state are prepared first. Adjacent RGB/depth/shift
rows are reduced, choosing the nearer sample when normalized depth differs by
more than 0.04. Horizontal disparity and window-mask coordinates keep their
original pixel units. Projection, hole resolution and reconstruction process half
as many rows. The output texture dimensions and playback format are unchanged.

The implementation reuses guided-filter scratch t1/t2/t3/b after make_shift.
These arrays are overwritten before their next guide use on the same CUDA stream.
Persistent source/depth/motion/range/window buffers remain separate. No new CUDA
allocation or ownership lifetime is introduced by this renderer.

## Comparison contract and quality

The reference is the prior production runtime, SHA-256
e1081f3c50dfe56cef0dcff79c4e7e568e8830e8299b1e7e616f9dec4898a597,
preserved at out/half-render-reference/live_texture_runtime.dll.
This is an intentional quality change, compared to full-resolution synthesis
followed by pair averaging. Initial numeric limits were RGB MAE <= 1/255,
pixels with any channel difference > 8 <= 1%, and such pixels within a dilated
reference Canny edge mask <= 5%. Depth-history maximum error must be zero.
These are development comparison thresholds, not binocular comfort certification.

Three prepared public sequences, FloorballGame, OfficeWalk and ParkingGarage,
were tested at 1920×1080 and 3840×2160. Seven samples per sequence included a
repeated frame, adjacent moving frames and later positions. The 4K raster is
resized from the prepared 1080p preview and does not establish native-4K detail
quality. Strength was 0.5 and live quality was detail.

| Reduced synthesis | Size | Samples | Samples outside numeric limits | Max RGB MAE / 255 |
|---|---|---|---|---|
| Half SBS | 1920×1080 | 21 | 21 | 2.661 |
| Half SBS | 3840×2160 | 21 | 0 | 0.692 |
| Half Top-and-Bottom | 1920×1080 | 21 | 0 | 0.242 |
| Half Top-and-Bottom | 3840×2160 | 21 | 0 | 0.076 |

All 84 samples had exactly equal full-resolution depth histories. Half SBS
differences were concentrated in high-frequency texture and object edges.
Horizontal reduction also changes the source-space support of fixed horizontal
reconstruction neighborhoods. Vertical reduction preserves those horizontal
neighborhoods. This supports selecting Half Top-and-Bottom for implementation.

The production DLL repeated all 42 Half Top-and-Bottom comparisons with zero
depth error and all numeric limits passed. The generic final-packing oracle also
passed 12 GPU/CPU exact comparisons, including odd dimensions, arbitrary alpha
and 4K. Small, Base and VDA passed actual Half Top-and-Bottom GUI output,
fullscreen/overlay switching, close, restart, minimize and cancellation.

Raw quality evidence and saved comparisons are in out/half-render-quality-scratch/
and out/half-render-production-quality/. The original allocated-buffer prototype
is in out/half-render-quality-1/. Reproduction uses v1/compare_half_render.py
with --layouts half-tb --production and a fresh --output directory.

## Native measurements

The original allocated-buffer trial introduced approximately 90 MiB of additional
device memory. The final scratch-backed implementation removes those allocations.
Five six-second windows after six seconds of discarded warmup were recorded per
Half format at a 3840×2160 capture raster, Small/Performance, strength 0.5, VFG off,
unlimited native output. The source painted at approximately 62 FPS.

For Half Top-and-Bottom, the scratch candidate's median sampled projection stream
interval decreased from 0.792 ms to 0.375 ms. Device-wide median GPU utilization
changed from 42.5% to 39%, power from 201.4 W to 191.1 W, and device memory from
4034 MiB to 4037 MiB. Output remained approximately 62.4 FPS, limited by the source.
GPU samples include the desktop and source painting; they are not process-only
attribution. CUDA event intervals include enqueue gaps.

Raw runs are in out/stereo-layout-final-half-tb/ (reference),
out/half-render-native-half-tb/ (allocated prototype) and
out/half-render-scratch-half-tb/ (scratch candidate). Aggregation is stored in
out/half-render-summary.json. Production-native measurements are recorded
separately in out/half-render-production-native/.

The production-native confirmation used the same five-window procedure and
recorded 62.45 FPS [62.29–62.48], 40% device-wide GPU utilization, 4037 MiB,
192.1 W and 0.375 ms median projection stream interval. The source painted at
62.30 FPS. This confirms the candidate's stage-time benefit in the deployed
path, with approximately 2.5 percentage points lower device-wide GPU usage than
the earlier reference. It does not establish maximum throughput or a universal
power reduction across workloads.

The approved source change is in half_render.cuh and live_texture_publish.cu.
The production runtime SHA-256 is
75b2796f1f3813df01fe5086b59735036906012985bf09331baa4772f648eeeb.
The Half SBS candidate remains available through the benchmark's explicit
--half-render-trial switch and the pinned half_render_trial_worker.py loader.
It is excluded from ordinary app selection because of the 1080p failures.

Saved stills received visual inspection. Normal-speed binocular playback on
Owl3D and native-4K fine-detail content remain unverified.
