---
oma-docs: skip
---

# Bug: Perceived capture-card output stutter despite a 60 FPS counter

- Reported: 2026-11-13
- Status: PARTIAL FIX (updated 2026-11-14); capped-output tearing permission fixed, residual frame pacing and user optical acceptance remain open
- Severity: MEDIUM
- Source: user-selected Veyra 2.1.5 capture-card preview, VFG disabled
- Output: DA2 Small, native GPU texture delivery, Half Top-and-Bottom, 60 FPS
- Displays: PG32UCWM 239.991 Hz input display; Owl3D Shift 60 Hz output display

## User observation

Veyra preview is smooth. ScreenTo3D output feels choppy in both windowed and full-screen modes while the overlay reports 60 FPS.

## Measurement and limitations

Used a separate ScreenTo3D diagnostic process, temporary INI preferences, the currently available Veyra window and an output on Owl3D Shift. User apps and normal preferences were preserved. No input images or audio were saved. This was a live, changing workload, not identical video replay. PresentMon 2.6.0 console executable was downloaded from its official GitHub release and verified against the published SHA-256. Windows elevation was explicitly authorized. Later runs obtained elevation before starting capture to avoid an approval wait starving the worker.

PresentMon records Windows presentation/display events. These results do not establish unique gameplay-content FPS or the final optical result after Owl3D processing. Owl3D's active SBS processing state during the original user session has not been reproduced or independently verified by these tests.

All rows below exclude the first and final 0.5 seconds of the approximately 30-second trace. The same analysis is used for all rows.

| Trial | Duration | Present FPS | Displayed FPS | Dropped | Display interval P99 |
|---|---:|---:|---:|---:|---:|
| Existing full-screen | 28.956 s | 59.953 | 59.953 | 0/1737 | 19.130 ms |
| Existing windowed | 28.922 s | 59.782 | 59.125 | 19/1730 | 33.201 ms |
| Vsync trial, windowed | 28.934 s | 59.792 | 58.720 | 31/1731 | 33.332 ms |

Existing full-screen used Hardware Independent Flip; windowed trials used Composed Flip. SyncInterval was 0 for existing behavior and verified as 1 in the vsync trial. The trial retained the existing QT_D3D_NO_VBLANK_THREAD workaround. The result does not support claiming vsync alone fixes frame pacing. The subsequent user clarification of horizontal tearing is a separate acceptance criterion, addressed below. Counts are individual measurements, not proof of a statistically repeatable regression caused by vsync.

## Confirmed findings

1. The current overlay counts distinct native Qt afterFrameEnd submissions. Its Source/Output counters with VFG disabled do not measure physical display or unique gameplay frames. Rounding over two seconds hides frame-time outliers and compositor discards.
2. The windowed test reproduced actual Windows display discards and roughly 33 ms tail intervals while submissions were near 60 FPS.
3. Full-screen did not reproduce substantial discards during this trace. It does not explain or dismiss the user's full-screen experience.
4. Processed WGC source timestamps sometimes have 25-33 ms gaps. Such timestamps can include UI/compositor updates; they are not proof of skipped distinct gameplay frames.
5. Neither small-input Qt timing probes nor a 4K probe established an improvement from vsync alone or from removing Qt's update-idle wait. Those initial trials did not change product settings. The later tearing clarification led to the scoped fix below.

## Remaining investigation

- Measure the original app and Owl3D's final active playback path during a representative scene that the user identifies as stuttering.
- Compare unique central video content progression, capture/source timestamps, worker timing and displayed intervals together. Avoid interpreting whole-window UI changes as new gameplay frames.
- If a scheduling change is warranted, evaluate display-clock scheduling and bounded buffering against both frame regularity and added input latency; preserve unlimited output behavior and the known mixed-display stall workaround.
- Preserve the distinction between source-content rate, processed/submitted frames and displayed frames in diagnostics.

## Local evidence

Ignored diagnostic files under `out/capture-card-pacing-20261113/`:

- `veyra-etw-baseline4/presentmon.csv` and `.trimmed-summary.json`
- `veyra-etw-windowed/presentmon.csv` and `.trimmed-summary.json`
- `veyra-etw-windowed-sync-retry/presentmon.csv` and `.trimmed-summary.json`
- `probe.py`, `summarize.py`, and generated-source/4K probe reports

One vsync trace was cancelled at the Windows elevation prompt and is excluded. An earlier trial used a zero-valued QSG_NO_VSYNC variable but still had swap interval 0; it is also excluded as an effective vsync comparison.

## References

- https://github.com/GameTechDev/PresentMon/blob/main/README-ConsoleApplication.md
- https://doc.qt.io/qt-6/qtquick-visualcanvas-scenegraph.html

## Verification status

Initial diagnostic runs and trace analysis completed. See the subsequent scoped fix and validation below. No commit/push/release action. User acceptance and reproduction through active Owl3D 3D output remain pending.


## Horizontal tearing clarification and fix (2026-11-14)

The user specifically described a horizontal boundary across the screen with the upper and lower images misaligned. This differs from depth-edge shimmer and from a skipped frame. The previous focus on display discards did not exclude tearing.

Root cause of the permissive output configuration: `create_app` requests swap interval 0 and sets QSG_NO_VSYNC. Limiting CPU work to 60 FPS does not synchronize presentation to scanout. The original full-screen trace has SyncInterval=0, PresentFlags=512 (DXGI_PRESENT_ALLOW_TEARING), AllowsTearing=1 for all 1798 events. This is evidence of permission to tear, not a camera measurement of a visible tear line.

Minimal fix: `LivePreview.configureOutputTiming` requests swap interval 1 for the separate output window at 30/60 FPS and 0 for unlimited output. The initial 60 FPS window is configured before first exposure; stopped selection changes update its requested format. Running-session limit changes remain rejected. Control-window formats and the existing QT_D3D_NO_VBLANK_THREAD workaround are unchanged. No additional user option was added.

