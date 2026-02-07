from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PlaybackStatus(str, Enum):
    PLAYING = "Playing"
    PAUSED = "Paused"
    STOPPED = "Stopped"


@dataclass(slots=True)
class Track:
    track_id: str
    title: str
    artist: str
    album: str = ""
    length_ms: int = 0
    art_url: str = ""
    url: str = ""
    liked: bool = False


@dataclass(slots=True)
class PlayerState:
    status: PlaybackStatus = PlaybackStatus.STOPPED
    position_us: int = 0
    volume: float = 1.0
    can_control: bool = True
    can_seek: bool = True
    can_go_next: bool = True
    can_go_previous: bool = True
    can_pause: bool = True
    can_play: bool = True
    can_quit: bool = False
    can_raise: bool = False
    identity: str = "Yandex Music Bridge"
    desktop_entry: str = "ym-bridge"
    track: Track = field(default_factory=lambda: Track(track_id="", title="", artist=""))
