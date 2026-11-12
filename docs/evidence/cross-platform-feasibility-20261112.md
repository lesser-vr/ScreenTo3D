# macOS / Linux support feasibility

Reviewed 2026-11-12 against `b3b76868eb9348c9a74228591a8521acf417eaaa`.
Evidence: local source inspection and official platform documentation. No macOS
or Linux application build, device test or performance measurement was performed.
This is a feasibility review, not a support declaration or implementation plan commitment.

## Recommendation

Both platforms are technically feasible. Start with **Linux x86_64 + NVIDIA**,
then **Apple Silicon macOS**. Retain the Qt/QML interface and separate platform
dependencies behind the existing worker/backend boundaries. Rebuilding the UI
would not remove the actual capture, compute and presentation work.

File conversion is the smaller first deliverable on either platform because it
does not require desktop capture or live GPU texture transport. It still needs
platform-specific inference, encoder selection, native libraries and packaging.

| Area | Linux + NVIDIA | Apple Silicon macOS |
| --- | --- | --- |
| Qt/QML interface | Largely reusable; choose a supported rendering backend | Largely reusable; use Metal rendering |
| Depth inference | Rebuild/use Linux CUDA and TensorRT components | Add Core ML inference; validate DA2 Small first |
| Stereo and depth postprocessing | Rebuild applicable CUDA kernels; replace Windows exports/loading | Implement equivalent GPU processing with Metal |
| Live capture | ScreenCast portal + PipeWire on Wayland | ScreenCaptureKit |
| Native live output | New Vulkan/OpenGL texture transport and synchronization | New Metal texture transport and synchronization |
| VFG | Linux SDK exists; separate integration and GPU/version validation needed | Current NVIDIA SDK route unavailable; leave disabled initially |
| Distribution | New Linux runtime packs, library paths and build/CI target | New arm64 app/runtime packs and distribution workflow |
| Relative effort | File conversion: medium; real time: high | File conversion: high; real time: very high |

Effort is qualitative, relative to the current Windows implementation. There is
no measured FPS or delivery-time estimate. Linux AMD/Intel GPUs and Intel Macs
should be separate targets rather than implied by initial platform support.

## What currently prevents running unchanged

- `v1/depthsbs_app/capture_sources.py` loads `user32` and `dwmapi` at import time.
  Window identities, enumeration and output recursion markers are Win32-based.
- `v1/depthsbs_app/desktop.py` unconditionally selects Qt Direct3D11 rendering.
- `experiments/cuda_projection/gpu_capture.cpp` implements Windows Graphics
  Capture -> D3D11 -> CUDA. That interop path must be replaced on both platforms.
- `experiments/cuda_projection/qt_native_delivery.cpp` uses Windows shared
  handles, D3D11 textures, DXGI adapter identities and keyed mutexes. Qt itself
  being portable does not make this consumer portable.
- CUDA compute sources such as `base_input.cu` also use Windows export syntax.
  Linux can retain much of the computation, but requires portable exports,
  `.so` builds, dependency verification and stream/lifetime validation.
- `engine_cache.py` uses the Windows CUDA driver loader and DPAPI-protected
  engine receipts. Other platforms need equivalent trusted artifact handling;
  an adjacent self-declared checksum is not equivalent provenance.
- Runtime catalogs, native module pins, FFmpeg executable discovery, worker
  validation and VFG loading currently describe Windows binaries/layouts.
- `src/platform/windows_nvidia_probe.cpp` explicitly reports non-Windows as
  unsupported. The portable-looking CMake core is not the complete desktop app.

Reusable policy includes job queues/cancellation, atomic output publication,
stereo layout definitions, temporal reset rules, settings/localization/error IDs,
and much of QML. The socket-pair/QSocketNotifier frame wakeup is also a useful
shared foundation. GPU memory, completion and texture leases still need explicit
backend contracts rather than assuming every native buffer is a CUDA buffer.

## Linux scope and constraints

