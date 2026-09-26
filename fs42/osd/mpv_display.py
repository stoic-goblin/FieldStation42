"""Appliance-compatible renderer for FieldStation42's status-driven OSD.

The historical renderer uses a transparent GLFW window.  Direct-DRM appliance
sessions do not provide an X11/Wayland desktop for that window, while the FS42
player already owns the screen through mpv.  This renderer preserves the OSD
status/config machinery and sends the resulting short-lived text to mpv's own
OSD over its existing IPC socket.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import stat
import time

from fs42.runtime_paths import MPV_IPC_SOCKET

from .status_display import (
    CONFIG_FILE_PATH,
    SOCKET_FILE,
    ChannelStatusTracker,
    HAlignment,
    StatusDisplayConfig,
    VAlignment,
    read_status,
)

MPV_SOCKET = MPV_IPC_SOCKET
POLL_SECONDS = 1.0 / 20.0
SOCKET_STABLE_SECONDS = 0.25


def _load_config(path: Path = CONFIG_FILE_PATH) -> StatusDisplayConfig:
    if not path.exists():
        return StatusDisplayConfig()
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("OSD config must be a list")
    for item in value:
        if not isinstance(item, dict):
            continue
        if item.get("type", "StatusDisplay") == "StatusDisplay":
            candidate = dict(item)
            candidate.pop("type", None)
            return StatusDisplayConfig.model_validate(candidate)
    return StatusDisplayConfig()


def _rgba_hex(color: tuple[int, int, int, int]) -> str:
    r, g, b, a = (max(0, min(255, int(value))) for value in color)
    return f"#{a:02X}{r:02X}{g:02X}{b:02X}"


def _mpv_font_name(font: str | None) -> str | None:
    if not font:
        return None
    path = Path(font)
    if path.is_file():
        try:
            from PIL import ImageFont
            return ImageFont.truetype(path, 12).getname()[0]
        except OSError:
            pass
    return font


def mpv_commands(config: StatusDisplayConfig, text: str) -> list[dict[str, object]]:
    align_x = {HAlignment.LEFT: "left", HAlignment.CENTER: "center", HAlignment.RIGHT: "right"}[config.halign]
    align_y = {VAlignment.TOP: "top", VAlignment.CENTER: "center", VAlignment.BOTTOM: "bottom"}[config.valign]
    size = max(1, round(config.font_size * config.expansion_factor))
    commands: list[dict[str, object]] = [
        {"command": ["set_property", "osd-align-x", align_x]},
        {"command": ["set_property", "osd-align-y", align_y]},
        {"command": ["set_property", "osd-font-size", size]},
        {"command": ["set_property", "osd-color", _rgba_hex(config.text_color)]},
        {"command": ["set_property", "osd-border-size", 2]},
        {"command": ["set_property", "osd-margin-x", max(0, round(config.x_margin * 1000))]},
        {"command": ["set_property", "osd-margin-y", max(0, round(config.y_margin * 1000))]},
    ]
    if font_name := _mpv_font_name(config.font):
        commands.append({"command": ["set_property", "osd-font", font_name]})
    commands.append({"command": ["show-text", text, max(1, round(config.display_time * 1000))]})
    return commands


def socket_identity(socket_path: str = MPV_SOCKET) -> tuple[int, int] | None:
    """Return a stable identity for the currently bound mpv Unix socket path."""
    try:
        value = os.stat(socket_path)
    except OSError:
        return None
    if not stat.S_ISSOCK(value.st_mode):
        return None
    return (value.st_dev, value.st_ino)


def send_commands(commands: list[dict[str, object]], socket_path: str = MPV_SOCKET) -> None:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.settimeout(0.5)
        client.connect(socket_path)
        with client.makefile("rwb", buffering=0) as stream:
            for request_id, command in enumerate(commands, start=1):
                request = dict(command)
                request["request_id"] = request_id
                stream.write((json.dumps(request, separators=(",", ":")) + "\n").encode("utf-8"))
                line = stream.readline()
                if not line:
                    raise OSError("mpv IPC closed before acknowledging OSD command")
                try:
                    response = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise OSError("mpv IPC returned invalid JSON") from exc
                if response.get("request_id") != request_id or response.get("error") != "success":
                    raise OSError(f"mpv rejected OSD command: {response}")
    finally:
        client.close()


def main() -> int:
    config = _load_config()
    tracker = ChannelStatusTracker()
    had_player = False
    player_socket_identity: tuple[int, int] | None = None
    socket_stable_since: float | None = None
    status_baseline_mtime_ns: int | None = None
    while True:
        current_socket_identity = socket_identity()
        if current_socket_identity is None:
            if had_player:
                tracker.reset()
            had_player = False
            player_socket_identity = None
            socket_stable_since = None
            status_baseline_mtime_ns = None
            time.sleep(POLL_SECONDS)
            continue
        if not had_player:
            tracker.reset()
            try:
                status_baseline_mtime_ns = os.stat(SOCKET_FILE).st_mtime_ns
            except OSError:
                status_baseline_mtime_ns = None
            had_player = True
            player_socket_identity = current_socket_identity
            socket_stable_since = time.monotonic()
            time.sleep(POLL_SECONDS)
            continue
        if current_socket_identity != player_socket_identity:
            # python-mpv-jsonipc can replace its startup socket while one FS42
            # session is coming up. Re-arm the presentation for the new socket,
            # but keep the original pre-session status baseline so a fresh
            # status already written during replacement still qualifies.
            tracker.reset()
            player_socket_identity = current_socket_identity
            socket_stable_since = time.monotonic()
            time.sleep(POLL_SECONDS)
            continue

        if socket_stable_since is None or time.monotonic() - socket_stable_since < SOCKET_STABLE_SECONDS:
            time.sleep(POLL_SECONDS)
            continue

        try:
            status_mtime_ns = os.stat(SOCKET_FILE).st_mtime_ns
        except OSError:
            time.sleep(POLL_SECONDS)
            continue
        if status_baseline_mtime_ns is not None:
            if status_mtime_ns == status_baseline_mtime_ns:
                time.sleep(POLL_SECONDS)
                continue
            status_baseline_mtime_ns = None

        status = read_status(SOCKET_FILE)
        if status is not None:
            text = tracker.changed_text(config, status)
            if text:
                try:
                    send_commands(mpv_commands(config, text))
                except OSError:
                    # mpv can replace its IPC socket between stat() and connect().
                    # Keep the current FS42 session baseline so a fresh status
                    # already written during startup is not lost on retry.
                    tracker.reset()
                    player_socket_identity = None
                    socket_stable_since = None
                else:
                    print(f"fs42-osd: displayed {text}", flush=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
