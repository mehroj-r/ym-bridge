# ym-bridge

`ym-bridge` is a standalone Linux daemon that bridges Yandex Music to native desktop media controls.

Release: `v0.1.0`

It exposes an MPRIS player on D-Bus (`org.mpris.MediaPlayer2.ymbridge`), so it works with:

- media keys
- `playerctl`
- Waybar `mpris` module
- SwayNC media UI

It also ships an IPC utility for custom Waybar controls (play/pause/next/previous/like/dislike).

## How It Works

1. `ym-bridge` authenticates to Yandex Music using your OAuth token.
2. It creates a Rotor session and resolves playable stream URLs.
3. Audio is played by `mpv` via local IPC.
4. Current state is exported over MPRIS.
5. Waybar/SwayNC read that MPRIS state natively.
6. Optional custom controls use `ym-bridge ctl ...` via a local Unix socket.

For architecture details, see `docs/architecture.md`.
For full onboarding, see `docs/setup-from-zero.md`.
For release process, see `docs/release-checklist.md`.

## Requirements

- Linux desktop with D-Bus session
- Python 3.14+
- `mpv`
- optional: Waybar, SwayNC

## Install

```bash
uv sync
```

Install CLI binary to `~/.local/bin` (recommended for systemd user service):

```bash
uv tool install --from . ym-bridge
```

For local development (so code changes apply without reinstall):

```bash
uv tool install --from . --editable --force ym-bridge
```

or:

```bash
pip install -e .
```

## Configure

Create `~/.config/ym-bridge/config.toml`:

```toml
[app]
poll_interval_seconds = 2.0
mpris_name = "ymbridge"
control_socket_path = "/tmp/ym-bridge.sock"
autoplay_on_start = false
waybar_max_length = 34
waybar_scroll = true
user_agent = "ym-bridge/0.1"

[yandex]
base_url = "https://api.music.yandex.net"
oauth_token = ""
device_id = ""
accept_language = "en"
music_client = "YandexMusicAndroid/24026072"
content_type = "adult"
device_header = ""
rotor_seeds = ["user:onyourwave", "settingDiversity:discover"]

[yandex.endpoints]
account_about = "/account/about"
rotor_session_new = "/rotor/session/new"
rotor_session_tracks = "/rotor/session/{session_id}/tracks"
likes_tracks_add = "/users/{user_id}/likes/tracks/actions/add"
likes_tracks_remove = "/users/{user_id}/likes/tracks/actions/remove"
plays = "/plays"

[recon]
output_dir = "./artifacts/recon"
```

You can also pass secrets via environment variables:

```bash
export YM_OAUTH_TOKEN="..."
export YM_DEVICE_ID="..."
```

## Commands

- `ym-bridge run` - run daemon
- `ym-bridge recon` - probe useful endpoints
- `ym-bridge doctor` - local readiness checks
- `ym-bridge account` - verify account/auth
- `ym-bridge like` / `ym-bridge dislike` - direct track action
- `ym-bridge ctl <action>` - daemon control over IPC
- `ym-bridge waybar` - JSON output for custom Waybar module

## Validate Native MPRIS

```bash
playerctl --player=ymbridge metadata
playerctl --player=ymbridge play-pause
```

## Waybar Setup

Native MPRIS module:

```json
"modules-right": ["mpris"],
"mpris": {
  "player": "ymbridge",
  "format": "{status_icon} {artist} - {title}",
  "status-icons": {
    "playing": "▶",
    "paused": "⏸",
    "stopped": "■"
  }
}
```

Custom control module:

```json
"modules-right": ["custom/ym"],
"custom/ym": {
  "exec": "ym-bridge waybar",
  "return-type": "json",
  "interval": 1,
  "on-click": "ym-bridge ctl play_pause",
  "on-click-right": "ym-bridge ctl like",
  "on-click-middle": "ym-bridge ctl dislike",
  "on-scroll-up": "ym-bridge ctl next",
  "on-scroll-down": "ym-bridge ctl previous"
}
```

## Systemd User Service

Copy service file:

```bash
mkdir -p ~/.config/systemd/user
cp contrib/ym-bridge.service ~/.config/systemd/user/ym-bridge.service
systemctl --user daemon-reload
systemctl --user enable --now ym-bridge.service
```

Verify executable resolution before enabling:

```bash
command -v ym-bridge
```

Check logs:

```bash
journalctl --user -u ym-bridge.service -f
```

## SwayNC

No custom integration is required. SwayNC reads MPRIS sessions automatically.

## Troubleshooting

- `YM offline` in Waybar custom module: daemon is not running or socket path differs from config.
- `status=203/EXEC` in systemd: `ym-bridge` is not on service PATH. Install with `uv tool install --from . ym-bridge` and restart service.
- service uses old code after changes: reinstall tool from current repo (`uv tool install --from . --editable --force ym-bridge`) and restart service.
- no audio: verify `mpv` is installed and available in `PATH`.
- no metadata: check `journalctl --user -u ym-bridge.service -f` and run `ym-bridge account`.
- auth failures: refresh OAuth token and update config/env.
