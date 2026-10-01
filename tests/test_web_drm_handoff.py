import logging
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from fs42.station_player import PlayerOutcome, PlayerState, StationPlayer


class FakePopen:
    def __init__(self, *, alive=True, timeout_once=False):
        self.alive = alive
        self.timeout_once = timeout_once
        self.wait_calls = []
        self.killed = False

    def poll(self):
        return None if self.alive else 0

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        if self.timeout_once:
            self.timeout_once = False
            raise subprocess.TimeoutExpired("mpv", timeout)
        self.alive = False
        return 0

    def kill(self):
        self.killed = True
        self.alive = False


class FakeMPVWrapper:
    def __init__(self, process=None):
        self.mpv_process = MagicMock()
        self.mpv_process.process = process or FakePopen()
        self.terminated = False
        self.stopped = False

    def terminate(self):
        self.terminated = True

    def stop(self):
        self.stopped = True


class FakeWebProcess:
    def __init__(self, events):
        self.events = events
        self.started = False
        self.alive = False
        self.terminated = False

    def start(self):
        self.events.append("web-start")
        self.started = True
        self.alive = True

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        self.events.append("web-join")
        self.alive = False

    def terminate(self):
        self.events.append("web-terminate")
        self.terminated = True
        self.alive = False


class FakeQueue:
    def __init__(self, events):
        self.events = events

    def put(self, value):
        self.events.append(("queue", value))


class WebDrmHandoffTests(unittest.TestCase):
    def make_player(self):
        player = StationPlayer.__new__(StationPlayer)
        player._l = logging.getLogger("web-drm-test")
        player._start_mpv_enabled = True
        player._shutting_down = False
        player.station_config = {"network_name": "Guide", "channel_number": 1}
        player.current_playing_file_path = "old.mp4"
        player.web_process = None
        player.web_queue = None
        player.now_playing_process = None
        player.mpv = FakeMPVWrapper()
        return player

    def test_release_mpv_waits_for_process_exit_before_clearing_wrapper(self):
        player = self.make_player()
        process = player.mpv.mpv_process.process
        wrapper = player.mpv
        player._release_mpv(timeout=0.5)
        self.assertTrue(wrapper.terminated)
        self.assertEqual(process.wait_calls, [0.5])
        self.assertIsNone(player.mpv)

    def test_release_mpv_kills_process_that_does_not_exit_in_time(self):
        player = self.make_player()
        process = FakePopen(timeout_once=True)
        player.mpv = FakeMPVWrapper(process)
        player._release_mpv(timeout=0.01)
        self.assertTrue(process.killed)
        self.assertEqual(process.wait_calls, [0.01, 1.0])
        self.assertIsNone(player.mpv)

    @patch("fs42.station_player.MPV")
    def test_start_mpv_recreates_the_standard_station_renderer(self, mpv_cls):
        player = self.make_player()
        player.mpv = None
        replacement = MagicMock()
        mpv_cls.return_value = replacement
        player._start_mpv()
        self.assertIs(player.mpv, replacement)
        mpv_cls.assert_called_once_with(
            start_mpv=True,
            ipc_socket="runtime/mpv.socket",
            input_default_bindings=False,
            fs=True,
            idle=True,
            force_window=True,
            script_opts="osc-idlescreen=no",
            hr_seek="yes",
        )

    def test_blocking_web_channel_releases_mpv_before_web_and_restores_after(self):
        player = self.make_player()
        events = []
        fake_web = FakeWebProcess(events)
        fake_queue = FakeQueue(events)
        response = PlayerOutcome(PlayerState.CHANNEL_CHANGE, '{"command":"up","channel":-1}')

        def release():
            events.append("mpv-release")
            player.mpv = None

        def restart():
            events.append("mpv-start")
            player.mpv = FakeMPVWrapper()

        player._release_mpv = release
        player._start_mpv = restart
        player._close_now_playing = lambda: events.append("overlay-close")
        player.input_check_fn = lambda: response

        with patch("fs42.station_player.multiprocessing.Queue", return_value=fake_queue), \
             patch("fs42.station_player.multiprocessing.Process", return_value=fake_web), \
             patch("fs42.station_player.update_status_socket"), \
             patch("fs42.station_player.StationManager") as manager, \
             patch("fs42.station_player.time.sleep"):
            manager.return_value.server_conf = {"date_time_format": "%Y-%m-%dT%H:%M:%S"}
            result = player.show_web({"web_url": "http://127.0.0.1:4242/"}, blocking=True)

        self.assertIs(result, response)
        self.assertLess(events.index("mpv-release"), events.index("web-start"))
        self.assertLess(events.index("web-join"), events.index("mpv-start"))
        self.assertIn(("queue", "hide_window"), events)
        self.assertIsNotNone(player.mpv)

    def test_nonblocking_web_content_keeps_existing_mpv_wrapper(self):
        player = self.make_player()
        wrapper = player.mpv
        events = []
        fake_web = FakeWebProcess(events)
        fake_queue = FakeQueue(events)
        player._release_mpv = MagicMock()
        player._start_mpv = MagicMock()

        with patch("fs42.station_player.multiprocessing.Queue", return_value=fake_queue), \
             patch("fs42.station_player.multiprocessing.Process", return_value=fake_web), \
             patch("fs42.station_player.update_status_socket"), \
             patch("fs42.station_player.StationManager") as manager:
            manager.return_value.server_conf = {"date_time_format": "%Y-%m-%dT%H:%M:%S"}
            result = player.show_web({"web_url": "http://127.0.0.1:4242/"}, blocking=False)

        self.assertEqual(result.status, PlayerState.SUCCESS)
        self.assertIs(player.mpv, wrapper)
        self.assertTrue(wrapper.stopped)
        player._release_mpv.assert_not_called()
        player._start_mpv.assert_not_called()


if __name__ == "__main__":
    unittest.main()
