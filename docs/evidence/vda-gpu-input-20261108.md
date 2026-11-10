# VDA Small window GPU input

Windows, RTX 5090, driver 621.14, TensorRT 11.2.1.2. The portable application used the existing user-built FP32 plans, Video Quality, strength 0.5 and native Full SBS with VFG off. The default window path consumed WGC/D3D11 capture on CUDA; the matched control explicitly selected mapped capture and the original CPU preprocessing. Both ran the same renderer and gap/reset policy.

| Captured pixels per eye | Input path | Output limit | Native output FPS | Mean whole-device GPU utilization |
|---|---|---:|---:|---:|
| 1920×1080 | Mapped / CPU | Unlimited | 27.24 | 39.8% |
| 1920×1080 | GPU | Unlimited | 55.52 | 84.6% |
| 1920×1080 | GPU | 60 | 51.65 | 73.8% |
| 3840×2160 | Mapped / CPU | Unlimited | 11.56 | 52.1% |
| 3840×2160 | GPU | Unlimited | 40.04 | 87.6% |
| 3840×2160 | GPU | 60 | 38.23 | 80.6% |

The owned public FloorballGame 1080p60 preview was scaled to each window and advanced about 62 FPS. Rates count distinct native output-window submissions over two adjacent eight-second windows after five seconds of warmup. Utilization includes the desktop and player and was sampled once a second. Unlimited A/B order was CPU–GPU at 1080p and GPU–CPU at 4K. The 4K GPU run still recorded 357 gap resets alongside 641 inferences. This is a short throughput test, not sustained 4K60 or physical display acceptance.

The GPU kernel uses float32 cubic resize, double normalization, and the same aspect-fit rectangle and replicated edges as the CPU VDA path. An isolated test of random and constant images at nine geometries observed maximum absolute input error below 0.000007. Running `v1/test_vda_gpu_input.py` on 73 matched sports frames at six sizes, including portrait and ultrawide, produced maximum absolute input error below 0.000005 and source-sized depth error below 0.0001. This included warmup, cached inference beyond the history eviction limit and a cut/reset. The full-resolution RGB upload and depth inference input upload were absent on the GPU frame path. The renderer can still read back small scene observations or request data for background handling.

Native output continued after each of three live aspect changes (wide, portrait, 4:3, then 16:9). Both profile widths were exercised. The new pinned DLL carries compute_75 PTX and SM120 machine code; physical GPU coverage is limited to this RTX 5090.
