import os
import socket
import tempfile
import unittest

from fs42.osd.mpv_display import MPV_SOCKET, mpv_commands, socket_identity
from fs42.runtime_paths import MPV_IPC_SOCKET
from fs42.osd.status_display import ChannelStatusTracker, StatusDisplayConfig, compact_network_name


class TestOsdStatus(unittest.TestCase):
    def setUp(self):
        self.config = StatusDisplayConfig(format_text="CH {channel_number} - {network_compact}")
        self.tracker = ChannelStatusTracker()

    def test_compact_network_name_is_generic(self):
        self.assertEqual(compact_network_name("Cable 13"), "CABLE13")
        self.assertEqual(compact_network_name("  weird-TV / 2 "), "WEIRDTV2")

    def test_channel_identity_change_emits_text(self):
        text = self.tracker.changed_text(self.config, {"status": "playing", "channel_number": 13, "network_name": "Cable 13"})
        self.assertEqual(text, "CH 13 - CABLE13")

    def test_unrelated_playback_state_does_not_retrigger(self):
        base = {"channel_number": 13, "network_name": "Cable 13"}
        self.assertEqual(self.tracker.changed_text(self.config, {**base, "status": "playing", "title": "A"}), "CH 13 - CABLE13")
        self.assertIsNone(self.tracker.changed_text(self.config, {**base, "status": "stuck", "title": "B"}))
        self.assertIsNone(self.tracker.changed_text(self.config, {**base, "status": "playing", "title": "C"}))

    def test_channel_or_network_change_retriggers(self):
        self.tracker.changed_text(self.config, {"status": "playing", "channel_number": 13, "network_name": "Cable 13"})
        self.assertEqual(self.tracker.changed_text(self.config, {"status": "playing", "channel_number": 14, "network_name": "Movie Time"}), "CH 14 - MOVIETIME")

    def test_stopped_or_invalid_status_does_not_emit(self):
        self.assertIsNone(self.tracker.changed_text(self.config, {"status": "stopped", "channel_number": -1, "network_name": ""}))


    def test_mpv_ipc_uses_shared_runtime_path(self):
        self.assertEqual(MPV_IPC_SOCKET, "runtime/mpv.socket")
        self.assertEqual(MPV_SOCKET, MPV_IPC_SOCKET)


    def test_mpv_socket_identity_changes_when_stale_path_is_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mpv.socket")
            first = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            first.bind(path)
            first_identity = socket_identity(path)
            self.assertIsNotNone(first_identity)
            first.close()

            # Unix socket paths can survive process/socket teardown. A new mpv
            # session unlinks and binds a new socket at the same pathname.
            os.unlink(path)
            second = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                second.bind(path)
                second_identity = socket_identity(path)
                self.assertIsNotNone(second_identity)
                self.assertNotEqual(first_identity, second_identity)
            finally:
                second.close()

    def test_mpv_commands_use_short_configured_duration(self):
        config = StatusDisplayConfig(display_time=1.75, font_size=12, expansion_factor=4)
        commands = mpv_commands(config, "13 - Cable 13")
        self.assertIn({"command": ["set_property", "osd-font-size", 48]}, commands)
        self.assertEqual(commands[-1], {"command": ["show-text", "13 - Cable 13", 1750]})


if __name__ == "__main__":
    unittest.main()
