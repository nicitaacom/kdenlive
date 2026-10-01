#!/usr/bin/env python3
"""Tests for paired candidate/baseline frame audits."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from audit_native_transition_pair import audit, continuous_black_edge_columns


class NativeTransitionPairAuditTest(unittest.TestCase):
    def test_detects_continuous_black_columns_touching_frame_edges(self) -> None:
        image = Image.new("RGB", (32, 16), (255, 255, 255))
        for x in range(4):
            for y in range(16):
                image.putpixel((x, y), (0, 0, 0))
        self.assertEqual(continuous_black_edge_columns(image), {"left": 4, "right": 0})

    def test_maps_both_event_ranges_and_detects_repeated_frames(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            candidate_stem = directory / "candidate"
            baseline_stem = directory / "baseline"
            candidate_values = [10, 20, 50, 80, 80, 90]
            baseline_values = [10, 20, 20, 20, 50, 90]
            for index, (actual, clean) in enumerate(zip(candidate_values, baseline_values)):
                Image.new("RGB", (32, 16), (actual, actual, actual)).save(f"{candidate_stem}-{index:03}.png")
                Image.new("RGB", (32, 16), (clean, clean, clean)).save(f"{baseline_stem}-{index:03}.png")

            result = audit(candidate_stem, baseline_stem, 1, 2,
                           directory / "measurements.json", directory / "contact.jpg")

            self.assertEqual(result["event_frame_mapping"], {"outgoing": [1, 2], "incoming": [3, 4]})
            self.assertTrue(result["events"]["outgoing"]["all_adjacent_pairs_differ"])
            self.assertEqual(
                result["events"]["outgoing"]["adjacent_changed_pixel_fraction_over_20_rgb"],
                {"min": 1.0, "median": 1.0, "max": 1.0},
            )
            self.assertEqual(result["events"]["incoming"]["identical_adjacent_pairs"], 1)
            self.assertEqual(
                result["events"]["incoming"]["adjacent_changed_pixel_fraction_over_20_rgb"],
                {"min": 0.0, "median": 0.0, "max": 0.0},
            )
            self.assertTrue(result["context_checks"]["pre_context_frames_identical_to_baseline"])
            self.assertTrue(result["context_checks"]["post_context_frames_identical_to_baseline"])
            self.assertTrue((directory / "measurements.json").is_file())
            self.assertTrue((directory / "contact.jpg").is_file())

    def test_records_project_time_and_cut_for_fractional_frame_rate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            candidate_stem = directory / "candidate"
            baseline_stem = directory / "baseline"
            for index in range(6):
                image = Image.new("RGB", (32, 16), (index * 20, index * 20, index * 20))
                image.save(f"{candidate_stem}-{index:03}.png")
                image.save(f"{baseline_stem}-{index:03}.png")

            result = audit(candidate_stem, baseline_stem, 1, 2,
                           directory / "measurements.json", directory / "contact.jpg",
                           fps_num=60000, fps_den=1001)

            self.assertEqual(result["fps"], {"numerator": 60000, "denominator": 1001})
            self.assertEqual(result["cut_location"]["between_timeline_frames"], [2, 3])
            self.assertAlmostEqual(result["cut_location"]["times_seconds"][1], 3 * 1001 / 60000)
            self.assertAlmostEqual(result["frames"][3]["time_seconds"], 3 * 1001 / 60000)

    def test_maps_different_outgoing_and_incoming_event_lengths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            candidate_stem = directory / "candidate"
            baseline_stem = directory / "baseline"
            values = [10, 20, 30, 40, 50, 60, 70]
            for index, value in enumerate(values):
                Image.new("RGB", (32, 16), (value, value, value)).save(f"{candidate_stem}-{index:03}.png")
                Image.new("RGB", (32, 16), (value, value, value)).save(f"{baseline_stem}-{index:03}.png")

            result = audit(candidate_stem, baseline_stem, 1, 2,
                           directory / "measurements.json", directory / "contact.jpg",
                           incoming_event_frames=3)

            self.assertEqual(result["rendered_frames"], 7)
            self.assertEqual(result["event_frame_mapping"], {"outgoing": [1, 2], "incoming": [3, 5]})
            self.assertEqual(result["events"]["outgoing"]["rendered_frames"], 2)
            self.assertEqual(result["events"]["incoming"]["rendered_frames"], 3)
            self.assertEqual([frame["region"] for frame in result["frames"]], [
                "pre-context", "outgoing", "outgoing", "incoming", "incoming", "incoming", "post-context",
            ])
            self.assertTrue(result["context_checks"]["post_context_frames_identical_to_baseline"])

    def test_rejects_one_based_frame_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for stem in (directory / "candidate", directory / "baseline"):
                for index in range(1, 7):
                    Image.new("RGB", (32, 16), (index, index, index)).save(f"{stem}-{index:03}.png")
            with self.assertRaisesRegex(ValueError, "must start at 000"):
                audit(directory / "candidate", directory / "baseline", 1, 2,
                      directory / "measurements.json", directory / "contact.jpg")

    def test_rejects_missing_or_unexpected_frame_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for stem in (directory / "candidate", directory / "baseline"):
                Image.new("RGB", (32, 16), (0, 0, 0)).save(f"{stem}-000.png")
            with self.assertRaisesRegex(ValueError, "expected 6 frames"):
                audit(directory / "candidate", directory / "baseline", 1, 2,
                      directory / "measurements.json", directory / "contact.jpg")


if __name__ == "__main__":
    unittest.main()
