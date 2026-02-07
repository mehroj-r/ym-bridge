from __future__ import annotations

import asyncio

from dbus_next import Variant
from dbus_next.aio import MessageBus
from dbus_next.constants import BusType, PropertyAccess
from dbus_next.service import ServiceInterface, dbus_property, method, signal

from ym_bridge.controller import BridgeController
from ym_bridge.models import PlayerState


OBJECT_PATH = "/org/mpris/MediaPlayer2"


class MediaPlayer2Interface(ServiceInterface):
    def __init__(self, controller: BridgeController) -> None:
        super().__init__("org.mpris.MediaPlayer2")
        self._controller = controller

    @method()
    def Raise(self) -> "":
        return None

    @method()
    async def Quit(self) -> "":
        await self._controller.stop()

    @dbus_property(access=PropertyAccess.READ)
    def CanQuit(self) -> "b":
        return self._controller.state.can_quit

    @dbus_property(access=PropertyAccess.READ)
    def CanRaise(self) -> "b":
        return self._controller.state.can_raise

    @dbus_property(access=PropertyAccess.READ)
    def HasTrackList(self) -> "b":
        return False

    @dbus_property(access=PropertyAccess.READ)
    def Identity(self) -> "s":
        return self._controller.state.identity

    @dbus_property(access=PropertyAccess.READ)
    def DesktopEntry(self) -> "s":
        return self._controller.state.desktop_entry

    @dbus_property(access=PropertyAccess.READ)
    def SupportedUriSchemes(self) -> "as":
        return ["https"]

    @dbus_property(access=PropertyAccess.READ)
    def SupportedMimeTypes(self) -> "as":
        return ["audio/mpeg", "audio/aac"]


class MediaPlayer2PlayerInterface(ServiceInterface):
    def __init__(self, controller: BridgeController) -> None:
        super().__init__("org.mpris.MediaPlayer2.Player")
        self._controller = controller

    @method()
    async def Next(self) -> "":
        await self._controller.next()

    @method()
    async def Previous(self) -> "":
        await self._controller.previous()

    @method()
    async def Pause(self) -> "":
        await self._controller.pause()

    @method()
    async def PlayPause(self) -> "":
        await self._controller.play_pause()

    @method()
    async def Stop(self) -> "":
        await self._controller.stop_playback()

    @method()
    async def Play(self) -> "":
        await self._controller.play()

    @method()
    async def Seek(self, offset: "x") -> "":
        await self._controller.seek(offset_us=int(offset))
        self.Seeked(self._controller.state.position_us)

    @method()
    async def SetPosition(self, track_id: "o", position: "x") -> "":
        track_path = str(track_id)
        track_identity = track_path.rsplit("/", maxsplit=1)[-1]
        await self._controller.set_position(track_id=track_identity, position_us=int(position))
        self.Seeked(self._controller.state.position_us)

    @method()
    def OpenUri(self, _uri: "s") -> "":
        return None

    @signal()
    def Seeked(self, position: "x") -> "x":
        return position

    @dbus_property(access=PropertyAccess.READ)
    def PlaybackStatus(self) -> "s":
        return self._controller.state.status.value

    @dbus_property(access=PropertyAccess.READ)
    def LoopStatus(self) -> "s":
        return "None"

    @dbus_property(access=PropertyAccess.READ)
    def Rate(self) -> "d":
        return 1.0

    @dbus_property(access=PropertyAccess.READ)
    def Shuffle(self) -> "b":
        return False

    @dbus_property(access=PropertyAccess.READWRITE)
    def Volume(self) -> "d":
        return self._controller.state.volume

    @Volume.setter
    def Volume(self, volume: "d") -> None:
        asyncio.create_task(self._controller.set_volume(float(volume)))

    @dbus_property(access=PropertyAccess.READ)
    def Position(self) -> "x":
        return self._controller.state.position_us

    @dbus_property(access=PropertyAccess.READ)
    def MinimumRate(self) -> "d":
        return 1.0

    @dbus_property(access=PropertyAccess.READ)
    def MaximumRate(self) -> "d":
        return 1.0

    @dbus_property(access=PropertyAccess.READ)
    def CanGoNext(self) -> "b":
        return self._controller.state.can_go_next

    @dbus_property(access=PropertyAccess.READ)
    def CanGoPrevious(self) -> "b":
        return self._controller.state.can_go_previous

    @dbus_property(access=PropertyAccess.READ)
    def CanPlay(self) -> "b":
        return self._controller.state.can_play

    @dbus_property(access=PropertyAccess.READ)
    def CanPause(self) -> "b":
        return self._controller.state.can_pause

    @dbus_property(access=PropertyAccess.READ)
    def CanSeek(self) -> "b":
        return self._controller.state.can_seek

    @dbus_property(access=PropertyAccess.READ)
    def CanControl(self) -> "b":
        return self._controller.state.can_control

    @dbus_property(access=PropertyAccess.READ)
    def Metadata(self) -> "a{sv}":
        track = self._controller.state.track
        track_obj = f"{OBJECT_PATH}/track/{track.track_id or 'none'}"
        metadata: dict[str, Variant] = {
            "mpris:trackid": Variant("o", track_obj),
            "xesam:title": Variant("s", track.title),
            "xesam:artist": Variant("as", [track.artist] if track.artist else []),
            "xesam:album": Variant("s", track.album),
            "mpris:length": Variant("x", track.length_ms * 1000),
        }
        if track.art_url:
            metadata["mpris:artUrl"] = Variant("s", track.art_url)
        if track.url:
            metadata["xesam:url"] = Variant("s", track.url)
        return metadata


class BridgeMprisService:
    def __init__(self, controller: BridgeController, mpris_name: str) -> None:
        self._controller = controller
        self._mpris_name = mpris_name
        self._bus: MessageBus | None = None
        self._root = MediaPlayer2Interface(controller)
        self._player = MediaPlayer2PlayerInterface(controller)

    async def start(self) -> None:
        self._bus = await MessageBus(bus_type=BusType.SESSION).connect()
        self._bus.export(OBJECT_PATH, self._root)
        self._bus.export(OBJECT_PATH, self._player)
        await self._bus.request_name(f"org.mpris.MediaPlayer2.{self._mpris_name}")
        self._controller.subscribe(self.on_state_changed)

    async def stop(self) -> None:
        if self._bus:
            self._bus.disconnect()

    async def on_state_changed(self, state: PlayerState) -> None:
        self._root.emit_properties_changed(
            {
                "CanQuit": state.can_quit,
                "CanRaise": state.can_raise,
                "Identity": state.identity,
                "DesktopEntry": state.desktop_entry,
            },
            [],
        )
        self._player.emit_properties_changed(
            {
                "PlaybackStatus": state.status.value,
                "Volume": state.volume,
                "Position": state.position_us,
                "CanGoNext": state.can_go_next,
                "CanGoPrevious": state.can_go_previous,
                "CanPlay": state.can_play,
                "CanPause": state.can_pause,
                "CanSeek": state.can_seek,
                "CanControl": state.can_control,
                "Metadata": self._player.Metadata,
            },
            [],
        )
