from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import logging

from ym_bridge.models import PlayerState
from ym_bridge.provider import MusicProvider


StateListener = Callable[[PlayerState], Awaitable[None]]
LOGGER = logging.getLogger(__name__)


class BridgeController:
    def __init__(self, provider: MusicProvider, poll_interval_seconds: float = 2.0) -> None:
        self._provider = provider
        self._poll_interval = poll_interval_seconds
        self._state = PlayerState()
        self._listeners: list[StateListener] = []
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()

    @property
    def state(self) -> PlayerState:
        return self._state

    def subscribe(self, listener: StateListener) -> None:
        self._listeners.append(listener)

    async def start(self) -> None:
        if self._task:
            return
        self._task = asyncio.create_task(self._sync_loop(), name="ym-bridge-sync")

    async def stop(self) -> None:
        self._stopped.set()
        if self._task:
            await self._task
        await self._provider.close()

    async def play(self) -> None:
        await self._provider.play()

    async def pause(self) -> None:
        await self._provider.pause()

    async def play_pause(self) -> None:
        await self._provider.play_pause()

    async def stop_playback(self) -> None:
        await self._provider.stop()

    async def next(self) -> None:
        await self._provider.next()

    async def previous(self) -> None:
        await self._provider.previous()

    async def seek(self, offset_us: int) -> None:
        await self._provider.seek(offset_us)

    async def set_position(self, track_id: str, position_us: int) -> None:
        await self._provider.set_position(track_id=track_id, position_us=position_us)

    async def set_volume(self, volume: float) -> None:
        await self._provider.set_volume(volume)

    async def like_current(self) -> None:
        await self._provider.like_current()

    async def dislike_current(self) -> None:
        await self._provider.dislike_current()

    async def _sync_loop(self) -> None:
        while not self._stopped.is_set():
            try:
                updated = await self._provider.fetch_state()
                self._state = updated
                await self._emit_state(updated)
            except Exception:
                LOGGER.exception("Failed to sync provider state")
            finally:
                try:
                    await asyncio.wait_for(self._stopped.wait(), timeout=self._poll_interval)
                except TimeoutError:
                    pass

    async def _emit_state(self, state: PlayerState) -> None:
        if not self._listeners:
            return
        await asyncio.gather(
            *(listener(state) for listener in self._listeners), return_exceptions=True
        )