TensorRT provides a Linux route, but **Windows serialized engines cannot be reused
on Linux**. Retain the trusted ONNX source and build/validate engines on the target
platform/device with new runtime pins and cache receipts. Official documentation
establishes the platform route, not validation of our exact pinned dependency set.
See the [TensorRT support matrix](https://docs.nvidia.com/deeplearning/tensorrt/latest/getting-started/support-matrix.html).

For Wayland, source selection should use the system portal rather than reproduce
Win32 window enumeration. Monitor/window availability depends on the installed
portal backend; streams arrive through PipeWire. Start with a named distribution,
compositor and NVIDIA driver combination and expand after testing. X11 is a
separate capture path, not proof of Wayland support.
See [ScreenCast portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.ScreenCast.html).

The Linux VFX SDK exists, but NVIDIA describes it as optimized for server-side
deployments. Linux VFG needs a matching SDK/model, `.so` bridge, supported GPU and
end-to-end desktop validation. Keep it disabled for the first port rather than
infer readiness from Windows success.
See [VFX SDK introduction](https://docs.nvidia.com/maxine/vfx/latest/index.html)
and [VFG filter](https://docs.nvidia.com/maxine/vfx/latest/Filters/VideoFrameGeneration.html).

## macOS scope and constraints

Use **DA2 Small on Apple Silicon** as the first inference experiment. A candidate
is ONNX Runtime's CoreML execution provider, followed by a native Core ML binding
if profiling justifies it. Check operator coverage, partition boundaries, CPU
fallback, tensor transfers and FP16 depth/stereo quality. Selecting all compute
units does not prove the entire model runs on the Neural Engine.
See [CoreML execution provider](https://onnxruntime.ai/docs/execution-providers/CoreML-ExecutionProvider.html).

Capture can use ScreenCaptureKit with the system content picker and explicit
screen-recording permission. Own-output exclusion and recursion prevention need
new platform-specific validation. Filtering our own capture is not a guarantee
that other applications cannot record our windows.
See [ScreenCaptureKit](https://developer.apple.com/documentation/screencapturekit).

Metal is required for the proposed GPU preprocessing, stereo and output route.
Qt exposes native texture import for both Metal and Vulkan, so retaining QML
does not require routing every completed frame through host images. Texture
ownership, render-thread use and completion synchronization remain our work.
See [Qt Metal textures](https://doc.qt.io/qt-6/qnativeinterface-qsgmetaltexture.html)
and [Qt Vulkan textures](https://doc.qt.io/qt-6/qnativeinterface-qsgvulkantexture.html).

Add macOS encoder capability selection instead of assuming NVENC. Unified memory
does not establish zero-copy execution. VDA/oVDA temporal state and mixed precision
need independent validation after Small; they are not initial-port prerequisites.

## Suggested delivery order and acceptance

1. Separate platform services, capture, inference, stereo compute and presentation
   implementations with narrow interfaces. Keep Windows behavior and its bounded
   resource/error contracts intact; avoid a simultaneous rewrite of every layer.
2. Deliver Linux/NVIDIA file conversion with Small, then add live capture/output
   on one declared desktop environment. Add other models and VFG after validation.
3. Prove Apple Silicon Small inference plus Metal stereo, then file conversion
   and live capture/output. Change order if macOS is the higher product priority.

Each OS/architecture requires its own native binaries, runtime manifests,
integrity checks, model/cache compatibility identities, notices and packaging.
Optional-model download policy can be reused; Windows runtime ZIPs cannot.
Global shortcuts, GPU telemetry, power actions, capture permission/revocation,
display hotplug and scaling need explicit capability checks and appropriate UX.
Do not imply parity for unavailable features or silently fall back to CPU.

Validate numerical depth/stereo parity, all four output layouts, source resize
and loss, cancel/restart and atomic file publication. Measure capture-to-display
latency, fresh/output FPS, GPU use and memory on actual hardware. Declare per-eye
versus packed resolution; do not promise the 4K-per-eye/60-fps product target from
inference timing alone. Check monitor capture feedback/privacy separately.

Producing SBS/TAB on another OS does not establish Owl3D or Quest viewing-stack
compatibility. Display software support and physical stereo comfort require
separate device tests. No such compatibility claim is made by this review.
