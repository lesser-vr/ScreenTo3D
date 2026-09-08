# Frame-generation feasibility

Historical evidence by recorded checkpoint. Current support is in
[implementation status](../implementation-status.md).

## Records

- [dlssg-feasibility-2026-09-07](#record-result-dlssg-feasibility-2026-09-07)
- [dlssg-frame-interpolation-review-2026-09-07](#record-result-dlssg-frame-interpolation-review-2026-09-07)

<a id="record-result-dlssg-feasibility-2026-09-07"></a>
## dlssg-feasibility-2026-09-07

Checkpoint date recorded in source: 2026-09-07.

> Status: **Rejected for the current post-SBS boundary**
> Owner: DepthSBS
> Date: 2026-09-07

### Decision

> Do not implement FG-03 through FG-06 against NVIDIA Streamline DLSS Frame
> Generation in the current application. This is a rejection of the proposed
> adapter, not a claim that DLSSG is defective or unusable in a game renderer.

> The current boundary cannot satisfy the documented contract without inventing
> engine data that DepthSBS does not own. It publishes a completed full-SBS RGBA
> image through D3D11/Qt. It does not own the D3D12 or Vulkan swap chain expected
> by Streamline, per-eye camera-space depth and matching engine motion vectors,
> camera matrices/jitter, or Streamline Reflex present markers. The available
> NVOF result is image-space optical flow between captured video frames; it is not
> evidence for the camera/dynamic-object motion-vector contract. The oVDA result
> is normalized monocular relative depth used to synthesize the SBS image; it is
> not the same depth surface used to render corresponding motion vectors.

> Moving the final texture to D3D12 would address only the graphics-API mismatch.
> It would not create truthful camera state or matching per-eye depth/motion data.
> Identity matrices, repackaged NVOF, or fabricated near/far planes are therefore
> not accepted as a capability probe or minimal adapter.

> Reconsider only if one of these conditions becomes true:

> - NVIDIA documents and licenses a standalone video/frame-interpolation API
>   whose required inputs DepthSBS can produce from decoded or captured video; or
> - DepthSBS gains an owned D3D12/Vulkan presentation renderer and a documented,
>   validated mapping from its video/depth/flow products to every DLSSG resource
>   and constant, including per-eye binocular consistency.

### FG-01 environment, provenance, and license result

> The local, read-only environment probe is recorded in
> `out/dlssg-feasibility/report.json`.

> - Windows is build 26200.9168 and the selected device is an RTX 5090 on driver
>   616.64, so the observed OS is above Streamline 2.12's build-19041 minimum.
> - `dxdiag` reports the RTX 5090 hardware scheduler as supported but
>   `Enabled:False`; `HwSchMode=1` is consistent with that direct observation.
>   DLSSG requires hardware-accelerated GPU scheduling enabled. Changing this
>   machine-wide setting and restarting Windows were outside this experiment.
> - No `sl.interposer.dll` or `sl.dlss_g.dll` was found in the searched NVIDIA
>   installation roots or local ChatGPT project roots. No official SDK package
>   was downloaded, no license was implicitly accepted, and
>   `slIsFeatureSupported` was not called. The result is an environment
>   prerequisite failure, not a completed SDK capability probe.
> - The reviewed public Streamline integration source is permissively licensed,
>   but the proprietary DLSS/NGX feature components have separate NVIDIA RTX SDK
>   terms. Those terms include object-code distribution conditions, NVIDIA-GPU
>   interoperability restrictions, notice/mark requirements, and notification
>   before commercial release. A release must retain the exact license from the
>   official package and receive a specific legal/redistribution review.
> - The local ComfyUI worker remains opaque prior art. Its unpublished worker and
>   copied binaries are neither a reproducible implementation nor an authorized
>   redistribution source.

> NVIDIA's 2.12 guide lists an RTX 5090 planning figure of 1.07 ms and 272 MB at
> 1080p 2x. These are vendor estimates from an in-game integration, not a local
> DepthSBS measurement and not a reason to bypass the failed prerequisites.

### FG-02 contract map

> | Streamline DLSSG contract | Current DepthSBS producer | Gap and disposition |
> | --- | --- | --- |
> | Initialize before D3D12/Vulkan and attach to the presented swap chain | Qt Quick is explicitly forced to D3D11; Qt owns presentation | **Unavailable.** A new owned presenter is required. |
> | Backbuffer intercepted at present | Full-SBS RGBA is copied from a two-slot D3D11 shared texture into a private Qt D3D11 texture | **Unavailable at the required API boundary.** The published texture is not a Streamline-managed D3D12/Vulkan backbuffer. |
> | Depth matching the motion-vector/rendering convention | Normalized monocular oVDA depth drives a 2D splat before the completed SBS texture is published | **Semantically mismatched.** No per-eye renderer depth surface or declared camera near/far mapping exists. |
> | Dense motion vectors including camera and dynamic-object motion | Optional NVOF image-space flow was tested for depth reuse | **Semantically unproven.** It is not per-eye engine motion and the fixed-cadence candidate already failed its quality stop rule. |
> | Per-frame camera matrices, jitter, projection flags, and reset | Captured/decoded 2D video has no source camera state; DepthSBS has scene-cut/reset policy | **Mostly unavailable.** Reset is reusable; camera constants cannot be reconstructed truthfully. |
> | Common constants and a frame index matching presentation | Texture mailbox carries session, generation, sequence, source time, and callback time | **Partial.** Source identity exists, but there is no Streamline frame token or matching Reflex present-marker integration. |
> | Reflex integration with present-start/end markers | No Streamline Reflex host integration | **Unavailable.** Required integration would belong to a new presenter. |
> | HUD-less color and UI alpha/color for best quality | The SBS image exists before QML composition; Qt owns any scene/UI composition | **Partial but inaccessible at present interception.** UI separation would need a new renderer contract. |
> | Turn off for non-game frames and before window/size transitions; recreate swap chain on mode changes | Live source-loss, resize, generation, and cut resets are bounded | **Policy signal exists; swap-chain ownership does not.** Cannot implement the required lifecycle on Qt's current D3D11 chain. |
> | Resources remain valid through present with deterministic cleanup | Two slots, keyed mutexes, generation checks, and completed-copy acknowledgement are implemented | **Reusable design principle only.** Resource types and present ownership do not satisfy Streamline. |
> | HAGS enabled and supported GPU/driver | RTX 5090/616.64; HAGS directly reported disabled | **Current environment failure.** Enabling it would not cure the input-contract failures. |

### Failed and deliberately skipped paths

> - **Current-machine feature probe:** not runnable because the official feature
>   binaries are absent and HAGS is disabled. This is recorded as not executed,
>   never as unsupported hardware.
> - **Reuse the ComfyUI worker:** rejected because its worker source is absent,
>   its external-depth behavior is undocumented, and its binary provenance is not
>   a DepthSBS build path.
> - **Wrap the existing D3D11 SBS texture:** rejected because Streamline reports
>   D3D12/Vulkan support flags and requires present-time resources/constants that
>   this texture does not carry.
> - **Fabricate game-renderer inputs from NVOF/oVDA:** rejected because it would
>   silently promote unvalidated conventions into an SDK contract and could
>   produce binocularly inconsistent frames.
> - **Download/build an adapter anyway:** skipped under the predeclared promotion
>   rule. Both the environment and input-contract gates fail before implementation.

### Queue consequence

> FG-01 and FG-02 are complete with a rejection. FG-03 through FG-06 are cancelled
> for this Streamline/post-SBS proposal. BI-01 remains a file-only research idea,
> but is not promoted merely because two higher-risk candidates failed. The next
> active item is the unfinished P0-1 continuous playback review of the existing
> NVOF review videos. Only after it closes should the P2 bidirectional-depth
> investment decision be made. Representative live validation, frame-identity
> latency attribution, and native WGC input sharing remain in the broader backlog.

### Sources

> - [NVIDIA Streamline 2.12 DLSSG programming guide](https://github.com/NVIDIA-RTX/Streamline/blob/main/docs/ProgrammingGuideDLSS_G.md)
> - [NVIDIA Streamline general programming guide](https://github.com/NVIDIA-RTX/Streamline/blob/main/docs/ProgrammingGuide.md)
> - [NVIDIA RTX SDK license](https://github.com/NVIDIA/DLSS/blob/main/LICENSE.txt)
> - [NVIDIA Streamline license](https://github.com/NVIDIA-RTX/Streamline/blob/main/license.txt)


<a id="record-result-dlssg-frame-interpolation-review-2026-09-07"></a>
## dlssg-frame-interpolation-review-2026-09-07

Checkpoint date recorded in source: 2026-09-07.

> Status: FG-01/FG-02 complete; P0-1 full-playback review remains active
> Owner: DepthSBS
> Date: 2026-09-07

### Decision summary

> Evaluate DLSS Frame Generation (DLSSG) as an isolated **post-SBS RGB frame-
> interpolation** candidate. Do not treat it as evidence that oVDA depth can be
> inferred less often, do not feed generated frames back into oVDA or temporal
> depth history, and do not add it to the application until capability,
> provenance, license, quality, latency, and lifecycle gates pass.

> The reviewed ComfyUI integration is useful prior art for exact output time grids,
> runtime capability probes, reset behavior, diagnostics, and preservation of
> container streams. It is not a reusable proof of real-time performance or of
> DepthSBS stereo quality. Its public Python side estimates motion with OpenCV DIS
> at a reduced width and sends full-resolution float16 motion to a separate D3D12
> worker. The worker source is not published in the reviewed repository, and the
> public interface has no external-depth input. The reported RTX 4060 Ti example
> is an offline 5-second 1024x640 24-to-120 fps cascade that took 153.747 seconds.

> Reviewed sources:

> - [ComfyUI NVIDIA DLSS Frame Interpolation repository](https://github.com/Konohamaru04/ComfyUI-NVIDIA-DLSS-Frame-Interpolation),
>   pinned for this review at commit `c755e274a405a7a47667bd567d489b6845066bcf`;
> - [NVIDIA Streamline DLSSG programming guide](https://github.com/NVIDIAGameWorks/Streamline/blob/main/docs/ProgrammingGuideDLSS_G.md);
> - [source discussion](https://www.reddit.com/r/StableDiffusion/comments/1w7db7b/nvidia_dlss_5_frame_interpolation/),
>   used only to discover the implementation, not as acceptance evidence.

### Applicable integration boundary

> The only selected initial boundary is:

> `fresh RGB -> fresh depth -> SBS projection -> per-eye DLSSG -> presentation/export`

> Left and right eyes use the same source timestamps, interpolation factors, cut
> resets, and frame identities, but are evaluated independently. Generated SBS/RGB
> must never become an oVDA cache input, depth-warp source, or post-depth history
> input. Metrics must report fresh depth inference rate and generated presentation
> rate separately; generated FPS is not inference FPS.

> An engine integration is expected to supply the backbuffer, motion vectors,
> depth, per-frame camera/constants, frame identity, and any required UI/HUD masks
> according to the SDK contract. Whether DepthSBS can provide sufficient inputs at
> the selected boundary is an experiment, not an assumption. Vendor cost examples
> are planning hints only and cannot replace an end-to-end measurement on the
> target pipeline.

### P0 — explain the failed depth-reuse result

> 1. **OF-00 history and baseline attribution.** Using identical candidate depth
>    inputs, compare continuous post history, reset-before-fresh history,
>    reset-every-frame history, and unwarped held depth. Review the existing full
>    videos and retain per-frame attribution so a fresh-frame error is not
>    mistaken for a current warp error.
> 2. **OF-01 actual inference skip.** Use separate recurrent engines for the
>    full-rate reference and the candidate. The candidate calls oVDA only on even
>    and cut frames. Record inference counts and same-frame fresh-depth drift so
>    the cache consequence of a real 1:2 schedule is measured.
> 3. **OF-02 smallest policy falsifier.** Before expanding GPU kernels, compare
>    NVOF warp against held depth and small host-oracle confidence/fallback
>    policies on the same frames. Stop fixed-cadence work if warp cannot beat the
>    baseline or recurrent drift dominates the result.

### P1 — conditional implementation; cancelled for fixed 1:2

> 4. **OF-03 device confidence and fallback.** If OF-00/01/02 retain the candidate,
>    implement the selected forward/backward, photometric, in-bounds, erosion, and
>    bounded fallback policy on-device. Compare the exact mask/output with an
>    independent host oracle and attribute every transfer.
> 5. **OF-04 history policy.** Implement the selected reset, dual-history, or
>    source-tagged update rule and prove that warped output cannot alter the next
>    fresh reference result beyond its declared semantics.
> 6. **OF-05 quality and savings rerun.** Rerun the 180-frame corpus plus an
>    explicit cut fixture. Report actual inference count and added NVOF/policy
>    cost alongside paired media and numerical gates. Only a pass can authorize
>    scheduler work.

### P1 — DLSSG feasibility, complete with rejection

> 7. **FG-01 capability, provenance, and license spike.** Inventory the exact
>    NVIDIA SDK/runtime, signed binaries, driver/GPU/HAGS requirements, permitted
>    redistribution, commercial-notification obligations, and source/build
>    reproducibility. Run only a local capability probe.
> 8. **FG-02 input-contract map.** Map required resources and constants to owned
>    DepthSBS producers: motion-vector/depth conventions, camera matrices/jitter,
>    frame identity, reset, and UI treatment. Exit with an implement/defer/reject
>    decision for the post-SBS boundary.
> 9. **FG-03 minimal adapter.** If FG-01/02 pass, build an isolated, lifecycle-
>    bounded adapter with exact rational timestamps, explicit reset/cut handling,
>    capability diagnostics, frame-source identity, and deterministic cleanup.
> 10. **FG-04 held-out odd-frame test.** For three public 60 fps clips, retain the
>    full-rate fresh-oVDA SBS output as reference, give the candidate only even
>    frames, generate the missing odd frames at 2x, and compare them with the held-
>    out reference. Record RGB error, perceptual similarity when reproducibly
>    available, edge/occlusion error, left-right disparity consistency, temporal
>    pumping, cuts, latency, VRAM, and paired review media.
> 11. **FG-05 baseline comparison.** Compare post-SBS DLSSG with duplicate/linear
>    presentation, the confidence-gated NVOF depth candidate, and bidirectional
>    depth interpolation where applicable. Separate quality, throughput, and
>    lookahead/presentation latency; do not collapse them into one FPS number.
> 12. **FG-06 product placement decision.** Decide whether a passing result belongs
>     only to offline export, optional live presentation smoothing, a named mode,
>     or nowhere. Keep it independent of the four depth-quality mode contracts.

### P2 and later — deferred or prerequisite-blocked

> 13. **BI-01 file-only bidirectional depth experiment.** Warp normalized depth
>     from both neighboring fresh frames with bidirectional flow and occlusion
>     handling. Measure the one-frame lookahead cost and use held-out odd fresh
>     depth/SBS as the oracle.
> 14. **PIPE-01 serial-to-async promotion.** Only after the selected quality path
>     passes, establish serial byte/numerical equivalence, bounded queues, explicit
>     ownership, cancellation, source loss, and device-loss cleanup before overlap.
> 15. **PIPE-02 end-to-end benchmark.** Measure capture/decode through depth, SBS,
>     optional FG, and presentation/export with P50/P95/P99, copy/sync counts,
>     queue high-water marks, VRAM, drops, and environment metadata.
> 16. **REL-01 release gates.** One-hour soak, headset/VR comfort review, broader
>     GPU/driver matrix, device-loss recovery, and redistribution review remain
>     open regardless of a short-run quality or performance pass.

### Promotion rules

> - A public implementation or vendor guideline is prior art, not local evidence.
> - A quality pass requires both predeclared automated thresholds and review of
>   full motion, not selected stills alone.
> - Exact source identity and cut/reset lineage are mandatory for every generated,
>   warped, held, filled, and fresh frame.
> - Any unavailable required input, license incompatibility, unbounded ownership,
>   cross-eye instability, or material latency regression can reject DLSSG without
>   proceeding to application integration.
> - Neural-rendering or super-resolution work stays deferred until a documented,
>   reproducible API and a separate quality/license case exist.

### 2026-09-07 priority result

> The history-attribution portion of OF-00 and all of OF-01 are complete in
> [[nvof.md](nvof.md#record-result-ovda-nvof-actual-skip-2026-09-07)](nvof.md#record-result-ovda-nvof-actual-skip-2026-09-07).
> The fixed 1:2 candidate failed the stop rule: two clips failed all warped history
> policies, ParkingGarage favored held depth over NVOF, and actual skipping changed
> later fresh recurrent depth. OF-02 therefore terminates the fixed-cadence branch
> instead of expanding confidence/fallback GPU work. OF-03 through OF-05 are
> cancelled for that branch; an adaptive policy would require a new proposal.
> The existing review videos all decode completely, but their continuous
> full-motion playback review remains the active P0-1 item. Selected worst-frame
> stills do not close it.

> FG-01 and FG-02 are complete in
> [[frame-generation.md](frame-generation.md#record-result-dlssg-feasibility-2026-09-07)](frame-generation.md#record-result-dlssg-feasibility-2026-09-07).
> The current Streamline/post-SBS adapter is rejected: HAGS is disabled and the
> official feature binaries are absent locally, while the decisive architecture
> failure is that the D3D11/Qt completed-image boundary cannot supply truthful
> renderer depth/motion/camera/Reflex inputs. FG-03 through FG-06 are cancelled
> for this proposal. Do not convert that result into an unsupported-GPU claim.

> The next work is the remaining P0-1 continuous playback review. After it closes,
> make the P2 investment decision for BI-01 as deferred file-only research.
> Representative live motion/text/cut validation and frame-identity latency work
> remain in the broader product backlog and do not jump ahead of this queue.
