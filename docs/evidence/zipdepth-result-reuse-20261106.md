# ZipDepth completed-result reuse fix — 2026-11-06

The reported `Invalid or expired ZipDepth result` was reproduced through the
real native renderer when an identical RGB frame followed its first output.
Performance policy intentionally reuses depth on exact-equal RGB frames between
inference cadence boundaries. ZipDepth tied token validity to `pending_device`,
which `complete_device` cleared after the first render. The next reuse therefore
failed despite the depth tensor and its engine still being valid.

The adapter now tracks the current result separately from pending inference.
Completion synchronizes work and clears the pending state; the current result
remains valid until superseded by a new inference or the engine closes. There
is only one engine-held current result. Owner/thread/device, identity, generation,
shape/dtype/layout and stream checks remain. New inference is still rejected
while an earlier result is pending. No model graph, preprocessing, stereo policy,
normal app default or capture protection changed.

Validation:

- `check_reuse.py --tag before` reproduced the exact exception on the second
  native render. Evidence: `out/zipdepth-reuse-before.{json,log}`.
- After the fix, the same native test passed 36 renders across 960x540,
  960x960 and 3840x2160. Each case exercised six reused outputs and six fresh
  inferences, a changed-RGB transition and native slot readback. Superseded
  tokens and tokens from a closed engine were rejected.
  Evidence: `out/zipdepth-reuse-after.json`.
- Actual `launch.py --smoke-static` used owned public stills repeatedly repainted
  through WGC and the Owl3D-compatible output launcher. 1920x1080, 960x960 and
  3840x2160 sessions produced 32/31/30 frames with 15/14/14 reused depths.
  Full SBS geometry, output hide/restore and stop/restart passed; no errors,
  zero native pools/nodes after every session.
  Evidence: `out/zipdepth-launch-static-smoke.json`.
- Four-aspect original-FP32 reference checks still meet the existing 1% depth-span
  MAE bound. Pending-inference rejection, completed-result reuse, old-generation
  rejection, wrong-thread rejection and engine close pass.
  Evidence: `out/zipdepth-reuse-adapter-validation.json`.
- Changed Python modules compile. All test-owned windows/processes closed.

The earlier moving-video FPS measurements did not exercise this static reuse
failure. This fix does not establish new FPS, visual quality or physical Owl3D
comfort results. The user's exact source window was not captured in validation.
