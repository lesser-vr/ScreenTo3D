# ZipDepth GPU load audit — 2026-11-06

## Question and matched workload

Investigate the user's high GPU usage report without changing the selected
unlimited default or reducing stereo quality. The owned UVG Jockey 4K120 player,
exact-forward ZipDepth mixed-FP16 plan, strength 0.25, detail stereo, VFG off and
7680x2160 native texture output match the [HFR contract](zipdepth-hfr-20261106.md).
This audit follows the [completed-result reuse fix](zipdepth-result-reuse-20261106.md).
The player's source SHA, model/renderer pins, settings and frame-ID timing are
retained in the raw per-run reports. Other applications were not terminated.

Whole-GPU nvidia-smi samples every 200ms were aligned with three ten-second
measurement intervals per condition. These are exploratory local comparisons,
not general throughput or sustained-support qualification. GPU usage/power
include player, desktop and other apps. Absolute FPS differs from earlier runs;
the current within-audit comparison is not evidence of a code speedup.

## Output cap comparison

| Condition | Output FPS, median | GPU usage, mean | GPU power, mean | Callback-to-output age P50, median |
|---|---:|---:|---:|---:|
| Player only, ten seconds | no SBS | 3.02% | 68.72W | not applicable |
| ZipDepth unlimited | 88.49 | 80.25% | 309.79W | 19.00ms |
| ZipDepth 60 FPS cap | 55.89 | 46.38% | 220.01W | 43.06ms |
| ZipDepth 30 FPS cap | 29.10 | 31.09% | 151.71W | 76.47ms |

Input arrivals remained about 119.7–119.8 FPS during SBS. All three sessions
completed without errors and cleaned up to zero native pools/nodes. After all
tests and the profile, a GPU snapshot was 0% / 38.19W / 4033 MiB, and no owned
benchmark/player/profiler processes remained. This is not a long-session leak test.

The cap materially reduces work and power through native-slot backpressure.
However, `PresentationCadence` is applied at native publication, while the worker
has already captured/prepared/inferred before waiting for a writable output slot.
The two-slot pipeline can therefore hold older work behind the presentation gate.
The increased age is measured; early work scheduling/latest-input selection is
the proposed remedy, not an implemented or validated fix. Conservative scheduling
also does not deliver exactly 60 FPS in this test. Preserve resource retirement
and ownership if changing the timing; do not bypass pending texture leases.

Raw telemetry: `out/public-hfr/audit-{unlimited,60,30}.json` and matching
`Jockey-zipdepth-audit-*.json`. Stop snapshot: `gpu-audit-after-stop.csv`.

## GPU kernel profile

Nsight Systems 2025.5.2 traced CUDA/NVTX for eight seconds after a twelve-second
launch delay in a separate real WGC/native-output run. CPU sampling/context-switch
tracing were disabled; profiling did not kill the target. The app finished and
cleaned up normally. Profiled FPS is excluded from the cap comparison.

The trace contains 711 instances of each four-pass guided-filter kernel and
1422 stereo-resolve invocations (two eyes). Percentages below use **summed CUDA
kernel execution time, 5.2436 seconds**, not total wall time, GPU peak capacity,
or nvidia-smi utilization. They exclude D3D11/Qt presentation and CUDA copy time.
Per-render values divide by the 711 guided-filter instances; boundary counts
for other operations can differ by a frame.

| Identified work | Share of CUDA kernel time | Kernel time per rendered frame |
|---|---:|---:|
| Full-4K guided depth filter: moments_x, coefficients, coefficients_x, guided | 47.63% | 3.513ms |
| Two-eye overlap/hole resolve: resolve_parallel | 17.09% | 1.260ms |
| Motion-history blend kernel | 5.34% | 0.394ms |
| Subpixel reconstruction | 3.95% | 0.291ms |
| Selective contour/background fill | 1.45% | 0.107ms |

The four guided-filter kernels and stereo resolve alone account for 64.72% of
recorded kernel time. Their source is shared stereo/postprocessing, independent
of ZipDepth's model graph. The radius-4 guided path uses four full-resolution
passes, repeated neighborhood sums and double-precision accumulation. This is
the clearest first optimization target; changing summation or precision requires
parity/quality checks, not a blind switch to lower precision. The current plan
input is 704x384 while these passes operate on 3840x2160.

The newer optional contour/fill kernels are only 1.45% in this trace. Removing
those quality features is not the main opportunity indicated by these results.
Kernel fractions do not predict an equal end-to-end FPS or power improvement.

CUDA memory-operation GPU time totaled about 0.192 seconds. CUDA API wall time
contains substantial memcpy/synchronization waiting; it must not be mistaken for
equivalent transfer-engine cost or a basis to blame upload bandwidth.

The existing ZipDepth `gpu_stage_ms` fields are zero because the inherited
source-depth path does not populate that model's stage array. Those zeros mean
missing measurements, not zero cost. This audit uses the independent profiler;
correct source-path stage telemetry remains follow-up work.

Raw evidence:

- `out/public-hfr/zipdepth-audit-profile.nsys-rep` and `.sqlite`
- `zipdepth-audit-stats_cuda_gpu_kern_sum.csv`, `_cuda_gpu_mem_time_sum.csv`, `_cuda_api_sum.csv`
- `gpu-audit-kernel-groups.json`
- `Jockey-zipdepth-audit-profile.json` (successful lifecycle, not performance baseline)

## Outcome

The measured high load is dominated by running the full pipeline without a cap
and expensive full-resolution postprocessing. The investigation identifies
guided filtering and stereo resolve as concrete optimization targets, plus
earlier pacing to reduce cap-induced latency. No production processing, quality
policy, model choice, output default or hardware setting was changed. Only
diagnostic harness controls and evidence were added; changed scripts compile.
