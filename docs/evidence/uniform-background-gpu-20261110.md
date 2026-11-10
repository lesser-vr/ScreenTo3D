# Shared GPU uniform-background correction — 2026-11-10

Scope: prepared local RTX 5090, driver 621.14, native Half TB, VFG off,
strength .5, uncapped submissions from the secured TC-UBG-01 SDR flower excerpt.
Rates below count distinct native submissions, not physical display scans or
maximum throughput. They are paired correction-on/off comparisons within each
model's run; sequential source/UI ceilings differ between runs.

## Implementation and comparison contract

`LiveGpuCandidate` now applies the common `flat_background_gpu` stage directly
to its owned device RGB/aligned depth. Full-resolution inclusive RGB predicates,
border eligibility, four-connectivity, border-connected background and foreground
components retain the CPU reference's semantics. Warp-compressed horizontal runs
avoid per-pixel contention when joining large uniform components. Foreground means
use FP64 sums; background median uses 4096 bins over normalized [0,1] depth.
Truncated jump flooding with eight final unit-step propagation passes estimates
the CPU chamfer distance. Interior depth and the correction's conditional gates
remain in place. Applied correction still invalidates motion history.

This is a declared bounded-quality replacement, not bit-exact median/distance
parity. The comparison contract was set before execution: exact background masks
and eligibility; normalized depth MAE <=.0003, P99.9 <=.002, max <=.01; native RGB
MAE <=.1 byte/channel and <=.5% pixels with any channel difference >8. Bypasses
must be byte exact. Tests compare against CPU correction, not depth ground truth.
The first coarse-distance candidate passed Base/oVDA but exceeded the maximum
depth error on Small (.01183 at default strength and .01401 at strength 2).
Eight local propagation passes resolve those concave-boundary cases; thresholds
were not relaxed and Small is not exempted from the quality comparison.

The full RGB/depth CPU roundtrip is removed from normal CUDA correction. A
qualifying frame reads 12 bytes of coverage counts, in addition to the existing
RGB border/scene observations. No corrected-depth H2D upload occurs. The stage's
wall interval includes its first wait for preceding CUDA postprocessing; it is
not an isolated kernel time. The metric is now `background_ms`; the TC evaluator
also reads historical `cpu_background_ms` reports.

Workspace is lazy, session-owned and reused: about 238.3 MiB at 3840x2160, maximum
254.2 MiB at the supported 4096x2160 bound, plus event handles. Stop/error drains
and frees it before the borrowed renderer/engine stream; uncertainty poisons the
session and reports an error. There is no silent CPU fallback. Model precision,
inference inputs and the `LiveDepth` ABI are unchanged.

Performance/DA2 Small now enables the same conditional correction. Its old live
policy skipped it to avoid expensive CPU work; that distinction was a performance
policy, not a model restriction. File policy already enabled correction.

## Executed checks

- 37 GPU/CPU mask and depth cases: thin structures, holes, diagonal contacts,
  nonblack background, uniform/bypass frames, odd widths/partial warps, disconnected
  components, low border-connected coverage and four flower samples at 1080p/4K.
- Default strength: 54 matched native output comparisons per model, 162 total.
  Each pair consumes the same owned inference token and source time, through
  independent GPU versus legacy CPU-correction postprocessors. Flower updates
  exercise c16 context, then a textured cut/bypass and return/reset. Both native
  texture leases are read and retired every update.
- Strength 2: 14 additional comparisons per model, 42 total.
- Across those 204 comparisons, maximum projection-depth difference is .00012006.
  Maximum per-frame RGB MAE is .00008151 byte/channel; maximum >8-byte pixel
  fraction is .000003376. Non-triggering output is byte exact. These numerical
  comparisons do not replace physical Owl3D visual/comfort acceptance.
- 290 affected CPU quality/platform/profile contracts pass, including byte-bound
  parity, owner/failure/close behavior and legacy/current TC metric compatibility.

Reports: `out/flat-background-20261110/quality-r5/report.json`,
`small-quality-r2/report.json`, `base-ovda-quality-r2/report.json`,
`strength2-quality-r2/report.json`, and `contracts-verified.json` under that root.
Early failed candidates are retained separately and are not acceptance evidence.

## Native performance

Final paired runs use `-WindowCount 2`: four 3-second windows per condition,
two independent sessions in opposite order, at each source size after warmup.
The manifest's unchanged limits are normal/control FPS >=.9 and background-stage
median <=8 ms, with a sufficiently fast control. Preferences are isolated;
each stop verifies zero native nodes/pools. The complete 90-frame source/hash
and triggering pattern are checked before measurement.

| Model | Source size | Correction ON FPS | OFF control FPS | ON/OFF | Background wall ms | TC |
|---|---|---:|---:|---:|---:|---|
| DA2 Small | 1920x1080 | 58.82 | 57.95 | 1.015 | 1.93 | pass |
| DA2 Small | 3840x2160 | 46.49 | 48.46 | .959 | 4.23 | pass |
| DA2 Base | 1920x1080 | 59.21 | 58.96 | 1.004 | 1.79 | pass |
| DA2 Base | 3840x2160 | 46.15 | 43.66 | 1.057 | 4.74 | pass |
| oVDA c16 | 1920x1080 | 56.36 | 55.72 | 1.012 | 1.91 | pass |
| oVDA c16 | 3840x2160 | 42.52 | 46.54 | .914 | 4.79 | pass |

