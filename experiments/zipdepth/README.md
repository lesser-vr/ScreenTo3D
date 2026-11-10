# ZipDepth experiment archive

Retired on 2026-11-07; see [current status](../../docs/implementation-status.md#zipdepth-retired).
The desktop launchers have been removed. This directory retains historical
experiment code and shared Small/guide/pacing measurement tools, not an app model
integration. The experiment descriptions below document the original conditions.

The trial temporarily registers the real `zipdepth-base` identity only in its own
GUI and worker processes. It shares Performance policy at strength 0.25 with the
DA2 Small comparison. The adapter preserves source aspect using a 704x384 padded
model input and source-sized device depth. GPU preprocessing uses bilinear
resampling with uint8 rounding; it is measured, not bit-identical to OpenCV.

Prepared files are under `out/zipdepth-exact-20261106`. `runtime.py` pins the local
plan hash, I/O signature, GPU and TensorRT version. This is not a portable release.

Reproduction uses the prepared `out/vda-oracle-env/Scripts/python.exe`, with
`PYTHONPATH=v1;experiments/zipdepth;out/gui-python-deps;out/capture-python-deps;out/v1-python-deps`:

- `prepare.py`: strict official weights loading, fusion, original-forward ONNX,
  explicitly typed mixed FP16 TensorRT, six public-image parity checks.
- `validate.py`: reference preprocessing/depth at four aspect ratios and owned
  result lifecycle checks.
- `benchmark.py`: existing real WGC/native Qt benchmark arguments, ZipDepth only.
  Small uses `v1/benchmark_live_modes.py` with the identical arguments.
- `quality.py`: identical 4K source frames, native output readback and temporal
  proxies for both models. Diagnostic readbacks are excluded from FPS measurements.
- `latency.py --model small|zipdepth`: three 10-second native-ID/age samples with
  an 8ms source timer. This is a source-paint contention test, not a maximum FPS claim.
- `verify_hfr_media.py`: records provenance, geometry, timing and 600 distinct
  decoded thumbnails for each prepared official UVG Jockey/Beauty 4K120 clip.
- `hfr_source.py Jockey|Beauty`: isolated source preflight with a pinned portable
  mpv D3D11 player, real WGC capture and thumbnail-change counts.
- `latency.py --model small|zipdepth --clip Jockey|Beauty --tag <new-name>`:
  genuine 4K120 window input, three 10-second native SBS/age samples, capture
  arrival rate and resource cleanup checks. Prepared media/player are required;
  see [HFR evidence](../../docs/evidence/zipdepth-hfr-20261106.md).
- `gpu_telemetry.py --tag <fresh-tag>`: Jockey Small/ZipDepth sequential runs
  with 200ms whole-GPU usage/power/VRAM samples aligned to each measured interval.
  Desktop and public-player costs are included; this is not per-process telemetry.
  `--model zipdepth --cap 0|30|60 --player-baseline` supports a matched load audit;
  `--quality budget|reference` is a diagnostic quality change, not a default.
- `check_reuse.py --tag <fresh-tag>`: native identical-RGB reuse, changed RGB,
  superseded token and closed-engine rejection checks.
- `launch.py --smoke-static`: actual WGC/static-frame reuse plus the launcher's
  size, hide/restore and stop/restart checks.

Run GPU experiments sequentially. Scripts refuse overwriting their evidence where
appropriate; use a new output name for a new comparison. Upstream checkout must
be clean at `91f3fd21e131641f51e8d35736d1958350180e3a` in `out/zipdepth-upstream`.
Do not install upstream's complete training requirements into the app environment.
Inference/export ran here with Torch 2.7.1+cu128 without changing installed packages.

The upstream exporter was rejected because it changes learned weighted global
context pooling to uniform averaging. The accepted export retains the original
forward graph. No upstream files were edited. The failed candidate is retained
under `out/zipdepth-20261106` and is never loaded by the adapter.

See [measured evidence](../../docs/evidence/zipdepth-20261106.md) for results and
limitations, and [license review](../../docs/references/2026-11-06-zipdepth-review.md)
for source/weight provenance questions. No new license clearance is asserted.
