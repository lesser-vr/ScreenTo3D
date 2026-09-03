# Security and licensing

Status: Proposed V1 baseline  
Last reviewed: 2026-09-03

## Trust boundaries

Untrusted inputs include media containers/bitstreams, paths and CLI values, model
files, TensorRT engines, sidecar metadata, and environment-provided library paths.
GPU/driver APIs and third-party codecs are privileged native dependencies whose
failures must be contained at the job boundary where possible.

## Required controls

- Validate dimensions, frame counts/durations, time bases, stream counts, codec
  parameters, output geometry, and allocation sizes with checked arithmetic.
- Apply configurable limits before allocation or engine submission.
- Never construct shell commands from media paths or metadata.
- Write only to the requested output and unique temporary sibling; prevent input
  overwrite unless a separate explicit feature is designed.
- Treat model and engine artifacts as data, never executable plugins. Validate
  checksum, expected tensor shapes, precision, TensorRT/CUDA/device compatibility,
  and provenance before loading.
- Do not search arbitrary current directories or environment paths for DLLs.
- Pin dependencies and generate a software/model inventory for release builds.
- Keep fuzzing entry points for container probe and configuration parsing.
- Redact user paths and media metadata from default diagnostics.

## Model licenses

Model selection is both a technical and distribution decision. The official
Depth Anything V2 repository states that Small uses Apache-2.0 while Base, Large,
and Giant use CC-BY-NC-4.0. Therefore DA2 Base is a development candidate, not an
assumed commercially distributable bundled default.

Before a backend is shipped, record:

- source repository and exact revision;
- weights and code licenses separately;
- permitted use and redistribution constraints;
- attribution/notice requirements;
- checksum and download/build provenance;
- whether the application bundles, downloads, or asks the user to supply it.

oVDA, VDA, DA3, TensorRT conversion code, FFmpeg configuration, and NVIDIA SDK
samples each require the same review. “Public on GitHub” is not a license result.

## Reporting

Until a dedicated private channel exists, security issues should not be filed with
sensitive media, local paths, crash dumps, or unpublished model artifacts in a
public issue. Add a project security contact and disclosure process before the
first public release.
