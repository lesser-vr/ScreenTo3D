# ScreenTo3D 1.0.0 release refresh — 2026-11-13

The existing release `441937625` was updated in place, remaining published,
non-prerelease and latest. The release URL and canonical download filenames are
unchanged. This operation did not recreate the release, change repository
visibility, modify the public model release or move the already-sanitized tag.

## Replaced assets

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| `ScreenTo3D-1.0.0-windows-x64.zip` | 182755816 | `2629fc86fad4866add859919f31665a867cd8b34243e7c57ef7f4595960ed8bd` |
| `ScreenTo3D-1.0.0-source-refresh.zip` | 11282656 | `f5c0c76c91029d5691439a51cf1162b041249e1ff3643c7a66ee532c4439f7f2` |
| `release-manifest.json` | 4991 | `23e7e7377d8134d6c96db86c8fe7a3f61234b554e21a8fc5737242a26517dabf` |
| `SHA256SUMS.txt` | 1520 | `766771b0b82e3c2e0c8d5362e11ae5c567ee342b5bed7f21c6b9dc8afb4da700` |

The other 13 assets preserve their IDs and hashes, including the extractor
helpers and optional offline packs. The compatibility manifest retains the
offline-pack entries, so supplying one with the extractor still works. All
16 non-checksum assets are covered by the downloaded checksum file. Existing
offline Base/VDA packs were independently checked against the current app pins.

The bilingual release body now describes direct publisher runtime downloads,
public fixed-version Base/VDA downloads, local GPU engine preparation, current
defaults, media/window fixes and privacy cleanup. Downloading the app still
requires access to the private source repository; the runtime/model downloads
themselves do not require an account or embedded credential.

## Publication and validation

Original metadata and the four replaced payloads were preserved locally. New
payloads were uploaded under temporary names and their server hashes verified
before canonical names were swapped. Retired remote revisions were deleted only
after every canonical asset passed verification. The final release has exactly
the original 17 canonical asset names and no temporary replacement names.

- [Source CI](https://github.com/lesser-vr/ScreenTo3D/actions/runs/43253117571)
  succeeds at `f20e9d8f81ac8f82d50d03e8dff00e267c15500b`; 526 local CPU/Qt contracts pass.
- Packaged application sources match that commit, allowing only CRLF/LF
  differences in 46 text files. Packaged source hashes themselves remain exact.
- The manifest truthfully records the build's original
  `bcbae96f6900e6a01a786ba729ee73006d4cf03d` base plus dirty-build flag. The provided
  source snapshot matches all 139 packaged application source hashes.
- App/source ZIPs and both helpers, manifest and checksum file were actually
  downloaded from GitHub. Each complete file matched size and SHA-256.
- Both ZIPs passed CRC and unique-entry checks. No bytecode entries or known
  personal paths were found in their members. This is the named-path regression
  scan, not a general guarantee that all possible personal information is absent.
- The actual downloaded manifest/helper extracted the app to a new directory.
  Its EXE opened the owned main window with a Windows-only PATH and closed with
  exit 0. No new GPU, clean-machine, sustained-performance or stereo-quality
  acceptance is claimed by this refresh.

Evidence is under Git-excluded `out/release-refresh-20261113/`:
`before.json`, `prepared.json`, `uploaded.json`, `swap-journal.json`,
`published.json`, `download-verified.json` and `downloaded-launcher.json`.
Credentials and signed download URLs are not retained in those reports.
