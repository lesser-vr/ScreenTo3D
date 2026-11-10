# VDA Small v3 live history across one skipped capture

The diagnostic setting `DEPTHSBS_DEPTH_HISTORY=vda-single-skip` retains VDA history for a sequence increment of two with positive, increasing source timestamps no more than 50 ms apart. Detected cuts and resizes reset history. Larger sequence gaps, duplicate or backward indices, invalid timestamps and pauses beyond 100 ms also reset it. The default retains the prior VDA behavior. File conversion uses a separate pipeline.

On an RTX 5090, the packaged native app captured FloorballGame at approximately 62.5 FPS with a 60 FPS output limit, VFG off and strength 0.5. Two eight-second 4K windows per policy ran in baseline/candidate/candidate/baseline order after five seconds of warmup per session.

| Policy | FPS by window | Gap resets in 16 s | Mean device GPU utilization |
|---|---|---:|---:|
| Reset on skips | 58.23, 57.99 | 67 | 68.4% |
| Retain one short skip | 57.36, 57.32 | 0 | 70.1% |

The matched replay used 63 frames each of FloorballGame, OfficeWalk and ParkingGarage, followed by six white frames. A reference pipeline processed every frame. The two test pipelines both skipped five individual frames in each video, including the last frame before the next cut. Results below cover the same 174 retained public-video frames per profile. The moving-edge metric measures error in consecutive aligned-depth differences relative to the reference on pixels with a luma change above 12 and a current Canny edge. It includes image motion and does not measure perceptual flicker or motion-to-photon latency.

| Canvas | Mean moving-edge depth-change error (reset → retain) | Mean SBS RGB error on 0–255 scale (reset → retain) |
|---|---:|---:|
| 518×896 | 0.004000 → 0.000307 | 0.635 → 0.081 |
| 518×924 | 0.004030 → 0.000349 | 0.884 → 0.117 |

The first retained frame at all three constructed cuts matched the reference in aligned depth and SBS bytes at both resolutions. Physical display review remains open. Local scripts and raw results are in `out/vda-single-skip-20261108/`.
