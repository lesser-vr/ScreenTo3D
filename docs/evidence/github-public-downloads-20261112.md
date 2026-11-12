# Public GitHub release distribution, 2026-11-12

Research only. No repository visibility, asset or release was changed.

- Public release assets can be downloaded without authentication. Use their
  versioned `browser_download_url` and follow HTTPS redirects; avoid embedding
  temporary signed redirect destinations.
  [Release asset API](https://docs.github.com/en/rest/releases/assets#get-a-release-asset)
- GitHub documents no total release-size or download-bandwidth limit. An
  individual asset must be under 2 GiB; one release can have up to 1000 assets.
  Base (392,348,171 bytes) and VDA (363,291,834 bytes) fit individually.
  [Release quotas](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases#storage-and-bandwidth-quotas)
- Git LFS is different: downloads count against the repository owner's metered
  bandwidth allowance. Model distribution should use release attachments rather
  than LFS if the desired property is the release download quota described above.
  [Git LFS billing](https://docs.github.com/en/billing/concepts/product-billing/git-lfs)
- Unauthenticated REST metadata calls have a separate 60 requests/hour/IP limit.
  Version-pinned direct asset URLs avoid a required API metadata request per app
  download. No throughput or service-availability guarantee is inferred from the
  absence of a bandwidth quota.
  [REST limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)

A separate public distribution repository is also feasible while keeping the
source repository private. This alternative was researched, not implemented;
the user's earlier model-bundling request remains the active implementation.
