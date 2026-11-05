# Prepared-local native output default — 2026-11-05

## Change and scope

Native Qt/D3D11 texture delivery is selected by default in the prepared source
desktop. Base remains the Balanced model, CUDA remains the stereo renderer,
strength remains 1.0 and the normal presentation target remains 30Hz. No extra
primary UI control is added. Existing GPU host-output and reference choices stay
in Settings, and the explicit `DEPTHSBS_LIVE_GPU_CANDIDATE=0` reference override
is retained. Old portable packages do not inherit source changes automatically.

Selection no longer requires eagerly loading the native DLL. The controller
registers it at SBS Start, before starting the capture/inference worker; QML only
loads NativeFrame after successful registration. A load/hash/version failure is
reported with the explicit host-output recovery choice, releases the processing
lease and never silently switches transport. No capture starts on failed native
preparation. File conversion and capture exclusion are unchanged.

This promotes an already implemented transport, not a new shader/model or output
format. Existing exact host/native pixel evidence, pinned native DLLs and keyed
mutex ownership are reused from the [GPU input record](base-gpu-input-20261105.md)
and [restart record](native-restart-base-profile-iw3-20261105.md). Base native
output had measured ~23.9fps at 4K versus ~12.6fps host output under the recorded
60Hz benchmark conditions. Those rates are submissions, not physical scanout.

The user selected public-video validation for this step. Real games, physical
binocular viewing, hardware unplug/device loss, multi-hour runs and other GPUs
remain outside this local default decision.

## Executed checks

- 94 controller/protocol/routing tests passed, including a default-native loader
  failure that retains selection, starts no worker, releases the lease and offers
  an explicit host choice. Existing host-controller mocks now explicitly choose
  host output, so they still exercise their original contract.
- Three benchmark measurement tests passed. Native overload/cleanup checks now
  inspect the resolved live path rather than requiring an explicit CLI path flag.
- The initial actual-GUI default-path run at Balanced/30Hz passed native startup,
  distinct eyes, no main preview or shared color buffer, hide/restore,
  fullscreen/Escape, resize, stop/restart, source loss and worker crash. Cleanup
  assertions require zero remaining native pools/nodes. Evidence:
  `out/native-default-lifecycle-20261105/report.json`.
- No native projection/Qt DLL or TensorRT plan was changed. The existing exact
  RGB/native parity checks still describe the unchanged rendering operation.
- `out/native-default-screens-20261105/report.json` repeats the default-path
  lifecycle with Performance/DA2 Small at target 60Hz, including 120.29s steady
  playback, movement between both connected screens and preparation cancellation.
  Both screen transitions continued submitting frames; cancelled preparation
  emitted no error and left no lease/frame/pool/node. Resize, source loss and
  worker-crash checks also passed. This is window movement, not physical unplug
  or a 3D mode/headset test.
- `out/native-default-ui-20261105/report.json`: real Qt input/source selection,
  preparation/running buttons, cancellation, separate error window copy/close and
  capture exclusion passed at DPR 1.5, with zero Qt warnings. The mock frame cases
  explicitly select host delivery; actual native Start is covered separately.
- Scoped Ruff E9/F and whitespace validation passed.

## Continuous playback method

`out/native-default-4k-soak-20261105` runs the actual app with no `--path` override:
3840x2160 input/per eye, 7680x2160 Full SBS, Balanced Base, CUDA stereo, graph off,
target 60Hz, public FloorballGame in its own source process. It uses 30s discarded
warmup then twenty consecutive 30s measurement windows in one live session.
The 60Hz target stresses throughput; it does not change the app's 30Hz default.

The fixture is the pinned six-second public excerpt looping, upscaled from its
1080p preview. Output is fitted to a window, not 1:1 7680x2160 scanout. The test
collects owned-worker/GUI private bytes, distinct native submitted IDs, bounded
native resources and device-wide GPU samples. All per-window diagnostic samples
are retained by the benchmark GUI until exit; GUI memory includes that growing
measurement dataset. GPU samples are device-wide, not per-process allocation.
The final overload/restart cleanup assertions are separate from warmed rates.

Result: all twenty windows completed (603.59s measured, plus warmup). Median
distinct output submission was **23.646fps**, range **23.585–23.795fps**. The
worker's private memory ranged 3731.44–3733.51MiB and changed from 3732.04 to
3733.48MiB. All sampled output pools/nodes remained bounded; final overload and
shutdown checks passed with **zero pools and zero nodes**. A total of 15,098
distinct output IDs had been submitted by final shutdown. These are not 30/60fps
support or a multi-hour leak proof. Summary: `summary.json` beside the raw runs.

Benchmark GUI private memory grew 308.19→356.18MiB while retaining all measurement
rows/samples. This observation alone does not establish a GUI leak or absence of
one; the smaller-memory lifecycle sampler is recorded separately below.

The separate two-minute lifecycle run retained only one small memory sample per
second. Its GUI process also decoded/drew the public source: private memory was
417.24MiB initially, 441.43MiB at 90s and 437.61MiB at the end. Worker private
memory changed 1134.16→1134.68MiB. Native pool/node counts stayed at one each
during steady playback and reached zero after cleanup. This still does not prove
multi-hour memory stability or attribute every GUI allocation to output delivery.

## Remaining acceptance

The public-video checks do not certify game-specific hooks, HDR, physical monitor
unplug or actual GPU device loss, commercial bundling, clean-machine install,
multi-hour memory behavior or Owl3D/Quest viewing comfort. No output capture
permission or external-display feature was reintroduced.

Use the normal `Run-DepthSBS.cmd` launcher for this local default. If a native
preparation error occurs, Settings retains the explicit GPU host-output path.
