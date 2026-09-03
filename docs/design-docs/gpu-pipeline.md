# GPU pipeline design

Status: Proposed  
Owner: Pipeline  
Last reviewed: 2026-09-03

## Objective

Build the smallest instrumented pipeline that can answer: how much faster and
more stable can a native NVIDIA path convert 2D video to SBS than the reference
workflow, and which stage limits each mode?

## V1 data path

```text
container bytes
  -> FFmpeg demux
  -> NVDEC surface
  -> CUDA preprocess / model tensor
  -> TensorRT depth
  -> depth normalize
  -> CUDA stereo synthesis
  -> NVENC surface
  -> FFmpeg mux
```

Audio is outside the pixel pipeline. The first implementation must explicitly
choose copy, transcode, or omit behavior and test A/V duration and sync.

The initial correctness path may use a documented copy or CPU reference when a
direct interop path is not ready. Such a path must emit a copy counter and remain
separate from zero-copy benchmark claims.

## Stage contracts

### Probe and demux

Validate codec, coded/display dimensions, time base, frame-rate representation,
pixel format, bit depth, color range/primaries/transfer, rotation, duration, and
audio streams before allocating long-lived resources.

### Decode

Produce ordered GPU-visible YUV frames with frame ID and PTS. Decoder surface
pool size is bounded and included in the memory budget.

### Preprocess

Fuse color conversion, resize, normalization, and layout conversion when this is
demonstrably correct and faster. The reference implementation keeps each step
independently testable.

### Depth

The backend contract returns depth, validity/confidence where available, native
resolution, normalization metadata, and temporal-state status. Engine creation
is not part of per-frame timing, but startup time is reported separately.

### Temporal policy

V1 supports full-rate inference. Experiments may add every-N-frame inference and
motion-compensated depth propagation. A propagated frame is tagged with source
depth frame ID, propagation distance, and confidence.

Adaptive inference may reduce work for static scenes and force inference after a
large change. It is not enabled by default until cut/reset behavior and quality
thresholds are validated.

### Stereo synthesis

Start with one deterministic symmetric SBS baseline. Inputs are normalized depth,
divergence, convergence, depth scale, and validated output geometry. V2 adds edge
dilation, occlusion-aware handling, EMA normalization, and alternative symmetric
or forward-warp kernels based on golden comparisons.

### Encode and mux

Encode to H.264 or H.265 with explicit pixel format, rate control, preset/tuning,
GOP, and metadata policy. Reorder output by PTS/DTS rules and finalize through an
atomic publication strategy so cancellation does not leave a valid-looking file.

## Scheduling experiments

Implement and measure in this order:

1. deterministic single-frame-at-a-time oracle;
2. bounded decode/process/encode queues;
3. decode and encode overlap with compute;
4. separate CUDA streams where traces show independent work;
5. temporal propagation cadence;
6. graph capture or kernel fusion only for a measured launch/synchronization cost.

Each step keeps the previous path as an oracle until output, timestamps, errors,
and cancellation behavior match.

## Memory budget

Report fixed engine memory, decoder/encoder surfaces, frame pools, tensor/depth
buffers, temporal cache, and peak transient allocation separately. The pipeline
must reject a plan before work begins when the estimated committed memory exceeds
the configured device budget.

V1 has no per-frame device allocation in steady state after warmup. Deviations
are tracked as technical debt with profiler evidence.

## Failure boundaries

- malformed or unsupported media: fail during probe;
- unsupported device/driver/codec: fail during capability resolution;
- engine mismatch: rebuild explicitly or fail with the incompatible fields;
- out of memory: cancel the graph, release resources, and preserve no final file;
- decode corruption: report frame/PTS and follow an explicit abort policy;
- temporal discontinuity/cut: reset state and mark the first re-primed frame;
- encode/mux failure: abort publication and retain diagnostic metadata.

## Rejected shortcuts

- Unbounded queues to make short benchmarks appear faster.
- Comparing TensorRT kernel time with another tool's end-to-end elapsed time.
- Calling host-pinned transfers “zero-copy” without trace evidence.
- Adding model-specific types or conditions to the scheduler.
- Using propagation on cuts or low-confidence motion merely to preserve fps.
