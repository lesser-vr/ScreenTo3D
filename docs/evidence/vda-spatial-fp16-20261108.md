# VDA Small spatial attention on the RTX 5090

The two trials start from the shipped v2 encoder-mixed ONNX pack and change the two spatial attention products in each of its twelve encoder blocks. Both widths (518×896 and 518×924) have warmup and cached engines. The local trial loader verifies the plan hashes and uses the existing VDA engine and native renderer. The trials stayed outside the distribution and user engine cache.

## Engine behavior

The first graph rounds the QK and AV operands and results to FP16. Casts express FP32 MatMul semantics and the original FP32 Softmax in ONNX. TensorRT 11.2.1.2 compiles the three operations into one `_gemm_mha_v2` kernel per encoder block. Engine inspection identifies the three operations and half-precision bindings, but does not expose the internal accumulator or Softmax precision.

The second graph keeps the QK scores in FP32 and spells out max-shifted Softmax before rounding the AV operands. The inspected cached plan materializes FP32 scores, chooses an FP32 QK GEMM and a separate normalization kernel, then uses a half-input AV GEMM. TF32 was disabled for both builds.

| 518×924 engine | Cached median (ms) | First-frame graph median (ms) |
|---|---:|---:|
| Installed v2, first comparison | 10.67 | 8.74 |
| Fused attention | 5.99 | 4.13 |
| Installed v2, second comparison | 10.60 | 8.65 |
| Explicit FP32 scores | 9.64 | 7.55 |

CUDA events bracketed TensorRT execution on its own stream. Each cell covers 108 samples across two sessions after warmup. A separate 24-frame profiler pass on the cached graph put the sum across the twelve spatial attention blocks at 5.20 ms for v2 and 0.82 ms for the fused trial. Capture, preprocessing, stereo rendering and display submission are outside these timings.

## Native SBS

The portable app captured the owned FloorballGame window at approximately 62.5 source advances/s, with GPU capture, VDA Small, strength 0.5, VFG off and a 60 FPS cap. 4K uses a scaled source. Counts are distinct native SBS submissions. GPU is device-wide NVML utilization including source playback. Each per-eye size and variant has six four-second windows across two runs, reversing order within each resolution after a five-second warmup.

| Per-eye size | v2 median FPS | Fused median FPS | v2 mean GPU | Fused mean GPU |
|---|---:|---:|---:|---:|
| 1920×1080 | 56.39 | 59.69 | 71.3% | 47.6% |
| 3840×2160 | 46.32 | 58.06 | 77.1% | 67.6% |

Fused 4K windows ranged from 57.65 to 58.33 FPS. At this source rate the VDA worker reset history on skipped capture indices. Four-second 4K windows recorded 63–65 gap resets on v2 and 16–18 on the fused trial. The image comparisons below use matched input sequences to isolate precision differences.

The explicit FP32 score trial repeated the same native protocol with fresh v2 controls. At 1080p the median rose from 56.49 to 58.23 FPS and mean GPU fell from 71.4% to 70.2%. At 4K the median rose from 46.17 to 48.74 FPS and mean GPU fell from 76.2% to 74.9%.

## Depth, stereo and installation checks

Independent engine and renderer histories processed the same FloorballGame, ParkingGarage and OfficeWalk frames, resetting between clips. Each trial produced 260 frame pairs across 1056×608, 1920×1080 and scaled 3840×2160, including sequences extending past cache eviction. All depth values were finite. The table compares each trial to the installed v2 engine.

| Metric | Fused | Explicit FP32 scores |
|---|---:|---:|
| Worst frame mean raw depth difference, fraction of P2–P98 expressed as % | 0.02451% | 0.02973% |
| Worst frame mean error in aligned depth changes, normalized units | 0.000155 | 0.000284 |
| Mean RGB absolute difference across SBS frames, 0–255 | 0.01915 | 0.01920 |
| Worst frame mean RGB difference, 0–255 | 0.05315 | 0.05829 |
| Largest fraction of pixels with any RGB difference above 8 | 0.1723% | 0.1787% |

