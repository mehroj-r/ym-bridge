# Changelog

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
