# Setup From Zero

## 1) Install Dependencies

```bash
sudo pacman -S --needed mpv playerctl waybar swaync
```

Install project:

```bash
uv sync
uv tool install --from . ym-bridge
```

## 2) Create Config

```bash
mkdir -p ~/.config/ym-bridge
cp contrib/config.example.toml ~/.config/ym-bridge/config.toml
```

Set your token in `~/.config/ym-bridge/config.toml` or env:

```bash
export YM_OAUTH_TOKEN="..."
```

If you do not want auto playback after service start, keep:

```toml
[app]
autoplay_on_start = false
```

## 3) Verify Locally

```bash
ym-bridge doctor
ym-bridge account
ym-bridge run
```

In another terminal:

```bash
playerctl --player=ymbridge metadata
ym-bridge ctl play_pause
ym-bridge waybar
```

## 4) Install as User Service

```bash
mkdir -p ~/.config/systemd/user
cp contrib/ym-bridge.service ~/.config/systemd/user/ym-bridge.service
systemctl --user daemon-reload
systemctl --user enable --now ym-bridge.service
command -v ym-bridge
```

## 5) Add Waybar Module

Use either native `mpris` module, custom `ym-bridge waybar`, or both.

After config changes:

```bash
pkill -SIGUSR2 waybar
```

## 6) Debugging

```bash
journalctl --user -u ym-bridge.service -f
ym-bridge ctl status
```
