"""Status-driven channel identity and formatting for FieldStation42 OSDs."""
from __future__ import annotations

from enum import Enum
import json
import re
from pathlib import Path

from pydantic import BaseModel


SOCKET_FILE = "runtime/play_status.socket"
CONFIG_FILE_PATH = Path("osd/osd.json")


class HAlignment(Enum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    CENTER = "CENTER"


class VAlignment(Enum):
    TOP = "TOP"
    BOTTOM = "BOTTOM"
    CENTER = "CENTER"


class StatusDisplayConfig(BaseModel):
    display_time: float = 2.0
    halign: HAlignment = HAlignment.LEFT
    valign: VAlignment = VAlignment.TOP
    format_text: str = "{channel_number} - {network_name}"
    text_color: tuple[int, int, int, int] = (0, 255, 0, 200)
    font_size: int = 40
    expansion_factor: float = 1.0
    font: str | None = None
    x_margin: float = 0.1
    y_margin: float = 0.1
    delay: float = 0.0


def compact_network_name(value: object) -> str:
    """Return a cable-box-friendly station token without station-specific rules."""
    return re.sub(r"[^A-Za-z0-9]+", "", str(value or "")).upper()


def render_status_text(config: StatusDisplayConfig, status: dict[str, object]) -> str:
    fields = dict(status)
    fields["network_compact"] = compact_network_name(status.get("network_name"))
    return config.format_text.format(**fields)


def channel_identity(status: dict[str, object]) -> tuple[object, str] | None:
    channel = status.get("channel_number")
    network = str(status.get("network_name") or "").strip()
    if status.get("status") == "stopped" or channel in (None, -1, "-1") or not network:
        return None
    return channel, network


def read_status(path: str | Path = SOCKET_FILE) -> dict[str, object] | None:
    try:
        raw = Path(path).read_text(encoding="utf-8")
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


class ChannelStatusTracker:
    """Emit only when actual channel/network identity changes.

    Playback state, title, timestamp, and duration changes deliberately do not
    retrigger a tune banner.
    """

    def __init__(self) -> None:
        self.last_identity: tuple[object, str] | None = None

    def reset(self) -> None:
        self.last_identity = None

    def changed_text(self, config: StatusDisplayConfig, status: dict[str, object]) -> str | None:
        identity = channel_identity(status)
        if identity is None:
            return None
        if identity == self.last_identity:
            return None
        self.last_identity = identity
        return render_status_text(config, status)
