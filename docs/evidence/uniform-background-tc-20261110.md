# Secured uniform-background video TC — 2026-11-10

**TC-UBG-01** now has an independent, pinned copy of the exact flower shot:
`tests/media/local/uniform-background/flower.mp4`, 1.5 seconds/90 frames at 60 Hz,
3840x2160 SDR H.264, 7,797,055 bytes. SHA256:
`7dd8e5d27a576ca37b94ca61710234532d3031fd29bfc4af1069309d0843575e`.
It is copied from the already inspected 65.2–66.7-second derivative. The original
large file, external drive/path and old `out/` diagnosis files are not dependencies.
The local clip is ignored by Git; the tracked manifest contains no private source
path. Redistribution clearance is not inferred from local test authorization.

The case/limits are owned by `tests/media/uniform-background.json`; commands and
fixture handling are in `tests/media/README.md`. Full validation checks SHA256 and
size, decodes all 90 frames and verifies backdrop/foreground eligibility at four
points. All four qualify (border ~98.5–98.6%, matching backdrop ~90.2–92.1%).

The native TC uses actual ordinary oVDA policy, GPU capture, native Half TB,
1080p/4K windows and an OFF diagnostic control. It does not force normal policy
back to a legacy algorithm. It measures normal/OFF/OFF/normal sessions with
three 3-second windows each after warmup: six windows per condition/size.
Performance passes require normal/control FPS >=0.9 and median background stage
<=8 ms. Missing/insufficient/invalid measurements and a control below 20 FPS
cannot count as passed. This detects both a visible collapse and an expensive
stage hidden behind a source-rate ceiling. These are scoped regression criteria,
not a sustained-4K60 or binocular-quality standard.

## Executed results

- Seven new case/evaluator tests pass in the real CPU quality-contract group.
  Quality group: 88 tests pass. Platform/profiles: 198 tests pass after classifying
  five previously unlisted test modules as required by the existing runner.
- `test_media_contracts.py`, already invoked by public CI, now generates and
  encodes **TC-UBG-CI**, an owned moving object/thin-line scene on black. Its
  24-frame 60 Hz video fully decodes and all four sampled frames qualify. Existing
  file success/cancel/failure/audio/PTS cases also pass.
- Natural-media integrity/full decode/pattern checks pass independently.
- The new PowerShell/native entry point completed all eight normal/control
  sessions using only the short secured clip. **Performance status is FAILED,
  exit code 1**, detecting the still-unfixed product bottleneck:

| Window | Normal median FPS | Control median FPS | Ratio | Median background stage |
|---|---:|---:|---:|---:|
| 1920x1080 | 14.26 | 53.72 | 0.265 | 55.09 ms |
| 3840x2160 | 3.16 | 44.40 | 0.071 | 285.83 ms |

The source/decode/capture conditions vary from the initial exploratory diagnosis;
these are within-run paired TC results, not maximum-FPS or physical-scanout claims.
No product processing, model, precision or default correction was changed here.
Resolved policy inspection also confirms Small/Performance disables correction,
whereas oVDA/Video Quality and Base/Balanced enable it. This explains why the
reported Small observation differs; it is not an actual Base FPS measurement.
The successful CPU/media contracts do not turn the failed GPU performance case
green. Natural-video GPU coverage is local and is not claimed to execute on the
GPU-less public CI runner.

Artifacts under `out/uniform-background-tc-20261110/`: `media/report.json`,
`media-ci/report.json`, `quality-contracts-r2.json`, `registry-contracts.json`,
`performance/report.json` and full `performance/native/report.json`.
