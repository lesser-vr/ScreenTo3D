# VDA background/history reset diagnosis — 2026-11-10

The reset trigger is the ordinary VDA live capture-continuity policy. With
`DEPTHSBS_DEPTH_HISTORY=continuous` (the default), VDA is neither a DA2 coalesced
adapter nor the oVDA short-skip adapter. `reset_reason()` therefore falls through
to `sequence != previous_sequence + 1`: even one replaced capture resets VDA's
model cache and renderer history. The previously tested `vda-single-skip` setting
is still an opt-in diagnostic, not the ordinary VDA default.

The new GPU background correction does not directly clear VDA's model cache.
Its extra work/readback waits lengthen the processing loop. The bounded capture
handoff retains only the latest WGC frame; intervening arrivals increment the
capture sequence and replace the prior pending frame. The continuity check then
classifies that short replacement as a gap. This can occur with good average
throughput and without a long source pause.

## Instrumented reproduction

Prepared RTX 5090, installed VDA mixed-FP16 v3, 518x924 canvas, 3840x2160 secured
TC-UBG-01 flower, native Half TB, VFG off, uncapped submissions. The model, GPU
correction DLL, source hash and production defaults are unchanged. Ordinary
correction ON/OFF runs twice each in opposite order; four three-second windows
per condition follow warmup. The same schedule is repeated with only the existing
single-skip diagnostic setting changed.

The optional `--trace-history` collector retains at most 2048 numeric decisions
per worker, records truncation explicitly and writes once after worker cleanup.
It records no captured pixels or input titles. It returns the original reset
decision unmodified, and also evaluates the pure single-skip predicate on the
same arguments. `--size 4k` bounds this investigation to the reproduced geometry.
The summary excludes decisions before processed index 80. This trace scope is
different from the exact benchmark windows and must not be mixed with their
reset totals.

### Direct observations

In the strict-policy trace after that warmup exclusion:

- Correction ON: 552 decisions, 14 gap resets, 538 retained updates.
- All 14 gaps have sequence increment **2**, source interval **25.0014–33.3352 ms**,
  and `cut=False`. The one-short-skip predicate retains all 14 identical inputs.
- Correction OFF: 569 decisions, zero gap resets, all sequence increments 1.
- Median preceding complete processing interval is **17.80 ms ON / 12.42 ms OFF**.
  At the 14 gap decisions it is **20.54 ms**; the preceding stereo interval is
  **8.00 ms**, including a **6.44 ms** background wall interval. The ordinary ON
  background median is **4.15 ms**. These are scoped processing intervals including
  waits/enqueue gaps, not isolated CUDA kernel utilization.

This connects the added processing time to ordinary latest-frame replacement,
and connects the reset itself directly to the strict capture-index predicate.
It does not attribute every tail fluctuation to a particular CUDA subkernel.

The single-skip trace has 453 ON decisions after warmup: four sequence increments
of 2, all retained, and zero gap resets. Its 473 OFF decisions also have zero gap
resets. The separate actual-output measurement windows record:

| Diagnostic policy | Correction | Gap resets in 12 measured seconds | FPS windows |
|---|---|---:|---|
| Default continuity | ON | 13 | 44.38, 40.76, 45.07, 42.88 |
| Default continuity | OFF | 0 | 44.79, 46.41, 44.41, 45.38 |
| One short skipped capture | ON | 0 | 33.12, 30.90, 41.99, 39.07 |
| One short skipped capture | OFF | 0 | 36.25, 36.62, 41.83, 45.08 |

These sequential diagnostic runs have different source/UI scheduling ceilings;
they do not establish an FPS benefit or cost for retaining history. The same-input
predicate evaluation and the actually retained skipped captures establish why
the cache was reset and how the existing option avoids those particular resets.
The earlier uninstrumented 39-versus-one result is preserved in the
[VDA TC follow-up](uniform-background-gpu-20261110.md#vda-follow-up-tc); its individual
events were not logged and are not retroactively labelled with these new timings.

## Consequence and scope

An applicable improvement candidate is retaining one missing capture with a
positive source interval <=50 ms. Larger skips, invalid/backward clocks, cuts and
resizes keep their existing reset guards. This protects temporal history; it is
not an established inference/FPS optimization. The earlier
[bounded public-video comparison](vda-single-skip-20261108.md) is relevant evidence,
but sustained irregular sampling with the new correction still needs its own
temporal-quality comparison before a default-policy promotion. This investigation
does not change normal VDA, file cadence, model precision or rendering defaults.

Fourteen existing boundary/reset-accounting unit tests pass. All instrumented
native sessions complete and assert zero native pools/nodes after stop. No
physical binocular, long-session or device-loss acceptance is claimed.

## Reproduction / data

In the prepared Python environment, run
`experiments/ovda/analyze_uniform_background.py` with:

```text
--output <new-directory> --media tests/media/local/uniform-background
--clip flower --windows 2 --normal-policy --model vda-small --size 4k
--trace-history --history-policy continuous
```

Repeat in another new directory with `--history-policy vda-single-skip`.
`experiments/vda/summarize_background_history.py <directory>` summarizes the
bounded numerical records without importing a GPU runtime.

Data root: `out/vda-background-history-20261110/`. Both `strict/` and
`single-skip/` contain completed `report.json`, worker records under `history/`
and `history-summary.json`. Unit results are in `contracts.log`.
Early strict records also contain an uncalibrated absolute source-clock offset;
it is excluded from the summary and is not a capture-to-display latency measure.
