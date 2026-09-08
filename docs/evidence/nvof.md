# NVOF temporal experiments

Historical evidence by recorded checkpoint. Current support is in
[implementation status](../implementation-status.md).

## Records

- [ovda-nvof-actual-skip-2026-09-07](#record-result-ovda-nvof-actual-skip-2026-09-07)
- [ovda-nvof-temporal-2026-09-06](#record-result-ovda-nvof-temporal-2026-09-06)
- [ovda-nvof-temporal](#record-plan-ovda-nvof-temporal)

<a id="record-result-ovda-nvof-actual-skip-2026-09-07"></a>
## ovda-nvof-actual-skip-2026-09-07

Checkpoint date recorded in source: 2026-09-07.

> Status: Fixed 1:2 cadence rejected; P0-1 full-playback review still open
> Owner: DepthSBS
> Date: 2026-09-07

### Question and protocol

> The earlier cadence study inferred oVDA on every frame, then substituted warped
> depth on odd candidate frames. This follow-up answers two missing questions:

> 1. what happens when the candidate recurrent engine actually omits every odd
>    inference; and
> 2. whether continuous post history, reset-before-fresh history, or separate
>    fresh/warped histories explains or repairs the output error.

> `v1/evaluate_ovda_nvof_actual_skip.py` uses independent full-rate reference and
> 1:2 candidate engines. Each 60-frame clip produces 60 reference and 30 candidate
> inferences. The candidate seeds NVOF from its own even-frame depth and warps it
> on the following odd frame. The same raw diagnostic depth is rendered through:

> - the earlier all-infer scheduled path;
> - actual-skip continuous history;
> - actual-skip history reset before each fresh frame after a warp;
> - actual-skip fresh/warped source histories;
> - actual-skip unwarped held depth with continuous history.

> The run reuses the fixed-cadence numerical output gates. Diagnostic depth
> readbacks and host post uploads are deliberate and are not runtime-performance
> evidence. Promotion requires exact 60/30 inference counts, ownership cleanup,
> valid coverage, NVOF warped depth no worse than held depth, and at least one
> actual-skip history path passing every output gate on every clip.

### Result

> The valid artifact is `out/ovda-nvof-actual-skip/current-v2/report.json`.
> All three review videos contain and decode exactly 60 frames at 1280x1080. Both
> engines closed without a pending depth token. The harness and media checks pass,
> but the candidate promotion gate fails.

> | Clip | Reference / candidate inferences | Fresh recurrent depth MAE | NVOF / held depth MAE | Continuous output gate | Reset / dual output gate |
> | --- | ---: | ---: | ---: | --- | --- |
> | OfficeWalk | 60 / 30 | 0.006795 | 0.954 | Fail | Fail / Fail |
> | FloorballGame | 60 / 30 | 0.003666 | 0.927 | Pass | Pass / Pass |
> | ParkingGarage | 60 / 30 | 0.002441 | 1.133 | Fail | Fail / Fail |

> Actual skipping changes later fresh depth: maximum fresh-frame normalized-depth
> MAE is `0.009687`, `0.007595`, and `0.007899` respectively. This is the recurrent
> cache effect that the earlier all-infer study could not measure.

> History separation is not a general repair. OfficeWalk mean SBS MAE changes from
> `0.008960` continuous to `0.016977` reset-before-fresh and `0.017250` dual-source.
> ParkingGarage changes from `0.003139` to `0.003292` and `0.004262`. FloorballGame
> passes all three paths, but that single clip cannot promote the policy.

> The unwarped held-depth path passes every output gate for ParkingGarage with mean
> SBS MAE `0.001835`; NVOF is worse than hold there at the depth level as well.
> OfficeWalk fails even with held depth. Therefore a larger confidence kernel does
> not address the demonstrated combination of recurrent-cache drift and scene-
> dependent projection error under a fixed 1:2 schedule.

> Six worst warped-frame stills and the largest fresh history-difference frame from
> each clip were inspected at stored resolution. No gross black hole or eye-order
> inversion was found. OfficeWalk's dual-source fresh frame 32 visibly changes
> object parallax/framing relative to the reference and continuous path. Still
> inspection does not establish temporal smoothness or headset comfort, but the
> automated rejection does not require those remaining reviews.

> The three review videos were decoded completely to verify their 60-frame media integrity, but they have not yet received continuous full-motion playback review.

> `current-v1` is retained as a harness diagnostic only. It used container frame
> metadata without decoding every review frame; `current-v2` added full decode
> verification before becoming the accepted result.

### Decision

> The fixed 1:2 NVOF depth cadence was rejected; its confidence/fallback policy and application scheduler were not pursued.

> The independent DLSSG capability, provenance, license, and input-contract spike subsequently completed and rejected its current adapter. Asynchronous integration remains gated on a candidate that first passes quality.

### Verification

> - `v1/tests/test_ovda_nvof_actual_skip.py`: cadence, reset, and missing-media
>   rejection tests pass;
> - three 60-frame public clips: exact 60/30 inference counts and 50% candidate
>   inference reduction;
> - three review videos: container and decoded frame counts both 60;
> - nine hashed worst-frame stills retained in the report;
> - `scheduler_authorized=false` and
>   `candidate_retained_for_confidence_experiment=false` in the accepted report.


<a id="record-result-ovda-nvof-temporal-2026-09-06"></a>
## ovda-nvof-temporal-2026-09-06

Checkpoint date recorded in source: 2026-09-07.

> Status: Device-resident component accepted; fixed 1:2 cadence rejected.
> Owner: DepthSBS. Updated: 2026-09-07.

### Decision

> NVIDIA Optical Flow is a useful motion source for aligning the previous oVDA
> depth map to the current RGB frame on the tested RTX 5090. Proceed with an
> isolated device-resident warp experiment. Do not yet skip oVDA inference, change
> any processing-mode cadence, select a new live DLL, or claim a live frame-rate
> or VR-quality improvement.

> The accepted evidence is `out/ovda-nvof/final-clean/report.json`. It is a
> host-input diagnostic: RGB packing and upload, the NVOF calculation plus coarse
> flow readback, and CPU validation/warp are all still present.

### Implementation boundary

> The working probe uses NVIDIA's official public CUDA Optical Flow headers at
> API version 2.0. It creates one CUDA NVOF session, two fixed input buffers, one
> 2x2-grid `SHORT2` output buffer, and distinct input/output streams. Buffer
> dimensions, pitch, owner thread, RTX 5090 identity, reset state, and output
> shape are checked. Flow is S10.5 and is divided by 32 before nearest-cell
> expansion.

> The earlier D3D11 probe copied the hand-written ABI bridge from the local DLSS
> experiment. Session initialization and resource registration succeeded, but the
> installed driver rejected the first `nvOFExecute` with `0x80004005`. That route
> is rejected; the product must not depend on its manually reconstructed function
> table or structures.

### Direction gate

> A deterministic 640x360 textured image translated eight pixels to the right
> verified the required current-to-previous convention:

> - median flow: `dx=-8.0`, `dy=0.0` pixels;
> - warped RGB MAE: `0.01193`;
> - unwarped RGB MAE: `19.77372`.

> This prevents a sign error from making the temporal proxy appear favorable.

### Public-footage result

> Each clip contributed 60 oVDA c16 FP32 depth maps. Eight named frame pairs per
> clip were evaluated with in-bounds, forward/backward-consistency, photometric,
> and erosion masks. Ratios below 1 mean that NVOF-warped previous depth was
> closer to the current independently inferred depth than the same previous depth
> at fixed coordinates.

> | Clip | Valid pixels | Depth MAE ratio | Edge MAE ratio | Median NVOF + readback |
> | --- | ---: | ---: | ---: | ---: |
> | OfficeWalk | 0.7411 | 0.8139 | 0.8107 | 1.343 ms |
> | FloorballGame | 0.8726 | 0.5941 | 0.4160 | 1.609 ms |
> | ParkingGarage | 0.9868 | 0.9824 | 0.9748 | 1.596 ms |

> All three passed the predeclared `valid >= 0.20`, global ratio `<= 1`, and edge
> ratio `<= 1` gate. ParkingGarage has near-zero median motion and therefore
> mainly establishes non-regression on a quiet sequence. The host Python call
> median was 3.933-4.170 ms; it includes RGB packing, upload, flow readback, and
> wrapper overhead and is not a projected live cost.

> Premiere Pro and ComfyUI held GPU contexts during the final cleanup snapshot,
> so the timing figures are diagnostic observations rather than an idle-GPU
> benchmark. The quality ratios reproduced exactly across the two CUDA runs.

### Provenance and limits

> The tested DLL SHA256 and both NVIDIA header SHA256 values are embedded in the
> report through `out/nvof-probe/build-manifest.json`. The three media hashes are
> also recorded per clip. The source-depth target is another model prediction,
> not ground-truth geometry, so this establishes temporal alignment only.

> No evidence here establishes occlusion quality outside the retained masks,
> scene-cut classification, propagation over multiple frames, perceptual depth
> stability, SBS geometry, live latency, 60-fps output, long-run cleanup, or VR
> comfort. The diagnostic also does not remove host RGB input or synchronize with
> the oVDA TensorRT stream.

> The final native build, analytic direction test, three-clip run, three new math
> tests, scoped Ruff format/lint, whitespace check, and the full 211-test Python
> unit suite passed. No probe process or NVOF context remained after completion.

### Device-resident warp result

> The follow-up DLL retains NVOF's 2x2 S10.5 flow and two source-resolution
> float32 depth buffers on CUDA. A CUDA event orders the fresh oVDA device-depth
> seed from its producer stream. Each warp produces one pointer/stream/generation
> token; reuse before completion, use after completion, foreign-thread access,
> and a pending token after close are rejected. The existing CUDA post/SBS context
> borrows the exact NVOF output stream.

> Evidence is `out/ovda-nvof-device-warp/current-v2/report.json`. The analytic
> translation retained `dx=-8`, matched the validity mask exactly, and differed
> from an independent float32 bilinear oracle by at most `1.19e-7`. The
> no-diagnostic chained path completed with zero readback bytes.

> Across eight named pairs from each of OfficeWalk, FloorballGame, and
> ParkingGarage:

> | Result | OfficeWalk | FloorballGame | ParkingGarage |
> | --- | ---: | ---: | ---: |
> | Maximum warp error | 1.91e-6 | 1.91e-6 | 1.91e-6 |
> | Exact CUDA SBS pairs | 8/8 | 8/8 | 8/8 |
> | Runtime stages excluding diagnostic readback | 3.176 ms | 3.120 ms | 2.996 ms |
> | CUDA post + host SBS readback | 3.868 ms | 3.847 ms | 3.833 ms |

> The runtime-stage figure contains host RGB packing/upload, NVOF, and the CUDA
> warp. Each diagnostic pair additionally copied 12,441,600 bytes of flow, depth,
> and validity data for the oracle; those bytes are absent from the proposed
> runtime path. The result proves the component boundary and pixel behavior, not
> concurrent inference/presentation throughput.

> The full 214-test Python suite, six focused NVOF math tests, scoped Ruff checks,
> and whitespace checks pass after this extension. The tested warp DLL SHA256 is
> `09ca4e5c1445f34157f6c1c775526586bd4b41a79f0652ec20ca1e9a72178f63`.

### Follow-up gate

> The next experiment evaluates a fixed 1:2 presentation cadence: even frames use
> fresh oVDA depth and odd frames use the accepted NVOF-warped prior depth. It must
> force fresh depth on cuts, compare all 60 frames against full-rate oVDA, inspect
> motion/thin-edge stills and temporal sequences, and report fresh/warped frame
> identity. Only that quality study may justify an asynchronous live scheduler;
> it still cannot establish VR comfort without headset review.

### Fixed 1:2 cadence result

> `out/ovda-nvof-cadence/current-v3/report.json` is the valid 180-frame result. The
> harness inferred recurrent oVDA on every frame for the full-rate reference, copied
> fresh device depth on 90 even frames, warped the immediately prior fresh depth on
> 90 odd frames, and kept separate continuous CUDA post/SBS histories. All fresh
> copies were exact, all review media decoded with the expected dimensions and 60
> frames, and every engine/device token completed. This is a quality run and reports
> no inference saving or live throughput.

> | Result | OfficeWalk | FloorballGame | ParkingGarage |
> | --- | ---: | ---: | ---: |
> | Minimum NVOF valid fraction | 0.9812 | 0.9862 | 0.9955 |
> | Warped/fixed normalized-depth MAE | 1.366 | 0.909 | 2.375 |
> | Mean SBS MAE (0-1) | 0.00801 | 0.00056 | 0.00212 |
> | P95 frame SBS MAE (0-1) | 0.01741 | 0.00098 | 0.00348 |
> | Mean reference-edge SBS MAE (0-1) | 0.01682 | 0.00221 | 0.00346 |
> | Channels over 8 levels | 0.0544 | 0.0030 | 0.0175 |
> | P95 temporal-change error | 0.00039 | 0.00005 | 0.00251 |
> | Automated quality result | Fail | Pass | Fail |

> The nine worst-frame PNGs were inspected at stored resolution. FloorballGame and
> ParkingGarage are visually close in those still views; OfficeWalk shows shifted
> parallax placement around furniture and high-contrast object boundaries. No gross
> hole, eye-order inversion, or large tear was found in the stills, but stills do not
> clear pumping or headset comfort. Continuous history also preserves some error on
> fresh frames after a warped frame, so merely alternating fresh and warped depth is
> not self-correcting at the output boundary.

> The fixed cadence is rejected and the application scheduler remains unchanged.
> The bounded follow-up is device-side confidence/fallback and history isolation,
> not asynchronous scheduling. `current-v1` and `current-v2` are retained only as
> diagnostic failures: the CPU reference readback did not wait for the oVDA producer
> stream, while the device-to-device candidate path did.


<a id="record-plan-ovda-nvof-temporal"></a>
## ovda-nvof-temporal

Checkpoint date recorded in source: 2026-09-06.

> Recorded outcome: 1:2 cadence rejected; full-playback review remains the active P0-1 item.
> Owner: DepthSBS. Date: 2026-09-06.

### Acceptance and decision

> The spike passes only if flow direction is analytically verified, all resources
> close cleanly, public clips retain useful valid coverage, and warped previous
> depth is not worse than unwarped depth on the named proxy. A favorable result
> authorizes a second, device-resident CUDA warp prototype; it does not
> authorize inference skipping, backend promotion or a 60-fps claim.

> Verification: native build manifest and DLL hash, analytic translation test,
> three public clips with per-frame bounded records, NVOF reset/recreate cycle,
> scoped lint/unit tests and the repository unit suite. Record rejected cases and
> remaining forward/backward confidence, occlusion, cut, latency, soak and VR gates.

### Result

> The official-header CUDA probe passed the analytic direction gate and all three
> public-clip gates. Global warped/fixed depth-MAE ratios were `0.8139`, `0.5941`,
> and `0.9824`; edge ratios were `0.8107`, `0.4160`, and `0.9748`. The accepted
> artifact is `out/ovda-nvof/final-clean/report.json`; the owning result document is
> [nvof.md](nvof.md#record-result-ovda-nvof-temporal-2026-09-06).
> The full 211-test Python suite and scoped Ruff checks pass. Final timing is not
> an idle-GPU benchmark because other user applications held GPU contexts.

### Device-warp result

> `out/ovda-nvof-device-warp/current-v2/report.json` passes. The analytic maximum
> error is `1.19e-7`; all three public clips have exact validity, maximum warp
> error `1.91e-6`, and exact SBS for all 24 named pairs. Median host-RGB packing,
> upload, NVOF, and CUDA warp cost is `2.996-3.176 ms` with diagnostic readback
> excluded. Early reuse, expired token, foreign thread, repeated reseed, chained
> no-readback operation, and pending-close cleanup pass. The repository unit suite
> passes 214 tests.

> The next bounded milestone is a full 60-frame 1:2 cadence quality evaluation.
> Generate full-rate fresh oVDA as the reference, use fresh device depth on even
> frames and device-warped depth on odd frames, force fresh depth at cuts, retain
> frame-source identity, and render reviewable paired outputs. Do not modify the
> application scheduler until numerical, temporal, and visual gates are recorded.

### 1:2 cadence result

> The valid run is `out/ovda-nvof-cadence/current-v3/report.json`. It completed all
> 180 frames, produced and decoded three 1920x1080/60-frame H.264 review videos,
> preserved nine hashed worst-frame PNGs, matched all 90 fresh device-depth copies
> exactly, kept NVOF valid coverage above `0.981`, and closed all owned tokens.
> No public clip contained a detected cut in this 60-frame interval; the pure
> schedule regression proves that an odd cut becomes `cut-fresh` and the following
> warp can only source post-cut depth.

> Only FloorballGame passed every automated quality limit. OfficeWalk failed five:
> warped/fixed depth-MAE ratio `1.366`, mean SBS MAE `0.00801`, P95 frame SBS MAE
> `0.01741`, mean edge SBS MAE `0.01682`, and channels over 8 levels `0.0544`.
> ParkingGarage met every output and temporal budget but failed the relative depth
> gate: NVOF warp was `2.375x` the error of holding the prior depth. Its absolute
> warped depth MAE remained small (`0.00187`). FloorballGame's ratio was `0.909`.

> All nine selected stills were inspected at their stored resolution. They show no
> obvious black holes, eye-order inversion, or gross edge tearing in the 2x2 views;
> OfficeWalk nevertheless has visible reference/candidate parallax-position changes
> around high-contrast furniture and object edges. Still inspection cannot clear
> temporal pumping or VR comfort, so video/headset review remains unpassed. The raw
> rows also show that continuous post history carries candidate differences onto
> subsequent fresh frames: mean fresh/warped SBS MAE is `0.00575/0.01027` for
> OfficeWalk, `0.00025/0.00087` for FloorballGame, and `0.00088/0.00336` for
> ParkingGarage.

> The scheduler is not authorized. The smallest next experiment is not asynchronous
> integration: add forward/backward plus photometric confidence to the device warp,
> replace rejected/invalid warped pixels from a bounded fallback, and explicitly
> prevent warped-frame history from contaminating the next fresh frame. The failed
> `current-v1` and `current-v2` runs are retained as harness diagnostics only; their
> unsynchronized CPU reference readback made fresh-depth comparisons invalid.

> DLSSG frame interpolation does not change this result. It is tracked as a
> separate post-SBS presentation/export experiment whose generated frames may not
> enter oVDA, depth-warp, or post-depth history. The capability/license spike,
> held-out odd-frame test, comparison candidates, and ordered follow-up tasks are
> defined in
> [`dlssg-frame-interpolation-review-2026-09-07.md`](frame-generation.md#record-result-dlssg-frame-interpolation-review-2026-09-07).

### Priority revision and actual-skip gate

> The next work is reordered after reviewing the failed cadence evidence. The
> existing harness advances one recurrent oVDA engine on every frame, so it cannot
> show what happens to oVDA cache state when inference is actually omitted. It also
> uses one continuous candidate post history, which combines current warped-frame
> error with error carried into later fresh frames.

> Proceed in these independently falsifiable slices:

> 1. Add an isolated diagnostic with separate full-rate reference and 1:2
>    candidate engines. The candidate must call oVDA only on even and cut frames;
>    record exact inference counts and compare every later fresh candidate depth
>    against the same-frame full-rate reference.
> 2. From the same candidate depths, render continuous history, reset-before-fresh
>    history, reset-every-frame history, and an unwarped held-depth baseline. This
>    is a quality attribution run; host diagnostic copies are allowed and timed
>    separately from any proposed runtime path.
> 3. Reject further fixed-cadence NVOF work if actual skipping causes material
>    recurrent-depth drift that post-history isolation cannot address, or if NVOF
>    does not beat the held-depth baseline on the predeclared corpus. Otherwise,
>    select the smallest confidence/fallback/history combination for device-side
>    implementation and rerun the 180-frame plus explicit-cut quality gate.
> 4. Keep DLSSG capability/input-contract research independent and begin its
>    adapter only after the short prerequisite spike establishes a supported,
>    reproducible integration boundary.

> No application scheduler or mode policy changes are authorized by this gate.

### Actual-skip and history result

> `out/ovda-nvof-actual-skip/current-v2/report.json` is the accepted follow-up.
> Each clip completed exactly 60 reference and 30 candidate oVDA inferences, and
> all three 60-frame review videos decoded completely. Actual skipping produced
> nonzero same-frame fresh recurrent-depth error on every clip. Only FloorballGame
> passed an actual-skip output gate. OfficeWalk failed every history policy, while
> ParkingGarage failed every warped policy and passed the continuous held-depth
> baseline. NVOF/held normalized-depth ratios were `0.954`, `0.927`, and `1.133`.

> Reset-before-fresh and dual fresh/warped histories increased error on OfficeWalk
> and ParkingGarage, so history isolation is not the missing general repair. The
> fixed 1:2 candidate is rejected and its device confidence/fallback implementation
> is cancelled under the predeclared stop rule. Adaptive reuse now requires a new
> proposal with a cheap difficulty predictor and measured realized inference
> savings. The owning result document is
> [`ovda-nvof-actual-skip-2026-09-07.md`](nvof.md#record-result-ovda-nvof-actual-skip-2026-09-07).

> The later DLSSG capability/provenance/license and input-contract spike completed
> and rejected its current adapter, but P0-1 was only partially closed. History
> attribution and full media decoding are complete; continuous playback review of
> the three review videos is not. That review is the next active item. P0-3 closed
> at its hold/history stop rule, so no confidence/fallback GPU expansion or fixed-
> cadence P1 rerun is authorized. The application scheduler remains unchanged.
