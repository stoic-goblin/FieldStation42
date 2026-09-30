import tempfile
import unittest
from pathlib import Path

from PIL import Image

from fs42.osd.content_classifier import ContentType
from fs42.osd.mpv_logo import (
    LogoOverlayController,
    load_logo_frames,
    logo_geometry,
    resolve_logo_path,
    overlay_add_command,
)


class MpvOsdLogoTests(unittest.TestCase):
    def test_resolve_logo_uses_existing_station_content_dir_semantics(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            logo = root / "catalog" / "CH31 NIGHT SIGNAL" / "logo" / "bug.gif"
            logo.parent.mkdir(parents=True)
            logo.write_bytes(b"gif")
            station = {
                "show_logo": True,
                "content_dir": "catalog/CH31 NIGHT SIGNAL",
                "logo_dir": "logo",
                "default_logo": "bug.gif",
            }
            self.assertEqual(resolve_logo_path(station, root), logo)
            station["show_logo"] = False
            self.assertIsNone(resolve_logo_path(station, root))

    def test_geometry_matches_historical_normalized_station_fields(self):
        station = {
            "logo_width": 0.09,
            "logo_height": 0.16,
            "logo_x_margin": 0.04,
            "logo_y_margin": 0.04,
            "logo_halign": "RIGHT",
            "logo_valign": "TOP",
        }
        g = logo_geometry(station, 1920, 1080)
        self.assertEqual((g.width, g.height), (173, 173))
        self.assertEqual((g.x, g.y), (1709, 22))
        self.assertEqual(g.stride, 692)

    def test_overlay_add_command_uses_bgra_file_geometry(self):
        g = logo_geometry({"logo_width": 0.09, "logo_height": 0.16}, 1920, 1080)
        command = overlay_add_command(Path("/run/fs42-osd/logo.bgra"), g, overlay_id=31)
        self.assertEqual(
            command,
            {
                "command": [
                    "overlay-add", 31, g.x, g.y, "/run/fs42-osd/logo.bgra",
                    0, "bgra", g.width, g.height, g.stride,
                ]
            },
        )

    def test_animated_gif_decodes_to_bgra_with_alpha_scaling(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bug.gif"
            a = Image.new("RGBA", (2, 2), (255, 255, 255, 255))
            b = Image.new("RGBA", (2, 2), (255, 255, 255, 0))
            a.save(path, save_all=True, append_images=[b], duration=[100, 200], loop=0, disposal=2)
            g = logo_geometry({"logo_width": 0.5, "logo_height": 0.5}, 4, 4)
            frames = load_logo_frames(path, g, 0.5)
            self.assertEqual(len(frames), 2)
            self.assertAlmostEqual(frames[0].duration, 0.1)
            self.assertAlmostEqual(frames[1].duration, 0.2)
            self.assertEqual(len(frames[0].bgra), g.width * g.height * 4)
            self.assertLessEqual(max(frames[0].bgra[3::4]), 128)
            pixels = [frames[0].bgra[i:i+4] for i in range(0, len(frames[0].bgra), 4)]
            self.assertTrue(all(b <= a and g <= a and r <= a for b, g, r, a in pixels))

    def test_controller_shows_only_feature_and_restarts_after_break(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            logo = root / "catalog" / "CH31 NIGHT SIGNAL" / "logo" / "bug.gif"
            logo.parent.mkdir(parents=True)
            logo.write_bytes(b"gif")
            station = {
                "show_logo": True,
                "content_dir": "catalog/CH31 NIGHT SIGNAL",
                "logo_dir": "logo",
                "default_logo": "bug.gif",
                "logo_permanent": False,
                "logo_display_time": 5.0,
            }
            controller = LogoOverlayController(root, lambda name: station if name == "CH31 NIGHT SIGNAL" else None)
            feature = {"network_name": "CH31 NIGHT SIGNAL", "title": "Goosebumps", "content_type": ContentType.FEATURE}
            bump = {"network_name": "CH31 NIGHT SIGNAL", "title": "NS-Bump-4", "content_type": ContentType.BUMP}
            self.assertEqual(controller.update(feature, 10.0), (True, True))
            self.assertEqual(controller.update(feature, 14.9), (True, False))
            self.assertEqual(controller.update(feature, 15.1), (False, False))
            self.assertEqual(controller.update(bump, 16.0), (False, False))
            self.assertEqual(controller.update(feature, 17.0), (True, True))


if __name__ == "__main__":
    unittest.main()
