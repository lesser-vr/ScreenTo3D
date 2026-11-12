# VDA FP16 candidate fixture

`vda-fp16-candidate-896.npz` contains sampled synthetic validation outputs, not
video frames, weights or executable plans. It was generated with the pinned
`vda-small-onnx-v3.zip` graphs, input seed 9071, profile 518x896, TensorRT 11.2.1.2
and RTX 5090 on 2026-11-12. The corresponding baseline is the existing
`models/engine-reference/vda-small-spatial-896.npz`.

The candidate fails the former per-element cache tolerance while its final-depth
samples pass the unchanged test. The maximum sampled cache relative RMSE is
0.6325%, and maximum error normalized by tensor RMS is 2.116%. A separate 48-frame
public-video comparison with independent 42-entry histories measured maximum
relative depth RMSE 0.03653% and depth-span-normalized MAE 0.01682%. Full evidence:
`out/vda-failed-candidates/896/metrics.json` and `out/vda-candidate-sequence.json`.
The largest raw depth difference was 0.16321; up to 1.0125% of pixels in one frame
exceeded the old pointwise depth threshold. These are numerical observations,
not pixel identity or visual/SBS quality acceptance.

The regression tests accept this observed rounding variant under the named cache
contract and reject bias, sparse spikes, zeroed cache and changed final depth.
The model source/weights retain their recorded VDA Apache-2.0 provenance.
