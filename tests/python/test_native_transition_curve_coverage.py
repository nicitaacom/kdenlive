#!/usr/bin/env python3
"""Tests for the source-only transition key-time coverage audit."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from audit_native_transition_curve_coverage import audit_record  # noqa: E402


class NativeTransitionCurveCoverageTest(unittest.TestCase):
    def record(self, animations: list[tuple[str, list[tuple[float, object]]]]) -> dict:
        parameters = []
        for name, keys in animations:
            parameters.append({
                "name": name,
                "animation": {"points": [
                    {"normalized_event_position": time, "value": value}
                    for time, value in keys
                ]},
            })
        return {
            "exact_name": "fixture",
            "components": [{"vendor_id": "native:test", "parameters": parameters}],
        }

    def test_early_track_is_not_mistaken_for_whole_preset_ending_early(self) -> None:
        result = audit_record(self.record([
            ("z", [(0.0, 1.0), (0.25, 0.9)]),
            ("shift", [(0.0, 5.0), (0.5, 0.0), (1.0, -5.0)]),
        ]))
        self.assertEqual(result["curves_ending_before_event_endpoint"], 1)
        self.assertEqual(result["curves_ending_at_least_10_percent_early"], 1)
        self.assertTrue(result["has_animated_key_at_event_endpoint"])
        self.assertFalse(result["all_animated_curves_end_at_event_endpoint"])
        self.assertAlmostEqual(result["tracks"][0]["trailing_hold_fraction"], 0.75)

    def test_all_tracks_without_endpoint_key_are_reported(self) -> None:
        result = audit_record(self.record([
            ("x", [(0.0, -1.0), (0.6, 0.0)]),
            ("y", [(0.1, 2.0), (0.8, 0.0)]),
        ]))
        self.assertFalse(result["has_animated_key_at_event_endpoint"])
        self.assertFalse(result["all_animated_curves_end_at_event_endpoint"])
        self.assertAlmostEqual(result["latest_animated_key_position"], 0.8)

    def test_equal_key_values_are_not_called_rendered_holds(self) -> None:
        result = audit_record(self.record([
            ("amount", [(0.0, 0.0), (0.4, 0.0), (1.0, 1.0)]),
        ]))
        self.assertEqual(result["equal_key_value_segment_count"], 1)
        self.assertAlmostEqual(result["tracks"][0]["equal_key_value_segments"][0]["normalized_span"], 0.4)
        self.assertIn("not rendered-motion evidence", result["limitation"])

    def test_single_static_points_are_not_counted_as_animated_curves(self) -> None:
        result = audit_record(self.record([
            ("static", [(0.0, 0.0)]),
        ]))
        self.assertEqual(result["animated_parameter_curve_count"], 0)
        self.assertIsNone(result["latest_animated_key_position"])
        self.assertFalse(result["has_animated_key_at_event_endpoint"])


if __name__ == "__main__":
    unittest.main()
