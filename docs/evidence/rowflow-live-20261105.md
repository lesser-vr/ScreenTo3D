# RowFlow v3 symmetric app trial — 2026-11-05

## Decision and implementation

Implemented an explicit local quality experiment, retaining CUDA as the normal
renderer. This is the compiled symmetric model only, not regular RowFlow, MLBW,
or a replacement of Base TensorRT. The previous [compile review](iw3-torch-compile-20261105.md)
remains renderer-only historical evidence; the measurements below include the app.

Launch the prepared checkout with `powershell -File scripts/run-desktop.ps1 -RowFlow`.
Use Balanced/Base, GPU processing and strength 0.25–1.92. The normal host output
is supported; native texture delivery remains an explicit Settings choice.
Ordinary launch is unchanged. No extra main-window controls or captured previews
were added. This source-local dependency set is not bundled or a clean-machine
installation claim.

`DEPTHSBS_STEREO_RENDERER=rowflow-sym` is snapshotted at Start. Invalid combinations
fail visibly instead of selecting another renderer. The adapter retains existing
Base TensorRT, GPU capture/preprocessing, normalized/guided temporal depth and
conditional background refinement. Final RGB/depth are copied on the engine stream
into owned PyTorch allocations. `torch.compile(dynamic=False, fullgraph=True)`
specializes each source size; FP16 autocast is used inside the upstream warp.
Divergence is 100 times the existing policy value, convergence is unchanged,
steps=1, and calibrated upstream eyes are swapped into DepthSBS order. The CUDA
conservative-coverage switch is not an input to this learned warp: this is an
intentional quality change, not a parity optimization against CUDA pixels.

Finite depth and floating output checks precede uint8 conversion. Native output
packs compiled RGB into the existing two-slot keyed-mutex pool; host output reads
the full SBS back. A pool is offered only after successful preparation. Resize
retires old textures and the renderer before replacing the engine. No silent
eager fallback is enabled; excessive shape recompilation can fail visibly at
PyTorch's configured limit. This does not promise unlimited interactive resizing.
Disk compiler caches under `out/rowflow-compile-cache` persist between sessions;
there is no automatic disk-cache quota/eviction in this local trial.

