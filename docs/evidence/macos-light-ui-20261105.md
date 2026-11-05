# Light utility visual pass — 2026-11-05

Scope: user-approved macOS-inspired appearance on the existing minimal Qt/QML
shell. No model, stereo, source size, default output path or native transport
changes. Product behavior is owned by PRODUCT.md; QML colors by Theme.qml.

## Delivered surfaces

- Light gray window, white source selector with selected application icon or
  neutral window fallback, blue primary action and restrained typography.
- Small ellipsis menu with accessible name and hover/keyboard label.
- Start/stop symbols and textual idle/preparing/running/stopping states; no
  decoration or animation added to the SBS video output itself.
- Shared light buttons/pickers, blue slider/checkboxes, separate native error
  window preserving Close, Escape and full-message Ctrl+C.
- Normal Windows title bar retained; no imitation traffic-light window controls.

Selected icons use WM_GETICON with a 40ms timeout and window-class fallback.
PID matching prevents a stale window request from reading another process's icon.
Only the selected image is cached; CopyIcon ownership is released with DestroyIcon
after QImage conversion. Iconless windows receive a transparent provider image
and a neutral QML window symbol. No thumbnails, client-pixel capture, executable
path lookup, persistent icon files or network retrieval are used.

## Evidence

| Check | Result |
|---|---|
| Controller/placement/icon units | 51 passed: v1.test_live_controller, v1.tests.test_output_placement, v1.tests.test_window_icons |
| Native icon | Real generated owned-window icon converted correctly; mismatched PID rejected; unselected requests do not read a window; cache changes with PID |
| Qt at DPR 1.5 | out/macos-light-ux-20261105-r2/report.json; no warnings |
| Final Qt at DPR ~1.0 | out/macos-light-final-100-20261105/report.json; no warnings |
| Final Qt at DPR 2.0 | out/macos-light-final-200-20261105/report.json; no warnings |
| Actual WGC/Base host output | out/macos-light-base-start-20261105/report.json; 49 submitted frames before first stop; startup, F11/Esc, minimize, X-to-stop, restart placement, button stop and preparation cancel passed |

UI runs use generated source labels and injected processing states, real mouse/
keyboard input, long-title/minimum layouts, menu navigation, native error copying,
capture-affinity checks and failure injection. Final runs also focus a checked
cursor checkbox and toggle it off/on with Space. Screenshots are in the matching
directories. Source icon integration does not make the screenshot fixture a real
captured video or promise every application supplies an icon.

The initial custom menu had no useful implicit width despite keyboard navigation
working. Visual inspection caught it; an explicit menu width and real mouse-menu
test corrected it. Independent finish review identified an invisible focus cue
on checked blue checkboxes; an outer focus ring fixed it. Final reviewer verdict:
ship the scoped UI change, finding resolved at 100% and 200%. Text contrast reviewed
at approximately 5.22:1 for muted text on the background and 5.33:1 for white primary
button text. Native title bars were checked in source, not in client-only captures.

## Limits

These checks cover UI behavior and a short generated-source Base runtime. They do
not establish subjective user acceptance, real VR/Owl3D viewing, long sessions or
new performance gains. Existing native transport/lifecycle evidence remains scoped
to its earlier tests. The real Base run emitted the existing TensorRT device-plan
compatibility warning. No commit or packaged release was made.