A preceding isolated per-output candidate used the same format override while retaining QSG_NO_VSYNC=1. In the full-screen trial, all 1803 PresentMon events have SyncInterval=1, PresentFlags=0, AllowsTearing=0. Qt content submissions remained about 59.97 FPS. However, Windows still discarded some presentations and the display-interval P99 was 31.898 ms. This fix addresses tearing permission, not all sources of judder; additional display waiting/latency is a possible cost. Optical review of the user's actual Owl3D 3D path is still required.

Evidence: `out/capture-card-pacing-20261113/tearing-flags.json` and `veyra-etw-fullscreen-output-sync/`.

Regression coverage:

- RED: the new capped-output selection regression failed with `0 != 1` before the fix.
- GREEN: the same regression plus pacing/native-delivery tests: 21 passed.
- Official CPU suite: 598 passed. One pre-existing adapter test still mocked SmallGpuCaptureEngine although the factory now uses NativeSmallEngine. Corrected that test-only mock to avoid accidentally constructing a real GPU engine in a CPU test. Product model routing is unchanged.
- Legacy standalone controller suite still has the same 13 pre-existing localization/error-message assertions failing; comparing the HEAD test module reproduced the same failures. Those tests were not rewritten as part of this fix.
- Real modified-product Veyra start/stop cycles: 60 -> unlimited -> 30 -> 60, with 300/300/150/300 Qt content submissions in respective 5-second windows. Requested swap intervals were 1/0/1/1, output default 1, control format 0. Every stop retired native pools and nodes to zero, no errors. The 60 FPS input limits the unlimited case; this is not proof of uncapped maximum throughput.
- The additional cycle ETW elevation was cancelled at the Windows prompt. The successful lifecycle cycle ran without ETW; it verifies requested formats and live restart/resource behavior, not per-cycle OS flags. Evidence: `product-output-timing-cycle-no-etw2/report.json`.
- `git diff --check` passes. No application ZIP/release replacement or commit/push was performed.

The corrected local source app requires a restart to load the change. A previously downloaded release remains unchanged.


## Actual user gameplay measurement (2026-11-14)

Measured the already-running Veyra, modified ScreenTo3D and active Owl3D display-mirror together for 60 seconds. No surrogate source/session was started and no user app setting was changed. Excluding startup/restart onset and common-window edges leaves 48.844 seconds. Veyra: 59.966 displayed events/s, 0 discards, display interval P99 20.845 ms, maximum 20.884 ms. Owl3D final output: 57.857 displayed events/s, P99 33.293 ms, maximum 220.872 ms; 33 intervals exceed 33 ms, including 12 above 50 ms. This reproduces output judder during gameplay while Veyra is stable.

ScreenTo3D's concrete output swapchain has 53.783 Present submissions/s, 52.596 Windows display events/s and 58 discards. Its window is covered by Owl3D's mirror/capture overlay; these intermediate display events are not equivalent to unique SBS frames captured by Owl3D. Do not attribute the final judder directly to those discards without capture/render correlation. Synthetic zero-address/SyncInterval=-1 events and the separate control-window swapchain were excluded.

Both actual output swapchains have SyncInterval=1, PresentFlags=0 and AllowsTearing=0. The tearing policy is active, with residual judder independently established. Whole-GPU usage observations partly overlap the trace: average 45.1%, maximum 52%; they do not exclude per-engine or synchronization stalls. The overlay usually still showed 60 FPS.

Evidence and caveats: `out/gameplay-pacing-20261114/report.md`, `steady-summary.json`, `gameplay.csv`, `window-and-gpu.jsonl`. Next diagnosis should correlate obscured Qt output rendering/Present, shared-texture/capture delivery and Owl3D composition/scanout scheduling. No source/setting changes were made during this measurement.


## Control-window render waste and controlled startup measurement (2026-11-14)

Confirmed a separate avoidable cost: every live frame explicitly requested repaint of both the minimal no-preview controller and the output. Replaced those connections with preview-aware window routing. Real Qt regression RED: 75 notifications -> 74 control renders + 74 output renders despite preview disabled. GREEN: 0 control + 74 output; explicit diagnostic preview remains 74/74. All 598 CPU tests and 21 related output tests pass.

After user restart confirmation, trace captured a continuous modified-app session with GUI/worker PIDs unchanged through completion. Raw DXGI trace has zero lost events. Common direct-call interval 42.116 s: Veyra 59.95, ScreenTo3D 60.10, Owl3D 59.79 Present calls/s; these are not unique content rates. The control-window Present count is zero. Owl3D displayed-event interval 41.96 s: 59.80/s, display P99 16.79 ms, maximum 33.37 ms, no intervals above 50 ms. Earlier gameplay trace had 57.86 displayed-event FPS, P99 33.29 ms, maximum 220.87 ms, and 12 intervals above 50 ms over 48.84 s. This is favorable observed evidence, not identical-scene causal attribution or final visual acceptance.

The intermediate SBS window is covered by Owl3D: its tracked display rate was only 17.57/s although raw calls and final Owl3D events were about 60/s. Do not interpret intermediate display counts as generated/captured content FPS. Both output chains still disallow tearing.

Excluded extra traces with stopped/restarting SBS (one missing ScreenTo3D, another only 11.85 s common overlap). A new 1Hz GPU sample started after this trace, so it was excluded from before/after GPU comparisons. Evidence and detailed caveats: `out/gameplay-control-update-20261114/report.md`. Remaining: user visual acceptance, occasional 33 ms intervals, and unique captured-content progression if residual judder is reported. No commit/push/release action.
