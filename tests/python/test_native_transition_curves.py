#!/usr/bin/env python3
"""Tests for the explicitly approximate native easing representation."""

from __future__ import annotations

import sys
import unittest
import json
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from native_transition_curves import (monotone_bezier_points,
                                      cubic_ease_out_endpoint_points,
                                      apply_screen_space_arc_length_candidate,
                                      apply_effect_strength_ease_candidate,
                                      apply_endpoint_progress_candidate,
                                      apply_endpoint_progress_bezier_candidate,
                                      endpoint_progress_bezier_points,
                                      apply_smoothstep_endpoint_bezier_candidate,
                                      apply_scroll_right_27_incoming_cubic_ease_out_v2,
                                      apply_zoom_out_spin_clockwise_incoming_eventwide_candidate,
                                      apply_zoom_out_spin_counterclockwise_incoming_shutter_taper_candidate,
                                      apply_zoom_out_spin_counterclockwise_incoming_settle_candidate,
                                      apply_endpoint_preserving_smoothstep_candidate,
                                      apply_slide_right_phase_shutter_candidate,
                                      smoothstep_endpoint_bezier_points,
                                      apply_reverse_time_monotone_candidate,
                                      reverse_event_time_monotone_candidate,
                                      apply_shared_arc_length_time_candidate,
                                      apply_vegas_enum_order_candidate,
                                      apply_vegas_zero_hold_destination_candidate,
                                      effect_strength_time_map,
                                      screen_space_arc_length_time_map,
                                      shared_arc_length_time_map,
                                      vegas_enum_order_candidate,
                                      vegas_zero_hold_candidate,
                                      vegas_zero_hold_incoming_key_candidate)  # noqa: E402


