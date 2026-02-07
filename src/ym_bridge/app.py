from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
import shutil
import time

from ym_bridge.config import AppConfig, load_config
from ym_bridge.controller import BridgeController
from ym_bridge.ipc import BridgeIpcServer, send_ipc
from ym_bridge.mpris import BridgeMprisService
from ym_bridge.yandex import YandexClientConfig, YandexMusicProvider, run_recon


ACTIVITY_MAP = {
    "wake-up": "activity:wake-up",
    "road-trip": "activity:road-trip",
    "work-background": "activity:work-background",
    "workout": "activity:workout",
    "fall-asleep": "activity:fall-asleep",
}


def _build_vibe_seeds(args: argparse.Namespace) -> list[str]:
    seeds: list[str] = []
    if args.activity:
        seeds.append(ACTIVITY_MAP.get(args.activity, f"activity:{args.activity}"))
    if args.diversity:
        seeds.append(f"settingDiversity:{args.diversity}")
    if args.mood:
        seeds.append(f"settingMoodEnergy:{args.mood}")
    if args.language:
        seeds.append(f"settingLanguage:{args.language}")
    if args.seed:
        seeds.extend(str(seed) for seed in args.seed)
    return seeds


def build_client_config(config: AppConfig) -> YandexClientConfig:
    return YandexClientConfig(
        base_url=config.base_url,
        oauth_token=config.oauth_token,
        device_id=config.device_id,
        autoplay_on_start=config.autoplay_on_start,
        user_agent=config.user_agent,
        accept_language=config.accept_language,
        music_client=config.music_client,
        content_type=config.content_type,
        device_header=config.device_header,
        endpoint_state=config.endpoint_state,
        endpoint_play=config.endpoint_play,
        endpoint_pause=config.endpoint_pause,
        endpoint_play_pause=config.endpoint_play_pause,
        endpoint_stop=config.endpoint_stop,
        endpoint_next=config.endpoint_next,
        endpoint_previous=config.endpoint_previous,
        endpoint_seek=config.endpoint_seek,
        endpoint_set_position=config.endpoint_set_position,
        endpoint_volume=config.endpoint_volume,
        endpoint_account_about=config.endpoint_account_about,
        endpoint_rotor_session_new=config.endpoint_rotor_session_new,
        endpoint_rotor_session_tracks=config.endpoint_rotor_session_tracks,
        endpoint_likes_tracks_add=config.endpoint_likes_tracks_add,
        endpoint_likes_tracks_remove=config.endpoint_likes_tracks_remove,
        endpoint_plays=config.endpoint_plays,
        rotor_seeds=config.rotor_seeds,
    )


async def run_daemon(config: AppConfig) -> None:
    provider = YandexMusicProvider(build_client_config(config))
    controller = BridgeController(
        provider=provider, poll_interval_seconds=config.poll_interval_seconds
    )
    mpris = BridgeMprisService(controller=controller, mpris_name=config.mpris_name)
    ipc = BridgeIpcServer(controller=controller, socket_path=config.control_socket_path)

    await mpris.start()
    await ipc.start()
    await controller.start()
    logging.getLogger(__name__).info(
        "Bridge started as org.mpris.MediaPlayer2.%s", config.mpris_name
    )

    try:
        await asyncio.Event().wait()
    finally:
        await ipc.stop()
        await mpris.stop()
        await controller.stop()


async def run_recon_command(config: AppConfig) -> None:
    results = await run_recon(
        base_url=config.base_url,
        oauth_token=config.oauth_token,
        user_agent=config.user_agent,
        device_id=config.device_id,
        music_client=config.music_client,
        content_type=config.content_type,
        device_header=config.device_header,
        accept_language=config.accept_language,
        output_dir=config.recon_output_dir,
    )
    for result in results:
        if result.error:
            print(
                f"{result.method:4} {result.path:26} -> ERR [{result.error}] {result.output_file}"
            )
            continue
        print(
            f"{result.method:4} {result.path:26} -> {result.status_code:3} "
            f"[{result.content_type}] {result.output_file}"
        )


