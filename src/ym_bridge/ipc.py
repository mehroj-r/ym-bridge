from __future__ import annotations

import asyncio
import json
from pathlib import Path
import time
from typing import Any

from ym_bridge.controller import BridgeController


class BridgeIpcServer:
    def __init__(self, controller: BridgeController, socket_path: str) -> None:
        self._controller = controller
        self._socket_path = Path(socket_path)
        self._server: asyncio.AbstractServer | None = None
        self._feedback_cooldown_seconds = 0.8
        self._last_feedback_at = 0.0

    async def start(self) -> None:
        self._socket_path.unlink(missing_ok=True)
        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=str(self._socket_path),
        )

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._socket_path.unlink(missing_ok=True)

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            line = await reader.readline()
            if not line:
                return
            request = json.loads(line.decode("utf-8"))
            response = await self._dispatch(request)
        except Exception as exc:  # noqa: BLE001
            response = {"ok": False, "error": str(exc)}
        writer.write((json.dumps(response) + "\n").encode("utf-8"))
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def _dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        action = str(request.get("action", "")).strip()
        if action == "status":
            return {"ok": True, "state": self._state_payload()}
        if action == "get_vibe":
            return {"ok": True, "seeds": list(self._controller.get_rotor_seeds())}
        if action == "set_vibe":
            raw_seeds = request.get("seeds", [])
            if not isinstance(raw_seeds, list):
                return {"ok": False, "error": "seeds must be a list"}
            seeds = tuple(str(seed) for seed in raw_seeds)
            await self._controller.set_rotor_seeds(seeds)
            await self._controller.refresh_state()
            return {
                "ok": True,
                "seeds": list(self._controller.get_rotor_seeds()),
                "state": self._state_payload(),
            }
        if action == "play":
            await self._controller.play()
            return {"ok": True, "state": self._state_payload()}
        if action == "pause":
            await self._controller.pause()
            return {"ok": True, "state": self._state_payload()}
        if action == "play_pause":
            await self._controller.play_pause()
            await self._controller.refresh_state()
            return {"ok": True, "state": self._state_payload()}
        if action == "next":
            await self._controller.next()
            await self._controller.refresh_state()
            return {"ok": True, "state": self._state_payload()}
        if action == "previous":
            await self._controller.previous()
            await self._controller.refresh_state()
            return {"ok": True, "state": self._state_payload()}
        if action == "like":
            if self._feedback_rate_limited():
                return {"ok": True, "skipped": "rate_limited", "state": self._state_payload()}
            await self._controller.like_current()
            await self._controller.refresh_state()
            return {"ok": True, "state": self._state_payload()}
        if action == "dislike":
            if self._feedback_rate_limited():
                return {"ok": True, "skipped": "rate_limited", "state": self._state_payload()}
            await self._controller.dislike_current()
            await self._controller.refresh_state()
            return {"ok": True, "state": self._state_payload()}
        return {"ok": False, "error": f"unknown action: {action}"}

    def _feedback_rate_limited(self) -> bool:
        now = time.monotonic()
        if now - self._last_feedback_at < self._feedback_cooldown_seconds:
            return True
        self._last_feedback_at = now
        return False

    def _state_payload(self) -> dict[str, Any]:
        state = self._controller.state
        return {
            "status": state.status.value,
            "position_us": state.position_us,
            "volume": state.volume,
            "vibe": {
                "seeds": list(self._controller.get_rotor_seeds()),
            },
            "track": {
                "id": state.track.track_id,
                "title": state.track.title,
                "artist": state.track.artist,
                "album": state.track.album,
                "liked": state.track.liked,
            },
        }


async def send_ipc(socket_path: str, action: str, **payload: Any) -> dict[str, Any]:
    try:
        reader, writer = await asyncio.open_unix_connection(socket_path)
    except FileNotFoundError:
        return {"ok": False, "error": "daemon socket not found"}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    request = {"action": action, **payload}
    writer.write((json.dumps(request) + "\n").encode("utf-8"))
    await writer.drain()
    line = await reader.readline()
    writer.close()
    await writer.wait_closed()
    if not line:
        return {"ok": False, "error": "empty response"}
    return json.loads(line.decode("utf-8"))
