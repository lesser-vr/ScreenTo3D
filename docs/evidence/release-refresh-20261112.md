# 1.0.0 release replacement, 2026-11-12

The user requested replacement of the existing 1.0.0 release with the tested
first-use distribution. Release ID `441356629`, URL
[ScreenTo3D 1.0.0](https://github.com/lesser-vr/ScreenTo3D/releases/tag/v1.0.0),
was updated in place. Repository visibility remains private. No Git commit,
branch push or tag move was performed.

## Published contents

17 assets remain: one application ZIP, the unchanged optional-model bundle,
eight GPU-resource alternatives, common TensorRT and media component ZIPs,
two extraction scripts, release manifest, checksums and corresponding source ZIP.
Only the matching GPU pack is normally needed; the full resource archive is an
alternative, not an additional required download. Old app parts02–04 were removed.

- App ZIP: 182,759,785 bytes; SHA-256
  `8bb6a81f9b3a760956a98f37e2ef170d4297c1ad4dcb985a02c0676f68e1c071`.
- Extracted application: 428,866,502 bytes.
- Common TensorRT component: 438,176,196 bytes.
- Media component: 92,456,432 bytes.
- Example SM120 resource: 272,016,861 bytes.
- `ScreenTo3D-1.0.0-source-refresh.zip`: 11,163,620 bytes, 842 source files.
  `SOURCE-SNAPSHOT.json` lists file digests; the included distribution build
  manifest ties all packaged app-source hashes to this snapshot.

The application binaries are byte-identical to the previously validated
`out/first-use-final/ScreenTo3D-1.0.0/` candidate. Existing functional/GPU evidence
in [the component report](first-use-components-20261111.md) therefore applies.
Release documentation and checksums were updated; no new FPS or quality claim
is made. The source snapshot records the working-tree source at packaging time,
before this post-publication record. It includes the uncommitted changes over
base `71b9216419fbdf5ddef6ad17db011a625d6910b4`. GitHub's automatic source archives
still describe the unchanged original tag; the release explicitly distinguishes
those from the refreshed source ZIP.

## Replacement and verification

`out/replace-release-1.0.0/before.json` preserves the original release metadata.
All nine original asset files were verified against their GitHub digests under
`out/release-1.0.0/assets/` before mutation. New uploads were staged and every
size/state/server SHA-256 checked before conflicting names were switched.
The two identical assets were retained without reuploading. Seven superseded
assets were deleted remotely only after actual replacement-download verification;
their original local files remain available for recovery.

`out/replace-release-1.0.0/published.json` records the final 17 names, sizes,
digests and download URLs. `verified.json` confirms:

- All 17 remote assets match the prepared local inventory and server SHA-256.
- Nine files were actually downloaded from GitHub and hashed: app, common core,
  media, SM120, both extractor scripts, manifest, checksums and source ZIP.
- Private GitHub asset requests use authentication only on api.github.com;
  redirects to signed GitHub storage do not receive the credential.
- The downloaded checksum-verifying extractor successfully produced the app and
  selected sidecars in a new directory. Representative extracted files match the
  known candidate.
- `downloaded-launcher.json` records the actual downloaded EXE opening its owned
  main window and exiting normally, with Windows-only PATH and another empty
  runtime cache. This check does not start user capture or repeat inference QA.
- All 842 downloaded source files and every packaged app-source hash match the
  source/build manifests.
- The tag object was unchanged, and the refreshed release remains latest and
  published, with no temporary/previous asset names left.

This private repository cannot serve anonymous app downloads from its release
URLs. No visibility change, embedded GitHub credential or false public origin
was introduced. The release explains authenticated manual pack download and
local first-use installation; a separate public HTTPS origin remains an option
for a later distribution. Credentials remained in process memory and were not
logged or put into any artifact.
