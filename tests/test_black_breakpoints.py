import unittest

from fs42.liquid_blocks import LiquidBlock
from fs42.media_processor import MediaProcessor
from fs42.reel_cutter import ReelCutter
from fs42.block_plan import BlockPlanEntry


class BlackBreakpointSegmentTests(unittest.TestCase):
    def assert_contiguous_coverage(self, segments, duration):
        self.assertTrue(segments)
        self.assertEqual(segments[0]["chapter_start"], 0.0)
        self.assertEqual(segments[-1]["chapter_end"], duration)
        for previous, current in zip(segments, segments[1:]):
            self.assertEqual(previous["chapter_end"], current["chapter_start"])
        self.assertAlmostEqual(
            sum(segment["segment_duration"] for segment in segments), duration
        )

    def test_short_middle_segment_merges_without_dropping_media(self):
        segments = MediaProcessor.segments_from_break_boundaries(
            [100.0, 150.0, 300.0], 400.0, min_segment_duration=60.0
        )
        self.assertEqual(
            [(segment["chapter_start"], segment["chapter_end"]) for segment in segments],
            [(0.0, 100.0), (100.0, 300.0), (300.0, 400.0)],
        )
        self.assert_contiguous_coverage(segments, 400.0)

    def test_short_final_segment_merges_backward(self):
        segments = MediaProcessor.segments_from_break_boundaries(
            [100.0, 350.0], 400.0, min_segment_duration=60.0
        )
        self.assertEqual(
            [(segment["chapter_start"], segment["chapter_end"]) for segment in segments],
            [(0.0, 100.0), (100.0, 400.0)],
        )
        self.assert_contiguous_coverage(segments, 400.0)

    def test_clustered_black_frames_collapse_until_all_segments_are_long_enough(self):
        segments = MediaProcessor.segments_from_break_boundaries(
            [100.0, 145.0, 180.0, 300.0], 420.0, min_segment_duration=60.0
        )
        self.assert_contiguous_coverage(segments, 420.0)
        self.assertTrue(all(segment["segment_duration"] >= 60.0 for segment in segments))

    def test_no_candidate_breaks_returns_no_break_segments(self):
        self.assertEqual(
            MediaProcessor.segments_from_break_boundaries([], 400.0, min_segment_duration=60.0),
            [],
        )

    def test_realistic_beetlejuice_chapters_drop_intro_and_credit_fragments(self):
        chapters = [
            {"chapter_start": 0.0, "chapter_end": 62.0},
            {"chapter_start": 62.0, "chapter_end": 637.0},
            {"chapter_start": 637.0, "chapter_end": 1332.5},
            {"chapter_start": 1332.5, "chapter_end": 1363.5},
            {"chapter_start": 1363.5, "chapter_end": 1365.760},
        ]
        segments = LiquidBlock.clip_break_points(chapters, 4, 1365.760)
        self.assertEqual(
            [(round(x["chapter_start"], 3), round(x["chapter_end"], 3)) for x in segments],
            [(0.0, 637.0), (637.0, 1365.76)],
        )
        self.assert_contiguous_coverage(segments, 1365.760)

    def test_timeline_selection_avoids_near_end_twilight_zone_break(self):
        boundaries = [598.2975, 1039.005, 1449.2, 1738.92, 2165.48, 2579.895, 3039.57]
        segments = MediaProcessor.segments_from_break_boundaries(boundaries, 3115.4123, 60.0)
        selected = LiquidBlock.clip_break_points(segments, 5, 3115.4123)
        self.assertEqual(
            [round(x["chapter_end"], 3) for x in selected[:-1]],
            [598.298, 1449.2, 1738.92, 2579.895],
        )
        self.assert_contiguous_coverage(selected, 3115.4123)
        self.assertGreater(selected[-1]["segment_duration"], 180.0)


class FakeClip:
    path = "show.mp4"
    duration = 1000.0
    content_type = "feature"
    media_type = "video"


class FakeReel:
    def make_plan(self):
        return [BlockPlanEntry("ad.mp4", 0, 30.0, content_type="commercial")]


class ReelCutterBreakpointTests(unittest.TestCase):
    def test_one_reel_uses_one_detected_midroll_break(self):
        plan = ReelCutter.cut_reels_into_base(
            FakeClip(), [FakeReel()], 0, 1000.0, "standard", None, None,
            break_points=[
                {"chapter_start": 0.0, "chapter_end": 400.0},
                {"chapter_start": 400.0, "chapter_end": 1000.0},
            ],
        )
        self.assertEqual([entry.path for entry in plan], ["show.mp4", "ad.mp4", "show.mp4"])
        self.assertEqual((plan[0].skip, plan[0].duration), (0.0, 400.0))
        self.assertEqual((plan[2].skip, plan[2].duration), (400.0, 600.0))


if __name__ == "__main__":
    unittest.main()
