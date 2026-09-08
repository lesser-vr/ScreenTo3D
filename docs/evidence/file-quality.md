# File stereo and motion quality

Historical evidence by recorded checkpoint. Current support is in
[implementation status](../implementation-status.md).

## Records

- [v1-1-coverage-performance](#record-plan-v1-1-coverage-performance)
- [v1-1-left-hand-edge](#record-plan-v1-1-left-hand-edge)
- [v1-1-local-motion-stability](#record-plan-v1-1-local-motion-stability)
- [v1-1-local-motion](#record-plan-v1-1-local-motion)
- [v1-1-motion-ab](#record-plan-v1-1-motion-ab)
- [v1-1-motion-refresh](#record-plan-v1-1-motion-refresh)
- [v1-1-motion-validation](#record-plan-v1-1-motion-validation)
- [v1-1-packaged-parity](#record-plan-v1-1-packaged-parity)
- [v1-1-stereo-ghosting](#record-plan-v1-1-stereo-ghosting)
- [letterbox-opt-in](#record-plan-letterbox-opt-in)
- [processing-modes](#record-reference-processing-modes)

<a id="record-plan-v1-1-coverage-performance"></a>
## v1-1-coverage-performance

> Implemented exact uint8 RGB difference reduction and inclusive color-range
> masking. Range bounds are derived from the old float32 predicate over all 256
> byte values, preserving threshold rounding. No depth or coverage changes.
> Joint percentile scanning was rejected: it changed scalar float32 results by
> up to 2.38e-8 in the synthetic check. Original percentile calls retained.
> 35 Python tests, 7 process-tree cases and C++ suite passed, including exhaustive
> byte-pair difference parity and fractional color/threshold mask parity.

> Packaged Balanced smoke: out/soak/70da670e44fb4d70b48372ca305df652/result.json, adjacent output.mp4. 124 frames, 15.8025 seconds, 7.8469 fps; temporal/stereo mean 108.83 ms. Previous coverage run was 17.7484 seconds, 6.9866 fps. These are separate single runs, not a controlled repeated speedup claim. Decoded full-video SHA256 equals the hand-corrected baseline: `b7f2669b270a2cb12ad1affe96df59717b28b90d6db4971de7776d856eb02dc3`. Thus this clip's full RGB result is unchanged; wider-scene quality is not proven. Saved-sample spatial medians (12 runs): guide 8.57 ms, backdrop 16.77 ms, conservative one-eye coverage 17.41 ms. Not end-to-end FPS. Portable executable rebuilt; original and previous outputs retained. Do not disable conservative coverage to recover throughput or declare universal ghost-free output.


<a id="record-plan-v1-1-left-hand-edge"></a>
## v1-1-left-hand-edge

> Recorded outcome: Implemented and packaged; user motion review pending

### Findings

> Matched-depth frame 48 reproduces the sleeve crack with EMA disabled, before
> encoding. Expanding the backdrop guard by 1-3 pixels did not fix it and was
> rejected. Nearest-center rasterization can skip a target pixel within foreground
> while projected background already occupies it, so empty-hole filling cannot
> repair that pixel. A synthetic fractional-shift near/far oracle reproduces this
> for both directions. Conservative floor/ceil visibility splats remove the
> reproduced real-frame crack with unchanged depth, RGB and disparity strength.

> Mode policy enables the new coverage; integer mappings are unchanged. Fractional
> silhouettes can expand by one pixel. This is conservative coverage, not filtered
> subpixel reconstruction, and cannot guarantee hidden texture or VR comfort.
> The nearest path is retained for diagnostic ablation. Earlier optimization
> pixel-equality evidence applies only to that path, not the new coverage output.
> Python 33 tests, process-tree 7 cases and C++ regression suite passed.

### Packaged result

> Balanced output and raw evidence:
> `out/soak/8fde4f6e7c77452d87c62182e98e5fd9/output.mp4` and `result.json`.
> Media/resource smoke passed: 124 frames, elapsed 17.748 s, 6.987 fps,
> temporal/stereo mean 125.16 ms. This is one run, not a paired benchmark.
> Coverage adds CPU work; do not carry forward the prior 8.15 fps claim.
> Decoded left-eye crops at frames 0/48/96 and right-eye frame 48 were inspected.
> The reproduced thin sleeve crack is no longer visible in frame 48; sampled
> hand/ear/tail outlines show no obvious new detached contour. These still checks
> do not establish full-motion or complex-scene acceptance. Original media and
> previous outputs remain unchanged. Next gate is user review of this new clip.


<a id="record-plan-v1-1-local-motion-stability"></a>
## v1-1-local-motion-stability

> Recorded outcome: Bounded stability regression passed

### Results

> Reproduction: scripts/test-v1-motion-stability.ps1 -FixtureRoot <generated
> two-second fixture directory>. Aggregate evidence:
> out/motion-stability/4a677f96f0904706914c170d56dd9bcb/validation.json.

> - Continuous Performance: out/soak/e253d447900140ba81f3ffe05a00e7d0/result.json.
>   720 frames, 29 cut resets, 720 inferences (360 scheduled + 15 off-cadence cuts
>   + 345 motion). Elapsed 22.660 s / 31.774 fps at 640x360 input only. This is
>   not applicable to the larger user clip or the proposed 1080p/4K targets.
> - 22 worker/process-tree samples, no observation errors or missing root
>   snapshots. Worker private bytes at first post-10s vs last differ by +8192.
>   Peak worker private bytes 1249644544; peak observed process-tree sum
>   1966559232. Short-lived children may be missed; no leak-free verdict.
> - Same-process real-GPU lifecycle: out/cleanup/repeat-vv2n3w9l/result.json.
>   All 12 scenarios pass over three cycles: success, cancel, injected inference
>   error, invalid input. Child processes/pipes and temporary artifacts are
>   checked; previous outputs survive failure. Device-global used bytes are
>   1800863744 at all 12 observations, not a per-process allocation proof.
> - Packaged cancellation: out/cleanup/package-83740666a8744e75951831a766a33602.
>   Cancellation after progress exits with code 2 at frame 3, emits no completion,
>   removes tokens/temporary outputs and preserves the seeded prior-output hash.

> Production code and user-facing quality settings were not changed in this step.
> Original inputs/results retained. Longer-duration/high-resolution runs and actual
> device-loss behavior remain open. Next work should prioritize the CPU stereo
> bottleneck, with exact parity and packaging gates before any GPU path is enabled.


<a id="record-plan-v1-1-local-motion"></a>
## v1-1-local-motion

> Recorded outcome: Implemented and packaged; natural-scene perceptual review remains open

### Results

> - 49 Python tests, process-tree tests and C++ suite pass. Small 4x4 and RGB
>   delta-8 synthetic cases now have zero stale-depth frames (previously 12/24).
>   Static still uses 12 inferences per 24 frames. Boundary positions, isolated
>   pixel noise, seeded distributed noise and uniform brightness deltas 2/4/8
>   pass their expected reuse/refresh checks. No universal noise immunity claim.
> - Eight packaged H.264/H.265 x mode cases pass. Report:
>   out/quality-fixtures/6a90bee5354946c39182fa459cb2f611/
>   validation-865ed4ab8f364747ba526985704e3148.json.
> - User Performance output: out/soak/95cadceb41e7479eb05769931240fa1a/output.mp4
>   and result.json. 124 frames and 124 inferences: 62 scheduled, 32 global-motion,
>   30 local-motion. Local is included in the 62 total extra motion inferences.
>   Elapsed 13.992 s / 8.862 fps in one packaged run, not a speedup comparison.
>   Guard mean 1.26 ms. Left-eye frame 48 was inspected; sleeve crack not apparent.
> - Matched global-only vs local+global development A/B, one warmup per variant
>   and two measured runs each: 8.0049 vs 8.2003 seconds median (+2.44%). Counts
>   94 vs 124 in both respective runs. Report:
>   out/motion-ab/358ce8d5fd1041899a0afd0925a1871a/report.json.
>   Small sample, warm development process; not comparable to packaged FPS.

> Original media and prior results preserved, portable package rebuilt. All
> full-rate modes retain their scheduling and spatial correction. The user clip
> now requires full-rate inference; no static-reuse benefit is claimed for it.

> Remaining: changes covering fewer than 16 pixels per local window, contrast at
> or below the local threshold, distributed motion failing concentration, and
> localized compression noise can still cause misses/extra work. Depth estimation
> itself may miss a small object even after inference. Next is full-motion user
> review and broader natural-video validation, not another claim of ghost removal.


<a id="record-plan-v1-1-motion-ab"></a>
## v1-1-motion-ab

Checkpoint date recorded in source: 2026-09-04.

### Results (2026-09-04)

> Report: out/motion-ab/61aab0d480e74d87aa399a82a3307534/report.json.
> The runner records source hash, dirty commit state, bundled package metadata,
> per-run policy/telemetry and output paths. All six media outputs were probed:
> 124 frames, 2112x608, 24 fps. Original source and earlier outputs are untouched.

> Two measured runs per variant after one warmup each, order off/on/on/off:
> - Off: median elapsed 7.6326 seconds, 62 inferences in both runs.
> - On: median elapsed 7.8610 seconds, 94 inferences in both runs.
> - Observed elapsed increase about 3.0%. Small sample, same development process;
>   not comparable to prior packaged-process FPS or a sustained speed claim.

> Known-depth synthetic results over 24 frames per case:
> - Static: both variants 12 inferences, zero stale-depth frames.
> - Large/fast motion: stale-depth frames decrease from 12 to 0, while inferences
>   increase from 12 to 24. Maximum wrong-depth pixels goes from 2432 to zero.
> - Small 4x4 object: still 12 stale frames, maximum 32 wrong-depth pixels.
> - Low-contrast object (RGB delta 8): still 12 stale frames, maximum 480 pixels.
> These are exact synthetic depth mismatches, not perceptual ghosting scores.

> 46 Python tests plus process-tree and C++ suite passed. Added characterization
> tests label current blind spots as limitations, not desired behavior. Production
> code and portable package were not changed in this comparison step.

> Keep the current working safeguard until a candidate improves these oracles without unacceptable unnecessary inference. Natural-video visual review remains necessary; no true depth or comfort oracle exists for the user clip.


<a id="record-plan-v1-1-motion-refresh"></a>
## v1-1-motion-refresh

> Recorded outcome: Implemented and packaged; broader perceptual validation remains open

### Evidence

> - 44 Python tests, process-tree tests and C++ suite passed. Static/noise reuse,
>   threshold boundary, cumulative change, cut/cadence priority and known-depth
>   moving-object output are covered. The moving-object oracle matches a fresh
>   renderer and differs from stale-depth rendering. No optical-flow claim.
> - Eight packaged codec/mode cases passed with exactly 48 inferences each on the
>   sustained-motion fixture. Performance accounts for 24 scheduled + 23 motion
>   + one cut inference. Report: out/quality-fixtures/
>   6a90bee5354946c39182fa459cb2f611/validation-af41853f2bdf447f99f76fc208ba93f6.json.
> - User clip Performance run: out/soak/2ac9c14aceaa4a6aad37f77005d2f2ba/result.json
>   and adjacent output.mp4. 124 frames, 94 inferences (62 scheduled + 32 motion),
>   no cuts; 30 skipped frames still reuse depth. 15.524 seconds, 7.988 fps in one
>   run, not a throughput comparison. Guard mean 1.21 ms per output frame.
> - Inspected left-eye frame 48: the corrected sleeve crack is not apparent.
>   This still sample does not establish full-motion acceptance. New output uses
>   Performance, not the earlier Balanced settings, so it is not an isolated
>   visual A/B comparison against the user's accepted Balanced clip.

> Original media and outputs retained; portable package rebuilt. Extra frame retention is bounded to one last-inferred RGB buffer. Small/low-contrast objects below the area/color threshold can still miss refresh; lighting can cause false positives.


<a id="record-plan-v1-1-motion-validation"></a>
## v1-1-motion-validation

### Results

> - Python 39 tests passed, plus 7 process-tree cases and C++ suite. New tests
>   compare both eye directions against an independent scalar visibility oracle,
>   verify textured-background bypass, known-depth fast-motion rejection across
>   all four policies, and reset equivalence at the hard cut.
> - Packaged matrix: H.264 and H.265 inputs x four modes, eight passes. Each output
>   contains 48 frames and exactly one detected cut. Performance performs 25
>   inferences (24 cadence + 1 off-cadence cut); other modes perform 48.
>   No frame incorrectly activates the uniform-background refinement.
> - Raw aggregate: out/quality-fixtures/6a90bee5354946c39182fa459cb2f611/
>   validation-103c52abb8e04b98b50f7a12b4977e27.json. Each entry links the full
>   media/environment/telemetry artifact. Inputs are 640x360, 24 fps, two seconds,
>   with a cut at frame 25 (zero-based), textured background and moving thin/body
>   geometry. There is deliberately no audio; audio preservation is not covered.
> - Production rendering was not changed in this validation step. Existing user
>   output and portable binary remain as previously validated.

### Reproduction and remaining limits

> Run scripts/test-v1.ps1 for the synthetic suite. Run scripts/test-v1-motion.ps1
> with development NumPy and a built GPU-capable portable package for fresh input
> generation and the eight-run matrix. Optional -FixtureRoot reuses generated
> inputs; each validation report gets a unique name.

> Fresh-depth temporal tests do not test skipped-frame propagation quality. Packaged media/cut counters do not prove inferred depth is correct on textured objects, nor do the short runs establish sustained throughput or leak freedom.


<a id="record-plan-v1-1-packaged-parity"></a>
## v1-1-packaged-parity

Checkpoint date recorded in source: 2026-09-04.

> Recorded outcome: Matched-package parity and short Performance comparison verified;
> historical mismatch attribution and sustained gates remain open

### Reproduction

> Build the GPU preview, then run:

> ```powershell
> python v1/compare_packaged_renderers.py --input <clip> --mode performance
> python v1/validate_packaged_comparison.py --input <clip> --report <report.json>
> ```

> The worker's explicit `--reference-cpu` option is only accepted in GPU preview;
> it is never a silent fallback. `--frame-hashes` adds three constant-memory SHA256
> accumulators and makes a run diagnostic-only. Hashes are absent in measured runs.
> The normal GUI still selects GPU in the preview and CPU in the standard package.

### Evidence (2026-09-04)

> RTX 5090, driver 616.56; user H.264 clip 1056x608, 24 fps, 124 frames, AAC.
> Report and independently checked media contracts:
> `out/packaged-comparison/f2b420a5a8c8462e909b5694eb000c8c/report.json`
> and adjacent `media-validation.json`.

> - Two diagnostic runs per renderer match decoded input, depth and pre-encode
>   SBS hashes exactly. Four diagnostics, two warmups and ten measured runs all
>   produce the same decoded RGB24 SHA256:
>   a9827ecc6a67a4fd106a99ea4422a226f0d35ca0f14ca154453f203fe31a22bc.
> - All 16 outputs pass frame count, double-width geometry, cadence and video/audio
>   duration within one frame. Every GPU run records 248 completed eye calls.
> - One warmup per renderer discarded; five measured runs each, alternating order.
>   Process-wall median CPU 13.475 s (12.287-13.758), GPU 7.353 s (6.902-7.381).
>   Ratio of process-wall medians 1.83x; time reduction about 45.4%.
>   Pipeline-reported FPS median CPU 9.379 (9.182-10.307), GPU 17.468
>   (17.404-18.652). These exclude process startup, unlike process-wall time.
> - 61 Python tests, seven process-tree checks and C++ tests pass. CPU unit/build
>   checks ran during this desktop benchmark; clocks/power and background desktop
>   work were not controlled. Treat this as a short comparative observation,
>   not an audited sustained performance or all-mode claim.

### Historical mismatch investigation

> The former CPU/GPU package output mismatch is NOT reproduced by matching
> the executable and dependencies. Model, NumPy BLAS and FFmpeg binaries match
> between old/new packages; embedded mode, stereo and depth-backend code also
> match. The old CPU package on isolated PATH and new CPU reference on normal PATH
> both produce the same current hash. Evidence:
> `out/package-environment/31c8202027744eb88f4989c05f3dec65/report.json`.
> This rules out a persistent CPU-vs-CUDA projection difference in this tested
> case, but does not identify which historical runtime state caused the earlier
> hash. Do not label it a fixed CUDA numerical bug or a proven PATH issue.

> A further old-CPU run on normal PATH also matches the current hash:
> `out/package-environment/554559f7af354c12be9502cefac7b40c/report.json`.
> The historical discrepancy is presently non-reproducible in either PATH setup.


<a id="record-plan-v1-1-stereo-ghosting"></a>
## v1-1-stereo-ghosting

Checkpoint date recorded in source: 2026-09-04.

> Balanced infers every frame; its observed extra contours are not from inference
> skipping. Hypotheses: inverse warping duplicates contours at depth boundaries;
> unaligned depth EMA adds moving-edge lag.

### Findings and changes (2026-09-04)

> - Frame 48 reproduced the detached contour in pre-encode legacy output with
>   identical inferred depth both with and without EMA. Thus encoding and EMA
>   alone do not explain the defect; inverse projection at depth boundaries is
>   sufficient to reproduce it. Balanced inference skipping was excluded by policy.
> - Forward projection with near-depth visibility removed detached duplicates in
>   the hard-edge oracle, but unrefined real depth produced smeared boundaries.
>   A broader far-background hole fill was rejected because it introduced gaps.
> - Final renderer combines forward visibility, farther-side horizontal hole
>   filling, image-guided depth and conservative uniform-backdrop refinement.
>   No specific green color is hardcoded. Border-connected flat background gets
>   constant depth; foreground component contour depth blends into interior depth.
>   This intentionally regularizes contour depth and can reduce local depth detail.
> - Temporal history is rejected around changed color/depth, and detected cuts
>   reset history and trigger extra inference. Mode policy carries thresholds;
>   telemetry reports cut counts and flat-background activation counts.
> - Historical eye direction and nominal disparity strength were retained. No
>   assurance of stereo comfort or absolute physical depth is inferred from this.

### Verification

> - Python regression suite: 29 tests; process-tree cases and C++ suite passed.
>   New oracles cover zero shift, near/far overlap, no duplicate silhouette,
>   both projection directions, row isolation, constant guided depth, backdrop
>   color independence/bypass, moving depth and scene-cut reset.
> - Rebuilt portable executable. Final Balanced output: 124 frames, 2112x608,
>   24 fps; media/resource smoke passed. All 124 frames used backdrop refinement.
> - Inspected decoded crops at 0/2/4 seconds and both eyes at 2 seconds. Large
>   detached ear/tail contours were reduced. Small boundary artifacts remain;
>   full motion/VR acceptance requires user review. This is not a universal fix.
> - Final artifact: `out/soak/b4ead39f158947bc83e915ade4efacf5/result.json` and
>   adjacent output.mp4. Source and earlier outputs were preserved.
> - CPU performance regression is material: this run took 18.988 s, 6.53 fps,
>   temporal/stereo mean 135.17 ms. Previous user-clip Balanced run was 40.62 fps.
>   These are single-run observations, not a controlled benchmark, but optimization
>   is required before claiming the previous throughput or real-time operation.
> - Packaged cancellation and one real-GPU success/cancel/inference-error/invalid
>   input cycle passed. Cleanup evidence: `out/cleanup/repeat-ev0vrl38/result.json`.

### Reproduction and follow-up

> `v1/diagnose_stereo.py --input <clip>` keeps a frozen legacy baseline and saves
> matched frame/depth evidence under out/stereo-ghost-diagnosis. Then run
> `v1/compare_projection.py` for the spatial candidate using that same sample.
> Use the development dependency/TensorRT paths documented by test-v1 scripts.
> Raw user images/depth/video stay in ignored out/, not in Git.

> Performance-mode cadence reuse between cuts still needs motion-aware validation.

### CPU optimization follow-up

> Delivered: hole-only gathers and exact float32 backdrop median representation. Spatial medians after change: guide 7.77 ms, backdrop 30.07 ms, one eye 14.28 ms. `v1/check_stereo_parity.py` passes 80 deterministic randomized cases plus real sample EMA/non-EMA depth in both eyes against fixed commit 55112b6. Decoded full-video SHA256 before and after is identical: `fe7e1e4c67946ef38b77f2dc35c6212979f1165069b033fd1e22c3e9a6599145`. New media/resource smoke: out/soak/ab6263ea15024804b3ab065a9dcabd13/result.json; 124 frames, temporal/stereo mean 107.23 ms, elapsed 15.47 seconds. Warmup 1 + measured 5 packaged Balanced conversions: out/benchmarks/v1-balanced-20260904T030026Z.json. Median 8.148 fps, range 8.129-8.175, median elapsed 15.218 seconds. The earlier 6.53 fps baseline was a single run, so the approximate 25% throughput increase is not a paired controlled comparison. Real-time throughput remains unmet. Python 31 tests pass (including empty rows and equal-depth ties); process-tree 7 cases and C++ tests passed. Portable package rebuilt.


<a id="record-plan-letterbox-opt-in"></a>
## letterbox-opt-in

Checkpoint date recorded in source: 2026-09-05.

### Verification and limits

> Implemented `depthsbs_app.padding.PaddingRefiner`, per-job policy, GUI checkbox,
> CLI `--letterbox-refinement` and launcher `-LetterboxRefinement`. Default is off.
> Only region/streak state is retained, not frame history. Three consecutive
> eligible identical regions activate correction; changed bounds, captions or
> failed eligibility disable it immediately. Scene cuts clear confirmation.
> The first two eligible frames and bypass frames retain existing behavior;
> padding restoration only occurs on active frames.

> - Canonical gate: 105 Python tests, seven process-tree cases and C++ CTest pass.
>   Real Tk GUI checks cover default-off and worker flag propagation.
> - Actual 1080p VDA conversion: all 124 frames decode with audio; two warmup,
>   122 applied/restored frames. Frame-62 hand crops retain the visible improvement.
>   Cancellation and injected failure after activation preserve prior output and
>   close media processes. Report and output:
>   `out/vda-application/2a53d095e310411d9392e054d80766c8/`.
> - The 48-frame HEVC cut case passes execution/reset, but correction applies to
>   zero frames (one warmup, 47 bypass); this is not HEVC correction-quality evidence.
> - Real launcher with the short upscaled 4K HEVC fixture passes 12-frame conversion
>   and flag propagation, but all 12 frames bypass correction. Evidence:
>   `out/letterbox-option/9b0a8929cac64a27bd7c3292ec71b5e2/`.
>   Compressed/ambiguous borders may fail strict eligibility; no thresholds were
>   relaxed. These fixtures do not certify native-4K quality or performance.

> No default promotion, portable rebuild, release, commit or push. General natural
> content, moving-edge quality, GPU-preview projection with this option and VR
> acceptance remain unverified; one-hour soak/VR remain deferred by request.


<a id="record-reference-processing-modes"></a>
## processing-modes

Checkpoint date recorded in source: 2026-09-05.

### Implemented Python V1 motion safeguard (2026-09-04)

> | Mode | Primary promise | Initial depth backend | Temporal policy | Frame-rate intent |
> |---|---|---|---|---|
> | Performance | Lowest latency and highest throughput | DA2 Small TensorRT FP16 | Full-rate first; propagation may be added only if it improves measured throughput without visible instability | 1080p/4K, 60–120 fps exploration |
> | Balanced | Practical default with stronger spatial depth | DA2 Base TensorRT FP16 | Full-rate baseline; adaptive 1:2 inference is an experiment | End-to-end 60 fps target where hardware allows |
> | Video Quality | Stable depth over time with low flicker | oVDA Small TensorRT candidate | Stateful online temporal inference; cut-aware cache reset | 60 fps goal, 30–60 fps acceptable test range |
> | Offline Quality | Best available SBS quality without realtime guarantee | VDA, DA3 Mono, or later validated backend | Model-native temporal processing or high-quality inference plus propagation | No realtime guarantee; quality first |

> These model assignments come from the project discussion and are starting
> hypotheses. Backend availability, conversion correctness, licenses, and complete
> pipeline measurements must be verified before a mode is called supported.
