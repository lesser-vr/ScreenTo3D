# VFG access and fixture preparation — 2026-11-05

Scope: independent 2x Maxine VFG experiment requested by the user; no product
backend/default change. This is access/preparation evidence, **not VFG execution**.

## Observed

- Official sample source cloned into `out/vfg-official-samples-20261105`, revision
  `52011f89c1741d06b40ea312af1f20be8be9ec62`. `GIT_LFS_SKIP_SMUDGE=1` avoided
  unnecessary sample media downloads. LFS pointers are not usable sample movies.
- The sample requires `nvVFXVideoFrameGeneration:1.3.0.0`. Source is MIT. Core
  runtime/headers and the feature model are separately distributed through NGC.
- No Maxine/VFX SDK was found in the inspected local output/install locations;
  no NGC CLI/config or relevant credential environment-variable names were found.
  This was a targeted inventory, not a search of all drives or browser sessions.
- An initial incorrect REST route returned 404; it is not an access diagnosis.
  The corrected official API route
  `https://api.ngc.nvidia.com/v2/org/nvidia/team/maxine/resources/vfx_sdk_core/versions`
  returned **401 Not Authenticated**. Local response:
  `out/vfg-access-20261105/core-access-v2.json`. No credential was sent or logged.
- The guest catalog requires access and lists NVIDIA Developer Program alongside
  AI Enterprise. This does not establish that a paid subscription is required.
- The user was asked for an existing official SDK location or local NGC credential
  setup, without disclosing an API key in chat.

## Completed checks

`experiments/vfg/prepare_fixtures.py` produced 9 synthetic cases / 27 PNGs at
640x180, 3840x1080 and 7680x2160 Full SBS. All 27 lossless pixel round trips pass;
translation midpoint and disparity crop equalities pass. Identity, translation
and manual-cut references are described in the experiment README.

Manifest and inputs: `out/vfg-fixtures-20261105/manifest.json`.
Ruff E9/F with target Python 3.12 passes for the generator.

## Not measured

No VFG model was downloaded or loaded; no native VFG executable was built or run.
7680x2160 acceptance, VFG processing cost, native FPS, latency, automatic cuts,
buffer lifecycle and binocular output quality remain unmeasured. Fixture
verification validates inputs only. RTX 5090 being in the documented hardware
family does not establish acceptance of Full SBS or a target frame rate.

Sources accessed 2026-11-05:

- [SDK installation](https://docs.nvidia.com/maxine/vfx/latest/WindowsVFXSDK/InstalltheVFXSDK.html)
- [Core catalog/access](https://catalog.ngc.nvidia.com/orgs/nvidia/maxine/resources/vfx_sdk_core/-)
- [VFG API](https://docs.nvidia.com/maxine/vfx/latest/Filters/VideoFrameGeneration.html)
- [Pinned official sample](https://github.com/NVIDIA-Maxine/VFX-SDK-Samples/tree/52011f89c1741d06b40ea312af1f20be8be9ec62/apps/VideoFrameGenerationEffectApp)
