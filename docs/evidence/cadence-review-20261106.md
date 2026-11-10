# Capped scheduling and polling review — 2026-11-06

## Decision and scope

Recommend a single work-rate owner with bounded deadline recovery and a short
publication-spacing guard for non-VFG native output. This is an **experimental
candidate, not an application change**. Normal launch retains `PresentationCadence`
and its strict relative minimum-spacing policy. No model, precision, quality,
native DLL, texture lease or user setting changed in this review.

The candidate is implemented only under `experiments/zipdepth/pacing_candidate.py`
and selected explicitly by the public-source benchmark's `--pacing` argument.
It is never imported by normal app launch. The result supports implementation
work, not exact display refresh, VFG/host compatibility or hardware qualification.

## Where the overhead comes from

`PresentationCadence.emitted(now)` currently sets `next_ns = now + period_ns`.
A late 1ms poll therefore moves every future deadline later. In the worker,
`emitted` is called after input capture/copy, so the next acquisition also pays
that work before the next interval starts. The previously recorded 60-cap
work-start interval is about 18.05ms rather than the nominal 16.67ms.

There is also an independent consumer-side full-period cap. Advancing the
producer alone can accumulate ready textures behind that second clock, as
demonstrated by the rejected acquisition-origin experiment in the
[notification investigation](native-notification-20261106.md).

The worker checks its wait predicate about every 1ms via interruptible stop-event
waits; the GUI uses a 1ms precise Qt timer. The issue is deadline drift and
independent scheduling, not evidence that the GPU needs another 1.4ms of compute.
CPU utilization and wakeup counts were not measured here, so no CPU-saving
percentage is claimed.

## Candidates and diagnostic evidence

- `phase`: both clocks retain the planned next deadline when lateness is at most
  2ms; larger delays reset phase. Two ten-second trace windows produce 58.70 FPS,
  with callback-age P95 17.81–18.24ms. Useful but still below 60.
- `phase3`: the same independent clocks allow 3ms recovery. Output approaches
  60, but one trace window's callback P50/P95 rises to 19.60/23.88ms. Ready-to-
  publication P95 reaches 7.20ms in the combined trace. Two improved clocks still
  do not coordinate their phases.
- `work-phase3`: only the worker owns the 60/30Hz schedule; the consumer publishes
  ready textures without a second full-period wait, one descriptor per poll.
  This improves throughput/age in the repeated runs below. However, variable
  completion times can make individual outputs close together: a diagnostic
  trace includes a 9.60ms output interval. It is not a strict per-frame 60 FPS cap.
- `work-guard3`: the worker retains that rate policy; consumer publication also
  enforces a short guard of `period - min(3ms, period/4)`. At 60Hz the broker
  minimum is 13.67ms, not 16.67ms. This prevents very close broker publications
  without restoring a second full-period clock. Qt scheduling/physical scanout
  can still change observed output intervals.

All candidates keep unlimited unchanged, a future deadline after large stalls,
bounded two-slot ownership, stop handling and one descriptor per capped poll.
Recovery is intentionally bounded; no tight spin loop or unbounded catch-up is
introduced. The eventual product contract must distinguish target cadence from
the current strict minimum spacing before promotion.

The initial `work-phase3` trace also contained an unexplained system/input/output
stall: input rate fell to 114.69 FPS, maximum work interval was 431ms and maximum
callback age 511ms. That run is retained, not edited or silently discarded.
The repeated runs below restored approximately 119.6–120.2 FPS input. This is
not proof that long stalls cannot recur or that this candidate handles every
external scheduling disruption without an observable pause.

Trace files: `out/public-hfr/Jockey-zipdepth-cadence-{phase,phase3,work-phase3}-trace.json`
with `.worker.json` companions. Joined summaries:
`out/cadence-review/{two-clock,single-clock}-summary.json`.

## Repeated measurements

RTX 5090, driver 621.14, 480W limit unchanged; the same pinned guide/FP16 model
artifacts as the notification investigation. Hash-verified UVG Jockey genuine
3840x2160/120fps through owned mpv/WGC, native 7680x2160 output, strength 0.25,
detail rendering, VFG off. All sessions run sequentially, three seconds warmup
then five ten-second windows each. GPU activity and power are whole-device
means from samples inside the windows, including player/compositor/desktop;
FPS/latency values are medians across windows.

