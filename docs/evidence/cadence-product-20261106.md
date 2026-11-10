# Native cadence and event-driven delivery — 2026-11-06

## Applied implementation

This implements the authorized follow-up to the
[cadence review](cadence-review-20261106.md) in the prepared-local application.
Non-VFG native sessions now use one worker-side rate owner with bounded 3ms
deadline recovery and a shorter publication-spacing guard. The controller
selects the guard only for non-VFG native output. Host and VFG retain their
previous strict full-period publication caps; VFG also preserves its timed
original/generated-frame schedule. Unlimited remains the default.

Worker deadline waits now block on the interruptible stop event for the remaining
time instead of checking every millisecond. A due-but-occupied native slot still
uses bounded 1ms acknowledgment checks. Work deadlines re-anchor after larger
stalls; missed work is not replayed. The displayed slot may remain leased while
the other is prepared.

Native producer offer/publication/retirement sends a one-byte advisory notification
through a local nonblocking socket pair after releasing the metadata lock.
`FrameWakeup` registers the GUI end with Qt. A full socket coalesces notifications
because unread data already guarantees readiness; no queue of captured frames,
background notification thread or clear-event race is introduced. On Windows,
the loopback sender disables packet coalescing. The sockets carry neither pixels
nor descriptors and do not authorize resource access or GPU acknowledgment.

The native controller services frame-ready events immediately, uses a precise
single-shot timer for pending publication/VFG deadlines, and retries at 1ms only
for outstanding older GPU leases/retirement. A retained current frame alone
does not cause retries. A 50ms health fallback continues servicing worker errors,
source health and cleanup. Stop cancels deadline callbacks; notifications close
after worker exit. Kernel mutexes, two-slot ownership, identity/hash checks and
retirement acknowledgments remain unchanged.

Pixel algorithms, model precision/artifact pins, capture privacy and output
geometry are unchanged. The intended timing contract changes from strict minimum
spacing to a native non-VFG target cadence: at 60Hz the worker's nominal period is
16.67ms and the consumer's short guard is 13.67ms. This does not guarantee exact
physical display intervals, and the host/VFG guard is not relaxed.

## Matched actual Qt output measurements

RTX 5090/driver 621.14, 480W limit unchanged. Owned, hash-verified UVG Jockey
3840x2160/120fps mpv/WGC input, native 7680x2160 output, strength 0.25/detail,
VFG off. Reuses the existing guide/FP16 artifact pins. Each case is sequential,
three seconds warmup then five ten-second windows, using actual `QEventLoop`
rather than the older manual `processEvents()+sleep` harness.

The explicit `--pacing relative` benchmark baseline uses the previous full-period
worker/consumer cadence and 1ms worker/GUI checks with no notification socket.
It keeps the prior render-notification fix and the same model/native binaries.
The default `--pacing production` runs the application implementation. Historical
experimental candidates remain opt-in benchmark code, never application fallback.

| Case | Output FPS median (range) | Callback age P50 / P95 ms | GUI polls/s | GUI CPU % | GPU % | GPU W |
|---|---:|---:|---:|---:|---:|---:|
| ZipDepth previous, 60 cap | 54.70 (54.60–54.90) | 13.55 / 17.17 | 998.05 | 13.91 | 31.12 | 169.24 |
| ZipDepth applied, 60 target | 60.00 (59.90–60.00) | 12.87 / 16.48 | 80.00 | 9.06 | 33.00 | 177.83 |
| ZipDepth applied, 30 target | 30.00 (30.00–30.00) | 14.86 / 18.53 | 50.10 | 5.00 | 23.60 | 122.31 |
| DA2 Small applied, 60 target | 59.90 (59.89–60.00) | 13.13 / 17.02 | 80.00 | 9.69 | 35.27 | 192.02 |
| ZipDepth applied, unlimited | 119.79 (119.69–119.80) | 8.91 / 11.63 | 139.79 | 20.94 | 58.14 | 276.66 |

FPS/age/poll/CPU values are medians across windows. GUI CPU is the GUI process's
`process_time` divided by wall time, normalized to one logical CPU; it includes
rendering/native GUI work, excludes the inference worker/player, and is not the
whole-machine percentage shown by Task Manager. GPU activity/power are whole-device
means of 200ms samples inside measurement windows, including player/compositor/
desktop. Driver-controlled clocks/power vary; this is not a per-kernel energy test.

At 60, actual output rises about 9.7%, GUI delivery checks fall about 92%, and
GUI CPU time per second falls about 35%. Whole-GPU power rises about 5.1% while
processing more frames. Tail age is slightly lower in this pair. Unlimited is
source-limited near 120, not a maximum-throughput result. All measured windows
have 100% distinct-ID age coverage and all five sessions stop with zero native
pools/nodes. Counts are Qt `afterFrameEnd`, not scanout/panel latency or physical
Owl3D comfort. This is bounded one-clip performance evidence, not a long soak.

Raw `out/public-hfr/` telemetry tags are `cadence-impl-{before60,after60,after30,
small60,after0}`, with matching `Jockey-{model}-*.json` reports. Aggregate medians,
ranges, coverage and cleanup assertions are in `out/cadence-product/summary.json`.
The preliminary two-window production smoke is `cadence-product-smoke60`; the
five-window table uses the final TCP_NODELAY-enabled implementation.

## Correctness and lifecycle checks

- 52 selected cadence/native-protocol/mailbox/live-boundary/VFG/source-helper
  tests pass. Added checks cover bounded jitter recovery, long-stall reset,
  remaining-time wait bounds, host/VFG policy preservation, publication guard,
  pending deadlines and retained-current-frame idle behavior.
- The 13-test Qt group passes. New socket tests cover coalesced writes, a new
  notification during the ready callback, channel saturation, peer closure and
  idempotent close. Tests wait for real Windows event delivery; an initial
  immediate `processEvents()` assertion was corrected because it did not wait
  for asynchronous socket readiness.
- Actual Base/Small VFG off/on passes five sessions at 60 cap and five at
  unlimited, including generated-frame records, unsupported-path rejection,
  immutable running settings, hide/restore and Small 4K resize. Notification
  sockets/timers close and GPU pools/nodes reach zero after every stop.
- Actual ZipDepth 30-target static source passes three sizes, active square/
  landscape resize, hide/restore and stop/restart with notification/GPU cleanup.
- Actual Small host output at 60, native at 60 and native at 30 pass with a
  slower 40ms source timer. Each produces about 50 frames over two moving
  seconds, stays active through source pause, and resumes output. During the
  paused second, native performs 20 health checks; host retains its existing
  roughly 998 polls. All three sessions close notifications/timers and resources.
- The existing real native lifecycle test passes at 60: SBS pixel differences,
  separate output/main-window visibility, fullscreen/Escape, active resize,
  source minimize/loss, stop/restart and resource cleanup. Its shorter five-second
  fixture run is lifecycle evidence, not a separate sustained performance claim.

Records are under `out/cadence-product/`: `qt-contracts.json`, contract logs,
`vfg60/result.json`, `vfg-unlimited/result.json`, `host-slow-pause/result.json`,
and `native-lifecycle/`; the static result is
`out/zipdepth-launch-static-smoke-cap30-cadence.json`.

The existing same-input numerical guide/model evidence remains applicable to
unchanged kernels. This timing change deliberately selects frames on a more
regular work schedule; source timestamps still govern temporal history/reset.
No new binocular comfort, device-loss, clean-machine packaging or redistribution
acceptance is claimed. No commit or push was requested or performed.
