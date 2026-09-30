import unittest

from fs42.media_processor import MediaProcessor


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
        segments = MediaProcessor.segments_from_black_midpoints(
            [100.0, 150.0, 300.0], 400.0, min_segment_duration=60.0
        )
        self.assertEqual(
            [(segment["chapter_start"], segment["chapter_end"]) for segment in segments],
            [(0.0, 100.0), (100.0, 300.0), (300.0, 400.0)],
        )
        self.assert_contiguous_coverage(segments, 400.0)

    def test_short_final_segment_merges_backward(self):
        segments = MediaProcessor.segments_from_black_midpoints(
            [100.0, 350.0], 400.0, min_segment_duration=60.0
        )
        self.assertEqual(
            [(segment["chapter_start"], segment["chapter_end"]) for segment in segments],
            [(0.0, 100.0), (100.0, 400.0)],
        )
        self.assert_contiguous_coverage(segments, 400.0)

    def test_clustered_black_frames_collapse_until_all_segments_are_long_enough(self):
        segments = MediaProcessor.segments_from_black_midpoints(
            [100.0, 145.0, 180.0, 300.0], 420.0, min_segment_duration=60.0
        )
        self.assert_contiguous_coverage(segments, 420.0)
        self.assertTrue(all(segment["segment_duration"] >= 60.0 for segment in segments))

    def test_no_candidate_breaks_returns_no_break_segments(self):
        self.assertEqual(
            MediaProcessor.segments_from_black_midpoints([], 400.0, min_segment_duration=60.0),
            [],
        )


if __name__ == "__main__":
    unittest.main()
