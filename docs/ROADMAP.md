# Current work

User-directed priorities, updated 2026-11-06. Choose the next useful task within the current
request; these are independent work areas, not a mandatory staged sequence.
The outcome is defined in [PRODUCT](PRODUCT.md), delivered facts and unpassed
acceptance in [implementation status](implementation-status.md).

## Prioritized quality / eye-4K work

The [2026-09-09 review](references/2026-09-09-depth-quality-vr-review.md) records
candidate rationale, sources and risks. The list below is planned work, not
implementation or experiment completion. Priorities do not require completing
every candidate; stop or reorder a branch when a small comparison falsifies it.

| Priority | Task | Useful outcome / decision |
|---|---|---|
| P0 | Validate coverage and depth stability at strength 0.5 | View coverage, depth-range stabilization, motion history, floating window, disparity compression and selective contour/background fill on Owl3D; assess remaining moving-object errors, thin edges, exposed background, edge masking, depth strength and lag. [Detail evidence](evidence/stereo-detail-20261106.md), [disparity evidence](evidence/disparity-budget-20261106.md), [window evidence](evidence/stereo-window-20261106.md), [motion evidence](evidence/motion-history-20261106.md), [range evidence](evidence/depth-range-20261106.md), [coverage evidence](evidence/stereo-coverage-20261106.md) |
| P0 | Establish the matched Small + LSFG comparison | Reuse the existing harness; capture the actual baseline/settings on games and video, exact geometry/rates and latency. Include short binocular/HMD review early, not only at the end |
| P0 | Separate high-quality model cost and history behavior | Measure preprocessing, GPU inference/cache, upscale/sync and stereo separately; inspect intentional sampling versus true discontinuity resets. Do not infer a model ceiling from aggregate depth timing |
| P2 | Evaluate Lightly DA3-relative-small if useful | Confirm artifact/license scope, output-depth direction and sky processing, then run the matched comparison; proceed only if it adds value over P1 candidates |
| P2 | Prototype RGB60 + lower-rate high-quality depth | Use profiling to choose a viable model/cadence; propagate depth to the current RGB timestamp, jointly render eyes, bound queues and reject stale/unreliable history. 20–30Hz depth is an experiment target, not a supported rate |
| P3 | Compare stable base30 + external FG x2 | Preserve 7680x2160, explicitly scope capturable output without feedback, measure GPU contention/latency/binocular artifacts; keep as a comparison branch rather than the default VR solution |
| P3 | Explore DepthART-S/B or higher-cost input | Pursue custom Windows/TRT integration or 518x924 input only if earlier comparisons justify the added cost; require quality benefit on target content |
| P4 | Qualify the selected complete path | Sustained eye-4K cadence, actual display/headset quality and latency, lifecycle and packaging/license checks appropriate to the intended support claim; early visual checks remain part of P0–P3 |

## Other retained work areas

RowFlow symmetric's direct quality/binocular comparison is deferred at the user's
request (2026-11-05). Keep the explicit local experiment and its evidence available;
resume the comparison when direct viewing is practical. It is not a prerequisite
for precision/quantization work, and no default renderer promotion is pending now.
See [current implementation status](implementation-status.md) for completed tests.

The bounded P1 Small-model, aspect-input and temporal-history experiments have
left this work list. Their decisions and unpassed acceptance are owned by
[implementation status](implementation-status.md); candidate rejection does not
constitute product quality acceptance. The implemented fresh-frame GPU motion
history does not establish the separate P2 lower-rate depth propagation case.

These remain useful when relevant to the user's active request.

| Work area | Useful next outcome |
|---|---|
| GPU data path | Reduce capture/input transfers, unnecessary preview work or synchronization where profiling predicts a benefit; retain correct resource ownership |
| 4K GPU load and output pacing | Native cadence/deadline waits/frame-ready delivery are applied. Qualify longer sessions, irregular source rates and physical display timing; evaluate wider-radius guide costs and measured source-depth CUDA events. [Applied timing evidence](evidence/cadence-product-20261106.md) |
| Maxine VFG 2x | Qualify the default-off desktop option on sustained actual content, investigate variable Small 4K results, and improve original-frame throughput/latency/memory; complete binocular review, portable packaging and runtime redistribution scope. [Small trial](evidence/small-vfg-20261106.md), [current status](implementation-status.md#vfg-experiment) |
| Simpler operation | Improve source/output selection and game/video workflows from the existing desktop shell |
| Reliability and support | Close the specific content, display, long-session or hardware gaps needed for the claim being made |
| Artifact setup | When needed, replace repetitive code pins with a trusted validated artifact registry; current loaders remain enforced until implementation changes |

Fixed 1:2 NVOF and the tested post-SBS Streamline DLSSG adapter failed in their
recorded conditions. Those results inform candidate selection; they do not block
unrelated work or require finishing their review videos first. Reviewing those
videos or bidirectional file depth is optional research if it helps the current goal.

Do not infer implementation absence from historical plans. Existing local models,
capture, SBS, native output and telemetry already have evidence. Public release,
other hardware and physical VR/device-loss acceptance remain unestablished until
tested; they are not prerequisites for every development task.