All six cases pass unchanged collapse/budget limits. These are window medians,
not a model-ranking benchmark. The previous secured oVDA CPU TC reported 14.26 /
3.16 FPS and 55.09 / 285.83 ms at 1080p / 4K, with controls 53.72 / 44.40 FPS.
Its collapse ratios .265 / .071 are removed by the new shared path. Base's
pre-fix scene FPS was not measured and is not inferred from oVDA.

Normal GPU capture/native correction reports zero steady-state H2D bytes and
21,088 / 39,088 D2H bytes per processed frame at 1080p / 4K, including scene,
border, eligibility and invalid-depth observations. This replaces full-resolution
RGB/depth transfers, not every CUDA/D3D copy. The 4K correction-off observation
is 3,076 D2H bytes/frame. Counts describe explicit submitted copies, not measured
PCIe bus traffic.

Final results and successful completion are recorded in the named
`small-verified/report.json`, `base-verified/report.json`, and
`ovda-verified/report.json` under `out/flat-background-20261110/`.

## Reproduction and build identity

```powershell
./scripts/build-portable-cuda.ps1 -Only flat_background
./scripts/run-uniform-background-tc.ps1 -Model da2-small -WindowCount 2
./scripts/run-uniform-background-tc.ps1 -Model da2-base -WindowCount 2
./scripts/run-uniform-background-tc.ps1 -Model ovda-small-c16 -WindowCount 2
```

GPU depth/native quality tools are `v1/check_flat_background_gpu.py` and
`v1/check_flat_background_native.py` in the prepared Python environment.
`profile_uniform_background.py` explicitly profiles the retained legacy CPU
reference on prepared depth; it no longer patches the product's replaced stage.

Source SHA256: `1d01574eb189254c87ab0ab0d4bec8c700d1ee62a7db74bb64e50f5e54ea7d9e`.
Portable DLL SHA256: `a3b630bf03b0975647a39965896dcb5e407fed0a1de6ec07dbe92d40da0140ad`.
Build: CUDA 13.1/MSVC 2022, `--fmad=false`, native SM120 plus compute_75 PTX.
Only RTX 5090 runtime execution was measured. The DLL is included through the
portable builder's existing pinned-binary inventory; archived ZIPs are not
implicitly rebuilt by this source/local-binary change.

## VDA follow-up TC

The same local entry point now also accepts:

```powershell
./scripts/run-uniform-background-tc.ps1 -Model vda-small
```

This selects ordinary Video Quality/VDA Small with GPU window capture, native
Half TB, uncapped submissions and VFG off. No model/rendering policy or acceptance
threshold was changed for this extension. The installed model is mixed-FP16 v3,
profile 518x924; image/depth/cache bindings remain FP32. The validated pack is
`b4e68c45328e37b601c95f1d06a024c41c510c6c980ba2fcdec5b1030603778f`.
Warmup/cached engine SHA256 values are respectively
`ec5b03a9617e4b7fb5cdadbcc878ac7d67dd082b9ed5106c101c2a245d44e686` and
`376fd4c50d77d02773a595a6038cb4df3ad253c05a2a46ea10ceff961ccaedc9`.

| Run | Source | ON FPS | OFF FPS | ON/OFF | Background ms | TC |
|---|---|---:|---:|---:|---:|---|
| Initial, 4 windows/condition | 1920x1080 | 52.34 | 42.49 | 1.232 | 1.93 | pass |
| Initial, 4 windows/condition | 3840x2160 | 40.99 | 42.49 | .965 | 4.41 | pass |
| Repeat, 6 windows/condition | 1920x1080 | 54.67 | 56.57 | .967 | 1.93 | pass |
| Repeat, 6 windows/condition | 3840x2160 | 41.70 | 45.38 | .919 | 4.33 | pass |

The initial 1080p windows varied substantially (32–54 FPS), so the ordinary
six-window configuration was rerun instead of treating the >1 ratio as a speedup.
Both runs satisfy the unchanged >=.9 ratio and <=8 ms background-stage contract.
The source is fully decoded/hash-checked and remains independent of the original
large video. H2D is zero and D2H is 21,088 / 39,088 bytes per processed frame with
correction at 1080p / 4K. Native stop/cleanup assertions pass in every session.

Important separate observation: in the repeat's 18 measured seconds per condition,
1080p has zero gap-induced history resets in either condition; 4K has 39 with
correction versus one without. The cause and temporal-quality impact were not
isolated here. This throughput TC does not qualify VDA cache continuity, binocular
quality, physical display cadence or long-session behavior. The harness's
`full_context_fraction` counter is oVDA-specific, not VDA cache occupancy; future
non-oVDA reports use null instead of the historical zero value. The VDA extension
does not add VDA to the earlier CPU-reference native-image comparison.

Reports: `out/flat-background-vda-20261110/report.json` and its
`native/report.json` / `artifact.json`; repeat at
`out/flat-background-vda-20261110-r2/report.json` and `native/report.json`.
All seven existing TC unit tests pass (`out/flat-background-vda-unit-20261110.log`),
and the modified Python entry points compile. No new production CUDA binary or
archived distribution was built for this test-only extension.
