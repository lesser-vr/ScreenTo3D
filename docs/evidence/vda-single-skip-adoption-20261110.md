# Bounded VDA live history retention adopted — 2026-11-10

## Behavior

Ordinary VDA live processing now retains model and renderer history across one
missing capture update (sequence increment 2) with increasing source time <=50 ms.
Consecutive captures preserve the existing <=100 ms pause bound. Larger skips,
invalid/reversed indices or clocks, cuts, resize and source changes reset history.
No missing frames are synthesized and cache positions count accepted updates.
Every accepted VDA capture still runs inference; the model's existing 42-entry
cache bound, precision and preprocessing are unchanged. File/full-rate bindings
continue requiring every decoded frame.

`LiveModelAdapter.single_skip_history` owns this VDA live capability.
`resolve_history_policy()` applies the capability before inference or renderer
state is updated. DA2 coalescing and oVDA's separate 50 ms short-skip rule retain
their prior behavior. `DEPTHSBS_DEPTH_HISTORY=legacy` retains strict reset-on-skips
for comparison; `vda-single-skip` remains an alias for the VDA candidate behavior.
No GUI option is added.

## Repeated-skip quality comparison

Prepared RTX 5090, installed mixed-FP16 v3, strength .5, current GPU background
correction, diagnostic native Half TB. Seven cases cover three public clips
(FloorballGame, OfficeWalk, ParkingGarage) at both 1056x608 / 518x896 and
1920x1080 / 518x924, plus the secured flower excerpt at 3840x2160 / 518x924.
Public prepared hashes and the secured local asset are verified. Flower repeats
its bounded 90-frame excerpt; the original large user video is not needed.

For each 192-frame case, three independent VDA/native sessions process:

1. Every source frame, providing the full-rate model reference.
2. The same retained source frames with strict reset on skips.
3. Those retained frames with bounded single-skip retention.

After 32 no-drop controls, the schedule alternates dense one-in-three drops and
irregular isolated drops. Each case drops 50 source updates, including the last
one before a controlled cut; the preceding frame is retained so the cut follows
exactly one missing update. Metrics cover 110 post-control retained frames per
policy/case (770 per policy total). White/black hard-cut separators verify that
cache and renderer history do not cross detected cuts. Every published texture
slot is read and retired before reuse.

The comparison contract was declared before execution in
`experiments/vda/evaluate_short_skip.py`: no-drop and first hard-cut depth/native
pixels must be exact; per-case retained depth MAE <=.025; moving-edge depth-change
residual <= strict*1.05+.00005; native RGB MAE <= strict+.05 byte/channel.
The motion mask is a current Canny edge with >12 gray-level change since the
previous retained update. The residual compares depth changes at those retained
timestamps against the full-rate reference. These are relative fidelity proxies,
not depth ground truth or perceptual comfort measures.

All seven cases pass without changing the contract:

| Case | Output | Moving-change residual: strict -> retain | RGB MAE, bytes: strict -> retain |
|---|---|---:|---:|
| FloorballGame | 1056x608 | .011249 -> .000728 | .275 -> .049 |
| OfficeWalk | 1056x608 | .016313 -> .001839 | 1.157 -> .256 |
| ParkingGarage | 1056x608 | .022013 -> .000788 | .692 -> .099 |
| FloorballGame | 1920x1080 | .010986 -> .000787 | .297 -> .051 |
| OfficeWalk | 1920x1080 | .017429 -> .001808 | 1.644 -> .337 |
| ParkingGarage | 1920x1080 | .021883 -> .000824 | .904 -> .144 |
| Flower | 3840x2160 | .067776 -> .002059 | .766 -> .075 |

Moving-change residual falls 88.7–97.0%; RGB error falls 77.9–90.3% relative to
strict reset-on-skips. Maximum retained mean depth error is .003944. There are
49 in-scene gap resets per case with strict policy and zero with retention;
49 single skips are retained per case. The final skipped update leads to a real
cut and is flushed rather than retained. All 448 no-drop comparisons and 28 first
hard-cut comparisons are exact. This is a bounded 3.2-second-per-case stress
comparison, not a long-session or physical Owl3D quality acceptance.

## Actual default-path check

The ordinary source desktop is exercised with no history override: VDA, GPU
window capture, current background correction, 4K secured flower, native Half TB,
VFG off, uncapped submissions. Two independent ON and OFF sessions in reverse
order each collect three three-second windows after warmup (18 measured seconds
per condition). All four sessions complete and native stop checks report zero
nodes/pools.

- New default ON: zero gap resets in the measured windows.
- OFF control: zero gap resets.
- Six-window medians: ON 38.26 FPS / OFF 38.54 FPS, ratio .993, background wall
  interval 3.98 ms. The unchanged 4K TC-UBG-01 subset limits pass.
- Source/UI scheduling varies (about 50–62 Hz source supply), so this is not a
  demonstrated FPS gain or maximum-throughput result. The improvement is history
  retention, not a model-speed claim.
- Both ON worker traces are available and confirm the default VDA capability
  active with `history_policy=continuous`: after processed-index-80 exclusion,
  668 decisions include 12 skipped captures, all retained, and no gap resets.
  One OFF worker's optional shutdown trace was not written; shared window counters
  cover all four sessions. The trace summary is not presented as a complete OFF
  per-frame audit.

The earlier [diagnosis](vda-background-history-20261110.md) established that strict
VDA reset short 25–33 ms single skips. Its uninstrumented TC had 39 gap resets in
18 ON seconds; the separate instrumented strict run had 13 in 12 ON seconds.
Those runs are retained as scoped baselines, not a deterministic reset-count or
FPS prediction for the new session.

## Checks and reproduction

203 affected platform/profile unit tests and five model-routing contracts pass.
New coverage verifies default capability selection, legacy overrides, 50 ms
inclusion/exclusion, large skips, invalid clocks/indices, cuts and resize. Model
and native CUDA bytes are unchanged; existing portable ZIPs are not rebuilt by
this source-code update. Physical binocular and multi-hour acceptance remain
separate.

Reports live under `out/vda-single-skip-adoption-20261110/`:
`quality/report.json`, `contracts.json`, `model-contracts.log`, and
`native/report.json` / `assessment.json` / `history-summary.json`.

Run `experiments/vda/evaluate_short_skip.py --output <new-directory>` in the
prepared environment for the numerical comparison. The native diagnostic is
`experiments/ovda/analyze_uniform_background.py` with `--model vda-small --size 4k
--clip flower --normal-policy --trace-history`; omit `--history-policy` to verify
the ordinary default, or pass `--history-policy legacy` for the old strict rule.
