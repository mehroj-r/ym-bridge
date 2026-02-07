# Reverse Engineering Workbook

Goal: map Yandex Music APIs needed for a standalone Linux MPRIS bridge.

## Guardrails

- Interoperability only.
- No DRM bypass.
- Do not commit raw account tokens/cookies.

## Required capabilities

- Auth/session bootstrap
- Current track + playback status
- Position updates
- Transport commands: play, pause, next, previous
- Seek/set position
- Metadata: title, artist, album, duration, cover URL

## Capture workflow

1. Launch browser with fresh profile.
2. Sign in to music.yandex.
3. Start a track and exercise controls.
4. Capture traffic (DevTools export HAR or mitmproxy).
5. Classify endpoints by capability.
6. Run `ym-bridge recon` and compare status/payloads with browser captures.

## Endpoint map template

| Capability | Method | Path | Headers | Body | Success payload | Error payload | Notes |
|---|---|---|---|---|---|---|---|
| playback state | GET | /... | ... | - | ... | ... | ... |
| play | POST | /... | ... | ... | ... | ... | ... |

Known useful endpoint:

- `GET /account/about` with OAuth and mobile-style headers verifies auth and account tier.
- `POST /rotor/session/new` returns playable sequence entries for radio playback.
- `POST /users/{uid}/likes/tracks/actions/add` applies library like for track.
- `POST /users/{uid}/likes/tracks/actions/remove` removes library like for track.
- `POST /rotor/session/{sessionId}/tracks` sends radio feedback events and returns sequence updates.
- `POST /plays` reports completed playback (`changeReason=finish`, `listenActivity=END`).

## Data model mapping to MPRIS

- `status` -> `PlaybackStatus`
- `position_ms` -> `Position` (microseconds)
- `duration_ms` -> `mpris:length` (microseconds)
- `title` -> `xesam:title`
- `artists[]` -> `xesam:artist`
- `album` -> `xesam:album`
- `cover_url` -> `mpris:artUrl`

## Validation checklist

- `playerctl --player=ymbridge metadata` returns real values.
- Media keys operate playback.
- Waybar mpris module shows title/artist and status icon.
- SwayNC media controls and artwork are populated.

## Notes on endpoint config

Fill endpoint paths in `~/.config/ym-bridge/config.toml` under `[yandex.endpoints]`.
The bridge assumes:

- state endpoint accepts `GET` and returns playback data
- transport endpoints accept `POST`
- seek/set position/volume accept `POST` with JSON body
