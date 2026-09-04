# User-provided short clip validation

Status: Four-mode smoke passed; long-media and visual quality gates remain open
Date: 2026-09-04

The user supplied a local clip for the pending real-input validation. Input:
H.264, 1056x608, 24 fps, 124 frames, 5.166667-second video, AAC stereo at 32000 Hz
with 5.167000-second audio. No source file was modified; SHA256 matched the
recorded input hash after all four conversions. Source path and metadata remain
in ignored local artifacts, not this document.

Performance, Balanced, Video Quality and Offline Quality each completed using
the packaged application and process-tree soak harness. All outputs contained
2112x608 video, 124 frames at 24 fps, and one audio stream. Process-tree probes
reported no errors (3-4 samples per run). The clip is too short to establish
memory stability, and single-run timings are not performance baselines.

Output audio duration was 5.152000 seconds in every mode, approximately 15 ms
shorter than the input audio and 14.7 ms shorter than output video. Audio
presence is verified, not sample-exact audio preservation or perceptual sync.
Visual stereo comfort/depth quality has not been accepted by this smoke test.

Local result directories under out/soak (each has result.json and output.mp4):

- Performance: 560b5ec271d048819bd0fa804f00fcae
- Balanced: 4d54d712314645f5b5d99776ec1dceed
- Video Quality: e416e268d3a242a2a71bb54b91334857
- Offline Quality: 2e10a2f7ce4a4e8cb0bd3826dd229ea1

Next: obtain longer representative footage for sustained validation; review
the generated SBS perceptually and assess the audio-duration tolerance.
