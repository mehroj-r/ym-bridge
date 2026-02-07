from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tomllib
import uuid


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "ym-bridge" / "config.toml"


@dataclass(slots=True)
class AppConfig:
    poll_interval_seconds: float = 2.0
    mpris_name: str = "ymbridge"
    control_socket_path: str = "/tmp/ym-bridge.sock"
    autoplay_on_start: bool = False
    user_agent: str = "ym-bridge/0.1"
    base_url: str = "https://api.music.yandex.net"
    oauth_token: str = ""
    device_id: str = ""
    endpoint_state: str = ""
    endpoint_play: str = ""
    endpoint_pause: str = ""
    endpoint_play_pause: str = ""
    endpoint_stop: str = ""
    endpoint_next: str = ""
    endpoint_previous: str = ""
    endpoint_seek: str = ""
    endpoint_set_position: str = ""
    endpoint_volume: str = ""
    endpoint_account_about: str = "/account/about"
    endpoint_rotor_session_new: str = "/rotor/session/new"
    endpoint_rotor_session_tracks: str = "/rotor/session/{session_id}/tracks"
    endpoint_likes_tracks_add: str = "/users/{user_id}/likes/tracks/actions/add"
    endpoint_likes_tracks_remove: str = "/users/{user_id}/likes/tracks/actions/remove"
    endpoint_plays: str = "/plays"
    rotor_seeds: tuple[str, ...] = ("user:onyourwave", "settingDiversity:discover")
    accept_language: str = "en"
    music_client: str = "YandexMusicAndroid/24026072"
    content_type: str = "adult"
    device_header: str = ""
    recon_output_dir: Path = Path("./artifacts/recon")


def load_config(path: Path | None = None) -> AppConfig:
    resolved = path or DEFAULT_CONFIG_PATH
    if resolved.exists():
        raw = tomllib.loads(resolved.read_text(encoding="utf-8"))
    else:
        raw = {}
    app = raw.get("app", {})
    yandex = raw.get("yandex", {})
    endpoints = yandex.get("endpoints", {})
    recon = raw.get("recon", {})

    configured_token = str(yandex.get("oauth_token", ""))
    oauth_token = os.getenv("YM_OAUTH_TOKEN", configured_token)
    configured_device_id = str(yandex.get("device_id", "")).strip()
    device_id = os.getenv("YM_DEVICE_ID", configured_device_id) or _default_device_id()
    device_header = str(yandex.get("device_header", "")).strip()
    if not device_header:
        device_header = _default_device_header(device_id)

    return AppConfig(
        poll_interval_seconds=float(app.get("poll_interval_seconds", 2.0)),
        mpris_name=str(app.get("mpris_name", "ymbridge")),
        control_socket_path=str(app.get("control_socket_path", "/tmp/ym-bridge.sock")),
        autoplay_on_start=_as_bool(app.get("autoplay_on_start", False)),
        user_agent=str(app.get("user_agent", "ym-bridge/0.1")),
        base_url=str(yandex.get("base_url", "https://api.music.yandex.net")),
        oauth_token=oauth_token,
        device_id=device_id,
        endpoint_state=str(endpoints.get("state", "")),
        endpoint_play=str(endpoints.get("play", "")),
        endpoint_pause=str(endpoints.get("pause", "")),
        endpoint_play_pause=str(endpoints.get("play_pause", "")),
        endpoint_stop=str(endpoints.get("stop", "")),
        endpoint_next=str(endpoints.get("next", "")),
        endpoint_previous=str(endpoints.get("previous", "")),
        endpoint_seek=str(endpoints.get("seek", "")),
        endpoint_set_position=str(endpoints.get("set_position", "")),
        endpoint_volume=str(endpoints.get("volume", "")),
        endpoint_account_about=str(endpoints.get("account_about", "/account/about")),
        endpoint_rotor_session_new=str(endpoints.get("rotor_session_new", "/rotor/session/new")),
        endpoint_rotor_session_tracks=str(
            endpoints.get("rotor_session_tracks", "/rotor/session/{session_id}/tracks")
        ),
        endpoint_likes_tracks_add=str(
            endpoints.get("likes_tracks_add", "/users/{user_id}/likes/tracks/actions/add")
        ),
        endpoint_likes_tracks_remove=str(
            endpoints.get("likes_tracks_remove", "/users/{user_id}/likes/tracks/actions/remove")
        ),
        endpoint_plays=str(endpoints.get("plays", "/plays")),
        rotor_seeds=tuple(
            str(item)
            for item in yandex.get("rotor_seeds", ["user:onyourwave", "settingDiversity:discover"])
        ),
        accept_language=str(yandex.get("accept_language", "en")),
        music_client=str(yandex.get("music_client", "YandexMusicAndroid/24026072")),
        content_type=str(yandex.get("content_type", "adult")),
        device_header=device_header,
        recon_output_dir=Path(str(recon.get("output_dir", "./artifacts/recon"))),
    )


def _default_device_id() -> str:
    machine_id_path = Path("/etc/machine-id")
    if machine_id_path.exists():
        machine_id = machine_id_path.read_text(encoding="utf-8").strip()
        if machine_id:
            return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"ym-bridge:{machine_id}"))
    return str(uuid.uuid4())


def _default_device_header(device_id: str) -> str:
    return (
        "os=Linux; os_version=unknown; manufacturer=Custom; model=ym-bridge; "
        f"clid=desktop; uuid={device_id.replace('-', '')}; display_size=0; dpi=96; "
        f"mcc=000; mnc=00; device_id={device_id.replace('-', '')}"
    )


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