The original PyTorch FP32 model also processed 148 public-video frames across both canvases, each engine carrying its own history. The frame-mean raw depth errors as percentages of the FP32 frame's P2–P98 range averaged 0.01086% for v2, 0.01056% for fused attention and 0.00971% for explicit FP32 scores. The worst frames reached 0.02560%, 0.03954% and 0.02877% respectively.

On the seeded install fixture, the existing absolute and relative tolerances are both 0.001. Of the 1,026 depth samples, v2 missed zero against PyTorch FP32, fused attention missed 214 (maximum absolute difference to the stored depth reference 0.00946), and explicit FP32 scores missed 309 (maximum 0.01082). Comparing caches against the shipped v2 references, 3,514 and 3,654 of 8,204 samples respectively exceeded tolerance. The current release check rejects both recipes. Physical stereo comfort, long sessions and other GPUs were outside these runs.

## One-block restoration

On the RTX 5090, twelve separate 518×896 warmup TensorRT engines each restored one encoder block's spatial attention to v2 precision. Inspector metadata confirmed the other eleven blocks used fused attention in each plan. All engines received the same installation input and twelve independent public-video frames (indices 0, 24, 48 and 72 in each of FloorballGame, OfficeWalk and ParkingGarage). The depth fixture uses the shipped reference and 0.001 absolute/relative tolerances. Video errors compare the final depth against the original FP32 PyTorch model, averaging the frame MAE as a percentage of each reference frame's P2–P98 range. A fresh all-fused build reproduced the original fixture count and the video mean to six decimal places.

| Block restored (zero-based) | Fixture samples outside tolerance / 256 | Video depth error (%) |
|---|---:|---:|
| All (shipped v2) | 0 | 0.013884 |
| None (all fused) | 153 | 0.013028 |
| 0 | 193 | 0.014652 |
| 1 | 150 | 0.014634 |
| 2 | 167 | 0.013683 |
| 3 | 163 | 0.013629 |
| 4 | 122 | 0.013764 |
| 5 | 169 | 0.012482 |
| 6 | 133 | 0.012021 |
| 7 | 146 | 0.014047 |
| 8 | 147 | 0.012985 |
| 9 | 172 | 0.013445 |
| 10 | 138 | 0.013840 |
| 11 | 154 | 0.013103 |

Restoring block 4 recovered the most fixture samples. Block 6 yielded the lowest average video error, improving OfficeWalk and ParkingGarage while increasing FloorballGame's mean from 0.00653% to 0.00761%. These are marginal effects with the other eleven blocks fused. Multiple-block interactions, cached video frames, the 518×924 canvas and end-to-end SBS quality were outside this screen. The local probe and per-input measurements are in `out/vda-block-sensitivity-896/`.

## Streaming with blocks restored

The follow-up built four engines per recipe, keeping either block 6 or blocks 4 and 6 at v2 spatial-attention precision. Both canvases were evaluated with independent first-frame and cached graphs. Scripts and per-frame data are in `out/vda-restore-6-20261108/` and `out/vda-restore-46-20261108/`.

The original PyTorch FP32 model and each TensorRT engine carried their own history through 148 public-video frames across both canvases. A separate 260-frame run compared the aligned depth and the complete native SBS textures against v2 at 1056×608, 1920×1080 and scaled 4K. These matched-input measurements isolate numerical changes. Physical viewing comfort was outside this experiment.

| Recipe | 896 first / cached depth misses (256 each) | 924 first / cached depth misses (257 each) | Depth misses / 1,026 | Cache misses / 8,204 |
|---|---:|---:|---:|---:|
| All fused | 153 / 61 | 0 / 0 | 214 | 3,514 |
| Restore 6 | 142 / 4 | 0 / 0 | 146 | 3,660 |
| Restore 4 and 6 | 185 / 229 | 0 / 4 | 418 | 3,701 |

The rebuilt block-6 recipe had 142 misses on the 896 first frame, compared with 133 in the earlier one-block screen. Comparisons here use the plans actually exercised on the fixture, video and native paths. Both recipes exceed the existing installation tolerances.