async def run_account_command(config: AppConfig) -> None:
    provider = YandexMusicProvider(build_client_config(config))
    try:
        about = await provider.fetch_account_about()
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"account probe failed: {exc}") from exc
    finally:
        await provider.close()

    sanitized = {
        "login": about.get("login"),
        "publicName": about.get("publicName"),
        "publicId": about.get("publicId"),
        "uid": about.get("uid"),
        "hasPlus": about.get("hasPlus"),
        "hasMusicSubscription": about.get("hasMusicSubscription"),
        "serviceAvailable": about.get("serviceAvailable"),
        "geoRegionIso": about.get("geoRegionIso"),
    }
    print(json.dumps(sanitized, indent=2))


async def _run_track_action(config: AppConfig, action: str) -> None:
    provider = YandexMusicProvider(build_client_config(config))
    try:
        await provider.fetch_state()
        current = await provider.fetch_state()
        if action == "like":
            await provider.like_current()
            payload = {
                "liked_track": current.track.title,
                "track_id": current.track.track_id,
            }
        else:
            await provider.dislike_current()
            payload = {
                "disliked_track": current.track.title,
                "track_id": current.track.track_id,
            }
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"{action} command failed: {exc}") from exc
    finally:
        await provider.close()
    print(json.dumps(payload, indent=2))


async def run_ctl_command(config: AppConfig, action: str) -> None:
    response = await send_ipc(config.control_socket_path, action)
    if not response.get("ok", False):
        raise SystemExit(f"ctl command failed: {response.get('error', 'unknown error')}")
    print(json.dumps(response, indent=2))


async def run_vibe_command(config: AppConfig, args: argparse.Namespace) -> None:
    seeds = _build_vibe_seeds(args)
    if not seeds:
        current = await send_ipc(config.control_socket_path, "get_vibe")
        print(json.dumps(current, indent=2))
        return
    response = await send_ipc(config.control_socket_path, "set_vibe", seeds=seeds)
    if not response.get("ok", False):
        raise SystemExit(f"vibe command failed: {response.get('error', 'unknown error')}")
    print(json.dumps(response, indent=2))


async def run_vibe_tui(config: AppConfig) -> None:
    print("ym-bridge vibe TUI")
    print("Press Enter to keep a field unchanged. q to cancel.")

    current = await send_ipc(config.control_socket_path, "get_vibe")
    if not current.get("ok", False):
        raise SystemExit(f"vibe-tui failed: {current.get('error', 'daemon not running')}")
    print(f"Current seeds: {', '.join(current.get('seeds', []))}")

    activity = input("Activity [wake-up|road-trip|work-background|workout|fall-asleep]: ").strip()
    if activity.lower() == "q":
        return
    diversity = input("Character [favorite|discover|popular|default]: ").strip()
    if diversity.lower() == "q":
        return
    mood = input("Mood [active|fun|calm|sad|all]: ").strip()
    if mood.lower() == "q":
        return
    language = input("Language [russian|not-russian|any|without-words]: ").strip()
    if language.lower() == "q":
        return
    extras = input("Extra seeds (comma-separated, optional): ").strip()
    if extras.lower() == "q":
        return

    seeds: list[str] = []
    if activity:
        seeds.append(ACTIVITY_MAP.get(activity, f"activity:{activity}"))
    if diversity:
        seeds.append(f"settingDiversity:{diversity}")
    if mood:
        seeds.append(f"settingMoodEnergy:{mood}")
    if language:
        seeds.append(f"settingLanguage:{language}")
    if extras:
        seeds.extend(part.strip() for part in extras.split(",") if part.strip())

    if not seeds:
        print("No changes requested.")
        return

    response = await send_ipc(config.control_socket_path, "set_vibe", seeds=seeds)
    if not response.get("ok", False):
        raise SystemExit(f"vibe-tui failed: {response.get('error', 'unknown error')}")
    print("Updated seeds:", ", ".join(response.get("seeds", [])))


