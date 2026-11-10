# Maxine VFG 2x execution — 2026-11-05

## Result and scope

Official NVIDIA VFX SDK/VideoFrameGeneration 1.3.0.0 executes at **7680x2160 Full
SBS** on the local RTX 5090 / driver 621.14. Low, Medium and High all load/run.
Medium is a reasonable candidate for a subsequent native-output prototype.
This is a standalone post-SBS interpolation experiment, not native app FPS,
display latency, continuous perceptual acceptance or a new default backend.

## Provenance and setup

- User downloaded Core through NGC:
  `%USERPROFILE%/vfx_sdk_core_v1.3.0.0_windows/VFXSDK_windows_1.3.0.0.zip`,
  1,063,840,846 bytes, SHA-256
  `468198eb68a72f995a061068b03f7dfc6600b7e9623add148a2378894295cab5`.
- Extracted under `out/vfg-sdk-1.3.0.0/VideoFX`; original archive preserved.
- NGC CLI 4.36.6, using the user's existing authenticated email-login session,
  downloaded `nvidia/maxine/nvvfxvideoframegeneration:1.3.0.0_lib_windows`.
  Feature ZIP SHA-256:
  `97aaac0bdbc0db24fbc4637c9a3c846c2e4a3d4c47fb06f21d9c8b20cd93d101`.
  Library-only version listing contained Windows/Linux/WoA variants, no separate
  SM120 package; this library package sufficed for execution. No Veyra DLL used.
- First CLI download reporting failed with CP949 encoding of a progress glyph.
  UTF-8 environment plus JSON output completed the retry. No key was printed.
- MSVC 19.51 / CUDA Toolkit 13.1.80 built `experiments/vfg/probe.cpp` against
  official headers and official SDK proxy sources. Runtime includes the official
  Core's CUDA 12/TRT 10 dependencies in an isolated process, separate from the
  app's TensorRT 11 pipeline. No global SDK/runtime installation was changed.
- Binary hashes are in each `provenance.json`, with the three loaded SDK DLLs
  also checked against pins by the runner. Measured probe executable SHA-256:
  `72501d8ef84b5ecccf3d0ce8e08f8b33f19eb4cb2690ea6cfc298e8a299face0`.
- Official sample reference revision:
  `52011f89c1741d06b40ea312af1f20be8be9ec62` (MIT sample/proxy source).
  SDK/feature licenses are retained in their `license` directories, including
  NVIDIA Software License, AI Product Specific Terms and Open Model License
  PDFs. This local experiment does not clear redistribution of SDK/models.

## Method

GPU RGBA8 inputs/output, one explicitly owned nonblocking CUDA stream, multiplier
2, frame index 1. Both inputs are rebound for every pair/repetition, including
unchanged buffer addresses, as required by the official sample. The output is
consumed before reuse. Manual cut is reset for the next pair. Owned work drains
before teardown; a timeout kills only the probe's owned process.

Each shape/mode uses five warmup calls then five groups of ten calls. CUDA event
elapsed time covers bind/run on the owned stream; wall time covers host submission
and event completion. These are not summed kernel durations. PNG I/O and input/
output transfers are outside the timed region. Timings reuse one fixed translated
pair with explicit rebind; this is not a long changing-video workload. Cold/load
time is separate. Main matrix load time ranges 14.98–292.38ms; the earlier Medium
smoke load was 334.00ms. The runner records failures rather than silently resizing.

## Synthetic geometry and timing

9 configurations: 3 Full SBS sizes x 3 modes. Identity, integer plane translation,
manual cut and post-cut translation are read back. Inputs were independently
validated by lossless round trip and exact midpoint/disparity crop equalities.

| Full SBS | Low GPU ms | Medium GPU ms | High GPU ms |
|---|---:|---:|---:|
| 640x180 | 0.293 | 0.830 | 2.134 |
| 3840x1080 | 0.549 | 2.248 | 10.729 |
| 7680x2160 | 0.997 | 2.718 | 11.410 |

All nine manual cuts copy current exactly; post-cut translation equals its pre-cut
result exactly. Identity is not guaranteed bit-exact by VFG. Nonzero binocular
residual remains: at 7680x2160, disparity-aligned translation MAE (0..255) is
1.172/0.625/0.824 for Low/Medium/High (rounded). This is a controlled plane only.

Artifacts: `out/vfg-smoke-20261105`, `out/vfg-matrix-20261105`,
`out/vfg-fixtures-20261105`.

## Held-out public Base FP16 SBS

Three hash-verified UVG-VCM clips: FloorballGame, OfficeWalk, ParkingGarage.
Attribution: Ultra Video Group, Tampere University; CC BY 4.0; T. Partanen et al.,
UVG-VCM, QoMEX 2026. Source links/hashes and modification notices are retained in
`out/vfg-public-inputs-final-20261105/provenance.json`.

