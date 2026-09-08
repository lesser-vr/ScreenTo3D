# DA2 Base build and evaluation

Historical evidence by recorded checkpoint. Current support is in
[implementation status](../implementation-status.md).

## Records

- [da2-base-app](#record-plan-da2-base-app)
- [da2-base-expansion](#record-plan-da2-base-expansion)
- [da2-base-integration](#record-plan-da2-base-integration)
- [da2-base-trt](#record-plan-da2-base-trt)
- [da2-base-local](#record-reference-da2-base-local)

<a id="record-plan-da2-base-app"></a>
## da2-base-app

Checkpoint date recorded in source: 2026-09-05.

> Implemented `depthsbs_app/da2_base.py`, GUI/worker/diagnostics selection and
> `scripts/run-da2-base.ps1`. The exact validated plan is allowlisted by SHA256 and
> byte size; arbitrary manifests/plans are not accepted. DA2 preprocessing uses
> float64 before cubic resize to match its upstream implementation exactly.
> Dedicated CUDA stream, finite owned output, owner/device checks and deterministic
> cleanup are implemented. Source dimensions are validated before output mutation.

> Passing app report: `out/da2-base-app/acaf4714b5864c23932b615cc1a154cf/report.json`.
> Real GPU tests cover exact preprocessing, depth parity (atol/rtol .001), repeated
> close/use-after-close and cancel/injected error preserving sentinel output.
> The actual public launcher produces `da2-base-sbs.mp4`: all 124 frames decode at
> 2112x608 with AAC. Real Tk selection/worker argument checks and public diagnostics
> pass. Missing plan and unsupported standard-16:9 input fail. Canonical gate:
> 106 Python tests, seven process-tree cases and C++ CTest pass.

> The first app reference test used PyTorch's default TF32 setting and failed a
> small subset of pixels; matching the previously specified TF32-off FP32 reference
> passes. This changed the test reference configuration, not tolerance or runtime.
> Failed evidence remains under `676da122535b4cfca0addffac2c371b7`.


<a id="record-plan-da2-base-expansion"></a>
## da2-base-expansion

Checkpoint date recorded in source: 2026-09-05.

> Recorded outcome: 16:9 delivery and comparison complete; FP16 candidates evaluated and rejected, 2026-09-05.

### Delivered evidence

> - Standard 16:9 FP32: `out/da2-base-trt/c08f132882cc47bfaca7d581a7da5ed7/`.
>   68/68 parity passes, max absolute error 0.000154495239257812.
>   Plan SHA256 `e5b17445993602abf2a01c0f6e7686d5fa67afec49bd9ef8bb4c133175c89d2e`,
>   402660828 bytes. Installed exact-hash profiles live in `out/da2-base-local/`.
> - App profile selection handles original ratio and 720p/1080p/4K 16:9 with one
>   engine per job. Invalid selection clears prior state; corrupt hashes and root
>   escape are rejected. User launcher/diagnostics use the profile root.
> - Public media matrix: `out/da2-base-matrix/208cd7b581364ef1814b5cc11dabdf13/`:
>   720p 124, 1080p 124, upscaled 4K HEVC 12 and HEVC cut 48 frames; every output
>   frame decodes at doubled width and retains audio. Cut input reports one reset.
> - 16:9 app lifecycle/GUI: `out/da2-base-app/19bd96eba6d74aeabb5c993c6ae046b3/`.
>   Preprocessing exact, resized-depth max error 0.00011301040649414062,
>   cancellation/injected error preserves prior output, GUI argument propagation.
> - Canonical gate passes 108 Python tests, seven process-tree tests and C++ CTest.
>   Existing VDA GUI tests and both DA2 Base public profile diagnostics pass.
> - FP16: two mixed-precision candidates build and run but fail all 68 numerical
>   gates each. Strict tolerances were not relaxed; no public FP16 option is added.
> - Five-repetition model/precision comparison, memory observations and synchronized
>   hand review: `out/model-evaluation/1086d3d9ede94afc8a3740f9177aeeee/`.
>   Findings and default decision: [model-comparisons.md](model-comparisons.md#record-result-model-evaluation-2026-09-05).

> All work authorized in this slice is concluded with the explicit FP16 rejection.
> Further selective precision tuning is a future experiment; supported Base remains
> FP32. No claim of native-4K detail quality, sustained targets, or blinded/VR
> acceptance follows from these short fixtures. Existing default models remain Small.


<a id="record-plan-da2-base-integration"></a>
## da2-base-integration

Checkpoint date recorded in source: 2026-09-05.

> Sources: https://github.com/DepthAnything/Depth-Anything-V2 and
> https://huggingface.co/depth-anything/Depth-Anything-V2-Base

### Completed intake / CUDA oracle slice

> - Source: `a561b849ebae10a6f5ef49e26c83cbbcd36c71bf`, clean clone in
>   `out/da2-base-source`. Imports suppress bytecode creation to retain a strict
>   clean-worktree gate. Only generated Python caches were removed after the first
>   repeated-load test exposed this issue; upstream source was not modified.
> - Weights revision: `a4e71a6c2ce52fe50df0f212066b0d4a87be9b5e`;
>   `depth_anything_v2_vitb.pth`, 389961218 bytes; published SHA256 verified as
>   `0d2b7002e62d39d655571c371333340bd88f67ab95050c03591555aa05645328`.
>   Download URL is the official model repository's `/resolve/<revision>/<filename>`.
> - `v1/da2_base_experiment.py` loads verified weights with `weights_only=True`,
>   requires CUDA and native PyTorch attention, validates RGB/aspect/allocation
>   bounds, returns owned finite float32 depth and enforces owner/close checks.
>   No UI registration or TensorRT claim. Original preprocessing is retained;
>   this sample maps to [1,3,518,896], not Small's square production input.
> - `v1/test_da2_base_oracle.py` validates first-frame equality to upstream
>   `infer_image` (max error 0), repeated result/ownership and double-close/use-after-
>   close behavior, then runs Balanced policy with a hard 124-inference budget.
> - Report: `out/da2-base-oracle/c7511c9316794b70b81ea9aeaee1e0e2/report.json`.
>   RTX 5090, torch 2.7.1+cu128, CUDA 12.8, FP32; all 124 output frames decode at
>   2112x608. Separate ffprobe verifies H.264 + AAC. Input boundary unit test and
>   compileall pass. This is not full-sequence golden parity or a performance gate.

> Reproduce after fetching the pinned source and verified checkpoint into the
> paths above, using the existing isolated VDA environment:

> ```powershell
> $env:PYTHONPATH = 'v1'
> out/vda-oracle-env/Scripts/python.exe v1/test_da2_base_oracle.py --input 'samples/input.mp4'
> ```

> Follow-up: the fixed 518x896 FP32 ONNX/TensorRT experiment now passes 68 numerical
> comparisons (64 real frames, repeat and three synthetic inputs), maximum absolute
> error 0.000189781188964844. See [da2-base.md](da2-base.md#record-plan-da2-base-trt). App-grade artifact validation,
> runtime/lifecycle and GUI/CLI registration remain pending. FP16 is a roadmap
> target, not implemented; no app defaults or distribution files changed.


<a id="record-plan-da2-base-trt"></a>
## da2-base-trt

Checkpoint date recorded in source: 2026-09-05.

> Record graph/plan/source/checkpoint hashes, environment, errors and per-frame
> finite/allclose checks at atol=rtol=0.001. Use bounded sequential inputs and
> explicit CUDA ownership/synchronization; retain failed evidence and publish no
> app manifest until later lifecycle/security gates. Test real frames plus repeated
> first-frame and synthetic constant-color inputs. No UI/default/release changes.

### Evidence

> `v1/build_da2_base_spike.py` freshly exports/builds/checks the model. No prior plan
> or unverified third-party graph is accepted. The positional constant equals the
> original model's output exactly before export; reference inference then uses the
> restored original method. Export warnings reflect the deliberate fixed shape,
> not support for dynamic geometry.

> Report: `out/da2-base-trt/805c434aeca042698607bcf504b9d980/report.json`.
> All 68 comparisons pass: 64 sequential source frames, repeated first frame,
> black/gray/green synthetic inputs. Maximum absolute depth error is
> 0.000189781188964844 at atol=rtol=0.001; all outputs are finite. First-frame raw
> expected/actual depth is saved in `first-frame-golden.npz`. This is model-grid
> parity, not complete SBS/temporal quality acceptance or a benchmark.

> - RTX 5090, TensorRT 11.2.1.2, torch 2.7.1+cu128; TF32 off, FP32 graph/I/O.
> - ONNX SHA256: `ea4395b7864fbeb6c4819a469006166d559ed124a5e9511273e00484aab4beec`.
> - Plan SHA256: `93d5159282cc96ac2ea79895051f7646514791cac9351917c62f444818b78209`.
> - Plan size: 402367692 bytes. Fresh build took 20.61 seconds on this host;
>   this is build duration, not video-processing performance.
> - Input boundary test, compileall and diff whitespace checks pass. Pinned source
>   remains clean. The diagnostic uses the default CUDA stream with explicit
>   synchronization; TensorRT warns this is not performance-optimal.

> Reproduce with the prepared, pinned source/weights/environment:

> ```powershell
> $env:PYTHONPATH = 'v1;out/v1-python-deps'
> out/vda-oracle-env/Scripts/python.exe v1/build_da2_base_spike.py --input 'samples/input.mp4' --frames 64
> ```

> Standard 16:9 and other profiles require separate validated builds. FP16 remains unimplemented; TensorRT 11 uses strongly typed graphs, so future precision conversion requires an explicit graph transformation and independent parity gate, not an FP16 builder flag. See [NVIDIA migration documentation](https://docs.nvidia.com/deeplearning/tensorrt/latest/api/migration/tensorrt-10x-to-11x-python-api-patterns.html).


<a id="record-reference-da2-base-local"></a>
## da2-base-local

Checkpoint date recorded in source: 2026-09-05.

> ```powershell
> .\scripts\run-da2-base.ps1 -Diagnostics
> .\scripts\run-da2-base.ps1 -InputVideo 'samples/input.mp4' -OutputVideo '.\out\base-sbs.mp4'
> ```

> The launcher selects from `out/da2-base-local`: 518x896 for the supplied 1056x608
> clip, and 518x924 for standard 16:9 (720p/1080p/4K). Input aspect ratio selects
> one engine per job; profile folders contain the exact validated FP32 plans.
> Portrait, other GPUs and other TensorRT versions require separately validated builds.
> Unsupported geometry is rejected before output mutation. Full SBS preserves
> per-eye source dimensions; it doubles width. FP32 inference uses a dedicated
> CUDA stream; CPU stereo synthesis and media pipes remain in use.

> Verification: 124-frame H.264/AAC output, upstream-exact preprocessing, first-frame
> depth parity, cancel/injected error preserving prior output, real Tk worker
> arguments, diagnostic launch, 106 Python tests plus process-tree and C++ gates.
> Results: `out/da2-base-app/acaf4714b5864c23932b615cc1a154cf/`.
> FP16 candidates are evaluated separately and are available only to diagnostic
> tools until their numerical gate passes. User conversion uses validated FP32.
> For 4K Full SBS, explicitly select HEVC with `-OutputCodec hevc`.
> Headset quality and distribution remain separate work.

> 2026-09-05 expansion verification passes 720p/1080p full 124-frame conversion,
> short 4K HEVC, HEVC scene cut, 16:9 cancel/error/GUI tests and 108 unit tests.
> Both tested FP16 candidates failed accuracy and remain unavailable in the GUI.
> See [model-comparisons.md](model-comparisons.md#record-result-model-evaluation-2026-09-05) for three-model performance,
> quality proxies, memory observations and the decision to retain mode defaults.
