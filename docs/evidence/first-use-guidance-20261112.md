# First-use download guidance, 2026-11-12

Local candidate over `b3b76868eb9348c9a74228591a8521acf417eaaa`; not published.
Current behavior is owned by [PRODUCT](../PRODUCT.md#files-and-models).

## Changes and checks

- Live/file Start preflights missing runtime, GPU resource, selected model and
  enabled VFG components. A missing distribution origin opens the protected setup
  window directly; it does not emit an installation error or spawn a media worker.
- Existing configured HTTPS/local-pack installation remains in use. The private
  release fallback opens the exact pinned asset in the user's browser. A bounded
  timer observes completed named files in the system Downloads directory. The
  existing installer still verifies archive size/hash and exact payload inventory.
- Browser waiting has no GPU/media lease. Another install cannot replace the
  current setup. Repeated Start retains the original selection guard. Cancellation,
  dismissal, timeout, browser-launch failure and integrity failure discard automatic
  continuation. File engine paths updated by installation are accepted; a changed
  input or processing selection requires a new Start.
- Core/Qt contracts: **181 passed**, including completed-file handoff through a
  real installer fixture, corruption rejection, cancellation and retry guards.
  File-controller contracts: **23 passed**, including missing runtime/model/VFG
  routing and selection-safe continuation. Reports/logs:
  `out/setup-guidance-contracts.{json,log}`, `out/setup-guidance-controller.log`.
- `v1/test_first_use_ux.py` renders Korean/English setup, narrow (380 logical-pixel)
  guidance, browser waiting and missing file-model setup. The production pruned
  Qt/Python package passes these QML action checks with no runtime warnings or
  error window: `out/setup-guidance-packaged-final/report.json`. Earlier source
  rendering also used actual QtTest pointer clicks. Representative captures were
  inspected; final mechanical design scan has no findings.
- Bilingual catalog build passes: 150 error IDs, 797 finished translations.
- New local app: `out/desktop-distribution/ScreenTo3D-SetupFix/ScreenTo3D.exe`.
  EXE launch with isolated PATH and normal close passes:
  `out/setup-guidance-launcher.json`. Build manifest records source identity and
  synchronized source hashes. No GPU/model algorithms or native output binaries
  changed; existing numerical/performance evidence is reused.

## Limits

The browser-open call/authenticated network download is simulated in these UI
checks; the real GitHub sign-in/download remains a user-side verification. The
repository stays private, and no token is embedded or read from a browser. A
custom browser save folder uses the explicit file picker. An external browser
download can continue after app setup is cancelled. No new public host, OAuth
client, remote release update or commit/push was performed.
