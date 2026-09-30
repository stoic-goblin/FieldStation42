"""Fixed per-item loudness gain support for FieldStation42 playback.

The player consumes a precomputed gain map.  Analysis and policy stay outside the
playback loop so media keeps its original internal dynamics; each item receives
one constant gain for its whole playback.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Mapping


def canonical_media_path(path: str | Path) -> str:
    """Return the local canonical path used for gain-map lookups."""
    text = str(path)
    if "://" in text:
        return text
    return str(Path(text).expanduser().resolve(strict=False))


def volume_filter_db(gain_db: float) -> str | None:
    """Build an mpv/FFmpeg fixed-volume filter, or None for effectively 0 dB."""
    gain = float(gain_db)
    if not math.isfinite(gain):
        return None
    if abs(gain) < 0.005:
        return None
    return f"lavfi=[volume={gain:.2f}dB]"


class LoudnessGainMap:
    """Read-only canonical-media-path -> fixed dB gain mapping."""

    def __init__(self, gains: Mapping[str, float] | None = None, metadata: Mapping | None = None):
        self.gains: dict[str, float] = {}
        for raw_path, raw_gain in (gains or {}).items():
            try:
                gain = float(raw_gain)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(gain):
                continue
            self.gains[canonical_media_path(raw_path)] = gain
        self.metadata = dict(metadata or {})

    @classmethod
    def from_file(cls, path: str | Path) -> "LoudnessGainMap":
        source = Path(path).expanduser()
        if not source.is_absolute():
            source = Path.cwd() / source
        with source.open(encoding="utf-8") as fh:
            payload = json.load(fh)
        if not isinstance(payload, dict):
            raise ValueError("loudness gain map must be a JSON object")
        if "gains" in payload:
            gains = payload.get("gains")
            if not isinstance(gains, dict):
                raise ValueError("loudness gain map 'gains' must be a JSON object")
            metadata = {k: v for k, v in payload.items() if k != "gains"}
            return cls(gains, metadata)
        return cls(payload)

    @classmethod
    def from_station_config(cls, station_config: Mapping, logger=None) -> "LoudnessGainMap":
        path = station_config.get("loudness_gain_map") if station_config else None
        if not path:
            return cls()
        try:
            result = cls.from_file(path)
            if logger:
                logger.info("Loaded %d fixed loudness gains from %s", len(result.gains), path)
            return result
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            if logger:
                logger.warning("Could not load loudness gain map %s: %s", path, exc)
            return cls()

    def gain_for(self, media_path: str | Path) -> float:
        return self.gains.get(canonical_media_path(media_path), 0.0)
