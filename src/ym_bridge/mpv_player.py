from __future__ import annotations

import asyncio
import json
from pathlib import Path
import subprocess
import tempfile


class MpvPlayer:
    def __init__(self) -> None:
        self._socket_path = Path(tempfile.gettempdir()) / f"ym-bridge-mpv-{id(self)}.sock"
        self._process: subprocess.Popen[bytes] | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self._request_id = 1

    async def start(self) -> None:
        if self._process and self._process.poll() is None and self._reader and self._writer:
            return

        if self._socket_path.exists():
            self._socket_path.unlink(missing_ok=True)

        self._process = subprocess.Popen(
            [
                "mpv",
                "--idle=yes",
                "--no-terminal",
                f"--input-ipc-server={self._socket_path}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        for _ in range(100):
            if self._socket_path.exists():
                break
            await asyncio.sleep(0.05)
        else:
            raise RuntimeError("mpv IPC socket did not appear")

        self._reader, self._writer = await asyncio.open_unix_connection(str(self._socket_path))

    async def load(self, url: str, *, paused: bool = False) -> None:
        await self.start()
        await self._command(["loadfile", url, "replace"])
        await self._command(["set_property", "pause", paused])

    async def play(self) -> None:
        await self.start()
        await self._command(["set_property", "pause", False])

    async def pause(self) -> None:
        await self.start()
        await self._command(["set_property", "pause", True])

    async def play_pause(self) -> None:
        await self.start()
        await self._command(["cycle", "pause"])

    async def stop(self) -> None:
        if not self._writer:
            return
        await self._command(["stop"])

    async def seek_relative(self, offset_us: int) -> None:
        await self.start()
        await self._command(["seek", offset_us / 1_000_000, "relative"])

    async def seek_absolute(self, position_us: int) -> None:
        await self.start()
        await self._command(["set_property", "time-pos", position_us / 1_000_000])

    async def set_volume(self, volume: float) -> None:
        await self.start()
        await self._command(["set_property", "volume", max(0.0, min(100.0, volume * 100.0))])

    async def state(self) -> dict[str, float | bool]:
        if not self._writer:
            return {
                "pause": True,
                "time-pos": 0.0,
                "idle-active": True,
                "volume": 100.0,
            }

        pause = await self._get_property("pause")
        time_pos = await self._get_property("time-pos")
        idle_active = await self._get_property("idle-active")
        volume = await self._get_property("volume")
        return {
            "pause": bool(pause) if pause is not None else True,
            "time-pos": float(time_pos) if time_pos is not None else 0.0,
            "idle-active": bool(idle_active) if idle_active is not None else True,
            "volume": float(volume) if volume is not None else 100.0,
        }

    async def close(self) -> None:
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
            self._reader = None
            self._writer = None
        if self._process and self._process.poll() is None:
            self._process.terminate()
            self._process.wait(timeout=3)
        self._process = None
        self._socket_path.unlink(missing_ok=True)

    async def _get_property(self, name: str):
        result = await self._command(["get_property", name])
        return result.get("data")

    async def _command(self, command: list[object]) -> dict:
        if not self._writer or not self._reader:
            raise RuntimeError("mpv IPC is not connected")

        async with self._lock:
            request_id = self._request_id
            self._request_id += 1
            payload = {"command": command, "request_id": request_id}
            self._writer.write((json.dumps(payload) + "\n").encode("utf-8"))
            await self._writer.drain()

            while True:
                line = await self._reader.readline()
                if not line:
                    raise RuntimeError("mpv IPC closed")
                message = json.loads(line.decode("utf-8"))
                if message.get("request_id") == request_id:
                    return message
