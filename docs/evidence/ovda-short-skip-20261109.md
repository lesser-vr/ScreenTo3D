# oVDA short capture-skip history — 2026-11-09

## Delivered scope

The live oVDA adapter separately enables `short_skip_history`. The worker checks
capture sequence and source timestamps before reset/inference. One missing update
at most is retained when both clocks are valid/forward and their interval is no
more than 50 ms. Larger skips, longer intervals (including consecutive IDs),
invalid/reversed clocks, cuts and geometry/source changes still reset. Cuts are
reported as cuts, and shape changes take precedence. The existing `legacy`
diagnostic selects the original index-strict policy for comparison.

The model is still inferred once per accepted update, with its original c16
schedule and FP32 engines. No synthetic frame, absolute capture-ID positional
mapping, model reuse cadence, interpolation or queue was added. File decoding
still requires every frame. oVDA's renderer-quality selection remains separate
and unchanged; the follow-up EMA/range proposals were not implemented here.

The source worker's fixed statistics array grows from 35 to 41 entries. Appended
metadata counts retained gaps, the number of past slots available before each
inference, full-context inferences, occupancy sum and current/maximum update
streak. Fifteen past slots plus the current frame is the full c16 context. This
avoids treating the post-update `used==15` on the fifteenth update as an already
full sixteen-frame inference. Snapshots are not a transaction across counters.

## Boundary and parity checks

Thirty-two affected unit checks pass: capture/model selection, reset/time/count
boundaries, occupancy/reset accounting, fixed metric capacity, oVDA binding and
the file every-frame contract. They include exact 50 ms acceptance, 50 ms + 1 ns
rejection, more than one missing update, missing/noninteger/reversed timestamps,
cuts and resize, while DA2 and VDA policy behavior stays separate.

Actual GUI start, input resizing across landscape/portrait/square/1056x608 and
back, both-monitor movement, fullscreen, minimization, stop/restart and preparation
cancellation pass at `out/ovda-short-skip-20261109/gui/report.json`.

## New sampled-timeline comparison contract

This intentionally changes results on dropped captures. Exact parity is required
only when no capture is missing. For missed captures, the reference is the same
oVDA processing every source frame; this is not depth ground truth.

`check_short_skip.py` uses the checksum-verified FloorballGame, OfficeWalk and
ParkingGarage previews. The no-drop phase has 24 source frames per clip and an
explicit midpoint reset: 72 comparisons, all source-depth/native Half TB pixels
exact. The sampled phases use 96 source frames per clip and drop every fourth
frame from both test timelines. The dense reference processes all frames; strict
resets on each index skip; retained history uses the product reset predicate.
All timelines receive equal controlled midpoint cuts. Automatic scene predicates
are overridden only in this explicit replay, so all three reference timelines
use identical known cut boundaries.

Three source geometries (1280x720, 1056x608 and 720x1280) exercise all three
installed FP32 canvases. Each of the nine sampled cases has 72 accepted frames
per candidate, including cache filling and eviction. Native texture/depth
readbacks are owner-stream fenced and excluded from performance measurements.

The comparison contract requires no worse mean raw-depth, temporal-gradient,
depth-edge and native-SBS differences to the dense reference in each sampled
case, fewer resets, and successful use of full context. `validate_short_skip_report.py`
checks that contract on the recorded data without repeating CUDA inference.

All nine cases pass. Compared with strict resets, differences to the dense
reference fall by:

| Metric | Reduction across the nine cases |
|---|---:|
| Raw depth MAE | 74.7–90.9% |
| Temporal-gradient error | 53.4–72.7% |
| Depth-edge error | 66.7–85.8% |
| Native Half TB RGB MAE | 63.3–77.0% |

Depth/temporal/edge errors use the dense reference's first-frame P2–P98 span,
fixed within each clip; no per-frame affine fit hides scale changes. Temporal
error compares candidate and reference differences over the same accepted source
intervals, including strict resets. In each sampled case, strict resets 24 times
and never reaches full context; retention resets twice at the controlled
start/cut boundaries and reaches full context on 42 of 72 updates.

Artifacts: `out/ovda-short-skip-20261109/quality/{report,comparison-contract}.json`.
The report contains source hashes and per-case values. Preview strips are
diagnostic only. These proxies show closer agreement with dense oVDA on the
tested sequence; they do not establish true depth accuracy or physical comfort.

## Actual native capture comparison

RTX 5090, driver 621.14, Torch 2.7.1+cu128 and TensorRT 11.2.1.2. Both variants use
the same validated current-device FP32 518x924 control plan, SHA256
`7bd4916e0104a1306c99dd0bb5a37e8bf27aed0f8ac698b5f35f1076147b0e75`, with GPU
capture/preprocessing and the same fixed-buffer runtime. An owned FloorballGame
window advances on a 16 ms timer (about 62.5/s). 4K scales the public source.
Settings: native Half TB, strength 0.5, VFG off, unlimited output. User defaults
and saved choices are unchanged.

At each size, session order is strict/retain/retain/strict. Each session discards
three warmup seconds and measures three adjacent three-second windows: six
windows, about 18 measured seconds per condition. All eight sessions stop with
zero live native pools/nodes. FPS counts distinct native submissions, not scanout.
GPU samples are device-wide, including playback/desktop and other clients.

| Input | Policy | Median FPS (window range) | Gap resets | Mean cached past slots | Full-context fraction | Mean GPU |
|---|---|---:|---:|---:|---:|---:|
| 1920x1080 | Strict | 59.98 (59.67–60.27) | 46 | 9.92 | 36.6% | 86.0% |
| 1920x1080 | Retain | 59.53 (58.98–59.97) | 0 | 15.00 | 100% | 86.0% |
| 3840x2160 | Strict | 47.09 (46.86–47.25) | 279 | 1.09 | 0% | 86.9% |
| 3840x2160 | Retain | 46.43 (45.87–46.66) | 0 | 15.00 | 100% | 87.3% |

Occupancy fractions are weighted by actual inference counts. No cuts occurred
inside these timed windows. Retention accepted 54/288 short gaps at 1080p/4K;
the maximum observed continuous update streaks were 722/565, compared with 43/6
under strict resets. The short-run FPS cost is about 0.8%/1.4%; the benefit is
using temporal context, not higher throughput. Other contents can still trigger
valid cuts or long-gap resets.

Artifact: `out/ovda-short-skip-20261109/native/report.json`.
Reproduction: `benchmark_precision_live.py --history-comparison --windows 3
--layout half-tb --output <new-directory>`. Long soaks, low-cadence sources,
physical latency and visual/comfort acceptance remain outside these checks.