Prepared 1920x1080 compressed 60fps previews are linearly upscaled to eye-4K.
This is full-sized processing, not native 4K source-detail evidence. Current Base
FP16 plan, Balanced policy and native texture readback produce frames 54..62;
54..59 warm the temporal state, 60/62 are interpolation endpoints, and 61 is the
held-out reference. Every prepared frame is newly inferred/rendered, with no
VFG in the reference. Endpoints thus have 60fps depth histories; this does not
simulate the depth history of a real 30fps app session.

First preparation attempt failed because the test harness did not acknowledge
warmup texture slots. It is retained in `out/vfg-public-inputs-20261105` and is
not evidence. Readback/acknowledgment now occurs for every prepared frame; the
successful rerun covers all three clips and all 27 rendered frames.

Per-mode medians across the three isolated clip measurements:

| Mode | GPU ms/generated frame | Observed clip-median range | Host completion ms |
|---|---:|---:|---:|
| Low | 0.999 | 0.995–1.003 | 1.047 |
| Medium | 2.706 | 2.706–2.707 | 2.762 |
| High | 11.421 | 11.383–11.487 | 11.527 |

RGB MAE against the held-out SBS, in 0..255 values (lower is better):

| Clip | Previous-frame hold | Endpoint average | Low | Medium | High |
|---|---:|---:|---:|---:|---:|
| FloorballGame | 5.047 | 4.018 | 1.598 | 1.423 | 1.391 |
| OfficeWalk | 16.005 | 13.338 | 4.268 | 4.128 | 4.054 |
| ParkingGarage | 0.778 | 0.494 | 0.539 | 0.371 | 0.365 |

Medium beats hold and blend in these three triplets. Low does not beat blend on
ParkingGarage. High slightly reduces overall error but costs about 4.2x Medium.
These are only three midframes, not aggregate video/perceptual quality rankings.
Readbacks, eye/seam errors and logs are in `out/vfg-public-<clip>-20261105`.
All nine manual-cut and post-cut equality checks pass.

## Cut and split-eye findings

Automatic detection was tested separately. On the synthetic inversion cut,
Medium returns previous exactly; Low/High are neither exact endpoint copies.
On the OfficeWalk-to-ParkingGarage cut, automatic Medium also returns previous
exactly. Therefore an assumed automatic `copy current` policy is false for these
conditions. Holding previous may be a valid interpolation cut convention; the
test does not establish the SDK's internal detection state or general accuracy.
Native integration needs a shared, explicit cut/timestamp policy for both eyes.
Artifacts: `out/vfg-auto-cut-20261105`, `out/vfg-public-auto-20261105`.

OfficeWalk Medium was also processed as two independent 3840x2160 eye inputs
with the same midpoint and manual cut settings. Combined vs split-eye MAE:
4.128 vs 4.130 overall; 8.387 vs 6.561 in the 16-pixel center seam band. Thus the
boundary improves in this case without an overall error benefit. The two isolated
eye GPU medians sum to 3.946ms vs 2.706ms for combined SBS. This sum is **not** a
measured two-instance app session or concurrent throughput. Independent eye
errors and continuous binocular quality remain unqualified.
Artifacts: `out/vfg-eye-{0,1}-20261105`, `out/vfg-eye-comparison-20261105.json`.

## Verification and remaining limits

Build passes; Ruff E9/F Python 3.12 passes for all experiment Python files.
25 bounded probe processes complete successfully across smoke, main matrices,
automatic cuts and eye splitting. This is not integrated resource-leak or
device-loss testing. SDK subprocesses exit before the next GPU workload.

No app/native delivery code changed. Unmeasured: actual original/generated native
presentation FPS, pair age/end-to-end latency, lookahead scheduling, depth/VFG GPU
contention, continuous changing-pair performance, pooled-output ownership during
resize/stop/restart, long-run memory and real game/Owl3D/HMD acceptance. Direct
continuous visual/binocular review was not performed. Do not multiply the prior
app FPS by two or infer app FPS from these isolated milliseconds.

Official references:
[VFG API](https://docs.nvidia.com/maxine/vfx/latest/Filters/VideoFrameGeneration.html),
[SDK install](https://docs.nvidia.com/maxine/vfx/latest/WindowsVFXSDK/InstalltheVFXSDK.html),
[pinned sample](https://github.com/NVIDIA-Maxine/VFX-SDK-Samples/tree/52011f89c1741d06b40ea312af1f20be8be9ec62/apps/VideoFrameGenerationEffectApp).