Preparation reports a real waiting state, without invented percentage progress.
Cancellation retains the live lease until worker exit; the existing 5s watchdog
can terminate synchronous compiler work. A worker-owned Windows job closes its
compiler descendants too. The GUI is not assigned to that job. The mechanism
follows [Microsoft's job ownership contract](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
and was separately exercised with real process handles. Advisory preparation
status has no shared lock that termination could strand.

## Artifact contract

- nunif source revision: `0d3d92c8f4396da564c44524b6390ee5c76b9668`, clean checkout
  at `out/iw3-render-source-20261105`; only the required RowFlow module is loaded.
- Checkpoint: `iw3_row_flow_v3_sym_20250628.pth`, SHA-256
  `b61518f9c83e1f0c19d8a8844dbe5304e5f47bfb65928d5bb74256c1640186a0`.
  `weights_only=True`, expected name/empty constructor kwargs, strict state load.
- New separate bridge: `out/rowflow-bridge/rowflow_bridge.dll`, SHA-256
  `a98ef1bc35e85c1582710c1bcbaf2ccf6663125f551f532f2d87d030ab7e4ec5`.
  Build: `scripts/build-live-texture-projection.ps1 -OutputName rowflow-bridge`.
- Borrowed LiveDepth layout remains pinned to live DLL SHA-256
  `e88697254fa9d81ade5d19b84b2f9107d5d1211fbeb9243cb4ec0af77b7ae6df`.
  The ordinary native texture DLL and Qt DLL were not rebuilt for this trial.
- PyTorch `2.7.1+cu128`, isolated `triton-windows==3.3.1.post21`, MSVC 2022;
  RTX 5090 / driver 621.14. The launcher adds only the prepared isolated compiler
  directory; dependencies/pins remain those in the prior compile evidence.
- Source MIT notice is retained in its checkout. A separately stated checkpoint
  redistribution grant was not established; no weights/compiler are added to the
  portable bundle. Base's recorded noncommercial restriction remains applicable.

## Checks executed

- `out/rowflow-live-parity-verified-20261105/report.json`: 12 real-engine cases,
  three each at 1920x1080, 3840x2160, 1080x1920 and 3440x1440. Ordinary image,
  inversion/cut and flat-background refinement all pass. Native RGB equals the
  same compiled host pixels exactly, alpha is 255 and depth tokens complete.
  Injected NaN depth is rejected. Compiled/eager pixels are not equal: maximum
  per-case MAE 0.02660/255 and maximum channel delta 8; no perceptual-equivalence
  threshold is inferred from this numerical result.
- `out/rowflow-native-lifecycle-20261105/report.json`: actual desktop start,
  distinct eye output, no main preview/shared color buffer, hide/restore,
  fullscreen/Escape, resize, stop/clear, restart, source minimization and worker
  crash all pass. Final cleanup assertions require zero native pools/nodes.
- `out/rowflow-cancel-host-20261105/report.json`: actual preparation message,
  cancellation, released lease/no stale output/no error dialog, then successful
  restart on the normal host-output path. Cancel reports preparation cancelled.
- `out/rowflow-job-20261105.json`: terminate an owned helper, then observe its
  child process handle signal within the deadline. The test uses the real Python
  interpreter as multiprocessing does, rather than a venv redirector process.
- 49 scoped unit tests pass: renderer selection/snapshot, bridge/layout rejection,
  source-depth ownership, live modes/backend routing and native mailbox protocol.
  The source-depth consumer again validates its profile before inference; its
  test double now explicitly models the optional input-transfer counter.
- Scoped Ruff E9/F checks and whitespace/diff validation pass.

The first parity attempt exposed a test-only inference-mode mutation error.
The next showed that a NaN warp can produce finite pixels; input finite checking
was moved inside the render boundary, and the complete 12-case run then passed.
The initial job test killed the venv redirector, not the actual worker; using the
same real-interpreter creation as multiprocessing verifies the intended job.
Those failed attempts are not counted as passing evidence.

## Application throughput

Public FloorballGame in a separately owned source process, Base Balanced strength
1.0, target 60Hz, graph optimization off, 6s discarded warmup and five 6s windows
per size. No concurrent GPU benchmark was run. Native counts distinct Qt submitted
IDs; host reports callback submission proxies. Neither is physical display FPS.
4K is an upscaled 1080p public excerpt processed as 7680x2160 Full SBS, displayed
in a fitted window, not 1:1 scanout. Compilation is excluded from warmed rates.

| Output / per eye | CUDA median fps | RowFlow symmetric median fps |
|---|---:|---:|
| Default host / 1920x1080 | 26.96 | 26.83 |
| Default host / 3840x2160 | 12.55 | 12.41 |
| Native / 1920x1080 | 32.15 | 29.36 |
| Native / 3840x2160 | 23.86 | 16.25 |

Native baseline is reused from the same-day, same-condition
`out/base-graph-live-off-20261105/runs.json`; measured new candidate is
`out/rowflow-native-benchmark-20261105/runs.json`. Native CUDA ranges are
31.98–32.66 and 23.67–24.03 fps; RowFlow ranges are 29.16–29.66 and
15.90–16.40 fps. The full integration is slower despite the earlier compile gain
over eager RowFlow. The earlier renderer-only result must not be called app gain.

Matched new host runs are `out/rowflow-cuda-host-control-20261105/runs.json` and
`out/rowflow-host-benchmark-20261105/runs.json`. CUDA ranges are 26.80–26.99 and
12.39–12.58 fps; RowFlow ranges are 26.67–26.98 and 12.25–12.58 fps. These ranges
overlap; no practical host-output speed gain is established. Initial native
measurements preceded the addition of two scalar-finite-readback bytes/syncs to
diagnostic counters; timings already included those checks. Subsequent host
measurements include the corrected counters. This instrumentation does not
change the renderer or its output.

## Visual scope and remaining limits

The actual output-window screenshot was inspected: both eyes are present, source
ratio is fitted, and no unexpected blank/color-swapped surface is visible.
The same-depth 180-frame comparison and analytic scene from the earlier renderer
record remain the quality reference: smoother diagonals in some areas coexist
with thin-structure/edge changes. This turn does not establish a subjective
quality winner, continuous binocular comfort, Owl3D/HMD acceptance, long soak,
actual GPU device-loss recovery, commercial clearance or portable installation.

Only RowFlow symmetric was integrated; the default remains CUDA.
