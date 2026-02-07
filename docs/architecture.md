# Architecture

## Runtime Components

- `ym_bridge.app`: command orchestration and daemon lifecycle
- `ym_bridge.config`: TOML/env config loading
- `ym_bridge.yandex.client`: Yandex API integration and playback session logic
- `ym_bridge.mpv_player`: local `mpv` process and IPC command bridge
- `ym_bridge.controller`: state sync loop and provider abstraction
- `ym_bridge.mpris`: D-Bus MPRIS export
- `ym_bridge.ipc`: local Unix socket command API for controls/Waybar

## Playback Data Flow

1. Provider opens Rotor session (`/rotor/session/new`).
2. Sequence track metadata is cached in memory.
3. Track stream URL is resolved through Yandex resource endpoints.
4. `mpv` plays stream and reports local runtime state.
5. Controller polls provider and emits new `PlayerState`.
6. MPRIS interface publishes state for desktop integrations.

## Feedback Data Flow

- Like/dislike:
  - library endpoint (`likes/.../add` or `likes/.../remove`)
  - rotor feedback endpoint (`/rotor/session/{id}/tracks`)
- Next/skip:
  - sends `trackStarted` + `skip` feedback bundle
- Natural track end:
  - sends `/plays` end-report payload
  - sends rotor `trackFinished` + `trackStarted`

## IPC Contract

Socket path: `app.control_socket_path` (default `/tmp/ym-bridge.sock`)

Request:

```json
{"action": "status|play|pause|play_pause|next|previous|like|dislike"}
```

Response:

```json
{"ok": true, "state": {...}}
```

Notes:

- Like/dislike actions are rate-limited in daemon IPC to avoid accidental request spam from repeated UI events.
- Action responses include refreshed state so UI integrations can reflect like/dislike updates quickly.

or

```json
{"ok": false, "error": "..."}
```
