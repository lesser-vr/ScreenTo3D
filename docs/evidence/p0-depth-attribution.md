# P0 baseline intake and depth-stage attribution — 2026-09-09

Historical diagnostic at revision `69e104d090bf7568ae26b23fcfb778045d0eaab9`
with new uncommitted diagnostic tools. Application backends and defaults were not
changed. This is not completion of the matched VR comparison.

## Baseline intake

The user identified iw3, 4K 60 fps input, Lossless Scaling FG x2 and Quest 3.
Read-only installed-setting snapshots additionally record:

- iw3 revision `8d5e8f64bcdd4a88dd52715575055b15c18e0ce7`: `Any_V2_S`,
  learned `row_flow_v3_sym`, both-eye synthesis, Full SBS, Local Viewer,
  `wc_mp`, EMA 0.9, screen-border preservation, divergence/convergence 1.0,
  default resolution, edge dilation 2, compile enabled, stream 60 fps/height 2160.
- Installed iw3 preprocessing defaults to lower bound 392, preserving aspect
  ratio and flooring dimensions to multiples of 14: HxW 392x686 for 16:9.
  Consequently the planned DepthSBS aspect-ratio experiment is not a novel
  advantage over this iw3 baseline. The learned stereo renderer also differs.
- Lossless Scaling 3.2.2: LSFG3, FIXED x2, flow scale 50, BALANCED, WGC,
  sync OFF, maximum latency 3, queue 1, G-Sync enabled, HDR disabled,
  multidisplay enabled and LS1 AutoFullscreen scaling. Saved target 60 does
  not establish final rate and is not the active control in FIXED mode.

Saved settings are not proof of the active profile, actual per-eye/combined
output geometry, fresh depth/base SBS/final generated rates or latency.
Quest 3 viewer/transport, actual game/video recordings and binocular/HMD review
remain unrecorded. No desktop capture or network viewer was started for intake;
authentication and display/window identities are excluded from the snapshot.

## Isolated model-stage measurement

RTX 5090, driver 616.64, Python 3.13.9, Torch 2.7.1+cu128, TensorRT 11.2.1.2,
one Torch CPU thread, existing validated FP32 HxW 518x924 engines.
Prepared public FloorballGame 1080p frames were also upscaled to 3840x2160;
this tests source-size processing cost, not native-4K detail quality.
Each case alternated traced/untraced batches over five repetitions, with 16
warmup and 10 measured frames per batch. Reset-each-frame is a diagnostic
condition, not a proposed product sampling contract; reset cost is separately
recorded, outside depth wall time.

| Model | Source | History | Depth wall ms | TRT stream interval P50 ms |
|---|---|---|---:|---:|
| VDA | 1920x1080 | continuous | 27.63 | 11.94 |
| VDA | 3840x2160 | continuous | 49.94 | 11.94 |
| VDA | 1920x1080 | reset each frame | 25.24 | 10.02 |
| VDA | 3840x2160 | reset each frame | 50.14 | 14.32 |
| oVDA | 1920x1080 | continuous | 31.00 | 11.08 |
| oVDA | 3840x2160 | continuous | 60.38 | 16.03 |
| oVDA | 1920x1080 | reset each frame | 31.05 | 11.05 |
| oVDA | 3840x2160 | reset each frame | 61.41 | 16.00 |

Depth wall is the median of five untraced batch means. TRT CUDA events enclose
submission/execution and can contain host enqueue gaps; they are not pure kernel
utilization or a fixed model ceiling. Exclusive host regions include native
work/waits. CUDA intervals must not be added to host intervals, nor separate
region percentiles summed.

For continuous 4K, mean exclusive CPU preprocessing accounts for 34.66 of 50.57
traced wall ms for VDA (68.5%), and 39.55 of 62.14 ms for oVDA (63.6%). Grouping
is performed per frame before averaging. oVDA input copy/upload is separate.
This identifies source-size CPU preprocessing as a concrete optimization target;
it does not demonstrate achievable end-to-end FPS. Upscale submission and waits
are separated, but host regions are not a pure GPU-upscale decomposition.

Separate three-frame instrumented/uninstrumented depth hashes match exactly for
each model/source size. All instrumentation overhead gates passed (10% maximum).
Both engines were closed before final report publication. Six new unit tests
and Python compilation passed. Ruff was unavailable in the prepared interpreter;
no lint pass is claimed.

## Recorded live history behavior

Existing native GUI run final cumulative processed/reset counters were
1015/1005 (VDA 1080p), 444/445 (VDA 4K), 849/848 (oVDA 1080p), and
342/343 (oVDA 4K). Sources are the `runs.json` files under
`out/model-native-vda-clean-20260909` and `out/model-native-ovda-clean-20260909`.
These are asynchronously sampled counters, not atomic per-frame reset traces;
one extra reset is possible while processing is in flight. They establish
near-per-frame resetting in those runs, not a reason classification for each
reset. The live sequence-gap guard can reset history when intermediate capture
frames are skipped. A cadence/timestamp contract needs examination before any
guard is relaxed; no guard was removed by this diagnostic.

## Raw report provenance

Paths below are local ignored artifacts, not bundled release evidence.
The main report's older oVDA subdivision is superseded by the final oVDA report
after correcting the source anchor for input copy/upload; its VDA rows remain valid.

| Report under `out/p0-20260909/` | SHA256 |
|---|---|
| `model-stages/report.json` (VDA rows) | `a34ede6ed449864161787217d6a9974aad06e6a857695a4a49cca72033bcdc97` |
| `ovda-stages-final/report.json` | `b405c072e3a19126e17f6b646a77fd0766144c3d4d37a377eab7a2decf1b62a2` |
| `iw3-settings/report.json` | `88966ef6ad058fa791424e511a9b7f0b6fa36a5cf2321511c3aa775dbc8c6485` |
| `ls-settings/report.json` | `247db8a5a9eabc5f8ba29eb3af21c4cfb86fe904d0e279832eabfd54c05be868` |

No capture, stereo synthesis, external FG, scanout, sustained rate, native-4K
quality or headset comfort was measured here. Existing stereo timings must not
be added to these separate-run measurements to assert a complete-path rate.
