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
- Load native code only from explicitly trusted sources with provenance,
  containment and integrity checks; do not accept arbitrary ambient DLL search
  paths or construct shell commands from media names. Current engine/DLL pins
  remain enforced until a validated loader change.
- Preserve output destination/temp-file controls, dependency pinning, inventory,
  parser/config validation and redacted default diagnostics.

## Capture, native handles and reporting

Capture starts only through the user's explicit selected source. Validate source
identity/SDR and capture exclusion; do not bypass secure or inaccessible content.
Recording is off by default and unsupported by the current live profile; no
implicit audio recording/download/build is added. Explicitly designed future
features must retain provenance, destination and privacy controls.

The main UI, utility window, error window and SBS output use capture exclusion.
Utility/error exclusion is checked before showing them; an error-dialog exclusion
failure keeps the dialog hidden and stops live capture while retaining its error
in status. The application
does not offer an option to clear SBS capture protection for external applications.

Cross-process GPU transport needs validated process identity, access control,
resource/adapter properties and lifetime. The current path uses unnamed handles;
an alternative transport can be implemented with equivalent isolation. Request
minimal rights, close owned duplicates and never terminate unrelated processes.

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
