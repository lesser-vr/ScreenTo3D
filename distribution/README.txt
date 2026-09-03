DepthSBS v1 Release Candidate
=============================

Requirements
------------

- Windows 11 64-bit
- NVIDIA GPU supported by TensorRT 11.2
- Current NVIDIA display driver
- Approximately 1 GB free disk space plus output video space

The CUDA Toolkit, TensorRT SDK, Python, and FFmpeg do not need to be installed.
Required application runtime files are included in this portable directory.

Usage
-----

Run DepthSBS.exe, select an input video, select an MP4 output path and mode,
then press Convert. The first run can take tens of seconds while an optimized
engine is built for the installed GPU. Later runs reuse the engine in:

  %LOCALAPPDATA%\DepthSBS\engines

The output is full side-by-side H.264 MP4 with AAC audio when the source has an
audio stream.

Modes
-----

- Performance: depth inference every second frame, fastest encode.
- Balanced: full-rate depth and practical default settings.
- Video Quality: stronger temporal smoothing and higher encode quality.
- Offline Quality: strongest stereo effect and highest encode quality.

All V1 modes use Depth Anything V2 Small. They differ in end-to-end processing
policy, not model identity.

Limitations
-----------

- NVIDIA GPU/driver required; there is no silent CPU fallback.
- H.264 full-SBS MP4 output only.
- HDR and rotation metadata preservation is not complete.
- The V1 stereo stage is CPU-based and is not a zero-copy pipeline.