async def run_waybar_command(config: AppConfig) -> None:
    response = await send_ipc(config.control_socket_path, "status")
    if not response.get("ok", False):
        print(
            json.dumps(
                {
                    "text": "YM offline",
                    "class": ["offline"],
                    "tooltip": "ym-bridge daemon not running",
                }
            )
        )
        return

    state = response.get("state", {})
    track = state.get("track", {})
    vibe = state.get("vibe", {})
    status = str(state.get("status", "Stopped"))
    icon = {"Playing": "▶", "Paused": "⏸", "Stopped": "■"}.get(status, "■")
    liked = bool(track.get("liked", False))
    liked_icon = " ♥" if liked else ""
    artist = str(track.get("artist", "")).strip()
    title = str(track.get("title", "")).strip() or "No track"
    full_text = (
        f"{icon} {artist} - {title}{liked_icon}" if artist else f"{icon} {title}{liked_icon}"
    )
    text = _compact_waybar_text(
        full_text, max_length=config.waybar_max_length, scroll=config.waybar_scroll
    )
    seeds = vibe.get("seeds", [])
    vibe_line = ", ".join(str(seed) for seed in seeds) if isinstance(seeds, list) else ""
    tooltip = (
        f"{artist}\n{title}\n{'Liked' if liked else 'Not liked'}"
        if artist
        else f"{title}\n{'Liked' if liked else 'Not liked'}"
    )
    if vibe_line:
        tooltip += f"\nVibe: {vibe_line}"
    print(
        json.dumps(
            {
                "text": text,
                "class": [status.lower(), "liked" if liked else "unliked"],
                "tooltip": tooltip,
            }
        )
    )


def _compact_waybar_text(text: str, *, max_length: int, scroll: bool) -> str:
    if len(text) <= max_length:
        return text
    if not scroll:
        return text[: max_length - 1] + "…"

    spacer = "   "
    marquee = text + spacer
    width = max(10, max_length)
    start = _next_waybar_cursor(text, len(marquee))
    looped = marquee + marquee
    return looped[start : start + width]


def _next_waybar_cursor(key: str, span: int) -> int:
    state_file = Path("/tmp/ym-bridge-waybar-state.json")
    previous_key = ""
    cursor = 0
    if state_file.exists():
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            previous_key = str(data.get("key", ""))
            cursor = int(data.get("cursor", 0))
        except Exception:  # noqa: BLE001
            previous_key = ""
            cursor = 0

    if previous_key == key:
        cursor = (cursor + 1) % max(span, 1)
    else:
        cursor = 0

    try:
        state_file.write_text(
            json.dumps({"key": key, "cursor": cursor, "updated_at": int(time.time())}),
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001
        pass
    return cursor


def run_doctor(config: AppConfig) -> None:
    checks = {
        "mpv_found": shutil.which("mpv") is not None,
        "oauth_token_present": bool(config.oauth_token),
        "control_socket_path": config.control_socket_path,
        "autoplay_on_start": config.autoplay_on_start,
        "waybar_max_length": config.waybar_max_length,
        "waybar_scroll": config.waybar_scroll,
        "mpris_name": config.mpris_name,
        "base_url": config.base_url,
    }
    print(json.dumps(checks, indent=2))


async def run(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    command = args.command or "run"

    if command == "run":
        await run_daemon(config)
        return
    if command == "recon":
        await run_recon_command(config)
        return
    if command == "doctor":
        run_doctor(config)
        return
    if command == "account":
        await run_account_command(config)
        return
    if command == "vibe":
        await run_vibe_command(config, args)
        return
    if command == "vibe-tui":
        await run_vibe_tui(config)
        return
    if command == "like":
        await _run_track_action(config, "like")
        return
    if command == "dislike":
        await _run_track_action(config, "dislike")
        return
    if command == "ctl":
        await run_ctl_command(config, args.action)
        return
    if command == "waybar":
        await run_waybar_command(config)
        return

    raise SystemExit(f"Unknown command: {command}")