| Video metric | All fused | Restore 6 | Restore 4 and 6 |
|---|---:|---:|---:|
| Mean raw depth error vs FP32, 518×896 (% of frame P2–P98) | 0.01193% | 0.01145% | 0.01265% |
| Mean raw depth error vs FP32, 518×924 (% of frame P2–P98) | 0.00920% | 0.01052% | 0.00833% |
| Worst frame mean raw depth error vs FP32 across canvases | 0.03954% | 0.03067% | 0.03088% |
| Worst frame mean error in raw depth changes vs FP32 | 0.02090% | 0.02320% | 0.02373% |
| Mean error in aligned depth changes vs v2 (0–1) | 0.0000364 | 0.0000375 | 0.0000358 |
| Worst frame mean error in aligned depth changes vs v2 (0–1) | 0.000155 | 0.000201 | 0.000219 |
| Mean native SBS RGB difference vs v2 (0–255) | 0.01915 | 0.01914 | 0.01886 |
| Worst frame mean native SBS RGB difference vs v2 (0–255) | 0.05315 | 0.05328 | 0.04442 |

Both restorations reduced the worst static depth error against FP32 but increased the worst error in frame-to-frame depth changes. Restoring 4 and 6 improved the average SBS match to v2 and widened the fixture failures. TensorRT inspector metadata confirmed the expected 11 or 10 fused spatial blocks in every plan. The inspection records, live counters and summary are in `out/vda-restore-native-20261108/`.

The 4K portable native run used the same public FloorballGame input, GPU capture, strength 0.5, VFG off and a 60 FPS limit. Source playback averaged 62.5 FPS. Each recipe ran twice, in reverse order on the second pass, with five seconds of warmup followed by three four-second measurement windows per session.

| Recipe | Median native submissions/s (range) | Mean device GPU utilization | History gap resets in 24 measured seconds |
|---|---:|---:|---:|
| Installed v2 | 46.20 (45.66–46.91) | 76.0% | 387 |
| All fused | 58.07 (57.84–58.44) | 68.0% | 102 |
| Restore 6 | 56.95 (56.72–57.16) | 69.2% | 130 |
| Restore 4 and 6 | 55.96 (55.73–56.24) | 72.0% | 155 |

## Portable v3 promotion

The user selected the all-fused recipe following a local viewing comparison. The v3 ONNX pack pins the four previously measured graphs and the completed trial's depth and cache samples. This changes the numerical reference for this recipe. The same absolute and relative tolerances of 0.001 still apply to all 9,230 installation samples. The earlier FP32 and v2 comparisons above quantify the precision change separately.

The release pack builder reproduced the 363,291,834-byte ZIP with SHA-256 `b4e68c45328e37b601c95f1d06a024c41c510c6c980ba2fcdec5b1030603778f`. The portable installer compiled and checked all four plans from that ZIP in the RTX 5090 user's v3 cache. Both older v2 profiles also passed the signed local loader check. The packaged GUI produced 12-frame 2112×608 files in Video Quality and Offline Quality from a 1056×608 fixture. With the installed plans, public FloorballGame native SBS delivered 59.87 FPS at 1056×608 and 58.09 FPS at scaled 4K. Mean device-wide GPU utilization was 42.9% and 67.8% respectively over one eight-second window per size. Release measurements are in `out/vda-spatial-release-20261108/`.

## Reproduction

Run `v1/build_vda_spatial_trial.py` in the ONNX/TensorRT build environment with the v2 ZIP, a fresh output directory and `--runtime C:/TensorRT/TensorRT-11.2.1.2/bin`. Add `--wide-scores` for the second recipe. The builder checks the pack digest and TensorRT version. Local run scripts, per-window counters, layer reports, fixture comparisons and independent FP32 results are in `out/vda-spatial-b8fc5e47/` and `out/vda-spatial-wide-b8fc5e47/`.

For a block sensitivity experiment, pass `--keep-fp32 N` for each zero-based block whose spatial attention should use v2 precision. The encoder has twelve blocks numbered 0–11.
