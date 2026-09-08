# Measuring DepthSBS

Use a bounded experiment sufficient for the question. Development probes may be
short; stronger performance/support claims need repeatable representative evidence.
No whole matrix, restart, full survey or benchmark is required for every change.

## Comparable runs

Record revision/dirty state, relevant compiler/runtime/GPU/driver configuration,
model/engine hashes and shapes, resolved policy, source checksum/metadata, output
geometry, warmup, measurement interval and instrumentation. Control competing GPU
workloads and display/power conditions. Do not terminate unrelated applications
or compare changed background conditions as an optimization A/B.

Warm up engine/pools and report startup separately. For repeatable performance
claims use at least five measured repetitions, median and range, after discarded
warmup; choose longer runs when sustained behavior is the claim. Retain raw JSON/CSV
and failures. A short exploratory result is useful when labeled with its scope.

Separate capture, selected model input, fresh depth, base SBS and FG output rates.
Record input/per-eye/combined dimensions and distinct IDs. Compare end-to-end time
with end-to-end time, not inference alone. Model/profile differences in a quality
comparison are deliberate variables to disclose, not something to hide.

P50/P95/P99 latency, queue occupancy, copy/sync counts, process memory and GPU-wide
load answer different questions. Qt callbacks/clock readback are not physical
scanout or motion-to-photon; sampled memory is not leak proof. Report denominators
and instrumentation overhead. Detailed hashes/readbacks belong outside timed
windows when they materially change work.

## Correctness and quality

Use generated fixtures for geometry, polarity/eye order, timestamps/cuts and
deterministic regressions; public/licensed natural content for visual behavior.
Choose motion, text, thin structures, occlusion, low texture/darkness and cuts
relevant to the change. Test codec/resolution cases affected by it. User footage
is not the implicit default; current public live fixtures are UVG-VCM.

Behavior-preserving changes use the appropriate parity oracle. Intentional model,
precision or quality changes compare against the previous baseline with declared
tolerances and temporal/binocular criteria. Spatial detail and stable but wrong
depth must not be confused. Full decoding is media verification, not playback
review; stills and flow proxies do not establish VR comfort.

Support claims require valid output/A-V policy, the stated throughput/latency,
quality and resource bounds on the named hardware/runtime envelope. Release,
long-session and real device-loss claims require those specific checks. Missing
evidence limits the claim; it does not block unrelated experimentation.

## Existing tools

| Question | Existing entry points |
|---|---|
| Portable/reference media and motion | `scripts/media-smoke.ps1`, `scripts/test-v1.ps1`, `scripts/test-v1-motion.ps1` |
| Lifecycle and long-run observation | `scripts/test-v1-motion-stability.ps1`, `scripts/soak-v1.ps1` |
| Matched file renderers | `v1/compare_packaged_renderers.py`, `v1/validate_packaged_comparison.py` |
| Model comparisons | `v1/evaluate_live_action.py`, `v1/evaluate_live_supplement.py`, `v1/evaluate_ovda_expansion.py` |
| Live/native/capture attribution | `v1/benchmark_live_modes.py`, `v1/probe_capture_only.py`, `v1/summarize_guarded_baseline.py`, `v1/analyze_live_gpu_boundary.py` |
| Host live-input alternatives | `v1/benchmark_live_input_layout.py` |
| Exact isolated guided-filter CUDA candidates | `v1/benchmark_live_guide_candidate.py` |
| Non-exact rolling guide quality/performance | `v1/evaluate_live_guide_rolling.py`, `v1/benchmark_live_guide_rolling.py`, `v1/benchmark_live_guide_rolling_native.py` |
| Current guided-filter subkernel attribution | `v1/profile_live_guide_kernels.py` |
| Installed Small + LSFG baseline settings | `scripts/snapshot-lossless-scaling.ps1` |

