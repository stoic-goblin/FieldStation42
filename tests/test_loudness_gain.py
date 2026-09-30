import json
import logging
import math
import tempfile
import unittest
from pathlib import Path

from fs42.loudness_gain import LoudnessGainMap, canonical_media_path, volume_filter_db
from fs42.station_player import StationPlayer


class FakeMpv:
    def __init__(self):
        self.commands = []

    def command(self, *args):
        self.commands.append(args)


class FixedLoudnessGainTests(unittest.TestCase):
    def test_map_resolves_catalog_symlink_to_measured_realpath(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            media = root / "media" / "episode.mp4"
            media.parent.mkdir()
            media.write_bytes(b"media")
            catalog = root / "catalog" / "episode.mp4"
            catalog.parent.mkdir()
            catalog.symlink_to(media)
            gain_map = root / "gains.json"
            gain_map.write_text(json.dumps({"version": 1, "gains": {str(media): 3.25}}))
            gains = LoudnessGainMap.from_file(gain_map)
            self.assertEqual(gains.gain_for(catalog), 3.25)
            self.assertEqual(canonical_media_path(catalog), str(media.resolve()))

    def test_invalid_and_nonfinite_values_are_ignored(self):
        gains = LoudnessGainMap({"/a": "bad", "/b": math.inf, "/c": -2.5})
        self.assertEqual(gains.gain_for("/a"), 0.0)
        self.assertEqual(gains.gain_for("/b"), 0.0)
        self.assertEqual(gains.gain_for("/c"), -2.5)

    def test_filter_is_fixed_db_gain_and_zero_is_noop(self):
        self.assertEqual(volume_filter_db(3.256), "lavfi=[volume=3.26dB]")
        self.assertEqual(volume_filter_db(-14.4), "lavfi=[volume=-14.40dB]")
        self.assertIsNone(volume_filter_db(0.0))

    def test_player_replaces_gain_filter_between_items(self):
        player = StationPlayer.__new__(StationPlayer)
        player._l = logging.getLogger("test")
        player.mpv = FakeMpv()
        player._active_loudness_afx = "lavfi=[volume=2.00dB]"
        player._loudness_gain_map = LoudnessGainMap({"/episode.mp4": -4.5})
        player._apply_loudness_gain("/episode.mp4")
        self.assertEqual(
            player.mpv.commands,
            [
                ("af", "remove", "lavfi=[volume=2.00dB]"),
                ("af", "add", "lavfi=[volume=-4.50dB]"),
            ],
        )
        self.assertEqual(player._active_loudness_afx, "lavfi=[volume=-4.50dB]")

    def test_player_removes_previous_filter_for_unmeasured_item(self):
        player = StationPlayer.__new__(StationPlayer)
        player._l = logging.getLogger("test")
        player.mpv = FakeMpv()
        player._active_loudness_afx = "lavfi=[volume=6.00dB]"
        player._loudness_gain_map = LoudnessGainMap()
        player._apply_loudness_gain("/unmeasured.mp4")
        self.assertEqual(player.mpv.commands, [("af", "remove", "lavfi=[volume=6.00dB]")])
        self.assertIsNone(player._active_loudness_afx)


if __name__ == "__main__":
    unittest.main()
