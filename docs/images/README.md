# README images

The English and Korean READMEs use the same stereo example and separate localized
screenshots. These assets illustrate the app; they do not replace the numerical
quality evaluation or certify viewing comfort, frame rate or another GPU.

## Stereo example and attribution

Source: **Spring: A High-Resolution High-Detail Dataset and Benchmark for Scene
Flow, Optical Flow and Stereo**, Lukas Mehl, Jenny Schmalfuss, Azin Jahedi,
Yaroslava Nalivayko and Andrés Bruhn, 2023. DaRUS V2,
[doi:10.18419/DARUS-3376](https://doi.org/10.18419/DARUS-3376).
[Dataset website](https://www.spring-benchmark.org/).
The scene assets originate from
[Spring, Blender Foundation / Blender Studio](https://studio.blender.org/films/spring/).
Dataset and film assets are credited under
[Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).

The input is training sequence `0001`, left-camera frame `0064`. All 64 sequential
frames are processed through the normal Small GPU preprocessing and live native
Half TB path, with strength 0.5, VFG off and the ordinary comfort policy enabled.
The model receives only the left-camera RGB; no original right-camera image,
ground-truth depth, metric fitting or benchmark camera calibration is used.
The fixture clock is 60Hz; this is not an actual playback/FPS measurement.

| Asset | Contents / changes |
|---|---|
| `spring-original.png` | Original RGB re-encoded losslessly at 1920×1080; no resize/crop |
| `spring-half-tb.png` | Actual native RGBA texture converted to PNG RGB at 1920×1080; left above right, 1920×540 per stored eye; no restoration, label or overlay |
| `spring-*-preview.webp` | 960×540 web previews, area reduction, lossy WebP quality 88; click through to the PNG for playback |

[example.json](example.json) records the source SHA256, model/settings, native
output geometry, generation revision and image hashes. Both eyes differ, and
the packed PNG was decoded and compared exactly with the native RGB pixels.
The source and generated stereo/example previews retain the attribution above;
these third-party images are not relicensed by the repository's code license.

## App screenshots

`en/ui-live.png` and `ko/ui-live.png` show a running production app, not a mockup.
An owned Spring player is the only enumerated capture source. A real native
Small/Half TB session has delivered at least 12 frames before screenshots are
taken. Language switching retains that same session. No other application window
or desktop content is captured.

`en/ui-files.png` and `ko/ui-files.png` show a real queued Spring clip, default
Base/Half TB, strength 0.5, VFG off and automatic shutdown off. The file window
is enlarged so strength, VFG and shutdown controls are all visible. A relative
example destination omits local user directories. The queue is not started and
no completed-file or performance state is simulated. Shutdown calls are forbidden
by the capture harness. Screenshot PNGs are unretouched Qt client-area captures
at 150% scaling; native title bars and the rest of the desktop are not included.

[ui.json](ui.json) records the capture revision, dimensions and hashes. Application
UI assets follow the repository's own license; the Spring input remains credited
above. The main screenshots contain only the public source title, not source pixels.

## Reproduction

Use the prepared local Windows GPU/Qt environment and the existing trusted model,
native runtime and Spring left-camera subset. This script never downloads models
or the dataset. Set the same isolated dependencies used by local validation:

```powershell
$env:PYTHONPATH = 'out/sbs-quality-python-deps;out/spring-python-deps;experiments/ovda;v1;out/gui-python-deps;out/capture-python-deps;out/ovda-python-deps;out/v1-python-deps'
& .\out\vda-oracle-env\Scripts\python.exe scripts/prepare-readme-images.py
& .\out\vda-oracle-env\Scripts\python.exe scripts/prepare-readme-images.py --ui
```

The first command publishes only the documented still images; the second opens
the actual app and its owned player temporarily and closes its live session on
completion. Screenshot preferences and the temporary clip stay under ignored
`out/readme-capture-20261111/`. Normal user preferences and outputs are preserved.
