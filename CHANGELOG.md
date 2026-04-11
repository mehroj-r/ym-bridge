# Changelog

## 0.2.0 - 2026-04-11

### Added

- Explicit dislike support through `/users/{uid}/dislikes/tracks/actions/add`.
- Rotor feedback fallback path via `/rotor/sessions/feedbacks` when session-scoped feedback fails.
- HAR-aligned recon probes for account settings, disclaimers, rotor wave settings/last station, and collection sync.
- HAR cleanup helper script: `scripts/clean_har.py`.

### Changed

- Updated Yandex client defaults to match observed mobile traffic (`music_client`, diversity seed values).
- Normalized vibe diversity handling to accept `discover` while sending `settingDiversity:diverse`.
- Expanded endpoint config surface with new dislike and rotor feedback-fallback endpoints.
- Improved `/plays` reporting to include transition-style reasons (`skip`, `dislike`, `finish`) with current context item.
- Updated architecture/reverse-engineering docs and README endpoint examples to match runtime behavior.
- Added `black` to the dev toolchain and standardized formatting in touched modules.

### Fixed

- Corrected dislike flow semantics (remove like + add dislike + rotate to next track with matching rotor feedback).
- Fixed default HAR drop regex list concatenation bug in `scripts/clean_har.py`.

## 0.1.0 - 2026-02-08

Initial public release of `ym-bridge`.

### Added

- Standalone Yandex Music daemon with Linux MPRIS export.
- Playback integration via `mpv` IPC.
- Rotor session support, queue progression, and stream resolution.
- Like/dislike support via Yandex library + rotor feedback endpoints.
- Track-end and skip reporting (`/plays`, rotor feedback events).
- Local control IPC socket and `ym-bridge ctl` actions.
- `ym-bridge waybar` JSON output for custom Waybar modules.
- `ym-bridge doctor` command for setup diagnostics.
- User service unit template: `contrib/ym-bridge.service`.
- End-to-end setup docs and architecture docs.

### Changed

- Hard rename from early internal package name to `ym-bridge` (`ym_bridge` module path).
- CLI refactor into dedicated `cli` and `app` modules for maintainability.

### Security

- Removed token-like fallback defaults from runtime config loading.
