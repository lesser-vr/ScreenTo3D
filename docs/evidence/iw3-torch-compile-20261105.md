# iw3 torch.compile follow-up — 2026-11-05

## Finding

The user's compile suggestion materially changes the iw3 performance comparison.
The earlier [renderer comparison](native-restart-base-profile-iw3-20261105.md)
measured eager PyTorch only. With model compilation specialized per source size,
the three learned renderers are 1.39–1.52x faster at 1080p and 1.82–1.96x faster
at 4K in this matched renderer-only test. This does not double whole-app FPS,
establish a speed advantage over the current native CUDA renderer, or qualify
the learned renderer's visual tradeoffs for default use.

Current Base inference runs a validated TensorRT engine, not a PyTorch model
forward. Its previous CUDA graph experiment reduces submission overhead and is
distinct from compiling PyTorch operators with Inductor. To compare torch.compile
for Base itself would require a separate PyTorch Base execution candidate. The
current native CUDA projection likewise has no PyTorch model forward to compile.

## Setup and actual compilation

- Windows, RTX 5090, existing PyTorch `2.7.1+cu128`, unchanged model weights and
  pinned iw3 source from the previous comparison.
- The existing environment initially raised `TritonMissing` on an explicit small
  compiled GPU function. iw3's `check_compile_support` catches such exceptions
  and can return the original model, so an enabled checkbox alone is not proof of
  compiled execution. Our benchmark calls torch.compile directly, does not
  suppress compiler errors, and records generated kernels and graph counters.
- Installed only `triton-windows==3.3.1.post21` into
  `out/iw3-compile-deps-20261105` using `pip --target --no-deps`. No existing Torch
  package, app launcher or global Python installation was changed. This folder
  is added to PYTHONPATH only for the explicit experiment.
- Wheel SHA-256:
  `6304328e899692993dabd1cfb2ea10b6c0ae5e1c9be3786c670718a94eadb6ed`.
  URL and package metadata are in `out/iw3-compile-install-20261105.json`.
  The package declares MIT. This is a local compiler dependency, not a bundled
  distribution addition; existing source/model license obligations remain.
- MSVC 2022's developer environment supplies the C compiler. The initial target
  installation without that environment failed compiler discovery, with no
  successful measurements claimed. Caches are local under
  `out/iw3-compile-cache-20261105/{inductor,triton}`.

The [Windows Triton documentation][triton] pairs Torch 2.7 with Triton 3.3 and
requires Torch >=2.7, Triton >=3.3 and CUDA >=12.8 for Blackwell. The implementation
uses the pinned iw3 [model-only compile boundary][iw3], with `mode='default'` and
`fullgraph=False`; the stronger experiment adds only `dynamic=False` to specialize
each fixed resolution. There are no changes to model resolution, depth, RGB,
divergence, eye ordering, AMP FP16, or TF32-disabled settings.

## Matched results

`v1/benchmark_iw3_compile.py` reuses saved public RGB and final Base depth from
the earlier experiment. Three natural 1080p stills, one synthetic scene resized
to 1080p, and OfficeWalk upscaled to 4K: five cases for each of three models.
The 4K sample is not native-4K quality evidence.

After first compilation and five warmups, each method receives 30 eager and 30
compiled samples in alternating order. CUDA events enclose the complete paired
renderer, including both backward warps but excluding CPU transfers, readback,
capture, depth inference and Qt. Host elapsed times are also recorded. Only the
model forward is compiled; the outer warp wrapper is unchanged.

Resolution-specialized (`dynamic=False`) median GPU milliseconds:

| Renderer | 1080p eager → compiled | Speedup | 4K eager → compiled | Speedup |
|---|---:|---:|---:|---:|
| RowFlow v3 symmetric | 3.140 → 2.078 | 1.51x | 27.472 → 13.990 | 1.96x |
| RowFlow v3 | 6.511 → 4.691 | 1.39x | 54.613 → 27.898 | 1.96x |
| MLBW small | 7.378 → 4.846 | 1.52x | 49.542 → 27.254 | 1.82x |

An important counterexample: the default `dynamic=None` run processes 1080p then
4K in the same process. Its automatically generalized 4K graph is slower:

| Renderer | 4K eager → compiled, automatic dynamic shapes |
|---|---:|
| RowFlow v3 symmetric | 27.494 → 33.184ms |
| RowFlow v3 | 54.613 → 66.637ms |
| MLBW small | 49.378 → 59.218ms |

The [PyTorch 2.7 documentation][compile] explains that default dynamic shape
handling may generalize after a size change, whereas `dynamic=False` specializes
each shape. The result therefore supports a fixed-resolution-per-session
candidate, not a blanket claim that the compile checkbox always improves 4K.
Starting directly at 4K with the default setting was not independently tested.
`max-autotune`, reduced stereo-field resolution and TensorRT conversion were not
part of this experiment.

Compilation also has startup cost. The initial uncached symmetric 1080p call
took 15.87s and its automatic dynamic 4K call 35.58s. In the later static run the
1080p graph reused disk cache (~0.93s); newly specialized symmetric 4K took 16.79s
and MLBW 4K took 11.57s. Regular RowFlow reuses the same graph structure/cache with
its own weight arguments. These are mixed cold/warm observations, not guarantees
about every installation's first launch.

## Correctness scope and artifacts

Static run: all 15 cases completed, with float-output finite checks before uint8
conversion. The compiler records graphs/kernels and no Dynamo graph breaks.
Output is not bit-identical: the largest mean absolute RGB difference among
tested cases is 0.05299 on a 0–255 scale, with a maximum channel difference of 6.
The default dynamic run's MLBW 4K case had a larger local maximum of 29. No claim
of exact parity or perceptual equivalence is made; no acceptance threshold was
retroactively chosen. This is a numerical comparison on still inputs, not a
continuous binocular/HMD or source-resize product acceptance test.

- `out/iw3-compile-msvc-benchmark-20261105/report.json`: default dynamic policy,
  timing samples, numerical differences, compiler counters.
- `out/iw3-compile-static-benchmark-20261105/report.json`: resolution-specialized
  results, timing samples, finite checks and compiler counters.
- Adjacent logs retain compilation diagnostics. SymPy/dynamic reduction warnings
  are not treated as failed or successful compilation without the runtime evidence.
- Both successful run directories contain eager/compiled OfficeWalk SBS PNGs.
- `v1/benchmark_iw3_compile.py` passes scoped Ruff error/name checks. No product
  runtime code was changed for this follow-up.

Reproduce by entering the existing MSVC 2022 developer PowerShell environment,
setting PYTHONPATH to `v1;out/iw3-compile-deps-20261105;out/gui-python-deps;out/capture-python-deps;out/v1-python-deps`,
then running `out/vda-oracle-env/Scripts/python.exe v1/benchmark_iw3_compile.py
--static --output <new-output-directory>`. Omit `--static` for the default dynamic
policy comparison. Existing output directories are never overwritten.

[compile]: https://docs.pytorch.org/docs/2.7/generated/torch.compile.html
[triton]: https://github.com/triton-lang/triton-windows/blob/readme/README.md
[iw3]: https://github.com/nagadomi/nunif/blob/0d3d92c8f4396da564c44524b6390ee5c76b9668/iw3/utils.py#L1156
