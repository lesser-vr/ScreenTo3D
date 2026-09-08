# oVDA build, runtime and evaluation

Historical evidence by recorded checkpoint. Current support is in
[implementation status](../implementation-status.md).

## Records

- [ovda-c16-experiment](#record-result-ovda-c16-experiment)
- [ovda-expansion-results-2026-09-05](#record-result-ovda-expansion-results-2026-09-05)
- [ovda-other-gpu-validation](#record-result-ovda-other-gpu-validation)
- [ovda-integration](#record-plan-ovda-integration)
- [ovda-user-integration](#record-plan-ovda-user-integration)
- [ovda-quality-performance-expansion](#record-plan-ovda-quality-performance-expansion)
- [ovda-local-preview](#record-reference-ovda-local-preview)

<a id="record-result-ovda-c16-experiment"></a>
## ovda-c16-experiment

Checkpoint date recorded in source: 2026-09-05.

> Status: Initial bounded experiment validated, 2026-09-05. Historical evidence below.

> Subsequent user integration now adds the 896 profile and source GUI/CLI without
> the 124-frame limit. See [ovda.md](../models/ovda.md) and
> [ovda.md](ovda.md#record-plan-ovda-user-integration) for current behavior and evidence.
> The bounded-run and no-GUI statements below describe the initial experiment only.
> The later [ovda.md](ovda.md#record-result-ovda-expansion-results-2026-09-05) also covers CUDA stereo, 4:3,
> short 4K, runtime dependency separation and evaluated-but-not-adopted c8/FP16.

### License and isolation

> User clarified personal use and source-sharing intent. Official oVDA code has
> mixed marked Apache-2.0 portions and NC-SA-UHDV1.0 components; the official
> weights also use NC-SA-UHDV1.0. This restricts commercial-purpose development,
> benchmarking and redistribution, and imposes same-license requirements on
> derivatives. Personal-use clarification permits this experiment's intended
> non-commercial scope, not unrestricted open-source/commercial distribution.

> The derived cache/export adapter lives under `experiments/ovda`, with the full
> upstream LICENSE and Heidelberg University/author attribution. No repository-wide
> relicensing, upstream modifications, public GUI option, bundle or default change.
> Directory separation does not itself resolve derivative-work/legal distribution
> questions; review those before publishing an integrated release.

> Source: https://github.com/FriedFeid/OnlineVideoDepthAnything at
> `4173c24e22f528062a0cf8ae235c58a5d4376a74` (`out/ovda-source`, clean).
> Weights: https://huggingface.co/FriedFeid/oVDA at
> `9eda2255e19c51dd1989b9c08b886e665f15007e`, `oVDA_c16.pth`, 116345367 bytes,
> SHA256 `ea531d53a1135a443bafcf106a175b26a6519c05ccc1e994d74e46159e14b7cb`.
> Bytes matched the official LFS hash before strict `weights_only=True` loading.
> c8 has not been downloaded or evaluated.

### Implemented boundary

> - Explicit personal-use CUDA FP32 oracle and separate TensorRT FP32 runner.
> - Original preprocessing, exact cache warm-up/rollover, four cache tensors with
>   16 slots. Persistent cache storage 190857216 bytes at 518x924 (not total VRAM).
> - Pinned clean source, fixed checkpoint/plan hashes, exact 12 tensor signatures,
>   FP32 image/depth/cache and INT64 mask/position; local RTX 5090 + TRT 11.2.1.2.
> - One owned finite float32 depth output per frame; owner/device/geometry checks,
>   cut/source/discontinuity reset, dedicated CUDA stream in the TRT adapter,
>   synchronization before releasing bound buffers, deterministic close on error.
> - Source app pipeline exercised through its existing BackendBinding, not a
>   renamed VDA model. Runtime identity says `ovda-small-c16` and experiment precision.
> - No CPU, precision, model or shape fallback. Ordinary app defaults stay Small.

> Current launcher supports known-count **1–124 frame standard-16:9 clips** within
> existing <=1920 dimensions, with H.264/H.265 input and H.264 Full SBS output.
> It requires a new output path. No crop/padding, frame drops or geometry conversion
> is introduced. 720p was exercised end to end; do not infer full 1080p support
> from profile mapping. Original 1056x608 is oracle-compatible but has no validated
> 518x896 TensorRT plan yet, so the TRT launcher rejects it. No long-job/GUI claim.

### Oracle and export evidence

> Oracle: `out/ovda-oracle/76d70009c8de460aba817bed7d88945d/report.json`.
> Original unmodified batch inference versus bounded adapter passes 32 frames,
> including cache fill and rollover, at atol=rtol=.001. Reset repeat checks,
> foreign-thread rejection, geometry-change rejection, close/use-after-close pass.
> Its real 120-frame FloorballGame SBS output fully decodes at 2560x720.

> First export `out/ovda-trt/24af842b4f9a4970871160076eb0eacf` builds but fails
> all 32 comparisons. First depth max error .206536, cache c1 .378877. Retained
> as a rejected diagnostic only. No tolerance relaxation or failed-plan promotion.

> The next export computes the original backbone's fixed 518x924 positional
> interpolation once, exports it as a constant buffer and restores the original
> method for reference comparisons. Original versus substituted method is exactly
> equal at export input. This avoids TensorRT's problematic position-resize path.
> Accepted experimental build:
> `out/ovda-trt/bb6a03e172414a60b470f70c2cfd9a98/report.json`.
> All **32 frames x 5 outputs = 160** depth/cache comparisons pass atol=rtol=.001,
> with reference and TRT each feeding their own previous caches. FP32, TF32 off.
> Plan 129402708 bytes, SHA256
> `6aab5d663f544192b78a7c16d8e86c2345774602c92f93c8c1bd02376e3d410a`.
> The initial unfixed export remains reproducible by omitting `--fold-position`.

### Pipeline and comparison evidence

> `out/ovda-trt-integration/7b440058ea7d40bf97893b8c9a8d5043/report.json`:
> real adapter versus CUDA oracle passes 32 frames (resized depth max error
> .000089169); all three reset reasons reproduce first-frame TRT output exactly.
> Six source-matched 120-frame conversions pass full decoding/count/2560x720
> geometry/audio-presence checks against existing Small/Base/VDA input hashes.
> The KnownCut at frame 60 matches a freshly initialized renderer exactly.

> All comparisons use Video Quality stereo/encode policy and the existing corpus
> from [model-comparisons.md](model-comparisons.md#record-result-live-action-model-decision-2026-09-05). Files retain original cadence:
> 60fps UVG-VCM and 120fps Beauty; no audio in those source excerpts. Source rights
> and transformations remain as recorded there (Beauty is separately NC media).

> | Scene | VDA aligned depth MAE | oVDA c16 aligned depth MAE |
> |---|---:|---:|
> | OfficeWalk | .006373 | .006971 |
> | HighwayDrive | .002840 | .003113 |
> | FloorballGame | .001053 | .001222 |
> | ParkingGarage | .001053 | .001154 |
> | KnownCut, cut excluded | .003902 | .004269 |
> | Beauty | .003036 | .003458 |

> On this proxy, VDA is slightly more stable. These numbers do not prove depth
> accuracy, perceived ghosting, comfort or superiority; see the metric's masks and
> normalization limitations in the corpus decision. No default promotion. Sample
> Floorball frame-60 source/VDA/oVDA both-eye sheet inspected; plausible contours
> and model-dependent parallax, not a blinded temporal or VR quality assessment.
> No new repeatable FPS/total-VRAM comparison has been performed.

> Real cancellation and injected failure preserve pre-existing output and release
> model/cache or TRT context: PyTorch report
> `out/ovda-failures/f39754d1ab8f443fbaac34bfc9711463/report.json`; TRT report
> `out/ovda-failures/206b9b0766094d209e975e293a73e92e/report.json`.
> Three isolated CPU contract tests pass; existing canonical 112 Python tests,
> seven process-tree cases and C++ CTest pass. `compileall` passes. The upstream
> source stays clean and no existing Torch/TRT dependencies were downgraded.

### Reproduction and use

> Actual `run.ps1` smoke:
> `out/ovda-launch-smoke-5ee2f01b1fb547d6b97f589d1665913b/output-sbs.mp4`.
> Input is a one-second FloorballGame excerpt re-encoded as HEVC with an explicitly
> synthetic 440Hz AAC tone (not original source audio). Full output decode confirms
> 60 frames, 2560x720 and retained audio. This is H.265 input coverage; the launcher
> still emits H.264 output. Source credit is retained in that directory.

> Environment: Windows 11, RTX 5090, driver 616.56, torch 2.7.1+cu128,
> numpy 2.5.2, TensorRT 11.2.1.2, einops .8.1, easydict 1.13. Additional pinned
> import dependencies live only in `out/ovda-python-deps` and are listed in
> `experiments/ovda/requirements-extra.txt`; native attention, no xFormers.

> ```powershell
> $env:PYTHONPATH='experiments/ovda;v1;out/ovda-python-deps;out/v1-python-deps'
> out/vda-oracle-env/Scripts/python.exe experiments/ovda/validate_oracle.py --input <short-clip>
> out/vda-oracle-env/Scripts/python.exe experiments/ovda/build_engine.py --fold-position --input <16:9-short-clip>
> out/vda-oracle-env/Scripts/python.exe experiments/ovda/validate_trt.py
> experiments/ovda/run.ps1 -InputVideo <16:9-short-clip> -OutputVideo <new-sbs.mp4>
> ```

> Builds create unique directories. The runtime intentionally pins the exact
> validated local plan; a rebuild does not automatically authorize its hash.
> Run GPU checks sequentially. Do not present this local launcher as the normal
> portable application or a universal engine installer.

> Remaining: original-aspect 518x896 profile, larger independent numerical corpus,
> long-video/cancel/device-failure envelope, repeatable whole-pipeline speed/VRAM,
> c8/FP16 experiments if justified, and license-aware GUI/install integration.
> Release, one-hour soak and headset testing remain deferred by user direction.


<a id="record-result-ovda-expansion-results-2026-09-05"></a>
## ovda-expansion-results-2026-09-05

Checkpoint date recorded in source: 2026-09-05.

> Status: Accepted for the stated local source-app envelope, 2026-09-05.
> No release, native-offline backend, broad GPU certification or VR acceptance.

### Decisions

> - Keep all existing DA2 Small mode defaults. oVDA remains an explicit choice;
>   this evaluation does not justify making it the Video Quality default.
> - Keep oVDA c16 FP32. c8 reduces cache storage but has mixed/worse temporal-edge
>   results; the FP16 export fails the existing numerical gate. Neither is exposed
>   as an automatic speed/quality fallback.
> - The dedicated oVDA launcher now selects CUDA stereo, shown explicitly in the
>   GUI. CPU stereo remains selectable. The generic app and old portable defaults
>   are unchanged. CUDA/CPU pre-encode SBS hashes match exactly on five inputs.
> - Add the exact 518x686 4:3 profile and short 4K HEVC compatibility. Source
>   geometry is preserved; unsupported profiles and 4K H.264 output fail early.
> - Runtime preprocessing is now local NC-licensed code, proven exact against the
>   pinned original. App inference no longer needs the upstream checkout, Git,
>   checkpoint, or the build-only `out/ovda-python-deps` packages.

### Matched quality

> The seven clips combine new four-model avatar runs with the earlier six matched
> public clips. `v1/summarize_ovda_quality.py` joins evidence; the c8 comparison
> additionally verifies source file hash, decoded RGB hash and actual frame count.
> No model-specific source crop, different source frame subset or proxy parameter
> change is used. All outputs use the same Video Quality stereo policy.

> Mean source-flow-aligned normalized raw-depth change (lower is steadier under
> this mask, not necessarily more accurate):

> | Clip | Small | Base | VDA | oVDA c16 |
> |---|---:|---:|---:|---:|
> | Avatar / hands | .006692 | .007124 | .002424 | .002978 |
> | OfficeWalk | .008963 | .006765 | .006373 | .006971 |
> | HighwayDrive | .003778 | .003086 | .002840 | .003113 |
> | FloorballGame | .001778 | .001151 | .001053 | .001222 |
> | ParkingGarage | .001754 | .001273 | .001053 | .001154 |
> | KnownCut | .005364 | .004111 | .003902 | .004269 |
> | Beauty / hair | .007640 | .006140 | .003036 | .003458 |

> VDA has lower aligned and edge-aligned change than c16 on all seven clips.
> This is not an overall VDA quality ranking: normalization hides global scale
> drift, optical-flow masks exclude difficult occlusions, and smooth inaccurate
> depth can score well. Spatial ground truth and blinded headset playback remain
> absent. Labeled avatar hand motion review and sampled hand/hair/sports images
> provide inspection material, not a claim that fine ghosting has disappeared.
> Sampled images show different silhouette/parallax placement; no sufficiently
> clear overall oVDA advantage warrants a default change.

> Raw evidence:

> - `out/ovda-expansion-evaluation/d6595c357e654ebfb6fba313845cbf9e/report.json`
>   and `quality-summary.json` / `.csv`; avatar `hands-review.mp4`, frame sheets.
> - Earlier six clips:
>   `out/ovda-trt-integration/7b440058ea7d40bf97893b8c9a8d5043/report.json`.
>   Source attribution stays with the corpus; no private user footage is published.

### Candidate precision/cache decisions

> FP16 candidate `out/ovda-trt/7c8b5d0fbef34ca1a4dddab41a3d70ab/report.json`
> keeps I/O, Resize, LayerNormalization and Softmax FP32 but fails all 32 frame
> comparison groups at atol/rtol .001. First-frame depth max absolute difference
> is .118854 and c1 cache difference .374247. It is not installed/allowlisted.
> This rejects this export candidate, not every possible future mixed-precision
> implementation.

> c8 official checkpoint SHA256:
> `af3788fbc6517704d3430ee1886f27e648b8d61e2da10b739b3bb59f4e8f585d`,
> 116299380 bytes, pinned weight revision
> `9eda2255e19c51dd1989b9c08b886e665f15007e`.
> `out/ovda-c8-quality/c66cf4b505fe4d5b820858964b3a5a3e/report.json` passes
> 32-frame original-batch vs bounded-adapter parity and source/cut checks.
> Relative to c16, aligned change is +17.5% on avatar and +7.9% on Floorball.
> Beauty aligned change improves 1.1%, but its edge change worsens 5.8% (avatar
> edge +7.8%, Floorball edge +3.9%). Persistent cache bytes halve to 92536832
> (896) / 95428608 (924); total VRAM does not halve. c8 is therefore retained as
> a developer candidate, not adopted for the current quality-oriented user path.
> Its PyTorch timings are not compared to c16 TensorRT whole-job speed.

### Whole-job performance

> User-path runtime, one discarded warmup plus five fresh-process repetitions per
> renderer/input. Hash/flow diagnostics are off. All outputs pass full decode,
> frame count, SBS dimensions and audio-presence checks. Pipeline FPS includes
> startup/processing/finalization under the existing denominator; process wall
> is separately retained. These are short exploratory runs, not sustained gates.

> | Input | CPU median FPS (range) | CUDA median FPS (range) | Ratio |
> |---|---:|---:|---:|
> | Avatar 1056x608, 124 frames | 12.55 (12.45–12.61) | 17.68 (16.78–17.74) | 1.41x |
> | 1920x1080, 60 frames | 3.96 (3.92–4.13) | 9.78 (9.62–10.62) | 2.47x |

> Both final comparisons output H.264 with audio; the 1080p input is HEVC with
> a synthetic tone and explicitly upscaled licensed footage. Original source
> cadence and A/V policy are preserved, not slowed to the processing speed.

> The median per-run mean temporal/stereo stage drops 42.94→21.66 ms on avatar
> and 190.89→43.32 ms on 1080p. Depth (including internal preprocess/copies) is
> 28.48 ms on avatar / 41.09 ms at 1080p in the CUDA runs. Remaining CPU temporal,
> normalization/refinement work and depth now matter; this is not full GPU interop
> or zero-copy and does not establish 30/60fps live conversion.

> Environment: Windows, RTX 5090, driver 616.56, torch 2.7.1+cu128, TensorRT
> 11.2.1.2, NumPy 2.5.2. Pinned CUDA projection DLL SHA256
> `e16e82674ad19373ecffc4d5ec8601f46bda359912200a941c3f29c743975114`.
> Commit/dirty state, source hashes, FFmpeg version, commands, plan identity,
> stage distributions and GPU/power observations are in the raw reports.
> No reboot was performed; desktop/Comfy processes remained resident. No unrelated
> process was stopped. Sampled device VRAM spans 23832–25871 MiB (avatar) and
> 24007–27358 MiB (1080p), including those resident workloads. These are not model
> requirements. PyTorch peaks are 395400192 / 414932992 bytes, excluding native
> TensorRT/NVENC. GPU observation parsing reports zero failures. Neither observation
> proves process-specific total peak or leak freedom.

> - Avatar: `out/ovda-expansion-evaluation/8d70b8a3d87441de89285a239898b9a9/`
> - 1080p: `out/ovda-expansion-evaluation/ad09b1729f93444492f67699e5ca1d55/`
> - Each has `report.json`, `benchmark.csv`, raw per-run media/JSON/GPU observations,
>   and `performance-summary.json`. `v1/summarize_ovda_performance.py` reproduces
>   the summaries. Earlier startup-dependent numbers are superseded by this table.

> After these repetitions, guard-only hardening made preprocessing constants
> explicitly CPU FP32 and checks every bound tensor's dtype/layout/device before
> submission. It does not change the tested algorithm or accepted precision.
> Original-preprocessor exactness plus a changed-default-dtype check passed again:
> `out/ovda-preprocessing/137d6a101dc04d26a36e5ed202465f09/report.json`.
> An injected float64 preprocessor output was rejected with engine cleanup; the
> final guarded user launcher passed full original decode/audio, and all 120
> Python regressions passed again. The throughput table records the pre-hardening
> repetitions rather than claiming a second post-hardening five-run benchmark.

### Input and reliability expansion

> 4:3 FP32 build:
> `out/ovda-trt/dfcf1b651d8b4986a1019356fc4d48be/report.json`, all 32 x 5
> depth/cache comparisons pass. 126622404-byte plan SHA256
> `db2cf668ef4347ad655983109f9e98c358d76eae9a7511a794c108b81f4d408f`.

> Local/original preprocessing matches exactly on 18 zero/one/random cases across
> original, 720p, 1080p, 4K, 4:3 and exact network dimensions plus a size sweep:
> `out/ovda-preprocessing/b549f022387a4f5287409a6994542def/report.json`.
> The original max<=1 near-black normalization behavior is intentionally preserved.

> Expanded user-path gate:
> `out/ovda-expanded-gate/05d776718fdf4cbcbe4af9f423c3f598/report.json`.

> - Original 124, 4:3 960x720 60, 1080p 60, 4K 3840x2160 30 and KnownCut 120
>   frames: CPU/CUDA decoded-source, raw-depth and pre-encode SBS hashes exact.
>   Every output fully decoded; 4K output is HEVC 7680x2160 with audio.
> - Original hashes also match the earlier upstream-preprocessor runtime.
>   A runtime-source-import trap proves conversion does not invoke the checkout.
> - `timing-report.json` independently verifies cadence, relative frame PTS
>   (<=0.0001 s tolerance), audio channels/sample rate/duration on all ten outputs,
>   plus full decode/audio for the actual CUDA user-launcher result.
> - Actual 4:3/4K cancellation, injected depth failure and injected projection
>   failure: six cases preserve prior output and release depth/cache/native handles.
> - 4K H.264 output is rejected before GPU setup or output mutation. The expected
>   rejection traceback in the test log is a passing negative test, not failure.
> - 4:3 persistent cache is 142163968 bytes; other profiles remain fixed at 16 slots.
>   4K is a 30-frame generated compatibility fixture, not a sustained/VR quality gate.

> Full regression: 120 Python tests, 7 process-tree cases and C++ CTest pass;
> 3 separate oVDA contract tests and real-Tk oVDA/VDA GUI checks pass. Actual
> minimal-environment launcher and all three engine diagnostics also pass.

> Other-GPU build/validation/promotion procedure:
> [ovda.md](ovda.md#record-result-ovda-other-gpu-validation). Hardware testing on another GPU, portable
> installation, distribution review, one-hour stability and VR playback are not
> claimed complete and remain outside this requested local step-1–3 delivery.


<a id="record-result-ovda-other-gpu-validation"></a>
## ovda-other-gpu-validation

### Recorded scope

> A target-device build/validation procedure was documented, but no second GPU was attached and no other hardware was certified. The procedure used pinned source/checkpoint, preprocessing and self-fed cache comparisons, artifact/capability validation, affected lifecycle/media checks and separately validated CUDA stereo. Current operational commands are in the oVDA model setup document.


<a id="record-plan-ovda-integration"></a>
## ovda-integration

Checkpoint date recorded in source: 2026-09-05.

### Initial intake history (before personal-use clarification)

> User requested oVDA integration. Official source inspected at
> https://github.com/FriedFeid/OnlineVideoDepthAnything , pinned revision
> `4173c24e22f528062a0cf8ae235c58a5d4376a74`, locally under `out/ovda-source`.
> This is separate from the already integrated Video Depth Anything streaming path.
> Official weight repository https://huggingface.co/FriedFeid/oVDA labels its
> license NC-SA-UHDV1.0. No weights downloaded or upstream inference executed.

### Initial license pause (resolved for personal experiment only)

> Source reference:
> https://github.com/FriedFeid/OnlineVideoDepthAnything/blob/4173c24e22f528062a0cf8ae235c58a5d4376a74/LICENSE

### Technical intake (not validated compatibility)

> Official c8/c16 Small configurations and ONNX/TensorRT build scripts are present.
> The c16 config specifies ViT-S, features 64, output channels 48/96/192/384,
> cache size 16, absolute positional encoding, and xFormers disabled. Upstream
> README describes Python 3.10/CUDA 12.1 and TensorRT 10.3 dependencies, unlike
> our existing Python 3.13/TensorRT 11.2 RTX 5090 environment. Do not install its
> pinned requirements over the working VDA environment or promise engine parity.


<a id="record-plan-ovda-user-integration"></a>
## ovda-user-integration

Checkpoint date recorded in source: 2026-09-05.

### Completed

> - Both fixed profiles are allowlisted and checked again before deserialization.
>   Original 896 build: `out/ovda-trt/ca1a0b2021064a63bc279ab323f37d48/report.json`,
>   all 32 x 5 depth/cache comparisons passed; plan SHA256
>   `fbfe8fc4547ddcfb16a27fa78fe0ae1039ee2f18bb2d1ec374a280d30fa6fe99`.
> - Source GUI and CLI expose `ovda-small-c16`; NC scope confirmation, early mode
>   rejection, trusted engine folder, automatic exact profile selection, progress,
>   cancel and errors are wired. `Run-oVDA.cmd` / `scripts/run-ovda.ps1` launch it.
> - The user binding has no BoundedEngine/124-frame diagnostic wrapper. Failed
>   profile selection invalidates prior selection; no fallback or geometry coercion.
> - `v1/test_ovda_user.py` passed:
>   `out/ovda-user-validation/86afad4c521147b492e052186b57a277/report.json`.
>   Original 124 frames (Balanced, H.264/AAC), repeated known-cut 600 frames
>   (Video Quality), and 1080p 60 frames (Offline Quality, HEVC/AAC) fully decoded
>   with exact SBS dimensions, count, cadence and audio presence. HEVC fixture
>   uses explicitly upscaled UVG-VCM content and a synthetic 440 Hz AAC tone.
>   The 600-frame clip is a 10-second loop, not a long-duration soak.
> - Cache samples stayed 185073664 bytes for 896 and 190857216 for 924, 16 slots;
>   600 frames produced 10 start/cut resets. This is cache evidence, not total
>   process memory/leak proof. Sample instrumentation means timings are diagnostic.
> - Both profiles passed actual cancellation and injected inference-error cleanup
>   with prior-output sentinels preserved and cache/context released.
> - Public PowerShell launcher separately converted the original successfully:
>   same evidence root, `launcher-original-sbs.mp4` and `launcher.log`.
> - Real Tk tests passed oVDA layout, unchecked-license refusal, worker arguments,
>   cancel flag and unsupported-mode refusal; existing VDA/DA2 GUI defaults pass.
> - `scripts/test-v1.ps1`: 116 Python tests, 7 process-tree cases, C++ CTest pass.
>   Separate oVDA cache/frame contract: 3 tests pass.

> An initial verification attempt used input-only `probe_video` on SBS output,
> incorrectly applying the double-width output limit again. The harness now uses
> FFprobe for output codec/cadence, plus full decode for geometry/count. Failed
> evidence root `bfa7356c9c074712b3bf3015e06be79c` is not a passing result.


<a id="record-plan-ovda-quality-performance-expansion"></a>
## ovda-quality-performance-expansion

Checkpoint date recorded in source: 2026-09-05.

### Work and gates

> Keep defaults DA2 Small unless quality gates justify a separate decision.
> oVDA remains NC-SA-UHDV1.0 personal/non-commercial; no release, global relicensing,
> V2 capture, one-hour soak or VR playback in this task. Preserve source geometry.
> Other GPU hardware is unavailable: complete the procedure, not hardware claims.
> All GPU work is sequential. Raw experiments stay under unique out/ directories.

### Results

> All three work items are implemented and verified. Full evidence and decisions:
> [ovda.md](ovda.md#record-result-ovda-expansion-results-2026-09-05).

> - Seven matched clips and an avatar hand review retain mode defaults. c8 was
>   verified against the original batch implementation and compared on avatar,
>   sports and hair clips; mixed/worse temporal-edge results mean no adoption.
>   FP16 failed all 32 numerical frame groups and is excluded from the allowlist.
> - Exact CPU/CUDA SBS hashes on five inputs; final warmup + five-run medians:
>   original 12.55→17.68fps (1.41x), 1080p 3.96→9.78fps (2.47x). Stage bottlenecks,
>   raw CSV/JSON and explicitly device-wide/Torch-only memory observations recorded.
> - 518x686 profile passes 32 x 5 numerical comparisons; original/1080p/4:3/4K/cuts
>   pass full decode and exact hash parity. Six 4:3/4K abort cases preserve prior
>   output and free resources; incompatible 4K H.264 output is rejected early.
> - App preprocessing no longer depends on source checkout/Git/build-only packages;
>   18 original-preprocessor comparisons and size sweep are exact. GUI/CLI expose
>   CUDA/CPU selection, installation report and actionable startup errors.
> - Other-GPU build/validation/promotion procedure is documented. Actual testing on
>   another GPU is not possible on this host and is not claimed completed.
> - 120 Python, 7 process-tree and C++ regression cases/gate pass; 3 oVDA contract
>   tests, real-Tk oVDA/VDA tests, three-profile diagnostics and public launcher pass.

> No release, V2 implementation, one-hour soak or VR playback was added. Other GPU
> support and clean-machine packaging still require their separate external gates.


<a id="record-reference-ovda-local-preview"></a>
## ovda-local-preview

Checkpoint date recorded in source: 2026-09-05.

### Supported environment and geometry

> - NVIDIA GeForce RTX 5090 (SM 12.0), validated driver 616.56, Windows.
> - TensorRT 11.2.1.2 runtime; `-RuntimeDirectory` may override its DLL location.
> - Local Python 3.13.14 environment `out/vda-oracle-env`, torch 2.7.1+cu128.
> - Source width 16..4096, height 16..2160, landscape AND an exact preprocessing
>   match to an installed 518x686, 518x896 or 518x924 engine.
>   Verified examples: 4:3 960x720, original 1056x608, standard 1280x720,
>   1920x1080 and short 3840x2160 HEVC input/output.
> - 4K requires explicit HEVC output (Full SBS 7680x2160). H.264 output is rejected
>   at that width. The 30-frame 4K test is compatibility evidence, not sustained FPS.
>   This gate uses 8-bit SDR media; HDR color-management correctness is not certified.
> - Unsupported profile gaps, portrait, square and ultrawide inputs are rejected, not converted
>   through padding or resizing to another aspect ratio.
> - No 124-frame application limit. The model retains 16 cache slots regardless
>   of duration; scene cuts clear temporal state. Long-duration stability and VR
>   playback are not certified by removing the short diagnostic limit.
> - H.264/HEVC video input through existing app decoding; audio follows the shared
>   app mux policy. Converted results retain source frame count and cadence.

### Local installation and reproducibility

> 1. `out/vda-oracle-env/Scripts/python.exe`, with the pinned torch/TensorRT/CV
>    environment recorded above; do not downgrade it using upstream requirements.
> 2. App dependencies in the existing `out/v1-python-deps` path; the optional
>    NC runtime source and license in `experiments/ovda` remain required.
> 3. FFmpeg/FFprobe at `out/gpu-preview/DepthSBS-GPU-Preview/_internal/ffmpeg`.
>    CUDA stereo additionally uses the checksum-validated local preview
>    `_internal/projection/projection.dll`. CPU selection does not require this DLL.
> 4. Trusted validated `model.plan` under named direct children
>    `out/ovda-local/518x686-fp32`, `518x896-fp32` and `518x924-fp32`.
>    A subset can be installed; inputs needing a missing profile fail explicitly.

> The application verifies plan size/SHA256 before deserialization, GPU/runtime and
> all tensor signatures. Runtime inference uses exact-validated local preprocessing
> and does not import the original checkout, invoke Git, load checkpoint weights,
> or need build-only `out/ovda-python-deps` packages.

> Build/reference tools still need the clean official source at
> `out/ovda-source` revision `4173c24e22f528062a0cf8ae235c58a5d4376a74`, Git,
> ONNX and the additive pinned `experiments/ovda/requirements-extra.txt` dependencies
> in `out/ovda-python-deps`. Do not install upstream requirements over the app stack.

> ```powershell
> $env:PYTHONPATH='experiments/ovda;v1;out/ovda-python-deps;out/v1-python-deps'
> out/vda-oracle-env/Scripts/python.exe experiments/ovda/build_engine.py --fold-position --width 896 --input '<1056x608 calibration clip with at least 32 frames>'
> out/vda-oracle-env/Scripts/python.exe experiments/ovda/build_engine.py --fold-position --width 924 --input '<16:9 calibration clip with at least 32 frames>'
> out/vda-oracle-env/Scripts/python.exe experiments/ovda/build_engine.py --fold-position --width 686 --input '<4:3 calibration clip with at least 32 frames>'
> ```

> Build additionally requires the pinned, checksum-verified c16 checkpoint at
> `out/models/ovda/oVDA_c16.pth` (source/weight URLs and hashes in the experiment
> README). It runs original-vs-export position checks and 32 self-fed comparisons
> of depth and all four cache outputs at atol/rtol .001. Inspect `report.json`;
> never install a failed engine. Different regenerated hashes require explicit
> validation and an allowlist update in `v1/depthsbs_app/ovda.py`, not trust in an
> arbitrary engine manifest. See the user integration execution plan for evidence.

<a id="provenance-docs-design-docs-ovda-other-gpu-validation-md"></a>
### Additional provenance: ovda-other-gpu-validation

> Recorded build provenance/artifact identifiers: `out/checkpoints`, `out/ovda-trt/`.
