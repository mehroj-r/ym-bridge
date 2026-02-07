from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import logging
from typing import Any
import uuid
import xml.etree.ElementTree as ET

import httpx

from ym_bridge.models import PlaybackStatus, PlayerState, Track
from ym_bridge.mpv_player import MpvPlayer
from ym_bridge.provider import MusicProvider


LOGGER = logging.getLogger(__name__)
SIGN_SALT = "XGRlBW9FXlekgbPrRHuSiA"


class ReverseEngineeringRequiredError(RuntimeError):
    pass


@dataclass(slots=True)
class YandexClientConfig:
    base_url: str
    oauth_token: str
    device_id: str
    user_agent: str
    autoplay_on_start: bool = False
    accept_language: str = "en"
    music_client: str = "YandexMusicAndroid/24026072"
    content_type: str = "adult"
    device_header: str = ""
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


class YandexMusicProvider(MusicProvider):
    def __init__(self, config: YandexClientConfig) -> None:
        self._config = config
        headers = {
            "Accept": "application/json",
            "Accept-Language": config.accept_language,
            "User-Agent": config.user_agent,
            "X-Yandex-Music-Client": config.music_client,
            "X-Yandex-Music-Content-Type": config.content_type,
            "X-Yandex-Music-Device": config.device_header,
        }
        if config.oauth_token:
            headers["Authorization"] = f"OAuth {config.oauth_token}"

        self._http = httpx.AsyncClient(base_url=config.base_url, headers=headers, timeout=20)
        self._player = MpvPlayer()
        self._rotor_seeds: list[str] = list(config.rotor_seeds)
        self._sequence: list[dict[str, Any]] = []
        self._index = 0
        self._session_id = ""
        self._session_batch_id = ""
        self._feedback_from = ""
        self._account_uid: int | None = None
        self._play_id = ""
        self._play_start_timestamp = ""
        self._reported_finish_play_id = ""

    async def fetch_state(self) -> PlayerState:
        if not self._config.oauth_token:
            return PlayerState(
                status=PlaybackStatus.PAUSED,
                track=Track(track_id="demo", title="Connect Yandex account", artist="ym-bridge"),
                can_control=False,
                can_seek=False,
                can_go_next=False,
                can_go_previous=False,
            )

        if not self._sequence:
            await self._ensure_sequence(autoplay=self._config.autoplay_on_start)

        runtime = await self._player.state()
        if runtime.get("idle-active") and self._sequence:
            finished_item = self._current_item()
            next_item = self._peek_item(1)
            played_seconds = float(runtime.get("time-pos", 0.0) or 0.0)
            await self._report_play_finished_if_needed(played_seconds)
            if finished_item and next_item:
                await self._send_finish_and_start_feedback(
                    finished_track_id=str(finished_item.get("id", "")).strip(),
                    finished_track_length_seconds=float(finished_item.get("durationMs", 0) or 0)
                    / 1000.0,
                    started_track_id=str(next_item.get("id", "")).strip(),
                    total_played_seconds=played_seconds,
                )
            await self._advance(1)
            runtime = await self._player.state()

        track = self._current_track()
        status = PlaybackStatus.PLAYING
        if runtime.get("idle-active"):
            status = PlaybackStatus.STOPPED
        elif runtime.get("pause"):
            status = PlaybackStatus.PAUSED

        return PlayerState(
            status=status,
            position_us=int(float(runtime.get("time-pos", 0.0)) * 1_000_000),
            volume=max(0.0, min(1.0, float(runtime.get("volume", 100.0)) / 100.0)),
            can_control=True,
            can_seek=True,
            can_go_next=bool(self._sequence),
            can_go_previous=bool(self._sequence),
            track=track,
        )

    async def play(self) -> None:
        if not self._sequence:
            await self._ensure_sequence(autoplay=False)
        runtime = await self._player.state()
        if runtime.get("idle-active"):
            await self._play_current()
            return
        await self._player.play()
        if runtime.get("pause") and not self._play_id:
            self._mark_play_started()

    async def pause(self) -> None:
        await self._player.pause()

    async def play_pause(self) -> None:
        runtime = await self._player.state()
        await self._player.play_pause()
        if runtime.get("pause") and not self._play_id:
            self._mark_play_started()

    async def stop(self) -> None:
        await self._player.stop()

    async def next(self) -> None:
        await self._advance(1, send_skip_feedback=True)

    async def previous(self) -> None:
        await self._advance(-1)

    async def seek(self, offset_us: int) -> None:
        await self._player.seek_relative(offset_us)

    async def set_position(self, track_id: str, position_us: int) -> None:
        current = self._current_track()
        if current.track_id and track_id and track_id != current.track_id:
            return
        await self._player.seek_absolute(position_us)

    async def set_volume(self, volume: float) -> None:
        await self._player.set_volume(volume)

    async def close(self) -> None:
        await self._player.close()
        await self._http.aclose()

    async def set_rotor_seeds(self, seeds: tuple[str, ...]) -> None:
        normalized = [seed.strip() for seed in seeds if seed.strip()]
        if not normalized:
            raise ReverseEngineeringRequiredError("At least one rotor seed is required")
        self._rotor_seeds = normalized
        await self._player.stop()
        self._sequence = []
        self._index = 0
        self._session_id = ""
        self._session_batch_id = ""
        self._feedback_from = ""
        self._play_id = ""
        self._play_start_timestamp = ""
        self._reported_finish_play_id = ""

    def get_rotor_seeds(self) -> tuple[str, ...]:
        return tuple(self._rotor_seeds)

    async def like_current(self) -> None:
        if not self._sequence:
            await self._ensure_sequence()

        item = self._current_item()
        if not item:
            raise ReverseEngineeringRequiredError("No current track to like")

        track_id = str(item.get("id", ""))
        queue_ref = self._track_queue_ref(item)
        if not track_id or not queue_ref:
            raise ReverseEngineeringRequiredError(
                "Current track is missing ids required for like action"
            )

        uid = await self._ensure_account_uid()
        timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
        likes_endpoint = self._config.endpoint_likes_tracks_add.format(user_id=uid)
        await self._request_json(
            "POST",
            likes_endpoint,
            json={
                "tracks": [
                    {
                        "clientTimestamp": timestamp,
                        "trackId": queue_ref,
                    }
                ]
            },
        )

        await self._send_rotor_feedback(
            track_id=track_id,
            timestamp=timestamp,
            event_type="like",
        )
        self._set_current_liked(True)

    async def dislike_current(self) -> None:
        if not self._sequence:
            await self._ensure_sequence()

        item = self._current_item()
        if not item:
            raise ReverseEngineeringRequiredError("No current track to dislike")

        track_id = str(item.get("id", "")).strip()
        if not track_id:
            raise ReverseEngineeringRequiredError(
                "Current track is missing id required for dislike action"
            )

        uid = await self._ensure_account_uid()
        timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
        remove_endpoint = self._config.endpoint_likes_tracks_remove.format(user_id=uid)
        await self._request_json(
            "POST",
            remove_endpoint,
            json={
                "tracks": [
                    {
                        "clientTimestamp": timestamp,
                        "trackId": track_id,
                    }
                ]
            },
        )

        await self._send_rotor_feedback(
            track_id=track_id,
            timestamp=timestamp,
            event_type="unlike",
        )
        self._set_current_liked(False)

    async def fetch_account_about(self) -> dict[str, Any]:
        payload = await self._request_json("GET", self._config.endpoint_account_about)
        result = payload.get("result") if isinstance(payload, dict) else None
        if isinstance(result, dict):
            return result
        return {}

    async def _ensure_sequence(self, autoplay: bool | None = None) -> None:
        if self._sequence:
            return
        payload = {
            "includeTracksInResponse": True,
            "includeWaveModel": True,
            "interactive": True,
            "seeds": list(self._rotor_seeds),
        }
        data = await self._request_json(
            "POST", self._config.endpoint_rotor_session_new, json=payload
        )
        result = data.get("result", {})
        self._session_id = str(result.get("radioSessionId", ""))
        self._session_batch_id = str(result.get("batchId", ""))
        wave = result.get("wave", {})
        if isinstance(wave, dict):
            from_id = str(wave.get("idForFrom", "")).strip()
            if from_id:
                self._feedback_from = f"radio-mobile-{from_id}-default"
        sequence = result.get("sequence", [])
        if not isinstance(sequence, list) or not sequence:
            raise ReverseEngineeringRequiredError("Rotor session returned empty sequence")
        self._sequence = [item for item in sequence if isinstance(item, dict)]
        self._index = 0
        should_autoplay = self._config.autoplay_on_start if autoplay is None else autoplay
        await self._play_current(paused=not should_autoplay)

    async def _advance(self, delta: int, send_skip_feedback: bool = False) -> None:
        if not self._sequence:
            await self._ensure_sequence(autoplay=True)
            return

        previous_item = self._current_item()
        runtime = await self._player.state()
        played_seconds = float(runtime.get("time-pos", 0.0) or 0.0)

        self._index = (self._index + delta) % len(self._sequence)

        current_item = self._current_item()
        if send_skip_feedback and previous_item and current_item:
            previous_track_id = str(previous_item.get("id", "")).strip()
            current_track_id = str(current_item.get("id", "")).strip()
            if previous_track_id and current_track_id:
                await self._send_skip_and_start_feedback(
                    skipped_track_id=previous_track_id,
                    started_track_id=current_track_id,
                    total_played_seconds=played_seconds,
                )

        await self._play_current()

    async def _play_current(self, *, paused: bool = False) -> None:
        track_id = self._current_track().track_id
        if not track_id:
            raise ReverseEngineeringRequiredError("Current sequence item has no track id")
        stream_url = await self._resolve_track_stream_url(track_id)
        await self._player.load(stream_url, paused=paused)
        if paused:
            self._play_id = ""
            self._play_start_timestamp = ""
            self._reported_finish_play_id = ""
            return
        self._mark_play_started()

    def _append_sequence_from_feedback(self, payload: dict[str, Any]) -> None:
        result = payload.get("result", {}) if isinstance(payload, dict) else {}
        if not isinstance(result, dict):
            return

        next_batch = result.get("batchId")
        if isinstance(next_batch, str) and next_batch:
            self._session_batch_id = next_batch

        sequence = result.get("sequence", [])
        if not isinstance(sequence, list):
            return

        for item in sequence:
            if isinstance(item, dict):
                self._sequence.append(item)

    def _current_item(self) -> dict[str, Any] | None:
        if not self._sequence:
            return None
        item = self._sequence[self._index]
        if not isinstance(item, dict):
            return None
        track_data = item.get("track")
        if not isinstance(track_data, dict):
            return None
        return track_data

    def _peek_item(self, delta: int) -> dict[str, Any] | None:
        if not self._sequence:
            return None
        item = self._sequence[(self._index + delta) % len(self._sequence)]
        if not isinstance(item, dict):
            return None
        track_data = item.get("track")
        if not isinstance(track_data, dict):
            return None
        return track_data

    def _track_queue_ref(self, track_data: dict[str, Any]) -> str:
        track_id = str(track_data.get("id", "")).strip()
        albums = track_data.get("albums", [])
        if not track_id or not isinstance(albums, list) or not albums:
            return ""
        first = albums[0]
        if not isinstance(first, dict):
            return ""
        album_id = str(first.get("id", "")).strip()
        if not album_id:
            return ""
        return f"{track_id}:{album_id}"

    def _queue_refs(self, limit: int, start_offset: int = 0) -> list[str]:
        if not self._sequence:
            return []
        refs: list[str] = []
        total = len(self._sequence)
        for offset in range(min(limit, total)):
            item = self._sequence[(self._index + start_offset + offset) % total]
            if not isinstance(item, dict):
                continue
            track_data = item.get("track")
            if not isinstance(track_data, dict):
                continue
            ref = self._track_queue_ref(track_data)
            if ref:
                refs.append(ref)
        return refs

    async def _ensure_account_uid(self) -> int:
        if self._account_uid is not None:
            return self._account_uid
        account = await self.fetch_account_about()
        uid = account.get("uid")
        if not isinstance(uid, int):
            raise ReverseEngineeringRequiredError(
                "Could not resolve account uid for likes endpoint"
            )
        self._account_uid = uid
        return uid

    async def _send_rotor_feedback(self, *, track_id: str, timestamp: str, event_type: str) -> None:
        if not self._session_id:
            return
        feedback_endpoint = self._config.endpoint_rotor_session_tracks.format(
            session_id=self._session_id
        )
        feedback_payload = {
            "feedbacks": [
                {
                    "batchId": self._session_batch_id or f"{uuid.uuid4()}.local",
                    "event": {
                        "timestamp": timestamp,
                        "trackId": track_id,
                        "type": event_type,
                    },
                    "from": self._feedback_from or "radio-mobile-user-onyourwave-default",
                }
            ],
            "queue": self._queue_refs(limit=2),
        }
        response = await self._request_json("POST", feedback_endpoint, json=feedback_payload)
        self._append_sequence_from_feedback(response)

    async def _send_finish_and_start_feedback(
        self,
        *,
        finished_track_id: str,
        finished_track_length_seconds: float,
        started_track_id: str,
        total_played_seconds: float,
    ) -> None:
        if not self._session_id or not finished_track_id or not started_track_id:
            return

        feedback_endpoint = self._config.endpoint_rotor_session_tracks.format(
            session_id=self._session_id
        )
        timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
        batch_id = self._session_batch_id or f"{uuid.uuid4()}.local"
        feedback_payload = {
            "feedbacks": [
                {
                    "batchId": batch_id,
                    "event": {
                        "timestamp": timestamp,
                        "totalPlayedSeconds": round(max(total_played_seconds, 0.0), 3),
                        "trackId": finished_track_id,
                        "trackLengthSeconds": round(max(finished_track_length_seconds, 0.0), 3),
                        "type": "trackFinished",
                    },
                    "from": self._feedback_from or "radio-mobile-user-onyourwave-default",
                },
                {
                    "batchId": batch_id,
                    "event": {
                        "timestamp": timestamp,
                        "trackId": started_track_id,
                        "type": "trackStarted",
                    },
                    "from": self._feedback_from or "radio-mobile-user-onyourwave-default",
                },
            ],
            "queue": self._queue_refs(limit=2, start_offset=1),
        }
        response = await self._request_json("POST", feedback_endpoint, json=feedback_payload)
        self._append_sequence_from_feedback(response)

    async def _send_skip_and_start_feedback(
        self,
        *,
        skipped_track_id: str,
        started_track_id: str,
        total_played_seconds: float,
    ) -> None:
        if not self._session_id:
            return

        feedback_endpoint = self._config.endpoint_rotor_session_tracks.format(
            session_id=self._session_id
        )
        timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
        feedback_payload = {
            "feedbacks": [
                {
                    "batchId": f"{uuid.uuid4()}.local",
                    "event": {
                        "timestamp": timestamp,
                        "trackId": started_track_id,
                        "type": "trackStarted",
                    },
                    "from": self._feedback_from or "radio-mobile-user-onyourwave-default",
                },
                {
                    "batchId": self._session_batch_id or f"{uuid.uuid4()}.local",
                    "event": {
                        "timestamp": timestamp,
                        "totalPlayedSeconds": round(max(total_played_seconds, 0.0), 3),
                        "trackId": skipped_track_id,
                        "type": "skip",
                    },
                    "from": self._feedback_from or "radio-mobile-user-onyourwave-default",
                },
            ],
            "queue": self._queue_refs(limit=1),
        }
        response = await self._request_json("POST", feedback_endpoint, json=feedback_payload)
        self._append_sequence_from_feedback(response)

    async def _report_play_finished_if_needed(self, played_seconds: float) -> None:
        if not self._play_id or self._play_id == self._reported_finish_play_id:
            return

        current_item = self._current_item()
        if not current_item:
            return

        track_id = str(current_item.get("id", "")).strip()
        if not track_id:
            return

        album_id = ""
        albums = current_item.get("albums", [])
        if isinstance(albums, list) and albums and isinstance(albums[0], dict):
            album_id = str(albums[0].get("id", ""))

        track_length_seconds = float(current_item.get("durationMs", 0) or 0) / 1000.0
        ended_seconds = round(max(played_seconds, track_length_seconds), 3)
        now_iso = datetime.now().astimezone().isoformat(timespec="milliseconds")

        payload = {
            "plays": [
                {
                    "albumId": album_id,
                    "audioAuto": "none",
                    "audioOutputName": "Phone",
                    "audioOutputType": "other",
                    "isFromAutoflow": False,
                    "batchId": self._session_batch_id or f"{uuid.uuid4()}.local",
                    "changeReason": "finish",
                    "context": "radio",
                    "contextItem": "user:onyourwave",
                    "isRestored": False,
                    "endPositionSeconds": ended_seconds,
                    "expectedTrackLengthSeconds": round(track_length_seconds, 3),
                    "fadeMode": "crossfade",
                    "from": self._feedback_from or "radio-mobile-user-onyourwave-default",
                    "fromCache": False,
                    "listenActivity": "END",
                    "maxPlayerStage": "play",
                    "navigationId": f"ym-bridge_{uuid.uuid4()}",
                    "isFromOfflineWave": False,
                    "pause": False,
                    "playbackActionId": str(uuid.uuid4()),
                    "isFromPumpkin": False,
                    "radioSessionId": self._session_id,
                    "isRepeated": False,
                    "seek": False,
                    "smartPreview": False,
                    "startPositionSeconds": 0.0,
                    "startTimestamp": self._play_start_timestamp or now_iso,
                    "timestamp": now_iso,
                    "totalPlayedSeconds": ended_seconds,
                    "trackId": track_id,
                    "trackLengthSeconds": round(track_length_seconds, 3),
                    "playId": self._play_id,
                }
            ]
        }
        await self._request_json(
            "POST",
            self._config.endpoint_plays,
            json=payload,
            extra_params={"client-now": now_iso},
        )
        self._reported_finish_play_id = self._play_id

    def _current_track(self) -> Track:
        if not self._sequence:
            return Track(track_id="", title="", artist="")
        item = self._sequence[self._index]
        track_data = item.get("track", {}) if isinstance(item, dict) else {}
        if not isinstance(track_data, dict):
            return Track(track_id="", title="", artist="")

        artists = track_data.get("artists", [])
        artist_names: list[str] = []
        if isinstance(artists, list):
            for artist in artists:
                if isinstance(artist, dict):
                    name = artist.get("name")
                    if name:
                        artist_names.append(str(name))

        album_title = ""
        albums = track_data.get("albums", [])
        if isinstance(albums, list) and albums:
            first_album = albums[0]
            if isinstance(first_album, dict):
                album_title = str(first_album.get("title", ""))

        art_url = str(track_data.get("coverUri", "") or "")
        if art_url:
            art_url = "https://" + art_url.replace("%%", "400x400")

        return Track(
            track_id=str(track_data.get("id", "")),
            title=str(track_data.get("title", "")),
            artist=", ".join(artist_names),
            album=album_title,
            length_ms=int(track_data.get("durationMs", 0) or 0),
            art_url=art_url,
            liked=bool(item.get("liked", False)) if isinstance(item, dict) else False,
        )

    def _set_current_liked(self, liked: bool) -> None:
        if not self._sequence:
            return
        current = self._sequence[self._index]
        if isinstance(current, dict):
            current["liked"] = liked

    def _mark_play_started(self) -> None:
        self._play_id = str(uuid.uuid4())
        self._play_start_timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
        self._reported_finish_play_id = ""

    async def _resolve_track_stream_url(self, track_id: str) -> str:
        payload = await self._request_json("GET", f"/tracks/{track_id}/download-info")
        result = payload.get("result", [])
        if not isinstance(result, list) or not result:
            raise ReverseEngineeringRequiredError(f"No download info for track {track_id}")

        chosen = None
        for item in result:
            if isinstance(item, dict) and item.get("codec") == "mp3":
                chosen = item
                break
        if chosen is None:
            chosen = result[0]
        if not isinstance(chosen, dict):
            raise ReverseEngineeringRequiredError(
                f"Unexpected download info shape for track {track_id}"
            )

        download_info_url = str(chosen.get("downloadInfoUrl", ""))
        if not download_info_url:
            raise ReverseEngineeringRequiredError(f"downloadInfoUrl missing for track {track_id}")

        xml_response = await self._http.get(download_info_url)
        xml_response.raise_for_status()
        xml_root = ET.fromstring(xml_response.text)

        host = xml_root.findtext("host")
        path = xml_root.findtext("path")
        ts = xml_root.findtext("ts")
        secret = xml_root.findtext("s")

        if not host or not path or not ts or not secret:
            raise ReverseEngineeringRequiredError("downloadInfo XML missing required fields")

        sign_src = SIGN_SALT + path[1:] + secret
        sign = hashlib.md5(sign_src.encode("utf-8")).hexdigest()
        return f"https://{host}/get-mp3/{sign}/{ts}{path}"

    async def _request_json(
        self,
        method: str,
        endpoint: str,
        json: dict[str, Any] | None = None,
        extra_params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {}
        if self._config.device_id:
            params["device-id"] = self._config.device_id
        if extra_params:
            params.update(extra_params)
        response = await self._http.request(
            method,
            endpoint,
            params=params or None,
            json=json,
            headers={
                "X-Request-Id": str(uuid.uuid4()),
                "X-Yandex-Music-Client-Now": datetime.now()
                .astimezone()
                .isoformat(timespec="seconds"),
            },
        )
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()
