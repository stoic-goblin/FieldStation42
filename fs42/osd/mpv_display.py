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
import time

from .status_display import (
    CONFIG_FILE_PATH,
    SOCKET_FILE,
    ChannelStatusTracker,
    HAlignment,
    StatusDisplayConfig,
    VAlignment,
    read_status,
)

MPV_SOCKET = "/tmp/mpvsocket"
POLL_SECONDS = 1.0 / 20.0


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
    if config.font:
        commands.append({"command": ["set_property", "osd-font", config.font]})
    commands.append({"command": ["show-text", text, max(1, round(config.display_time * 1000))]})
    return commands


def send_commands(commands: list[dict[str, object]], socket_path: str = MPV_SOCKET) -> None:
    payload = b"".join((json.dumps(command, separators=(",", ":")) + "\n").encode("utf-8") for command in commands)
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.settimeout(0.25)
        client.connect(socket_path)
        client.sendall(payload)
    finally:
        client.close()


def main() -> int:
    config = _load_config()
    tracker = ChannelStatusTracker()
    had_player = False
    while True:
        player_present = os.path.exists(MPV_SOCKET)
        if not player_present:
            if had_player:
                tracker.reset()
            had_player = False
            time.sleep(POLL_SECONDS)
            continue
        if not had_player:
            tracker.reset()
        had_player = True
        status = read_status(SOCKET_FILE)
        if status is not None:
            text = tracker.changed_text(config, status)
            if text:
                try:
                    send_commands(mpv_commands(config, text))
                except OSError:
                    # mpv can replace its IPC socket during startup/teardown.
                    tracker.reset()
                    had_player = False
                else:
                    print(f"fs42-osd: displayed {text}", flush=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
