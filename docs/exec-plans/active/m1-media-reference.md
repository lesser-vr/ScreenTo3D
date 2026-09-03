# M1 media reference oracle

Status: Active

## Outcome

Establish a deterministic, generated-media reference path before native FFmpeg,
NVDEC, and NVENC integration. The oracle validates container finalization,
dimensions, frame count, duration, audio preservation, and atomic publication.
It is not a performance or zero-copy path.

## Current implementation

`scripts/media-smoke.ps1`:

1. generates two one-second 1280x720@30 H.264 shots with a hard cut;
2. adds a two-second 48 kHz AAC tone;
3. creates a deterministic duplicate-eye 2560x720 SBS reference;
4. encodes video with NVENC and copies audio;
5. probes the temporary output with ffprobe;
6. validates one video stream, one audio stream, dimensions, 60 frames, and
   approximately two seconds of duration;
7. writes a machine-readable report and only then publishes the final output.

Canonical command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\media-smoke.ps1
```

Generated artifacts live under `out/media-smoke/` and are ignored by git.

## Limitations

- FFmpeg is an executable dependency discovered on `PATH`; native headers and
  libraries are not installed in the current environment.
- The SBS image duplicates the source into both eyes and does not estimate depth.
- Filtering is not GPU-zero-copy and cannot support performance claims.
- The first implementation is Windows PowerShell-only.

## Next steps

- Pin a reproducible FFmpeg development dependency with libavformat/libavcodec.
- Define validated C++ media descriptors and native probe/demux boundaries.
- Reproduce the oracle's stream, frame, duration, and atomic-publication checks in
  the native pipeline.
- Add non-trivial PTS and corrupt-input fixtures.