class NativeTransitionCurveTests(unittest.TestCase):
    def test_cubic_ease_out_starts_fast_and_settles_at_the_end(self):
        points = cubic_ease_out_endpoint_points(-1.0, 0.0)
        self.assertEqual((points[0][0], points[0][1]), (0.0, -1.0))
        self.assertEqual((points[-1][0], points[-1][1]), (1.0, 0.0))
        self.assertAlmostEqual(points[0][4], 1.0 / 3.0)
        self.assertAlmostEqual(points[-1][2], 2.0 / 3.0)

        def evaluate(t):
            u = 1.0 - t
            return (u ** 3 * points[0][1]
                    + 3 * u ** 2 * t * points[0][5]
                    + 3 * u * t ** 2 * points[-1][3]
                    + t ** 3 * points[-1][1])

        values = [evaluate(t) for t in (0.0, 0.25, 0.5, 0.75, 1.0)]
        self.assertEqual(values, sorted(values))
        self.assertAlmostEqual(values[1], -0.421875)
        self.assertAlmostEqual(values[2], -0.125)
        self.assertAlmostEqual(values[3], -0.015625)

    def test_cubic_ease_out_rejects_non_finite_endpoints(self):
        with self.assertRaises(ValueError):
            cubic_ease_out_endpoint_points(float("nan"), 1.0)

    @staticmethod
    def zoom_out_spin_10_6_incoming_fixture():
        source_time = 0.7540976357699892
        parameters = {
            "Z Dist": [(source_time, 0.5), (1.0, 1.0)],
            "Rotate": [(0.0, 45.0), (source_time, 45.0), (1.0, 0.0)],
            "Shutter Duration": [(source_time, 1.5), (1.0, 1.0)],
        }
        record = {
            "exact_name": "10.6 Zoom Out Spin ClockWise (2) 15k",
            "source_identifier": "{8251884A-4379-40BE-BBB4-A30EFC673140}",
            "event_variant": "incoming",
            "components": [{
                "vendor_id": "{Svfx:com.genarts.sapphire.BlurSharpen.S_BlurMoCurves}",
                "parameters": [{"name": name, "animation": {"points": [
                    {"normalized_event_position": time, "value": value}
                    for time, value in points
                ]}} for name, points in parameters.items()],
            }],
        }
        curves = {
            "z_distance": [[t, v, t, v, t, v, 0] for t, v in parameters["Z Dist"]],
            "rotation": [[t, v, t, v, t, v, 0] for t, v in parameters["Rotate"]],
            "shutter_duration": [[t, v, t, v, t, v, 0] for t, v in parameters["Shutter Duration"]],
        }
        root = ET.fromstring("<mlt><producer><filter>"
                             "<property name='native_preset_id'>{8251884A-4379-40BE-BBB4-A30EFC673140}</property>"
                             "<property name='mlt_service'>kdenlive_motion_curve</property>"
                             "<property name='native_event_role'>incoming</property>"
                             "<property name='native_curves'></property>"
                             "</filter></producer></mlt>")
        root.find(".//property[@name='native_curves']").text = json.dumps(curves)
        return record, ET.ElementTree(root)

    def test_10_6_incoming_candidate_spreads_source_endpoint_values_across_event(self):
        record, tree = self.zoom_out_spin_10_6_incoming_fixture()
        apply_zoom_out_spin_clockwise_incoming_eventwide_candidate(tree, record)
        element = tree.getroot().find(".//filter")
        curves = json.loads(element.find("property[@name='native_curves']").text)
        self.assertEqual({name: [(point[0], point[1]) for point in points]
                          for name, points in curves.items()}, {
            "z_distance": [(0.0, 0.5), (1.0, 1.0)],
            "rotation": [(0.0, 45.0), (1.0, 0.0)],
            "shutter_duration": [(0.0, 1.5), (1.0, 1.0)],
        })
        self.assertAlmostEqual(curves["z_distance"][0][5], 0.5 + 0.5 * 0.35 / 3)
        self.assertAlmostEqual(curves["rotation"][0][5], 45.0 - 45.0 * 0.35 / 3)
        self.assertEqual(element.find("property[@name='native_curve_candidate_id']").text,
                         "10.6-cw-incoming-eventwide-linear-floor-smoothstep-65-v1")
        self.assertIn("candidate timing differs", element.find("property[@name='native_curve_candidate_note']").text)

    @staticmethod
    def zoom_out_spin_10_7_incoming_fixture():
        source_time = 0.7540976357699892
        parameters = {
            "Z Dist": [(source_time, 0.5), (1.0, 1.0)],
            "Rotate": [(0.0, 45.0), (source_time, -45.0), (1.0, 0.0)],
            "Shutter Duration": [(source_time, 1.5), (1.0, 1.0)],
        }
        record = {
            "exact_name": "10.7 Zoom Out Spin CounterClockWise (2) 15k",
            "source_identifier": "{57C53ED1-D794-4D49-9665-47A23F873410}",
            "event_variant": "incoming",
            "components": [{
                "vendor_id": "{Svfx:com.genarts.sapphire.BlurSharpen.S_BlurMoCurves}",
                "parameters": [{"name": name, "animation": {"points": [
                    {"normalized_event_position": time, "value": value}
                    for time, value in points
                ]}} for name, points in parameters.items()],
            }],
        }
        curves = {
            {"Z Dist": "z_distance", "Rotate": "rotation", "Shutter Duration": "shutter_duration"}[name]:
            [[t, v, t, v, t, v, 0] for t, v in points]
            for name, points in parameters.items()
        }
        root = ET.fromstring("<mlt><producer><filter>"
                             "<property name='native_preset_id'>{57C53ED1-D794-4D49-9665-47A23F873410}</property>"
                             "<property name='mlt_service'>kdenlive_motion_curve</property>"
                             "<property name='native_event_role'>incoming</property>"
                             "<property name='native_curves'></property>"
                             "</filter></producer></mlt>")
        root.find(".//property[@name='native_curves']").text = json.dumps(curves)
        return record, ET.ElementTree(root)

    def test_10_7_incoming_shutter_taper_keeps_transform_curves_and_sharpens_endpoint(self):
        record, tree = self.zoom_out_spin_10_7_incoming_fixture()
        element = tree.find(".//filter")
        before = json.loads(element.find("property[@name='native_curves']").text)

        apply_zoom_out_spin_counterclockwise_incoming_shutter_taper_candidate(tree, record)

        after = json.loads(element.find("property[@name='native_curves']").text)
        self.assertEqual(after["z_distance"], before["z_distance"])
        self.assertEqual(after["rotation"], before["rotation"])
        shutter = after["shutter_duration"]
        self.assertEqual([(point[0], point[1]) for point in shutter], [
            (0.7540976357699892, 1.5), (1.0, 0.0),
        ])
        self.assertEqual([point[6] for point in shutter], [1, 0])
        self.assertAlmostEqual(shutter[0][4], 0.7540976357699892 + (1 - 0.7540976357699892) / 3)
        self.assertAlmostEqual(shutter[-1][2], 1 - (1 - 0.7540976357699892) / 3)
        self.assertEqual(element.find("property[@name='native_curve_candidate_id']").text,
                         "10.7-ccw-incoming-endpoint-sharp-shutter-taper-smoothstep-65-v1")
        self.assertIn("changes Shutter Duration", element.find("property[@name='native_curve_candidate_note']").text)

    def test_10_7_incoming_shutter_taper_rejects_wrong_record_or_changed_source(self):
        record, tree = self.zoom_out_spin_10_7_incoming_fixture()
        record["source_identifier"] = "{8251884A-4379-40BE-BBB4-A30EFC673140}"
        with self.assertRaisesRegex(ValueError, "limited to the 10.7 counterclockwise incoming"):
            apply_zoom_out_spin_counterclockwise_incoming_shutter_taper_candidate(tree, record)

        record, tree = self.zoom_out_spin_10_7_incoming_fixture()
        curves = json.loads(tree.find(".//property[@name='native_curves']").text)
        curves["rotation"][-1][1] = 5.0
        tree.find(".//property[@name='native_curves']").text = json.dumps(curves)
        with self.assertRaisesRegex(ValueError, "rotation keys do not match"):
            apply_zoom_out_spin_counterclockwise_incoming_shutter_taper_candidate(tree, record)

    def test_10_7_incoming_settle_candidate_eases_only_final_rotation_segment(self):
        record, tree = self.zoom_out_spin_10_7_incoming_fixture()
        element = tree.find(".//filter")
        before = json.loads(element.find("property[@name='native_curves']").text)
        expected_bezier = smoothstep_endpoint_bezier_points(-45.0, 0.0, 0.65)

        apply_zoom_out_spin_counterclockwise_incoming_settle_candidate(tree, record)

        after = json.loads(element.find("property[@name='native_curves']").text)
        self.assertEqual(after["z_distance"], before["z_distance"])
        self.assertEqual([(p[0], p[1]) for p in after["rotation"]],
                         [(p[0], p[1]) for p in before["rotation"]])
        self.assertEqual(after["rotation"][0], before["rotation"][0])
        self.assertEqual(after["rotation"][1][2:4], before["rotation"][1][2:4])
        self.assertEqual(after["rotation"][1][6], expected_bezier[0][6])
        self.assertAlmostEqual(after["rotation"][1][4],
                               0.7540976357699892 + expected_bezier[0][4] * (1 - 0.7540976357699892))
        self.assertAlmostEqual(after["rotation"][1][5], expected_bezier[0][5])
        self.assertAlmostEqual(after["rotation"][2][2],
                               0.7540976357699892 + expected_bezier[1][2] * (1 - 0.7540976357699892))
        self.assertAlmostEqual(after["rotation"][2][3], expected_bezier[1][3])
        self.assertEqual(after["shutter_duration"][-1][1], 0.0)
        self.assertEqual(element.find("property[@name='native_curve_candidate_id']").text,
                         "10.7-ccw-incoming-shutter-taper-rotation-settle-65-v2")

    def test_10_6_incoming_candidate_rejects_other_source_rows_and_modified_source_curves(self):
        record, tree = self.zoom_out_spin_10_6_incoming_fixture()
        record["source_identifier"] = "{F30DA728-F4D7-4D24-8454-BF3D99972694}"
        record["event_variant"] = "outgoing"
        with self.assertRaisesRegex(ValueError, "limited to the 10.6 clockwise incoming"):
            apply_zoom_out_spin_clockwise_incoming_eventwide_candidate(tree, record)

        record, tree = self.zoom_out_spin_10_6_incoming_fixture()
        curve = tree.getroot().find(".//property[@name='native_curves']")
        source = json.loads(curve.text)
        source["z_distance"][0][1] = 0.6
        curve.text = json.dumps(source)
        with self.assertRaisesRegex(ValueError, "saved project z_distance keys"):
            apply_zoom_out_spin_clockwise_incoming_eventwide_candidate(tree, record)

    def test_reverse_time_candidate_keeps_source_values_and_fits_endpoints(self):
        source = [
            {"normalized_event_position": 0.0, "value": -0.5},
            {"normalized_event_position": 1.0, "value": 0.0},
        ]
        candidate = reverse_event_time_monotone_candidate(source)
        self.assertEqual([(point[0], point[1]) for point in candidate],
                         [(0.0, 0.0), (1.0, -0.5)])
        self.assertEqual([point[6] for point in candidate], [1, 0])
        self.assertAlmostEqual(candidate[0][5], 0.0)
        self.assertAlmostEqual(candidate[1][3], -0.5)

    def test_reverse_time_candidate_requires_full_event_endpoints(self):
        with self.assertRaises(ValueError):
            reverse_event_time_monotone_candidate([
                {"normalized_event_position": 0.1, "value": 1.0},
                {"normalized_event_position": 1.0, "value": 0.0},
            ])

    def test_reverse_time_apply_candidate_is_limited_to_outgoing_record(self):
        root = ET.fromstring(
            "<mlt><producer><filter><property name='native_curves'>"
            "{&quot;shift_x&quot;:[[0,-0.5,0,-0.5,0,-0.5,0],[1,0,1,0,1,0,0]]}"
            "</property></filter></producer></mlt>")
        record = {"event_variant": "incoming", "components": []}
        with self.assertRaises(ValueError):
            apply_reverse_time_monotone_candidate(ET.ElementTree(root), record)

    def test_reverse_time_apply_candidate_updates_only_animated_native_parameter(self):
        root = ET.fromstring(
            "<mlt><producer><filter><property name='native_curves'>"
            "{&quot;shift_x&quot;:[[0,-0.5,0,-0.5,0,-0.5,0],[1,0,1,0,1,0,0]],"
            "&quot;rotation&quot;:[[0,0,0,0,0,0,0],[1,0,1,0,1,0,0]]}"
            "</property></filter></producer></mlt>")
        points = [
            {"normalized_event_position": 0.0, "value": -0.5},
            {"normalized_event_position": 1.0, "value": 0.0},
        ]
        record = {
            "event_variant": "outgoing",
            "components": [{
                "vendor_id": "{Svfx:com.genarts.sapphire.BlurSharpen.S_BlurMoCurves}",
                "parameters": [{"name": "Shift X", "animation": {"points": points}}],
            }],
        }
        apply_reverse_time_monotone_candidate(ET.ElementTree(root), record)
        curves = json.loads(root.find(".//property").text)
        self.assertEqual([(point[0], point[1]) for point in curves["shift_x"]],
                         [(0.0, 0.0), (1.0, -0.5)])
        self.assertEqual(curves["rotation"], [[0, 0, 0, 0, 0, 0, 0],
                                               [1, 0, 1, 0, 1, 0, 0]])

    def test_preserves_decoded_key_times_and_values(self):
        source = [[0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0],
                  [0.2381620607, -0.2, 0.0, 0.0, 0.0, 0.0, 0],
                  [0.6192213579, 0.0, 0.0, 0.0, 0.0, 0.0, 0]]
        result = monotone_bezier_points(source)
        self.assertEqual([(p[0], p[1]) for p in result],
                         [(p[0], p[1]) for p in source])
        self.assertEqual([p[6] for p in result], [1, 1, 0])

    def test_handles_stay_inside_monotone_segments(self):
        result = monotone_bezier_points([
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0],
            [0.4, 10.0, 0.4, 10.0, 0.4, 10.0, 0],
            [1.0, 15.0, 1.0, 15.0, 1.0, 15.0, 0],
        ])
        for left, right in zip(result, result[1:]):
            low, high = sorted((left[1], right[1]))
            self.assertGreaterEqual(left[5], low)
            self.assertLessEqual(left[5], high)
            self.assertGreaterEqual(right[3], low)
            self.assertLessEqual(right[3], high)

    def test_flat_and_turning_segments_have_zero_velocity_handles(self):
        result = monotone_bezier_points([
            [0.0, 2.0, 0, 2, 0, 2, 0],
            [0.25, 2.0, 0, 2, 0, 2, 0],
            [0.5, 1.0, 0, 1, 0, 1, 0],
            [1.0, 3.0, 0, 3, 0, 3, 0],
        ])
        self.assertEqual(result[0][5], 2.0)
        self.assertEqual(result[1][3], 2.0)
        self.assertEqual(result[1][5], 2.0)
        self.assertEqual(result[2][3], 1.0)
        self.assertEqual(result[2][5], 1.0)
        self.assertEqual(result[3][3], 3.0)

    def test_single_key_remains_constant(self):
        point = [0.4, 3.0, 0.2, 3.0, 0.6, 3.0, 1]
        self.assertEqual(monotone_bezier_points([point]),
                         [[0.4, 3.0, 0.4, 3.0, 0.4, 3.0, 0]])

    def test_duplicate_or_reversed_times_are_rejected(self):
        with self.assertRaises(ValueError):
            monotone_bezier_points([[0.5, 1, 0, 1, 0, 1, 0],
                                    [0.5, 2, 0, 2, 0, 2, 0]])
        with self.assertRaises(ValueError):
            monotone_bezier_points([[0.8, 1, 0, 1, 0, 1, 0],
                                    [0.2, 2, 0, 2, 0, 2, 0]])

    def test_candidate_maps_inferred_linear_hold_and_easing_types(self):
        source = [
            {"normalized_event_position": 0.0, "value": 0.0, "interpolation_code": 2},
            {"normalized_event_position": 0.5, "value": 1.0, "interpolation_code": 1},
            {"normalized_event_position": 1.0, "value": 1.0, "interpolation_code": 0},
        ]
        native = vegas_enum_order_candidate(source)
        self.assertEqual(native[0][6], 1)  # explicit native Bezier
        self.assertEqual(native[1][6], 2)  # explicit native hold
        self.assertEqual(native[2][6], 0)  # unused terminal type
        self.assertAlmostEqual(native[0][5], 0.0)  # slow segment starts at rest
        self.assertAlmostEqual(native[1][3], 1.0 - 1.0 / 3.0)

    def test_candidate_refuses_unresolved_sharp_segment(self):
        source = [
            {"normalized_event_position": 0.0, "value": 0.0, "interpolation_code": 5},
            {"normalized_event_position": 1.0, "value": 1.0, "interpolation_code": 0},
        ]
        with self.assertRaises(ValueError):
            vegas_enum_order_candidate(source)

    def test_zero_hold_hypothesis_maps_code_zero_to_hold_and_code_one_to_linear(self):
        source = [
            {"normalized_event_position": 0.0, "value": 2.0, "interpolation_code": 0},
            {"normalized_event_position": 0.5, "value": 2.0, "interpolation_code": 1},
            {"normalized_event_position": 1.0, "value": 0.0, "interpolation_code": 0},
        ]
        native = vegas_zero_hold_candidate(source)
        self.assertEqual(native[0][6], 2)
        self.assertEqual(native[1][6], 0)

    def test_incoming_key_candidate_uses_each_destination_keys_type(self):
        source = [
            {"normalized_event_position": 0.0, "value": 0.0, "interpolation_code": 2},
            {"normalized_event_position": 0.5, "value": 1.0, "interpolation_code": 4},
            {"normalized_event_position": 1.0, "value": 2.0, "interpolation_code": 1},
        ]
        native = vegas_zero_hold_incoming_key_candidate(source)
        self.assertEqual([point[6] for point in native], [1, 0, 0])
        # Destination code 4 is Smooth (a Bezier segment); destination code 1
        # is Linear. Endpoints remain the decoded values and times.
        self.assertAlmostEqual(native[0][0], 0.0)
        self.assertAlmostEqual(native[0][1], 0.0)
        self.assertAlmostEqual(native[1][0], 0.5)
        self.assertAlmostEqual(native[1][1], 1.0)
        self.assertAlmostEqual(native[2][0], 1.0)
        self.assertAlmostEqual(native[2][1], 2.0)

    def test_source_interpolation_candidate_maps_animated_shutter_duration(self):
        root = ET.Element("mlt")
        producer = ET.SubElement(root, "producer")
        effect = ET.SubElement(producer, "filter")
        curves = ET.SubElement(effect, "property", {"name": "native_curves"})
        curves.text = json.dumps({"shutter_duration": [
            [0.0, 1.5, 0.0, 1.5, 0.0, 1.5, 0],
            [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0],
        ]})
        record = {"components": [{
            "vendor_id": "{Svfx:com.genarts.sapphire.BlurSharpen.S_BlurMoCurves}",
            "parameters": [{"name": "Shutter Duration", "animation": {"points": [
                {"normalized_event_position": 0.0, "value": 1.5, "interpolation_code": 2},
                {"normalized_event_position": 1.0, "value": 1.0, "interpolation_code": 3},
            ]}}],
        }]}

        apply_vegas_zero_hold_destination_candidate(ET.ElementTree(root), record)

        result = json.loads(curves.text)["shutter_duration"]
        self.assertEqual([point[6] for point in result], [1, 0])
        self.assertEqual((result[0][0], result[0][1]), (0.0, 1.5))
        self.assertEqual((result[1][0], result[1][1]), (1.0, 1.0))

    def test_source_interpolation_candidate_maps_animated_brightness(self):
        root = ET.Element("mlt")
        producer = ET.SubElement(root, "producer")
        effect = ET.SubElement(producer, "filter")
        curves = ET.SubElement(effect, "property", {"name": "native_curves"})
        curves.text = json.dumps({"brightness": [
            [0.0, 1.25, 0.0, 1.25, 0.0, 1.25, 0],
            [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0],
        ]})
        rsmb = ET.SubElement(producer, "filter")
        record = {"components": [{
            "vendor_id": "{Svfx:com.genarts.sapphire.BlurSharpen.S_BlurMoCurves}",
            "parameters": [{"name": "Brightness", "animation": {"points": [
                {"normalized_event_position": 0.0, "value": 1.25, "interpolation_code": 2},
                {"normalized_event_position": 1.0, "value": 1.0, "interpolation_code": 3},
            ]}}],
        }, {
            "vendor_id": "{Svfx:com.revisionfx.RSMB}",
            "parameters": [{"name": "valMBAmount", "animation": None}],
        }]}

        apply_vegas_enum_order_candidate(ET.ElementTree(root), record)

        result = json.loads(curves.text)["brightness"]
        self.assertEqual([point[6] for point in result], [1, 0])
        self.assertEqual((result[0][0], result[0][1]), (0.0, 1.25))
        self.assertEqual((result[1][0], result[1][1]), (1.0, 1.0))

    def test_shared_arc_length_time_map_collapses_a_full_stack_hold(self):
        source = [[0.0, 0.0, 0, 0, 0, 0, 0],
                  [0.25, 1.0, 0, 0, 0, 0, 0],
                  [0.5, 1.0, 0, 0, 0, 0, 0],
                  [1.0, 2.0, 0, 0, 0, 0, 0]]
        mapped = shared_arc_length_time_map([{"shift_x": source}], sample_count=9)
        self.assertEqual(mapped[0], 0.0)
        self.assertEqual(mapped[-1], 1.0)
        self.assertTrue(all(a <= b for a, b in zip(mapped, mapped[1:])))
        # The source-value plateau from .25 to .5 no longer consumes a range
        # of output event time; it maps to its shared path endpoint.
        self.assertGreater(mapped[4], 0.45)
        self.assertLess(mapped[4], 0.55)

    def test_shared_time_candidate_keeps_component_curves_synchronized(self):
        root = ET.fromstring("<mlt><producer><filter><property name='native_curves'/></filter>"
                             "<filter><property name='native_curves'/></filter></producer></mlt>")
        filters = root.findall(".//producer/filter")
        first = [[0.0, 0.0, 0, 0, 0, 0, 0], [0.5, 1.0, 0, 0, 0, 0, 0], [1.0, 2.0, 0, 0, 0, 0, 0]]
        second = [[0.0, 2.0, 0, 0, 0, 0, 0], [1.0, 0.0, 0, 0, 0, 0, 0]]
        filters[0].find("property").text = json.dumps({"shift_x": first})
        filters[1].find("property").text = json.dumps({"amount": second})
        apply_shared_arc_length_time_candidate(ET.ElementTree(root), sample_count=9)
        a = json.loads(filters[0].find("property").text)["shift_x"]
        b = json.loads(filters[1].find("property").text)["amount"]
        self.assertEqual([point[0] for point in a], [point[0] for point in b])
        self.assertEqual((a[0][1], a[-1][1]), (0.0, 2.0))
        self.assertEqual((b[0][1], b[-1][1]), (2.0, 0.0))

    def test_screen_space_time_map_weights_translation_by_raster_distance(self):
        curves = [{
            "z_distance": [[0.0, 1.0], [0.25, 0.9]],
            "shift_x": [[0.4, 0.0], [0.7, -0.2], [1.0, 5.0]],
        }]
        screen_map = screen_space_arc_length_time_map(curves, 640, 360, sample_count=21)
        normalized_map = shared_arc_length_time_map(curves, sample_count=21)
        self.assertEqual((screen_map[0], screen_map[-1]), (0.0, 1.0))
        self.assertTrue(all(a <= b for a, b in zip(screen_map, screen_map[1:])))
        # A five-frame-width translation should consume more fitted duration
        # than the small 10% Z change when measured in approximate pixels.
        self.assertGreater(screen_map[5], normalized_map[5] + 0.3)

    def test_screen_space_time_map_rejects_invalid_raster_size(self):
        with self.assertRaises(ValueError):
            screen_space_arc_length_time_map([{"shift_x": [[0.0, 0.0], [1.0, 1.0]]}],
                                             0, 360, sample_count=9)

    def test_screen_space_candidate_uses_one_map_across_components(self):
        root = ET.fromstring("<mlt><producer><filter><property name='native_curves'/></filter>"
                             "<filter><property name='native_curves'/></filter></producer></mlt>")
        filters = root.findall(".//producer/filter")
        first = [[0.0, 0.0, 0, 0, 0, 0, 0], [0.5, 1.0, 0, 0, 0, 0, 0], [1.0, 2.0, 0, 0, 0, 0, 0]]
        second = [[0.0, 2.0, 0, 0, 0, 0, 0], [1.0, 0.0, 0, 0, 0, 0, 0]]
        filters[0].find("property").text = json.dumps({"shift_x": first})
        filters[1].find("property").text = json.dumps({"amount": second})
        apply_screen_space_arc_length_candidate(ET.ElementTree(root), 640, 360, sample_count=9)
        a = json.loads(filters[0].find("property").text)["shift_x"]
        b = json.loads(filters[1].find("property").text)["amount"]
        self.assertEqual([point[0] for point in a], [point[0] for point in b])
        self.assertEqual((a[0][1], a[-1][1]), (0.0, 2.0))
        self.assertEqual((b[0][1], b[-1][1]), (2.0, 0.0))

    def test_screen_space_candidate_uses_independent_maps_per_producer(self):
        root = ET.fromstring(
            "<mlt>"
            "<producer id='early'><filter><property name='native_curves'/></filter></producer>"
            "<producer id='late'><filter><property name='native_curves'/></filter></producer>"
            "</mlt>"
        )
        early_filter = root.find("producer[@id='early']/filter")
        late_filter = root.find("producer[@id='late']/filter")
        early_filter.find("property").text = json.dumps({
            "shift_x": [[0.0, 0.0, 0, 0, 0, 0, 0],
                        [0.25, 1.0, 0, 0, 0, 0, 0],
                        [1.0, 1.0, 0, 0, 0, 0, 0]],
        })
        late_filter.find("property").text = json.dumps({
            "shift_y": [[0.0, 0.0, 0, 0, 0, 0, 0],
                        [0.75, 0.0, 0, 0, 0, 0, 0],
                        [1.0, 1.0, 0, 0, 0, 0, 0]],
        })

        apply_screen_space_arc_length_candidate(ET.ElementTree(root), 320, 180, sample_count=9)

        early = json.loads(early_filter.find("property").text)["shift_x"]
        late = json.loads(late_filter.find("property").text)["shift_y"]
        # The outgoing-only map evaluates the early source key at .625; the
        # incoming-only map evaluates its late key at .15625. A combined map
        # would instead bias both producer paths using their summed distance.
        self.assertAlmostEqual(early[2][1], 0.625, places=4)
        self.assertAlmostEqual(late[2][1], 0.15625, places=4)

    def test_incoming_effect_strength_candidate_spreads_motion_toward_the_endpoint(self):
        curves = [{
            "shift_y": [[0.0, 5.0], [0.2382, -0.2], [0.6192, 0.0]],
            "z_distance": [[0.0, 0.9], [0.7621, 0.9], [1.0, 1.0]],
        }, {"amplitude": [[0.0, 2.0], [1.0, 0.0]]},
           {"amount": [[0.0, -0.3], [0.9526, 0.0]]}]
        mapped = effect_strength_time_map(curves, 640, 360, "incoming", sample_count=121)
        self.assertEqual((mapped[0], mapped[-1]), (0.0, 1.0))
        self.assertTrue(all(a <= b for a, b in zip(mapped, mapped[1:])))
        # The major shift endpoint at source progress .619 is now reached
        # late in the fitted event rather than in its first quarter.
        self.assertLess(mapped[60], 0.6192)
        self.assertGreater(mapped[102], 0.6192)

    def test_effect_strength_candidate_keeps_all_component_curves_on_one_map(self):
        root = ET.fromstring("<mlt><producer><filter><property name='native_event_role'>incoming</property>"
                             "<property name='native_curves'/></filter>"
                             "<filter><property name='native_curves'/></filter></producer></mlt>")
        filters = root.findall(".//producer/filter")
        first = [[0.0, 5.0, 0, 5, 0, 5, 0], [0.25, 0.0, 0, 0, 0, 0, 0],
                 [1.0, 0.0, 0, 0, 0, 0, 0]]
        second = [[0.0, 2.0, 0, 2, 0, 2, 0], [1.0, 0.0, 0, 0, 0, 0, 0]]
        filters[0].find("property[@name='native_curves']").text = json.dumps({"shift_y": first})
        filters[1].find("property[@name='native_curves']").text = json.dumps({"amplitude": second})
        apply_effect_strength_ease_candidate(ET.ElementTree(root), 640, 360, sample_count=9)
        a = json.loads(filters[0].find("property[@name='native_curves']").text)["shift_y"]
        b = json.loads(filters[1].find("property[@name='native_curves']").text)["amplitude"]
        self.assertEqual([point[0] for point in a], [point[0] for point in b])
        self.assertEqual((a[0][1], a[-1][1]), (5.0, 0.0))
        self.assertEqual((b[0][1], b[-1][1]), (2.0, 0.0))

    def test_endpoint_progress_candidate_fits_incoming_tracks_and_scales_shutter(self):
        root = ET.fromstring(
            "<mlt><producer><filter>"
            "<property name='mlt_service'>kdenlive_motion_curve</property>"
            "<property name='native_event_role'>incoming</property>"
            "<property name='native_event_frames'>63</property>"
            "<property name='native_nominal_frames'>20</property>"
            "<property name='shutter_duration'>1</property>"
            "<property name='native_curves'/></filter></producer></mlt>")
        element = root.find(".//producer/filter")
        source = [[0.0, 5.0, 0, 5, 0, 5, 0], [0.25, -0.2, 0, -0.2, 0, -0.2, 0],
                  [0.619, 0.0, 0, 0, 0, 0, 0]]
        element.find("property[@name='native_curves']").text = json.dumps({"shift_y": source})

        apply_endpoint_progress_candidate(ET.ElementTree(root), sample_count=5)

        points = json.loads(element.find("property[@name='native_curves']").text)["shift_y"]
        values = [point[1] for point in points]
        self.assertEqual((values[0], values[-1]), (5.0, 0.0))
        self.assertTrue(all(left > right for left, right in zip(values, values[1:])))
        # At one quarter, the event is already recovering, but retains a
        # linear floor so the eased tail cannot collapse into a visual hold.
        self.assertAlmostEqual(values[1], 5.0 * (1.0 - 0.325))
        self.assertEqual(float(element.find("property[@name='shutter_duration']").text), 1.0)
        shutter = json.loads(element.find("property[@name='native_curves']").text)["shutter_duration"]
        self.assertEqual((shutter[0][1], shutter[-1][1]), (1.0, 0.0))
        self.assertTrue(all(left[1] > right[1] for left, right in zip(shutter, shutter[1:])))

    def test_endpoint_progress_candidate_fits_outgoing_from_neutral(self):
        root = ET.fromstring(
            "<mlt><producer><filter>"
            "<property name='mlt_service'>kdenlive_motion_curve</property>"
            "<property name='native_event_role'>outgoing</property>"
            "<property name='shutter_duration'>1</property>"
            "<property name='native_curves'/></filter></producer></mlt>")
        element = root.find(".//producer/filter")
        source = [[0.0, 0.0, 0, 0, 0, 0, 0], [0.35, 0.2, 0, 0, 0, 0, 0],
                  [1.0, -5.0, 0, -5.0, 0, -5.0, 0]]
        element.find("property[@name='native_curves']").text = json.dumps({"shift_y": source})

        apply_endpoint_progress_candidate(ET.ElementTree(root), sample_count=5)

        points = json.loads(element.find("property[@name='native_curves']").text)["shift_y"]
        values = [point[1] for point in points]
        self.assertEqual((values[0], values[-1]), (0.0, -5.0))
        self.assertTrue(all(left > right for left, right in zip(values, values[1:])))
        self.assertAlmostEqual(values[1], -5.0 * 0.175)
        shutter = json.loads(element.find("property[@name='native_curves']").text)["shutter_duration"]
        self.assertEqual((shutter[0][1], shutter[-1][1]), (0.0, 1.0))

    def test_two_key_bezier_matches_incoming_and_outgoing_easing(self):
        ease_weight = 0.4
        for role in ("incoming", "outgoing"):
            start, end = 5.0, -1.5
            points = endpoint_progress_bezier_points(start, end, role, ease_weight)
            self.assertEqual(len(points), 2)
            self.assertEqual((points[0][0], points[0][1]), (0.0, start))
            self.assertEqual((points[1][0], points[1][1]), (1.0, end))
            p1, p2 = points[0][5], points[1][3]
            samples = []
            for index in range(101):
                t = index / 100
                one_minus = 1.0 - t
                actual = (one_minus**3 * start + 3 * one_minus**2 * t * p1
                          + 3 * one_minus * t**2 * p2 + t**3 * end)
                if role == "outgoing":
                    progress = (1 - ease_weight) * t + ease_weight * t * t
                else:
                    progress = ((1 - ease_weight) * t
                                + ease_weight * (2 * t - t * t))
                expected = start + (end - start) * progress
                self.assertAlmostEqual(actual, expected, places=10)
                samples.append(actual)
            self.assertTrue(all(a > b for a, b in zip(samples, samples[1:])))

    def test_bezier_pilot_keeps_curves_compact_and_shutter_editable(self):
        root = ET.fromstring(
            "<mlt><producer><filter>"
            "<property name='mlt_service'>kdenlive_motion_curve</property>"
            "<property name='native_event_role'>incoming</property>"
            "<property name='shutter_duration'>1</property>"
            "<property name='native_curves'/></filter></producer></mlt>")
        element = root.find(".//producer/filter")
        curve = [[0.0, 5.0, 0, 5, 0, 5, 0], [0.238, -0.2, 0, -0.2, 0, -0.2, 0],
                 [0.619, 0.0, 0, 0, 0, 0, 0]]
        element.find("property[@name='native_curves']").text = json.dumps({"shift_y": curve})

        apply_endpoint_progress_bezier_candidate(ET.ElementTree(root))

        curves = json.loads(element.find("property[@name='native_curves']").text)
        self.assertEqual(set(curves), {"shift_y", "shutter_duration"})
        self.assertEqual(len(curves["shift_y"]), 2)
        self.assertEqual((curves["shift_y"][0][1], curves["shift_y"][1][1]), (5.0, 0.0))
        self.assertEqual((curves["shutter_duration"][0][1],
                          curves["shutter_duration"][1][1]), (1.0, 0.0))

    def test_linear_floor_smoothstep_bezier_has_eased_nonzero_tangents(self):
        start, end, weight = 5.0, 0.0, 0.65
        points = smoothstep_endpoint_bezier_points(start, end, weight)
        self.assertEqual((points[0][0], points[0][1]), (0.0, start))
        self.assertEqual((points[1][0], points[1][1]), (1.0, end))
        self.assertAlmostEqual(points[0][5], start + (end - start) * (1 - weight) / 3)
        self.assertAlmostEqual(points[1][3], end - (end - start) * (1 - weight) / 3)
        samples = []
        for index in range(101):
            t = index / 100
            one_minus = 1 - t
            progress = (1 - weight) * t + weight * (3 * t * t - 2 * t * t * t)
            samples.append(start + (end - start) * progress)
        self.assertTrue(all(a > b for a, b in zip(samples, samples[1:])))
        self.assertGreater(abs(samples[1] - samples[0]), 0.0)
        self.assertLess(abs(samples[1] - samples[0]), abs(samples[50] - samples[49]))
        self.assertGreater(abs(samples[99] - samples[100]), 0.0)

    def test_linear_floor_smoothstep_candidate_fits_incoming_curve_and_shutter(self):
        root = ET.fromstring(
            "<mlt><producer><filter>"
            "<property name='mlt_service'>kdenlive_motion_curve</property>"
            "<property name='native_event_role'>incoming</property>"
            "<property name='shutter_duration'>1.5</property>"
            "<property name='native_curves'/></filter></producer></mlt>")
        element = root.find(".//producer/filter")
        element.find("property[@name='native_curves']").text = json.dumps({
            "shift_y": [[0.0, 5.0, 0, 5, 0, 5, 0],
                        [0.238, -0.2, 0, -0.2, 0, -0.2, 0],
                        [0.619, 0.0, 0, 0, 0, 0, 0]]})

        apply_smoothstep_endpoint_bezier_candidate(ET.ElementTree(root))

        curves = json.loads(element.find("property[@name='native_curves']").text)
        self.assertEqual(set(curves), {"shift_y", "shutter_duration"})
        self.assertEqual(len(curves["shift_y"]), 2)
        self.assertEqual((curves["shift_y"][0][1], curves["shift_y"][1][1]), (5.0, 0.0))
        self.assertEqual((curves["shutter_duration"][0][1],
                          curves["shutter_duration"][1][1]), (1.5, 0.0))

    def test_scroll_right_27_incoming_cubic_ease_out_settles_each_track(self):
        root = ET.fromstring(
            "<mlt><producer>"
            "<filter><property name='mlt_service'>kdenlive_motion_curve</property>"
            "<property name='native_event_role'>incoming</property><property name='native_curves'/></filter>"
            "<filter><property name='mlt_service'>kdenlive_shake</property>"
            "<property name='native_event_role'>incoming</property><property name='native_curves'/></filter>"
            "<filter><property name='mlt_service'>kdenlive_fisheye_warp</property>"
            "<property name='native_event_role'>incoming</property><property name='native_curves'/></filter>"
            "</producer></mlt>")
        filters = root.findall(".//producer/filter")
        curves = [
            {"shift_x": [[0.0, 5.0, 0, 5, 0, 5, 0], [1.0, 0.0, 1, 0, 1, 0, 0]],
             "z_distance": [[0.0, 0.9, 0, 0.9, 0, 0.9, 0], [1.0, 1.0, 1, 1, 1, 1, 0]],
             "shutter_duration": [[0.0, 1.0, 0, 1, 0, 1, 0], [1.0, 0.0, 1, 0, 1, 0, 0]]},
            {"amplitude": [[0.0, 2.0, 0, 2, 0, 2, 0], [1.0, 0.0, 1, 0, 1, 0, 0]],
             "frequency": [[0.0, 8.0, 0, 8, 0, 8, 0], [1.0, 0.1, 1, 0.1, 1, 0.1, 0]]},
            {"amount": [[0.0, -0.3, 0, -0.3, 0, -0.3, 0], [1.0, 0.0, 1, 0, 1, 0, 0]]},
        ]
        for element, value in zip(filters, curves):
            element.find("property[@name='native_curves']").text = json.dumps(value)

        record = {
            "source_identifier": "{CEFDEE77-588E-4932-9CBD-5D707852264A}",
            "exact_name": "2.7 Scroll Right (2) 20k",
            "event_variant": "incoming",
        }
        apply_scroll_right_27_incoming_cubic_ease_out_v2(ET.ElementTree(root), record)

        motion = json.loads(filters[0].find("property[@name='native_curves']").text)
        points = motion["shift_x"]
        self.assertEqual([(point[0], point[1]) for point in points], [(0.0, 5.0), (1.0, 0.0)])
        self.assertAlmostEqual(points[0][5], 0.0)
        self.assertAlmostEqual(points[1][3], 0.0)
        # Ease-out changes are strictly decreasing per equal time step.
        values = []
        for index in range(11):
            t = index / 10
            values.append(5.0 * (1.0 - t) ** 3)
        deltas = [abs(right - left) for left, right in zip(values, values[1:])]
        self.assertTrue(all(left > right for left, right in zip(deltas, deltas[1:])))
        self.assertEqual(json.loads(filters[2].find("property[@name='native_curves']").text)["amount"][-1][1], 0.0)

    def test_shutter_shift_fit_candidate_retains_peak_and_tapers_at_both_endpoints(self):
        root = ET.fromstring(
            "<mlt><producer><filter>"
            "<property name='mlt_service'>kdenlive_motion_curve</property>"
            "<property name='native_event_role'>incoming</property>"
            "<property name='shutter_duration'>1.5</property>"
            "<property name='shutter_shift'>0.85</property>"
            "<property name='native_curves'/></filter></producer></mlt>")
        element = root.find(".//producer/filter")
        element.find("property[@name='native_curves']").text = json.dumps({
            "shift_x": [[0.0, 0.5, 0, 0.5, 0, 0.5, 0],
                        [1.0, 0.0, 1, 0.0, 1, 0.0, 0]]})

        apply_smoothstep_endpoint_bezier_candidate(
            ET.ElementTree(root), ease_weight=0.4, fit_shutter_shift=True)

        curves = json.loads(element.find("property[@name='native_curves']").text)
        shift = curves["shutter_shift"]
        self.assertEqual([(point[0], point[1]) for point in shift],
                         [(0.0, 0.0), (0.5, 0.85), (1.0, 0.0)])
        self.assertEqual([point[6] for point in shift], [1, 1, 0])

    def test_smoothstep_candidate_uses_each_delivery_filter_role(self):
        root = ET.fromstring(
            "<mlt><chain>"
            "<filter><property name='mlt_service'>kdenlive_motion_curve</property>"
            "<property name='native_event_role'>outgoing</property>"
            "<property name='native_curves'/></filter>"
            "<filter><property name='mlt_service'>kdenlive_motion_curve</property>"
            "<property name='native_event_role'>incoming</property>"
            "<property name='native_curves'/></filter>"
            "</chain></mlt>")
        filters = root.findall(".//filter")
        filters[0].find("property[@name='native_curves']").text = json.dumps({
            "shift_y": [[0.0, 0.0, 0, 0, 0, 0, 0], [1.0, -5.0, 1, -5, 1, -5, 0]]})
        filters[1].find("property[@name='native_curves']").text = json.dumps({
            "shift_y": [[0.0, 5.0, 0, 5, 0, 5, 0], [1.0, 0.0, 1, 0, 1, 0, 0]]})

        apply_smoothstep_endpoint_bezier_candidate(ET.ElementTree(root))

        outgoing = json.loads(filters[0].find("property[@name='native_curves']").text)["shift_y"]
        incoming = json.loads(filters[1].find("property[@name='native_curves']").text)["shift_y"]
        self.assertEqual((outgoing[0][1], outgoing[-1][1]), (0.0, -5.0))
        self.assertEqual((incoming[0][1], incoming[-1][1]), (5.0, 0.0))
        self.assertAlmostEqual(outgoing[0][5], -5.0 * 0.35 / 3.0)
        self.assertAlmostEqual(incoming[0][5], 5.0 - 5.0 * 0.35 / 3.0)

    def test_endpoint_preserving_candidate_keeps_all_decoded_endpoints(self):
        root = ET.fromstring(
            "<mlt><producer><filter>"
            "<property name='native_curves'/></filter></producer></mlt>")
        element = root.find(".//filter")
        element.find("property[@name='native_curves']").text = json.dumps({
            "shift_x": [[0.0, 0.0, 0, 0.0, 0, 0.0, 0], [1.0, -0.25, 1, -0.25, 1, -0.25, 0]],
            "shutter_duration": [[0.0, 1.0, 0, 1.0, 0, 1.0, 0], [1.0, 1.5, 1, 1.5, 1, 1.5, 0]],
            "brightness": [[0.0, 1.0, 0, 1.0, 0, 1.0, 0], [1.0, 1.25, 1, 1.25, 1, 1.25, 0]],
        })

        apply_endpoint_preserving_smoothstep_candidate(ET.ElementTree(root), ease_weight=0.4)

        curves = json.loads(element.find("property[@name='native_curves']").text)
        self.assertEqual((curves["shift_x"][0][1], curves["shift_x"][-1][1]), (0.0, -0.25))
        self.assertEqual((curves["shutter_duration"][0][1], curves["shutter_duration"][-1][1]), (1.0, 1.5))
        self.assertEqual((curves["brightness"][0][1], curves["brightness"][-1][1]), (1.0, 1.25))
        self.assertAlmostEqual(curves["shift_x"][0][5], -0.25 * 0.6 / 3.0)

    def test_slide_right_candidate_keeps_source_shutter_and_adds_peak_envelope(self):
        import xml.etree.ElementTree as ET

        def fixture(role):
            root = ET.fromstring(
                "<mlt><producer><filter>"
                "<property name='mlt_service'>kdenlive_motion_curve</property>"
                f"<property name='native_event_role'>{role}</property>"
                "<property name='quality_samples'>8</property>"
                "<property name='native_curves'/></filter>"
                "<filter><property name='mlt_service'>kdenlive_motion_vector_blur</property>"
                "<property name='blur_amount'>0.65</property></filter>"
                "</producer></mlt>")
            element = root.find(".//filter")
            element.find("property[@name='native_curves']").text = json.dumps({
                "shift_x": [[0.0, 0.0, 0, 0, 0, 0, 0], [1.0, -0.25, 1, -0.25, 1, -0.25, 0]],
                "shutter_duration": [[0.0, 1.0, 0, 1, 0, 1, 0], [1.0, 1.5, 1, 1.5, 1, 1.5, 0]],
                "brightness": [[0.0, 1.0, 0, 1, 0, 1, 0], [1.0, 1.25, 1, 1.25, 1, 1.25, 0]],
            })
            return ET.ElementTree(root), element

        for role, expected_envelope in (("outgoing", (0.0, 1.0)), ("incoming", (1.0, 0.0))):
            tree, element = fixture(role)
            apply_slide_right_phase_shutter_candidate(tree)
            props = {node.get("name"): node.text for node in element.findall("property")}
            curves = json.loads(props["native_curves"])
            self.assertEqual(set(curves), {"shift_x", "shutter_duration", "brightness", "shutter_envelope"})
            self.assertEqual((curves["shutter_duration"][0][1], curves["shutter_duration"][-1][1]),
                             (1.0, 1.5))
            self.assertEqual((curves["shutter_envelope"][0][1], curves["shutter_envelope"][-1][1]),
                             expected_envelope)
            self.assertEqual(props["shutter_gain_adjust"], "8.0")
            self.assertEqual(props["shutter_envelope_adjust"], "1")
            self.assertEqual(props["quality_samples"], "16")
            if role == "outgoing":
                points = curves["shutter_envelope"]
                self.assertAlmostEqual(points[0][4], 0.2)
                self.assertAlmostEqual(points[0][5], 0.04)
                self.assertAlmostEqual(points[1][2], 0.65)
                self.assertAlmostEqual(points[1][3], 0.6)
            else:
                points = curves["shutter_envelope"]
                self.assertAlmostEqual(points[0][4], 1.0 / 3.0)
                self.assertAlmostEqual(points[0][5], 1.0 / 3.0)
                self.assertAlmostEqual(points[1][2], 2.0 / 3.0)
            for name in curves:
                points = curves[name]
                self.assertEqual((points[0][0], points[-1][0]), (0.0, 1.0))
                self.assertEqual((points[0][6], points[-1][6]), (1, 0))
            vector_filter = tree.getroot().findall(".//filter")[1]
            vector_props = {node.get("name"): node.text for node in vector_filter.findall("property")}
            vector_curves = json.loads(vector_props["native_curves"])
            self.assertEqual(vector_curves["blur_envelope"], curves["shutter_envelope"])
            self.assertEqual(vector_props["blur_envelope_adjust"], "1")

        with self.assertRaises(ValueError):
            tree, _ = fixture("outgoing")
            apply_slide_right_phase_shutter_candidate(tree, gain=20.0)

    def test_slide_right_candidate_supports_motion_only_source_chain(self):
        import xml.etree.ElementTree as ET

        root = ET.fromstring(
            "<mlt><producer><filter>"
            "<property name='mlt_service'>kdenlive_motion_curve</property>"
            "<property name='native_event_role'>outgoing</property>"
            "<property name='brightness'>1</property>"
            "<property name='native_curves'/></filter></producer></mlt>")
        motion = root.find(".//filter")
        motion.find("property[@name='native_curves']").text = json.dumps({
            "shift_x": [[0.0, 0.0, 0, 0, 0, 0, 0],
                        [1.0, -0.5, 1, -0.5, 1, -0.5, 0]],
            "shutter_duration": [[0.0, 1.8775510204, 0, 1.8775510204, 0, 1.8775510204, 0],
                                 [1.0, 1.8775510204, 1, 1.8775510204, 1, 1.8775510204, 0]],
        })
        tree = ET.ElementTree(root)
        apply_slide_right_phase_shutter_candidate(tree, cut_acceleration=True)
        props = {node.get("name"): node.text for node in motion.findall("property")}
        curves = json.loads(props["native_curves"])
        self.assertEqual(set(curves), {"shift_x", "shutter_duration", "shutter_envelope"})
        self.assertEqual(props["brightness"], "1")
        self.assertEqual(props["shutter_gain_adjust"], "8.0")
        self.assertEqual(props["quality_samples"], "16")
        self.assertEqual([node.findtext("property[@name='mlt_service']")
                          for node in tree.getroot().findall(".//filter")],
                         ["kdenlive_motion_curve"])

    def test_slide_right_candidate_keeps_static_shutter_for_single_motion_component(self):
        import xml.etree.ElementTree as ET

        root = ET.fromstring(
            "<mlt><producer><filter>"
            "<property name='mlt_service'>kdenlive_motion_curve</property>"
            "<property name='native_event_role'>outgoing</property>"
            "<property name='shutter_duration'>1.8775510204</property>"
            "<property name='brightness'>1</property>"
            "<property name='native_curves'/></filter></producer></mlt>")
        motion = root.find(".//filter")
        motion.find("property[@name='native_curves']").text = json.dumps({
            "shift_x": [[0.0, 0.0, 0, 0, 0, 0, 0],
                        [1.0, -0.5, 1, -0.5, 1, -0.5, 0]],
        })
        tree = ET.ElementTree(root)
        apply_slide_right_phase_shutter_candidate(tree, cut_acceleration=True)
        props = {node.get("name"): node.text for node in motion.findall("property")}
        curves = json.loads(props["native_curves"])
        self.assertEqual(set(curves), {"shift_x", "shutter_envelope"})
        self.assertEqual(props["shutter_duration"], "1.8775510204")
        self.assertEqual(props["brightness"], "1")
        self.assertEqual(curves["shutter_envelope"][0][1], 0.0)
        self.assertEqual(curves["shutter_envelope"][-1][1], 1.0)

    def test_slide_right_cut_acceleration_keeps_motion_live_at_cut_on_both_halves(self):
        def fixture(role, start, end):
            root = ET.fromstring(
                "<mlt><producer><filter>"
                "<property name='mlt_service'>kdenlive_motion_curve</property>"
                f"<property name='native_event_role'>{role}</property>"
                "<property name='native_curves'/></filter>"
                "<filter><property name='mlt_service'>kdenlive_motion_vector_blur</property>"
                "<property name='blur_amount'>0.65</property></filter>"
                "</producer></mlt>")
            motion = root.find(".//filter")
            motion.find("property[@name='native_curves']").text = json.dumps({
                "shift_x": [[0.0, start, 0, start, 0, start, 0],
                            [1.0, end, 1, end, 1, end, 0]],
                "shutter_duration": [[0.0, 1.0, 0, 1, 0, 1, 0],
                                     [1.0, 1.5, 1, 1.5, 1, 1.5, 0]],
                "brightness": [[0.0, 1.0, 0, 1, 0, 1, 0],
                               [1.0, 1.25, 1, 1.25, 1, 1.25, 0]],
            })
            return ET.ElementTree(root), motion

        fixtures = (("outgoing", 0.0, -0.25), ("incoming", 0.25, 0.0))
        envelopes = []
        for role, start, end in fixtures:
            tree, motion = fixture(role, start, end)
            apply_slide_right_phase_shutter_candidate(tree, cut_acceleration=True)
            props = {node.get("name"): node.text for node in motion.findall("property")}
            curves = json.loads(props["native_curves"])
            self.assertEqual((curves["shift_x"][0][1], curves["shift_x"][-1][1]), (start, end))
            self.assertEqual((curves["shutter_duration"][0][1], curves["shutter_duration"][-1][1]),
                             (1.0, 1.5))
            envelope = curves["shutter_envelope"]
            self.assertEqual((envelope[0][1], envelope[-1][1]), (0.0, 1.0) if role == "outgoing" else (1.0, 0.0))
            envelopes.append(envelope)
            if role == "outgoing":
                points = curves["shift_x"]
                start_slope = ((points[0][5] - points[0][1]) / (points[0][4] - points[0][0])
                               / (end - start))
                end_slope = ((points[1][1] - points[1][3]) / (points[1][0] - points[1][2])
                             / (end - start))
                self.assertAlmostEqual(start_slope, 0.2)
                self.assertAlmostEqual(end_slope, 2.0)
            else:
                points = curves["shift_x"]
                start_slope = ((points[0][5] - points[0][1]) / (points[0][4] - points[0][0])
                               / (end - start))
                self.assertAlmostEqual(start_slope, 2.0)
            vector = tree.getroot().findall(".//filter")[1]
            vector_props = {node.get("name"): node.text for node in vector.findall("property")}
            self.assertEqual(json.loads(vector_props["native_curves"])["blur_envelope"], envelope)
        self.assertAlmostEqual(envelopes[0][0][5] / (envelopes[0][-1][1] - envelopes[0][0][1]), 0.35 / 3)
        self.assertAlmostEqual(envelopes[1][0][5], 1 - 0.35 / 3)

    def test_endpoint_preserving_candidate_rejects_multikey_source_tracks(self):
        root = ET.fromstring(
            "<mlt><producer><filter><property name='native_curves'/></filter></producer></mlt>")
        element = root.find(".//filter")
        element.find("property[@name='native_curves']").text = json.dumps({
            "shift_x": [[0.0, 0.0, 0, 0, 0, 0, 0], [0.5, -0.2, 0.5, -0.2, 0.5, -0.2, 0],
                        [1.0, -0.25, 1, -0.25, 1, -0.25, 0]],
        })
        with self.assertRaisesRegex(ValueError, "exactly two"):
            apply_endpoint_preserving_smoothstep_candidate(ET.ElementTree(root))


if __name__ == "__main__":
    unittest.main()