Check each tool's current arguments before use; reproduction commands and their
measured limitations are in [evidence](evidence/README.md). No command here is an
instruction to start a GPU job. Preserve the user's
[guarded-run condition](evidence/live-performance.md#guarded-run-condition)
when reproducing that specific recurrence test.

`analyze_live_gpu_boundary.py --runs <runs.json> --output <new-json>` checks the
cumulative CUDA byte/synchronization formulas and summarizes all retained GPU and
host stage samples. CUDA event intervals can include host enqueue gaps, so their
percentiles rank observed work but are neither utilization nor an additive critical
path. `benchmark_live_input_layout.py --output <new-json>` is a CPU-only microbench
for full-resolution capture ownership/color alternatives. It cannot establish an
end-to-end speedup; increased transfer bytes or slower host work should reject a
candidate before integration.

`benchmark_live_guide_candidate.py --candidate-dll <dll> --output <new-directory>`
loads the pinned current DLL and an isolated candidate in the same process. It
requires exact aligned-depth bits and SBS RGB across odd/minimum dimensions and
all three live guide radii, then alternates 4K timing order. The guide CUDA-event
interval is the primary metric because the equal host-output path includes full
SBS readback. Declare `--minimum-guide-improvement-percent` before the run; exact
pixels without the required effect do not support promotion.

`profile_live_guide_kernels.py --profile-dll <diagnostic-dll> --output
<new-directory>` verifies the event-instrumented current algorithm against the
pinned DLL, bounds instrumentation overhead/event accounting, and reports the
four guide subkernels separately. Use the subkernel result only when exact parity
and both declared instrumentation gates pass. Whole-path host-output FPS is
supplementary because it includes allocations and full SBS readback.

The rolling-window candidate intentionally changes floating-point addition order,
so it uses two ordered gates instead of the exact-candidate command. First run
`evaluate_live_guide_rolling.py --candidate-dll <dll> --output <new-directory>`.
It compares the pinned and candidate DLLs over minimum/odd synthetic motion and
cuts plus contiguous licensed public frames at all three radii. Its declared
aligned-depth and final-RGB limits are gating; consecutive-frame RGB change is
reported as a non-gating proxy unless a temporal limit was declared before a
future run. Only a passing quality report may be supplied to
`benchmark_live_guide_rolling.py --quality-report <report> --candidate-dll <dll>
--output <new-directory>`. The benchmark verifies the artifact hash, then uses
five order-alternated 20-frame 4K Balanced repeats and a predeclared guide-event
improvement threshold. It does not establish integrated capture or 4K60.
`benchmark_live_guide_rolling_native.py` additionally includes native texture
publication and a test-only no-copy keyed-mutex consumer; pass its separately
built `live-texture-runtime-consume` DLL. Its predeclared minimum-improvement
arguments may be negative to express a bounded non-regression contract (for
example, `-1` means no more than 1% regression); values at or below `-100` are
rejected. It still excludes WGC, IPC and Qt.

The raw rolling implementation is not a global candidate because radius 4 failed
its measured non-regression check. The promoted production implementation retains
the exact direct radius-4 algorithm and selects 64-pixel rolling chunks only for
radii 8/12. `live-depth-guide-hybrid` and `live-depth-guide-promoted` remain
reproducible evidence builds; treat each as a distinct artifact and rerun quality
and each mode's native gate against its hash rather than inheriting another DLL's
results. The normal prepared-local product path is `live-depth-parallel`.

For a historical actual-app candidate run, `benchmark_live_modes.py --path
gpu-texture --guide-candidate rolling`, `hybrid` or `promoted` selects only that
fixed, hash-pinned artifact inside its owned worker. Arbitrary DLL paths are not
accepted. Omitting `--guide-candidate` exercises the normal prepared-local product
DLL. For an A/B, keep geometry, source, mode, warmup, windows, native/runtime
hashes, presentation target and output guard matched. Validate the pair with
`summarize_live_guide_rolling_app.py`; the observed effect is not a post-hoc 4K60
gate.

## Scoped regression entry points

Install `tools/requirements-contracts.txt` in a separate Python 3.12 environment.
`python scripts/test-contracts.py --group cpu --report <json>` runs all GPU-free
groups; use `--group core`, `platform`, `profiles` or `quality` for affected work.
CI runs these separately. Missing/import-failed/empty/skipped required modules fail.
The runner owns classification; current-profile expectations can change with
intentional product changes and do not freeze future models or algorithms.

`python v1/test_media_contracts.py --media-tools <directory> --output <new-directory>`
checks real FFmpeg media, timestamps/audio, cancellation, failed encoder and owned
child cleanup with explicitly synthetic depth and CPU encoding. CI obtains a
checksum-pinned test-only FFmpeg through `scripts/prepare-contract-media.ps1`.
It does not replace or bundle the app's media tools. Add `--encoder nvenc` for the
prepared GPU path. These are short fixtures, not general codec support claims.

In the existing prepared GPU/Qt Python environment, run
`python scripts/test-hardware-contracts.py --output <new-directory> --fault-fixture <fixture-directory>`.
Prepare that test-only fixture once with
`scripts/build-cuda-projection-spike.ps1 -OutputDirectory <new-fixture-directory>`;
rebuild it when the CUDA source changes. Production exports remain free of fault
injection, while the separately built fixture tests six real allocation-failure
stages. Only the projection/all group needs this fixture.
Its optional `--group runtime|projection|transport|qt|media|jobs` scopes dependency
tests, real CUDA close/parity, NT-handle lifecycle, actual synthetic Qt pixels and
lease rejection, NVENC media, or repeated real depth/projection job cleanup.
The jobs-only group requires `--input <short-fixture>`; all uses its generated
media fixture. Model assets and the previously built engine must be prepared. Missing runtime/artifacts are failures, not passes.
Only owned test processes are used; each child has a timeout. GPU and Qt checks
are explicit local runs, not self-hosted jobs exposed to external PRs.

For a changed quality algorithm, run `v1/compare_quality_regression.py` with
`--source`, matched `--baseline`/`--candidate`, `--media-tools` and a new `--output`.
It bounds inspection to `--frames` (at most 240), records hashes/eye geometry/rate,
emits review frames and reports RGB/temporal proxies. Optional predeclared
`--max-rgb-mae` and `--max-temporal-change-increase` apply only to that comparison.
Without thresholds the result is measurement, not acceptance; visual review stays
pending in either case. Low change can mean frozen or wrong depth. Existing
natural-content evaluation and real playback/VR checks remain necessary for those
claims. Long soak and physical device loss keep their separate evidence scope.

For a product-baseline comparison, also pass `--contract` using
`docs/matched-quality-comparison.example.json` as the starting shape. The contract
records the workload identity, environment, input/per-eye/combined geometry,
capture/model/fresh-depth/base-SBS/generated-output rates, exact path descriptions,
latency evidence state and the seven review decisions named by the product. The
tool rejects inconsistent rate ordering or media geometry and hashes the contract
into the report. A valid contract can still remain pending; it never converts RGB
proxies or unreviewed motion into a depth-quality verdict.

Before recording the Small + LSFG side, run
`scripts/snapshot-lossless-scaling.ps1 -OutputDirectory <new-directory>`. It hashes
the installed executable, settings and renderer config and records only the
quality-relevant saved profile fields plus GPU/driver and active power scheme.
The snapshot is read-only and does not prove which profile was active during a
capture; pair its hash with the capture contract and confirm the visible profile.
