# Uniform-background regression media

`uniform-background.json` owns **TC-UBG-01**, the compact natural-video case.
The secured local asset is `local/uniform-background/flower.mp4`: 1.5 seconds,
90 frames at 60 Hz, 3840x2160 H.264/BT.709 SDR, 7,797,055 bytes (~7.4 MiB).
It contains the flower following the supplied OLED video's 01:04 transition
(source excerpt 65.2–66.7 seconds). It is an independent copy: neither test
execution nor asset validation reads or requires the original full-size file,
its drive, or the earlier exploratory `out/` directory.

The fixture is a local user-supplied derivative, not redistribution-cleared
public corpus material. Its bytes are retained under the ignored `local/`
directory; source paths and media are not uploaded by public CI. Copy this small
fixture directory when moving the local GPU TC to another prepared machine.
If absent/corrupt, the TC fails explicitly; it does not download the original,
silently skip, or substitute an easier public scene.

Run the secured natural-video TC in the prepared local environment:

```powershell
./scripts/run-uniform-background-tc.ps1
./scripts/run-uniform-background-tc.ps1 -Model da2-base
./scripts/run-uniform-background-tc.ps1 -Model da2-small
./scripts/run-uniform-background-tc.ps1 -Model vda-small
./scripts/run-uniform-background-tc.ps1 -MediaOnly
```

The first command validates clip size/SHA256, decodes all frames, verifies that
sampled frames still qualify as a uniform backdrop plus foreground object, then
uses actual WGC/native Half TB with the selected Small, Base, VDA or oVDA at
1080p and 4K. It compares ordinary product
policy with a diagnostic correction-off control in reversed session order, six
3-second windows per condition after warmup. User preferences are isolated.
The normal condition does not force the legacy correction on: a future intentional
policy change is exercised as implemented.
This native entry point defaults to oVDA's Video Quality policy; `-Model da2-base`
targets Base's Balanced policy and `-Model da2-small` targets Small's Performance
policy; `-Model vda-small` targets VDA's Video Quality policy. Each invocation
compares its ordinary correction-enabled policy with its
own diagnostic correction-off control. Historical Small policy disabled correction
to avoid the old CPU path; the new GPU policy shares the correction across models.

The performance contract in the manifest requires normal/control FPS ratio >=0.9
and background-stage median <=8 ms, with >=4 windows per condition and control
FPS >=20. These are scoped collapse/frame-budget checks, not certification of
sustained 4K60 or binocular quality. Missing measurements or a source-limited
control cannot count as a pass. Failure/inconclusive returns nonzero; media-only
success is labelled separately and does not pass the performance case.

**TC-UBG-CI** is a repository-owned moving silhouette/thin-line counterpart,
generated on demand by `uniform_background_tc.generated_media()`. It runs in the
existing real media-contract CI entry point, which encodes and decodes the short
video and checks its triggering pattern. CPU quality contracts also verify the
pattern, correction behavior, missing/corrupt assets and performance evaluator.
These CPU/CI checks do not stand in for the actual GPU performance TC.