The old measurement harness manually called `processEvents()` then slept 1ms.
This review adds an explicit `--event-loop qt` using `QEventLoop` and a precise
single-shot duration timer, without that manual sleep. Both arms below use the
same actual Qt event loop. The slowdown still appears in the control, so it is
not solely an artifact of the manual harness.

| Actual Qt loop, ZipDepth 60 cap | Current app policy | Guarded single-rate candidate |
|---|---:|---:|
| Output FPS median (range) | 54.60 (54.50–54.80) | 59.89 (59.80–60.00) |
| Callback-to-output age P50 | 13.72ms | 13.13ms |
| Median-window callback age P95 | 18.30ms | 18.76ms |
| Median-window output interval P95 | 20.39ms | 19.31ms |
| GPU activity | 29.45% | 31.10% |
| Whole-GPU power | 175.02W | 185.22W |

The guarded candidate delivers about 9.7% more frames for 5.8% more whole-device
power in this pair. Tail age is approximately unchanged/slightly higher, **not
an all-percentile latency improvement**. Better average output rate also does
not establish uniformly spaced 16.67ms output or physical 60Hz synchronization.

The earlier matched manual-harness pair and additional model/rate probes are:

| Manual harness | Output FPS | Callback age P50 / P95 ms | GPU activity | Power W |
|---|---:|---:|---:|---:|
| ZipDepth control, 60 cap | 55.20 | 15.09 / 19.85 | 29.92% | 177.40 |
| ZipDepth `work-phase3`, 60 cap | 59.90 | 13.75 / 17.70 | 31.18% | 186.22 |
| Small `work-phase3`, 60 cap | 59.90 | 14.58 / 17.73 | 33.81% | 202.12 |
| ZipDepth `work-phase3`, 30 cap | 30.00 | 15.33 / 19.20 | 23.00% | 133.05 |

Do not combine the manual-harness unguarded measurements with the guarded Qt
pair as if they were the same candidate/measurement mode. Input phase also
affects capture age; fixed work deadlines need not align with source arrivals.
Reduced CPU polling would not by itself prove reduced GPU power while producing
more frames. All six repeated sessions have 100% distinct-ID age coverage and
zero native pools/nodes after stop.

Raw `out/public-hfr/` telemetry tags are `cadence-review-{before60,work60,small60,work30}`
and `cadence-qt-{relative,work-guard3}`, with corresponding `Jockey-{model}-*.json`
benchmark reports. `out/cadence-review/summary.json` records window medians/ranges,
coverage and cleanup assertions. Counts are distinct Qt `afterFrameEnd`, not
physical scanout, panel response or stereo comfort.

Example reproduction:

```powershell
python experiments/zipdepth/gpu_telemetry.py --model zipdepth --cap 60 --repeats 5 --pacing relative --event-loop qt --tag NEW-control
python experiments/zipdepth/gpu_telemetry.py --model zipdepth --cap 60 --repeats 5 --pacing work-guard3 --event-loop qt --tag NEW-candidate
```

Use the repository's existing runtime Python/dependency environment. Tags must
be fresh; the harness rejects overwriting evidence.

## Recommended implementation order

1. Give one component ownership of non-VFG native work rate. Preserve planned
   deadlines across small scheduling jitter, re-anchor after larger stalls, and
   deliver ready results without an independent full-period consumer wait.
   Retain a short explicit publication-spacing guard. This has measured benefit.
2. Replace repeated worker 1ms deadline checks with interruptible waits for the
   remaining deadline. Keep separate bounded waits for free slots and parent
   health. A stop event must interrupt immediately; a delayed wake must not
   start catch-up work. This is a design recommendation, not a measured change.
3. Wake GUI delivery on frame-ready/retirement signals, with deadline wakeups
   when capped and a bounded fallback to service GPU lease releases, errors and
   source health. Clearing a signal must be paired with rechecking pending work
   to avoid lost wakeups. Avoid a render loop that spins just to reduce latency.
   Measure actual wakeups and process CPU before claiming resource savings.

Before promotion, cover the guarded candidate on Small/30Hz, ordinary host and
VFG timelines separately; test pause/resize/hide/restart, irregular/slower source
rates and long stalls. Source-arrival alignment and P95/P99 age need attention
alongside FPS. No model or pixel algorithm change is needed for these steps.

Five deterministic candidate checks pass: accumulated-jitter rate, adversarial
spacing, long-pause reset, unlimited parity and the publication guard. These
are in `experiments/zipdepth/check_pacing_candidate.py`; they do not substitute
for the named runtime/visual/device acceptance. No production promotion, commit,
push or redistribution was performed.
