# Standard LR stereo geometry correction — 2026-11-06

## Report and cause

After independent native-window ownership fixed Owl3D SBS recognition, the user
confirmed that stereo worked but near/far viewing was uncomfortable. Strength
0.50x improved it somewhat; Owl3D Live 3D still looked deeper and comfortable.
This is user feedback, not a matched measurement of Owl3D's depth algorithm.

The backend contract is `larger_is_nearer`. Forward splatting uses
`destination_x = source_x + shift`, but both `StereoSynthesizer` and CUDA
`make_shift` supplied **negative** near-depth shift to the first/left eye.
Standard LR stereo requires the opposite: for a point in front of the screen,
the left-eye image lies to the right of the right-eye image (crossed disparity).
The right-eye image has the opposite displacement. Occlusion priority was
already larger-is-nearer, so binocular disparity contradicted the depth ordering.
Reference geometry: [Calculating Stereo Pairs](https://paulbourke.org/stereoscopy/stereorender/).

Previous CPU/GPU equality checks preserved this shared error. The optional iw3
adapter also swapped upstream eyes to match that baseline; its former
"calibration" was a relative naming comparison, not physical validation.

## Change and comparison contract

- CPU single/paired projection and shared CUDA `make_shift` now use positive
  `(near_depth - convergence) * scale / 2` for the left eye.
- Host, shared-texture and VFG original projection include that CUDA function.
  The optional RowFlow adapter preserves upstream LR output. Active renderer
  comparison/compile scripts and their synthetic truth use the same physical sign.
- Model precision, normalization, convergence, strength, resolution, fill method,
  VFG timing and capture permissions are unchanged.
- New GPU output must equal the **eye-swapped legacy output**, byte for byte;
  equality with the old packed order would be an incorrect acceptance criterion.
- Corrected DLLs use separate local directories, preserving old loaded binaries
  and negative controls. New processes verify the updated explicit hashes.
  An already running app must be fully closed and reopened.

## Checks

1. `v1/tests/test_stereo_geometry.py`: generated far/screen/near marker planes
   through actual CPU synthesis, single-eye and paired-eye entry points. Before:
   left-minus-right offsets `+16, 0, -16`; after: `-16, 0, +16` pixels.
   Registered in the `core` CI group. Core + profiles: **143 passed**.
2. `v1/check_stereo_geometry_gpu.py`: actual old/new CUDA host output, D3D texture
   readback, VFG original projection and publication at 256x72, 1920x1080 and
   3840x2160 per eye, strengths 1.0 and 0.5, convergence 0.5. All **6 cases**
   have correct independent geometry and exact swapped-legacy/new-path parity.
   At 4K strength 1, measured far/screen/near offsets changed from `+49,0,-49`
   to `-49,0,+49` pixels (rasterized). These are diagnostic planes, not content
   or a new product convergence default. `out/stereo-geometry-20261106/gpu.json`.
3. `experiments/vfg/check_native_bridge.py`: real Base FP16 inference on three
   public FloorballGame frames at each of 1080p and 4K. Six original/native
   comparisons exact; actual VFG interpolation ran at both sizes. Artifacts:
   `out/stereo-geometry-20261106/real-base-vfg/`.
4. `v1/check_rowflow_geometry.py`: pinned symmetric weights, product pixel
   packing, eager GPU execution. Far/screen/near offsets approximately
   `-8.298, +0.004, +8.306` pixels. This does not rerun compiled performance or
   promote RowFlow from its visual-review backlog.

### Prepared binary pins

| Directory under out/ | DLL SHA-256 |
|---|---|
| live-depth-stereo-lr | d60fde89efe1cebc1ae0599f5c0ed1ada51b54b5851aedd232774d4a4fb2a8f7 |
| live-texture-stereo-lr | 69dee1abc8dda7a4d1be7aa38fa86898e87177c7f8589838fc128cc1ea03fb96 |
| vfg-native-bridge-stereo-lr | 5bc26a62a2f5106f6940d6c9adfa31d66be5636e31afb313ba1904a6d2032ca2 |

Build with `scripts/build-live-depth.ps1`,
`scripts/build-live-texture-projection.ps1 -OutputName live-texture-stereo-lr`,
and `experiments/vfg/build-native.ps1`. The LiveDepth structure is unchanged;
the existing RowFlow copy/publish bridge does not call the corrected splat path.

The verified sign error can explain conflicting depth cues. It does not prove
that all of the user's discomfort is resolved. Physical Owl3D comfort and a
same-scene Live 3D comparison after relaunch remain unverified. No new FPS or
latency claim is made by these checks.
