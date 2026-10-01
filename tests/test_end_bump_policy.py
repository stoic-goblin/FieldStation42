import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fs42.block_plan import BlockPlanEntry
from fs42.catalog import ShowCatalog
from fs42.liquid_blocks import LiquidBlock
from fs42.liquid_schedule import LiquidSchedule


class FakeFeature:
    path = "catalog/Test/show.mp4"
    realpath = "/media/show.mp4"
    title = "Test Show"
    duration = 2640.0  # 44 minutes in a one-hour block
    content_type = "feature"
    media_type = "video"


class FakeReel:
    duration = 60.0

    def make_plan(self):
        return [BlockPlanEntry("ad.mp4", 0, self.duration, content_type="commercial")]


class FitAwareEndBumpTests(unittest.TestCase):
    def test_catalog_end_bump_filters_directory_candidates_by_available_duration(self):
        catalog = ShowCatalog.__new__(ShowCatalog)
        catalog.clip_index = {
            "end_bumps": [
                SimpleNamespace(path="catalog/Test/Interstitials/short.mp4", duration=360.0),
                SimpleNamespace(path="catalog/Test/Interstitials/long.mp4", duration=720.0),
            ]
        }

        with patch("fs42.catalog.random.choice", side_effect=lambda choices: choices[-1]):
            bump = catalog.get_end_bump("Interstitials", max_duration=500.0)

        self.assertEqual(bump, {"path": "catalog/Test/Interstitials/short.mp4", "duration": 360.0})
        self.assertIsNone(catalog.get_end_bump("Interstitials", max_duration=300.0))

    @patch("fs42.liquid_blocks.FluidBuilder")
    @patch("fs42.liquid_blocks.random.random", return_value=0.1)
    def test_end_bump_reserves_boundary_airtime_before_reel_fill(self, _random, fluid_cls):
        fluid_cls.return_value.get_chapters.return_value = []
        fluid_cls.return_value.get_breaks.return_value = []
        catalog = MagicMock()
        catalog.config = {"break_duration": 120}
        catalog.get_end_bump.return_value = {
            "path": "catalog/Test/Interstitials/cartoon.mp4",
            "duration": 420.0,
        }
        catalog.make_reel_fill.return_value = [FakeReel()]

        start = datetime.datetime(2026, 10, 1, 20, 0)
        block = LiquidBlock(
            FakeFeature(),
            start,
            start + datetime.timedelta(hours=1),
            break_info={
                "end_bump_path": "Interstitials",
                "end_bump_probability": 0.4,
                "end_bump_min_reel_seconds": 180,
            },
        )
        block.make_plan(catalog)

        # 60m block - 44m feature = 960s slack.  Reserve 180s for reels, so
        # only bumps <=780s are eligible. A 420s bump leaves 540s for reels.
        catalog.get_end_bump.assert_called_once_with("Interstitials", max_duration=780.0)
        self.assertEqual(catalog.make_reel_fill.call_args.args[1], 540.0)
        self.assertEqual([entry.path for entry in block.plan], ["catalog/Test/show.mp4", "ad.mp4", "catalog/Test/Interstitials/cartoon.mp4"])
        self.assertEqual(block.plan[-1].content_type, "bump")

    @patch("fs42.liquid_blocks.FluidBuilder")
    @patch("fs42.liquid_blocks.random.random", return_value=0.9)
    def test_probability_skip_leaves_full_slack_for_normal_reel_fill(self, _random, fluid_cls):
        fluid_cls.return_value.get_chapters.return_value = []
        fluid_cls.return_value.get_breaks.return_value = []
        catalog = MagicMock()
        catalog.config = {"break_duration": 120}
        catalog.make_reel_fill.return_value = []

        start = datetime.datetime(2026, 10, 1, 20, 0)
        block = LiquidBlock(
            FakeFeature(),
            start,
            start + datetime.timedelta(hours=1),
            break_info={
                "end_bump_path": "Interstitials",
                "end_bump_probability": 0.4,
                "end_bump_min_reel_seconds": 180,
            },
        )
        block.make_plan(catalog)

        catalog.get_end_bump.assert_not_called()
        self.assertEqual(catalog.make_reel_fill.call_args.args[1], 960.0)
        self.assertIsNone(block.end_bump)

    def test_station_level_policy_is_inherited_and_tag_override_can_tune_it(self):
        sched = LiquidSchedule.__new__(LiquidSchedule)
        sched.conf = {
            "content_dir": "catalog/Test",
            "break_strategy": "standard",
            "schedule_increment": 30,
            "bump_dir": "bump",
            "commercial_dir": "Ads",
            "end_bump": "Interstitials",
            "end_bump_probability": 0.4,
            "end_bump_min_reel_seconds": 180,
            "tag_overrides": {
                "Movies": {
                    "end_bump_probability": 0.75,
                    "end_bump_min_reel_seconds": 300,
                }
            },
        }
        sched.catalog = MagicMock()

        with patch("fs42.liquid_schedule.PathQuery.match_any_from_base", return_value=None):
            break_info, strategy, increment = sched._break_info(
                {"tags": "Movies"}, "Movies", "catalog/Test/Movies/movie.mp4"
            )

        self.assertIsNone(break_info["end_bump"])
        self.assertEqual(break_info["end_bump_path"], "Interstitials")
        self.assertEqual(break_info["end_bump_probability"], 0.75)
        self.assertEqual(break_info["end_bump_min_reel_seconds"], 300)
        self.assertEqual(break_info["bump_dir"], "bump")
        self.assertEqual(break_info["commercial_dir"], "Ads")
        self.assertEqual(strategy, "standard")
        self.assertEqual(increment, 30)


if __name__ == "__main__":
    unittest.main()
