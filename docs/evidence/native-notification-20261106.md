# Native render notification timing — 2026-11-06

## Cause and change

The radius-4 guide optimization exposed an existing ordering bug in the Qt
controller. Worker statistics could arrive and advance `frameRevision` before
the output cap allowed `NativeDelivery.consume` to publish that texture to the
broker. A later successful publication did not request rendering. The surface
could therefore retain its previous image until the next worker-statistics
notification, approximately one more input/work interval later. This explains
both missing distinct output IDs and the extra roughly 16.7ms observed after
broker publication; it is not evidence of a slow depth kernel or physical scanout.

`LivePreview.poll` now advances the revision and notifies the surface whenever
native consumption changes its broker frame or retires it. Worker statistics
are still acknowledged and reported, but cannot issue a native render request.
Ordinary and timed VFG delivery use this one notification point; the former
VFG-only callback is no longer connected. Host image delivery keeps its existing
copy/notification sequence. Native leases, keyed mutexes, artifact pins,
retirement, minimum publication spacing and worker pacing are unchanged.

## Attribution probe

Two sequential 20-second Jockey/4K120/ZipDepth/60-cap sessions, before and after
the notification-only change, use bounded timestamp deques. The opt-in
`latency.py --timing-trace` wrapper records worker ready, broker publication
and distinct Qt `afterFrameEnd` IDs without capturing pixels. Every output ID in
the measured windows joins to worker/publication records. Diagnostic overhead
is separate from the uninstrumented runs below.

| Matched phase | Before P50 / P99 ms | After P50 / P99 ms |
|---|---:|---:|
| Work-start intervals | 18.05 / 18.96 | 18.05 / 19.00 |
| Work start to ready | 5.91 / 8.08 | 5.92 / 8.18 |
| Ready to broker publication | 1.87 / 4.48 | 1.80 / 5.00 |
| Broker publication to output | 1.09 / 16.88 | 2.04 / 3.58 |
| Capture callback to output | 14.43 / 33.86 | 14.50 / 19.70 |

Before: 39 of 1,078 displayed samples exceed 25ms callback age, and the same
39 exceed 10ms broker age. After: neither threshold is exceeded in 1,108 samples;
maximum broker-to-output is 4.48ms and maximum callback age is 24.04ms.
The before-run tail is intermittent: its second ten-second window has callback
P95 27.26ms, while the combined probe P95 is only 18.61ms. Do not hide this by
mixing combined-sample and median-window percentiles. The earlier five-window
guide measurements also reproduced P95 27.76/31.65ms in separate sessions.

Raw: `out/public-hfr/Jockey-zipdepth-pacing-{old,notify}-trace.json` and matching
`.worker.json`; joined quantiles in `out/pacing-notify/trace-summary.json`.
`experiments/zipdepth/summarize_pacing.py` reproduces the join and asserts coverage.

## Uninstrumented actual native output

RTX 5090, driver 621.14, existing 480W limit unchanged. Same owned, hash-verified
UVG Jockey 3840x2160/120fps mpv source, native 7680x2160 window, strength 0.25,
detail rendering, VFG off. No concurrent GPU tests. Three seconds of warmup;
five ten-second windows at ZipDepth 60 cap, three at each other setting.
FPS/age columns are medians across windows; GPU/power are whole-device means
from 200ms samples inside the windows, including player/compositor/desktop.

| Case | Output FPS | Callback age P50 / P95 ms | GPU activity | Power W |
|---|---:|---:|---:|---:|
| Prior guide build, 60 cap, original five-window session | 53.20 | 14.49 / 27.76 | 31.20% | 171.96 |
| Notification fix, ZipDepth 60 cap | 55.39 | 14.51 / 19.17 | 30.98% | 170.81 |
| Notification fix, ZipDepth unlimited | 119.79 | 11.47 / 13.31 | 63.29% | 283.41 |
| Notification fix, ZipDepth 30 cap | 28.80 | 16.15 / 19.39 | 23.01% | 122.89 |
| Notification fix, DA2 Small 60 cap | 55.49 | 14.49 / 18.90 | 33.36% | 184.81 |

The capped five-window output range is 55.30–55.50 FPS. Unlimited remains
source-limited near 120 FPS, not a maximum throughput measurement. The historical
before row is the same artifact/input/settings but a separate earlier session;
the paired timestamp probe provides the direct notification-change attribution.
All completed sessions have 100% distinct-ID age sample coverage and zero native
pools/nodes after stop. Counts/ages are software output, not monitor scanout,
physical display latency, binocular comfort or long-session qualification.

Raw telemetry and benchmark reports: `out/public-hfr/pacing-notify-{0,30,60}.json`
and `Jockey-zipdepth-pacing-notify-{0,30,60}.json`.
Small uses `pacing-notify-small60.json` and
`Jockey-small-pacing-notify-small60.json`. The aggregate with coverage/cleanup
assertions is `out/pacing-notify/performance-summary.json`.

## Remaining rate limit and rejected experiment

This fixes the observed tail/output-loss regression, not exact 60Hz pacing.
The existing strict minimum-spacing policy starts a fresh period after each
accepted work/output event. Input-copy and polling overhead remain visible in
the roughly 18.05ms work interval (about 55.4 FPS), despite a 16.67ms cap period.
There is no catch-up burst, removed cap or hidden quality reduction.

A separate experiment moved the worker cadence origin before capture/copy.
It increased output only to 55.79 FPS while callback P50 worsened to 21–22ms
and P95 to 26ms: the faster producer accumulated extra publication wait. It was
reverted. Raw `Jockey-zipdepth-pacing-acquire-trace.{json,worker.json}` is retained.
A future exact-rate design must coordinate work and output timing and validate
both latency and load; simply advancing acquisition is not the promoted fix.

## Regression coverage

Three new Qt controller tests cover statistics-before-publication,
publication-before-statistics, and timed publication/retirement. They prove the
surface wakes without new stats and does not render twice when stats arrive
later. They are included in the existing `qt` contract group (10 tests pass).
An initial test harness mocked a Qt slot on the class and triggered a PySide
metaobject crash; the final test mocks source enumeration instead, leaving the
QObject class intact. The application runtime did not encounter that harness fault.
The existing cadence/native-protocol/live-boundary/VFG groups pass 28 tests.

Actual desktop checks also pass:

- Base/Small VFG off/on: five 60-cap sessions, generated-frame records, running
  setting immutability, unsupported-path rejection, hide/restore and Small 4K
  resize. All sessions stop with zero native pools/nodes. This is compatibility,
  not a new VFG quality or performance claim.
- ZipDepth 30-cap static input: three sizes, active resize, hide/restore,
  stop/restart and zero-resource cleanup.

Runtime records: `out/pacing-notify/vfg60/result.json`,
`out/zipdepth-launch-static-smoke-cap30-pacing.json`; scoped test logs and
`qt-contracts.json` are under `out/pacing-notify/`.

Depth/projection kernels and pins are untouched; the guide's existing matched
pixel evidence remains applicable. No new normal-speed stereo/physical Owl3D
acceptance, portable package, commit or push is claimed.
