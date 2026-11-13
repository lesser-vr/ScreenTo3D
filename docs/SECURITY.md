# Security and licensing

Trust boundaries, reviewed 2026-09-07. Concrete pins and profiles describe the
current loader, not permanent restrictions on future implementations.

## Trust boundaries and controls

- Media, metadata, paths, CLI values and external artifacts are untrusted inputs.
  Validate dimensions, durations, time bases, streams, formats and allocation
  sizes with checked arithmetic and limits before allocation/submission.
- Model weights are structured inputs. Serialized TensorRT engines are trusted
  executable artifacts and can execute native GPU code. Neither may introduce
  arbitrary host plugins. Verify trusted provenance, hashes, tensor contracts,
  precision and runtime/device compatibility before loading. A matching checksum
  detects corruption; it does not authenticate an untrusted producer.
- The portable Base and VDA installers pin archive and ONNX digests, build in
  an isolated child process, and compare tensor outputs against packaged reference
  samples before publishing. The per-user Windows DPAPI record binds engine
  hashes to the source revision and GPU/runtime identity. Workers verify those
  hashes before deserialization. Explicit legacy plan imports retain their own checks.
- Load native code only from explicitly trusted sources with provenance,
  containment and integrity checks; do not accept arbitrary ambient DLL search
  paths or construct shell commands from media names. Current engine/DLL pins
  remain enforced until a validated loader change.
- Preserve output destination/temp-file controls, dependency pinning, inventory,
  parser/config validation and redacted default diagnostics.
- Official runtime downloads verify full archive hashes before selective extraction
  and independently check payload hashes. Existing SDK and the explicitly pinned
  official wheel signatures are accepted for eleven TensorRT DLLs only after their
  remaining PE bytes were compared equal. Runtime loading never normalizes a
  binary or trusts an arbitrary same-version replacement. Legacy component marker
  hashes identify the canonical payload revision, not a claim that a repacked ZIP
  was downloaded. Numerical candidate retries never alter the declared acceptance
  contract. VDA's separately bounded FP16 cache/final-depth contract is recorded
  in build receipts; finite/signature checks remain mandatory. The named depth
  alternative requires both aggregate and outlier bounds and does not authorize
  arbitrary per-element exceptions. Base's acceptance and graph pins are unchanged.

## Capture, native handles and reporting

Capture starts only through the user's explicit selected source. Validate source
identity/SDR and capture exclusion; do not bypass secure or inaccessible content.
Recording is off by default and unsupported by the current live profile; no
implicit audio recording/download/build is added. Explicitly designed future
features must retain provenance, destination and privacy controls.

In normal application launch, the main UI, utility window and error window use
capture exclusion. The marked SBS output allows external capture for window input,
including by other recording software. Monitor input requires capture exclusion
on that output to prevent feedback.
Utility/error exclusion is checked before showing them; an error-dialog exclusion
failure keeps the dialog hidden and stops live capture while retaining its error
in status. The application
does not offer a normal GUI option to clear SBS capture protection for external applications.

The user-requested Owl3D trial (`Run-Compare-A.cmd` / `Run-Compare-B-VFG.cmd` /
`Run-Compare-Small.cmd` / `Run-Compare-Small-VFG.cmd`)
allows external capture of its owned SBS output, so the display compositor can
include it. Other applications can capture that output too; this is not an Owl3D
process allowlist. Main/tools/errors remain excluded. Only original window input
is supported by the trial; monitor capture is rejected. Output windows carry a
process-owned Win32 property and are excluded from DepthSBS source enumeration
and rejected again during source validation across processes, without title-based
identity or a separate-monitor requirement. The marker is a recursion guard, not
an OS security boundary or a guarantee against third-party capture relay chains.
The experiment changes only its own output affinity, verifies it by readback,
and stops visibly on failure. It never clears protection on another app's window.

Cross-process GPU transport needs validated process identity, access control,
resource/adapter properties and lifetime. The current path uses unnamed handles;
an alternative transport can be implemented with equivalent isolation. Request
minimal rights, close owned duplicates and never terminate unrelated processes.
The native frame-ready socket pair is local, carries only bounded wakeup bytes
and has no listening endpoint after creation. A wakeup conveys no authority or
GPU completion: session/PID/resource validation and final-lease acknowledgments
still occur through the existing metadata/native protocol. No captured pixels
or window identities are sent through this channel.

Do not put private frames, paths, dumps or unpublished model artifacts in public
issues. A disclosure contact/process remains required before public release.

## Model licenses and artifact scope

Existing recorded provenance and notices remain mandatory:

- DA2 Small uses the recorded Apache-2.0 source/weights scope; Base/Large/Giant
  have the recorded CC-BY-NC-4.0 weights restriction. Local Base validation is
  not commercial bundling/default clearance. See [da2-base.md](models/da2-base.md).
- VDA Small uses the pinned source/weights and profile validation recorded in
  [public-depth-integrations.md](references/public-depth-integrations.md) and [vda.md](models/vda.md).
  This is not blanket approval for other variants or shapes.
- oVDA retains its recorded mixed Apache/NC-SA-UHDV1.0 scope and explicit personal,
  non-commercial user selection. Its restrictions include commercial-purpose
  development/benchmarking and ShareAlike; isolation alone does not settle
  redistribution. Keep notices and the runtime boundary under `experiments/ovda`.
  See [ovda.md](evidence/ovda.md#record-result-ovda-c16-experiment) and [ovda.md](models/ovda.md).

Before shipping, record source and weights revisions/licenses separately,
permitted use, notices, provenance and bundle/download/user-supplied policy.
Public availability is not license clearance. Qt, FFmpeg and NVIDIA dependencies
retain their recorded packaging obligations; source-local use is not clean-machine
or redistribution certification. Recheck changed artifacts/terms before new use.

The separate public model repository supplies fixed-version Base/VDA ZIPs only;
the app retains its own size, archive/graph hashes and numerical acceptance rules.
Remote manifests/checksums are provenance, not authority to replace app pins.
Public model staging allowlists archive members and excludes app/runtime binaries,
serialized GPU engines and videos. Model-specific CC BY-NC/Apache notices remain
separate; repository separation does not relax Base's non-commercial restriction.

## Build validation and future manifest boundary

Existing local loaders still enforce their exact validated shapes, hashes,
filenames, sizes, GPU/runtime signatures and cache contracts. Failed FP16 artifacts
remain outside accepted runtime allowlists. New builds need affected validation;
where a pin is currently in code, changing that pin still requires a code update.

A future manifest-backed revision registry may remove repetitive code edits when
the loader contract is unchanged, but is not implemented by this documentation
change. It must retain trusted provenance, integrity, compatibility and numerical
evidence; never accept arbitrary self-declared passing manifests. Track relevant setup work in [ROADMAP.md](ROADMAP.md).

Current artifact procedures and provenance are in `models/`; historical
validation is in `evidence/`. Changing implementation is allowed; weakening trust
checks by merely editing a manifest is not an implementation of a safe loader.

The CPU groups exercise artifact rejection before native load and explicit model
selection using the existing loader tests. `test_error_reporting.py` checks that
worker errors omit arbitrary exception text and cleanup notes by default;
`--detailed-errors` explicitly enables private diagnostics. The selected final
output path remains in the private worker completion protocol because the desktop
needs it; that protocol is not a public log. Other UI/native diagnostic channels
are not certified by this scoped worker test. Tests do not authenticate arbitrary
artifacts or replace license review. CI's pinned FFmpeg is a test dependency,
separate from app distribution.
