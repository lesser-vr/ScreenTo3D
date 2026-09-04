# V1.1 stereo silhouette ghosting

Status: Correctness improvement delivered for review; performance and broad visual acceptance open

Balanced infers every frame; its observed extra contours are not from inference
skipping. Hypotheses: inverse warping duplicates contours at depth boundaries;
unaligned depth EMA adds moving-edge lag.

Plan: matched-depth EMA-on/off ablation before encoding, visibility-aware
forward projection and background-aware hole filling, temporal history gating,
geometry/occlusion/motion regressions, then packaged conversion of the user's
clip. Preserve input and old output. Measure CPU cost; no real-time guarantees.

## Findings and changes (2026-09-04)

- Frame 48 reproduced the detached contour in pre-encode legacy output with
  identical inferred depth both with and without EMA. Thus encoding and EMA
  alone do not explain the defect; inverse projection at depth boundaries is
  sufficient to reproduce it. Balanced inference skipping was excluded by policy.
- Forward projection with near-depth visibility removed detached duplicates in
  the hard-edge oracle, but unrefined real depth produced smeared boundaries.
  A broader far-background hole fill was rejected because it introduced gaps.
- Final renderer combines forward visibility, farther-side horizontal hole
  filling, image-guided depth and conservative uniform-backdrop refinement.
  No specific green color is hardcoded. Border-connected flat background gets
  constant depth; foreground component contour depth blends into interior depth.
  This intentionally regularizes contour depth and can reduce local depth detail.
- Temporal history is rejected around changed color/depth, and detected cuts
  reset history and trigger extra inference. Mode policy carries thresholds;
  telemetry reports cut counts and flat-background activation counts.
- Historical eye direction and nominal disparity strength were retained. No
  assurance of stereo comfort or absolute physical depth is inferred from this.

## Verification

- Python regression suite: 29 tests; process-tree cases and C++ suite passed.
  New oracles cover zero shift, near/far overlap, no duplicate silhouette,
  both projection directions, row isolation, constant guided depth, backdrop
  color independence/bypass, moving depth and scene-cut reset.
- Rebuilt portable executable. Final Balanced output: 124 frames, 2112x608,
  24 fps; media/resource smoke passed. All 124 frames used backdrop refinement.
- Inspected decoded crops at 0/2/4 seconds and both eyes at 2 seconds. Large
  detached ear/tail contours were reduced. Small boundary artifacts remain;
  full motion/VR acceptance requires user review. This is not a universal fix.
- Final artifact: `out/soak/b4ead39f158947bc83e915ade4efacf5/result.json` and
  adjacent output.mp4. Source and earlier outputs were preserved.
- CPU performance regression is material: this run took 18.988 s, 6.53 fps,
  temporal/stereo mean 135.17 ms. Previous user-clip Balanced run was 40.62 fps.
  These are single-run observations, not a controlled benchmark, but optimization
  is required before claiming the previous throughput or real-time operation.
- Packaged cancellation and one real-GPU success/cancel/inference-error/invalid
  input cycle passed. Cleanup evidence: `out/cleanup/repeat-ev0vrl38/result.json`.

## Reproduction and follow-up

`v1/diagnose_stereo.py --input <clip>` keeps a frozen legacy baseline and saves
matched frame/depth evidence under out/stereo-ghost-diagnosis. Then run
`v1/compare_projection.py` for the spatial candidate using that same sample.
Use the development dependency/TensorRT paths documented by test-v1 scripts.
Raw user images/depth/video stay in ignored out/, not in Git.

Next: user review of the final clip, CPU/GPU optimization without restoring the
duplicate-contour path, subpixel projection and more complex-background goldens.
Performance-mode cadence reuse between cuts still needs motion-aware validation.
