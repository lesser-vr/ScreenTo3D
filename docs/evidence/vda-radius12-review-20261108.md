# VDA Small next-step review: fixed radius 12

The released VDA Small Video Quality renderer uses radius 12. Its existing rolling-sum filter dispatches a general radius above 8. The review candidate dispatches the existing fixed-radius CUDA implementation at radius 12, preserving the 25×25 neighborhood, full source resolution, FP32 model engines, output settings and temporal policy. The alternative DLL was built and loaded only in the benchmark workspace. The release pins and distribution are unchanged.

## Native SBS

RTX 5090, Windows, driver 621.14. The LocalGPU portable captured the same owned 1080p60 FloorballGame preview window at two sizes, using GPU input, strength 0.5 and VFG off. Source advances were approximately 62.5 FPS. Each configuration discarded five seconds after initial output and counted two adjacent eight-second windows in one session. The unlimited test ran original then candidate at 1080p and candidate then original at 4K. GPU utilization is the mean of one-second device-wide NVML samples. Output FPS counts distinct native submissions.

| Input and limit | Output FPS, original → fixed | GPU use, original → fixed | Sampled stereo stage, original → fixed |
|---|---:|---:|---:|
| 1920×1080 unlimited | 55.59 → 55.98 | 83.1% → 84.9% | 1.21 → 1.02 ms |
| 3840×2160 unlimited | 39.91 → 45.36 | 87.9% → 86.4% | 5.47 → 2.59 ms |
| 3840×2160 capped at 60 | 38.27 → 43.14 | 81.3% → 79.4% | 5.56 → 2.60 ms |

The capped 4K test ran the original first. The candidate gained 12.7% under the default cap and 13.7% with unlimited output.

The 4K unlimited runs observed 356 sequence-gap resets among 640 completed backend calls originally and 272 among 726 with the candidate. The faster run processed more frames on the cached branch. Median depth-stage samples therefore mix different proportions of warmup and cached frames.

## Same-input comparison

Two renderer instances shared each VDA depth token. They alternated render order, used identical frame timestamps and reset their histories halfway through each 30-frame sequence. Tests used FloorballGame at 1080p and scaled 4K, ParkingGarage at scaled 4K, and a 513×289 moving thin-edge and flat-background fixture. Aligned depth and all BGRA channel bytes in the shared SBS textures matched on all 120 frame pairs. On the two 4K clips the dedicated guide GPU interval (CUDA events 5–6 after six initial frames) fell from 3.37–3.39 ms to 0.77 ms. This comparison covers these inputs on one GPU.

## Remaining cost

In an isolated 1080p GPU-input replay, two 54-frame runs per policy discarded the first eight frames and measured CUDA event intervals on the engine stream. Median TensorRT execution took 10.22–10.27 ms on forced warmup and 12.17–12.18 ms with continuous history. Cache concatenation took 0.50–0.53 ms on the cached branch; finite-output checks took 0.61–0.88 ms wall time. This replay excludes capture and SBS delivery.

Prioritize the full-resolution radius-12 specialization for 4K. For a further model-side experiment, compare a separate mixed-precision TensorRT build to FP32 with both canvas widths, real warmup-to-cached transitions, long histories and cuts. Keep full-rate depth/temporal quality and repeated native FPS in the acceptance criteria. End-to-end gains from changing precision have not been measured.

## Portable release verification

Built the production source with the portable CUDA script and updated the release pin and the two local desktop portables. The shipped `live_depth.dll` SHA-256 is `205bfa0df9ed5c1969e4c6759f680f94d426fdcd46a3730179965102bc044b8c`. CUDA object inspection found compute_75 PTX and SM120 machine code. The VDA pack and engine identity are unchanged.

With the previous release DLL as the control and the other renderer using the packaged loader, all 120 matched frames from the four cases above had identical aligned depth and full SBS bytes. Median 4K guide time was 3.38–3.39 ms before and 0.77 ms after. In the LocalGPU portable, at the default 60 FPS limit, two eight-second intervals of public window capture yielded 51.99 and 52.36 native submissions/s at 1080p and 43.25 and 43.21 at 4K. Raw local results are in `out/vda-radius12-release-9b05e5fd/{pairs,default60}.json`.
