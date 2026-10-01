import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fs42.station_player import StationPlayer


class FakeMPV:
    def __init__(self, target_path, *, stale_path_reads=0):
        self.target_path = target_path
        self.stale_path_reads = stale_path_reads
        self.path_reads = 0
        self.commands = []
        self.play_calls = []
        self.panscan = None
        self.keepaspect = None
        self.vf = ""
        self.af = ""
        self.duration = 600.0

    def command(self, *args):
        self.commands.append(args)

    def play(self, path):
        self.play_calls.append(path)

    @property
    def path(self):
        self.path_reads += 1
        if self.path_reads <= self.stale_path_reads:
            return "previous-file.mkv"
        return self.target_path

    @property
    def time_pos(self):
        # Deliberately non-null even while path still points at the old file.
        return 42.0


class LivePointLoadTests(unittest.TestCase):
    def make_player(self, mpv):
        player = StationPlayer.__new__(StationPlayer)
        player._l = logging.getLogger("live-point-test")
        player.mpv = mpv
        player.station_config = {}
        player.current_playing_file_path = None
        player.now_playing_process = None
        player._active_afx = None
        player._active_loudness_afx = None
        player._apply_vfx = lambda _when: None
        player._apply_loudness_gain = lambda _path: None
        player._close_now_playing = lambda: None
        return player

    def test_prerecorded_live_join_uses_loadfile_start_option_not_post_load_seek(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "movie.mkv")
            Path(path).touch()
            mpv = FakeMPV(path)
            player = self.make_player(mpv)

            with patch("fs42.station_player.update_status_socket"), \
                 patch("fs42.station_player.StationManager") as manager, \
                 patch("fs42.station_player.NFOAgent", create=True), \
                 patch("fs42.station_player.time.sleep"):
                manager.return_value.server_conf = {
                    "video_seek_timeout": 1,
                    "date_time_format": "%Y-%m-%dT%H:%M:%S",
                }
                ok = player.play_file(
                    path,
                    file_duration=600,
                    current_time=123.5,
                    is_stream=False,
                    title="Movie",
                    content_type="feature",
                    media_type="video",
                )

            self.assertTrue(ok)
            self.assertIn(("loadfile", path, "replace", "start=123.5"), mpv.commands)
            self.assertFalse(any(cmd and cmd[0] == "seek" for cmd in mpv.commands))
            self.assertEqual(mpv.play_calls, [])

    def test_readiness_requires_new_path_even_if_old_time_pos_is_non_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "movie.mkv")
            Path(path).touch()
            mpv = FakeMPV(path, stale_path_reads=2)
            player = self.make_player(mpv)

            with patch("fs42.station_player.update_status_socket"), \
                 patch("fs42.station_player.StationManager") as manager, \
                 patch("fs42.station_player.time.sleep"):
                manager.return_value.server_conf = {
                    "video_seek_timeout": 1,
                    "date_time_format": "%Y-%m-%dT%H:%M:%S",
                }
                ok = player.play_file(
                    path,
                    file_duration=600,
                    current_time=45,
                    is_stream=False,
                    title="Movie",
                    content_type="feature",
                    media_type="video",
                )

            self.assertTrue(ok)
            self.assertGreaterEqual(mpv.path_reads, 3)

    def test_zero_offset_keeps_normal_play_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "movie.mkv")
            Path(path).touch()
            mpv = FakeMPV(path)
            player = self.make_player(mpv)

            with patch("fs42.station_player.update_status_socket"), \
                 patch("fs42.station_player.StationManager") as manager, \
                 patch("fs42.station_player.time.sleep"):
                manager.return_value.server_conf = {
                    "video_seek_timeout": 1,
                    "date_time_format": "%Y-%m-%dT%H:%M:%S",
                }
                ok = player.play_file(
                    path,
                    file_duration=600,
                    current_time=0,
                    is_stream=False,
                    title="Movie",
                    content_type="feature",
                    media_type="video",
                )

            self.assertTrue(ok)
            self.assertEqual(mpv.play_calls, [path])
            self.assertFalse(any(cmd and cmd[0] == "loadfile" for cmd in mpv.commands))


if __name__ == "__main__":
    unittest.main()
