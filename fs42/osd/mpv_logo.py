"""mpv-native station-logo support for the direct-DRM appliance OSD.

This module intentionally consumes the existing station logo configuration
(`logo_dir`, `default_logo`, placement/alpha/timing fields) rather than creating
an appliance-specific branding system.  Rendering is delegated to mpv's
`overlay-add` command by :mod:`fs42.osd.mpv_display`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageChops, ImageSequence

from .content_classifier import ContentType


@dataclass(frozen=True)
class LogoFrame:
    bgra: bytes
    duration: float


@dataclass(frozen=True)
class LogoGeometry:
    x: int
    y: int
    width: int
    height: int
    stride: int


def resolve_logo_path(station: dict, project_root: Path) -> Path | None:
    """Resolve the station's default logo using historical FS42 path semantics."""
    if station.get("show_logo", True) is False:
        return None

    logo_dir = station.get("logo_dir")
    if not logo_dir:
        return None

    content_dir = station.get("content_dir")
    if content_dir:
        base_dir = project_root / content_dir / logo_dir
    else:
        candidate = Path(logo_dir)
        base_dir = candidate if candidate.is_absolute() else project_root / candidate

    default_name = station.get("default_logo")
    if default_name:
        candidate = base_dir / default_name
        return candidate if candidate.is_file() else None

    for pattern in ("*.png", "*.jpg", "*.jpeg", "*.gif", "*.bmp"):
        matches = sorted(base_dir.glob(pattern))
        if matches:
            return matches[0]
    return None


def logo_geometry(station: dict, screen_width: int, screen_height: int) -> LogoGeometry:
    """Map historical normalized logo geometry onto mpv OSD pixel coordinates."""
    width_frac = float(station.get("logo_width", 0.112))
    height_frac = float(station.get("logo_height", 0.15))
    x_margin_frac = float(station.get("logo_x_margin", 0.05))
    y_margin_frac = float(station.get("logo_y_margin", 0.05))

    width = max(1, round(screen_width * width_frac))
    height = max(1, round(screen_height * height_frac))
    # Historical OpenGL coordinates span -1..1, so x/y margin values correspond
    # to half that fraction in screen pixels.
    x_margin = max(0, round(screen_width * x_margin_frac / 2.0))
    y_margin = max(0, round(screen_height * y_margin_frac / 2.0))

    halign = str(station.get("logo_halign", "RIGHT")).upper()
    valign = str(station.get("logo_valign", "TOP")).upper()

    if halign == "LEFT":
        x = x_margin
    elif halign == "CENTER":
        x = max(0, (screen_width - width) // 2)
    else:
        x = max(0, screen_width - width - x_margin)

    if valign == "BOTTOM":
        y = max(0, screen_height - height - y_margin)
    elif valign == "CENTER":
        y = max(0, (screen_height - height) // 2)
    else:
        y = y_margin

    return LogoGeometry(x=x, y=y, width=width, height=height, stride=width * 4)


def load_logo_frames(path: Path, geometry: LogoGeometry, alpha: float) -> list[LogoFrame]:
    """Decode a static/animated station logo into resized BGRA frames for mpv."""
    alpha = max(0.0, min(1.0, float(alpha)))
    frames: list[LogoFrame] = []
    with Image.open(path) as image:
        default_duration_ms = int(image.info.get("duration", 100))
        for source in ImageSequence.Iterator(image):
            rgba = source.convert("RGBA").resize(
                (geometry.width, geometry.height), Image.Resampling.LANCZOS
            )
            if alpha < 1.0:
                a = rgba.getchannel("A").point(lambda value: round(value * alpha))
                rgba.putalpha(a)
            # mpv overlay-add requires premultiplied BGRA: each color component
            # must already be multiplied by the final alpha component.
            a = rgba.getchannel("A")
            r = ImageChops.multiply(rgba.getchannel("R"), a)
            g = ImageChops.multiply(rgba.getchannel("G"), a)
            b = ImageChops.multiply(rgba.getchannel("B"), a)
            premultiplied = Image.merge("RGBA", (r, g, b, a))
            duration_ms = int(source.info.get("duration", default_duration_ms))
            duration = max(duration_ms / 1000.0, 0.01)
            frames.append(LogoFrame(premultiplied.tobytes("raw", "BGRA"), duration))
    return frames


def overlay_add_command(frame_file: Path, geometry: LogoGeometry, overlay_id: int = 31) -> dict[str, object]:
    return {
        "command": [
            "overlay-add",
            overlay_id,
            geometry.x,
            geometry.y,
            str(frame_file),
            0,
            "bgra",
            geometry.width,
            geometry.height,
            geometry.stride,
        ]
    }


class LogoOverlayController:
    """Track when the current FS42 feature should display its station logo."""

    def __init__(
        self,
        project_root: Path,
        station_lookup: Callable[[str], dict | None],
    ) -> None:
        self.project_root = project_root
        self.station_lookup = station_lookup
        self.network_name: str | None = None
        self.title: str | None = None
        self.content_type: str | None = None
        self.station: dict | None = None
        self.logo_path: Path | None = None
        self.started_at: float | None = None

    def reset_remote(self) -> None:
        """Force the next FEATURE update to restart logo presentation."""
        self.network_name = None
        self.title = None
        self.content_type = None
        self.station = None
        self.logo_path = None
        self.started_at = None

    def update(self, status: dict, now: float) -> tuple[bool, bool]:
        """Return ``(show, restarted)`` for the supplied play status."""
        network = status.get("network_name")
        title = status.get("title")
        content_type = status.get("content_type", ContentType.UNKNOWN)

        entering_feature = self.content_type != ContentType.FEATURE and content_type == ContentType.FEATURE
        identity_changed = network != self.network_name or title != self.title

        self.network_name = network
        self.title = title
        self.content_type = content_type

        if content_type != ContentType.FEATURE or not network:
            self.started_at = None
            return (False, False)

        restarted = entering_feature or identity_changed or self.station is None
        if restarted:
            self.station = self.station_lookup(str(network))
            self.logo_path = (
                resolve_logo_path(self.station, self.project_root)
                if isinstance(self.station, dict)
                else None
            )
            self.started_at = now

        if not self.logo_path or not self.station:
            return (False, restarted)

        permanent = bool(self.station.get("logo_permanent", False))
        display_time = float(self.station.get("logo_display_time", 5.0))
        elapsed = 0.0 if self.started_at is None else max(0.0, now - self.started_at)
        return (permanent or elapsed < display_time, restarted)
