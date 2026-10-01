#!/usr/bin/env python3
"""Regression coverage for paired, whole-event native transition fixtures."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from create_paired_native_transition_fixture import make_fixture


class NativeTransitionPairFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inventory = json.loads((ROOT / "plans/native-transition-inventory.json").read_text(encoding="utf-8"))
        cls.args = (
            cls.inventory,
            "2.1 Slide Right (1) 10k",
            "2.1 Slide Right (2) 10k",
            Path("first-scene.mp4"),
            Path("second-scene.mp4"),
            30,
            8,
            320,
            180,
            60,
            1,
        )

    def test_pair_fits_both_stacks_to_inclusive_event_endpoints(self) -> None:
        tree = make_fixture(
            *self.args,
            event_frames=62,
            curve_policy="endpoint-smoothstep-bezier-candidate",
            ease_weight=0.4,
            fit_shutter_shift=True,
        )
        root = tree.getroot()
        playlist = root.find("playlist")
        self.assertIsNotNone(playlist)
        entries = playlist.findall("entry")
        self.assertEqual(
            [(entry.get("producer"), entry.get("in"), entry.get("out")) for entry in entries],
            [("before", "22", "29"),
             ("outgoing_event", "30", "91"),
             ("incoming_event", "30", "91"),
             ("after", "92", "99")],
        )
        self.assertEqual(sum(int(entry.get("out")) - int(entry.get("in")) + 1 for entry in entries), 140)
        for producer_id in ("outgoing_event", "incoming_event"):
            producer = root.find(f"producer[@id='{producer_id}']")
            self.assertIsNotNone(producer)
            motion = next(effect for effect in producer.findall("filter")
                          if effect.findtext("property[@name='mlt_service']") == "kdenlive_motion_curve")
            self.assertEqual(motion.findtext("property[@name='native_event_frames']"), "62")
            self.assertEqual(motion.findtext("property[@name='native_nominal_frames']"), "10")

    def test_matched_baseline_removes_only_event_stacks(self) -> None:
        tree = make_fixture(*self.args, event_frames=62, effects_enabled=False)
        root = tree.getroot()
        playlist = root.find("playlist")
        self.assertEqual(len(playlist.findall("entry")), 4)
        self.assertEqual(
            [(entry.get("producer"), entry.get("in"), entry.get("out")) for entry in playlist.findall("entry")],
            [("before", "22", "29"),
             ("outgoing_event", "30", "91"),
             ("incoming_event", "30", "91"),
             ("after", "92", "99")],
        )
        for producer_id in ("outgoing_event", "incoming_event"):
            producer = root.find(f"producer[@id='{producer_id}']")
            self.assertEqual(producer.findall("filter"), [])

    def test_scroll_left_14_fits_outgoing_keys_and_recovers_incoming(self) -> None:
        tree = make_fixture(
            self.inventory,
            "1.4 Scroll Left (1) 20k",
            "1.4 Scroll Left (2) 20k",
            Path("first-scene.mp4"),
            Path("second-scene.mp4"),
            30, 3, 320, 180, 30, 1,
            event_frames=15,
            curve_policy="scroll-left-14-full-event-pair-v1",
        )
        root = tree.getroot()
        outgoing = root.find("producer[@id='outgoing_event']")
        incoming = root.find("producer[@id='incoming_event']")
        motion_out = next(effect for effect in outgoing.findall("filter")
                          if effect.findtext("property[@name='mlt_service']") == "kdenlive_motion_curve")
        motion_in = next(effect for effect in incoming.findall("filter")
                         if effect.findtext("property[@name='mlt_service']") == "kdenlive_motion_curve")
        out_curves = json.loads(motion_out.findtext("property[@name='native_curves']"))
        in_curves = json.loads(motion_in.findtext("property[@name='native_curves']"))
        self.assertAlmostEqual(out_curves["shift_x"][0][0], 0.0490, places=3)
        self.assertAlmostEqual(out_curves["shift_x"][1][0], 0.1250, places=3)
        self.assertEqual(out_curves["shift_x"][-1][0], 1.0)
        self.assertEqual([point[1] for point in out_curves["shift_x"]], [0.0, -0.2, 5.0])
        self.assertEqual(in_curves["shift_x"][-1][0], 1.0)
        self.assertEqual(in_curves["shutter_duration"][-1][1], 0.0)

    def test_smooth_r_to_l_pair_builds_from_readable_outgoing_to_sharp_incoming(self) -> None:
        tree = make_fixture(
            self.inventory,
            "1.1 Smooth R to L (1) 10k",
            "1.1 Smooth R to L (2) 10k",
            Path("first-scene.mp4"),
            Path("second-scene.mp4"),
            30, 3, 320, 180, 60, 1,
            event_frames=30,
            curve_policy="smooth-r-to-l-role-ease-v1",
        )
        root = tree.getroot()
        outgoing = root.find("producer[@id='outgoing_event']")
        incoming = root.find("producer[@id='incoming_event']")
        motion_out = next(effect for effect in outgoing.findall("filter")
                          if effect.findtext("property[@name='mlt_service']") == "kdenlive_motion_curve")
        motion_in = next(effect for effect in incoming.findall("filter")
                         if effect.findtext("property[@name='mlt_service']") == "kdenlive_motion_curve")
        out_curves = json.loads(motion_out.findtext("property[@name='native_curves']"))
        in_curves = json.loads(motion_in.findtext("property[@name='native_curves']"))
        self.assertEqual((out_curves["shift_x"][0][1], out_curves["shift_x"][-1][1]), (0.0, -0.5))
        self.assertEqual((out_curves["shutter_duration"][0][1],
                          out_curves["shutter_duration"][-1][1]), (0.0, 1.9047619047619047))
        self.assertEqual((in_curves["shift_x"][0][1], in_curves["shift_x"][-1][1]), (0.2, 0.0))
        self.assertEqual((in_curves["shutter_duration"][0][1],
                          in_curves["shutter_duration"][-1][1]), (1.5, 0.0))
        stretch = next(effect for effect in incoming.findall("filter")
                       if effect.findtext("property[@name='mlt_service']") == "kdenlive_axis_stretch")
        stretch_curves = json.loads(stretch.findtext("property[@name='native_curves']"))
        self.assertEqual((stretch_curves["scale_x"][0][1], stretch_curves["scale_x"][-1][1]), (1.6, 1.0))

    def test_distinct_incoming_source_inpoint_keeps_cut_and_context_lengths(self) -> None:
        tree = make_fixture(*self.args, event_frames=62, second_source_in=600)
        entries = tree.getroot().find("playlist").findall("entry")
        self.assertEqual(
            [(entry.get("producer"), entry.get("in"), entry.get("out")) for entry in entries],
            [("before", "22", "29"),
             ("outgoing_event", "30", "91"),
             ("incoming_event", "600", "661"),
             ("after", "662", "669")],
        )

    def test_distinct_event_lengths_keep_one_role_stack_per_clip(self) -> None:
        tree = make_fixture(
            self.inventory,
            "4.3 Scroll Up (1) 20k",
            "4.3 Scroll Up (2) 20k",
            Path("first-scene.mp4"),
            Path("second-scene.mp4"),
            30, 1, 320, 180, 60, 1,
            event_frames=62,
            incoming_event_frames=63,
            curve_policy="endpoint-smoothstep-bezier-candidate",
        )
        root = tree.getroot()
        self.assertEqual(
            [(entry.get("producer"), entry.get("in"), entry.get("out"))
             for entry in root.find("playlist").findall("entry")],
            [("before", "29", "29"),
             ("outgoing_event", "30", "91"),
             ("incoming_event", "30", "92"),
             ("after", "93", "93")],
        )
        expected = {
            "outgoing_event": ("outgoing", "62", ["kdenlive_motion_curve", "kdenlive_fisheye_warp"]),
            "incoming_event": ("incoming", "63", ["kdenlive_motion_curve", "kdenlive_shake", "kdenlive_fisheye_warp"]),
        }
        for producer_id, (role, frame_count, services_expected) in expected.items():
            producer = root.find(f"producer[@id='{producer_id}']")
            filters = producer.findall("filter")
            self.assertEqual(
                [f.findtext("property[@name='mlt_service']") for f in filters],
                services_expected,
            )
            self.assertTrue(all(f.findtext("property[@name='native_event_role']") == role
                                for f in filters))
            self.assertTrue(all(f.findtext("property[@name='native_event_frames']") == frame_count
                                for f in filters))
        self.assertNotEqual(
            root.find("producer[@id='outgoing_event']/property[@name='resource']").text,
            root.find("producer[@id='incoming_event']/property[@name='resource']").text,
        )

    def test_slide_right_15k_candidate_preserves_two_key_values_and_component_order(self) -> None:
        tree = make_fixture(
            self.inventory,
            "2.2 Slide Right (1) 15k",
            "2.2 Slide Right (2) 15k",
            Path("first-scene.mp4"),
            Path("second-scene.mp4"),
            30, 8, 320, 180, 60, 1,
            curve_policy="endpoint-preserving-smoothstep-candidate",
            ease_weight=0.4,
            second_source_in=600,
        )
        root = tree.getroot()
        expected = {
            "outgoing_event": {
                "shift_x": (0.0, -0.25),
                "shutter_duration": (1.0, 1.5),
                "brightness": (1.0, 1.25),
            },
            "incoming_event": {
                "shift_x": (0.25, 0.0),
                "shutter_duration": (1.5, 1.0),
                "brightness": (1.25, 1.0),
            },
        }
        for producer_id, curves_expected in expected.items():
            producer = root.find(f"producer[@id='{producer_id}']")
            effects = producer.findall("filter")
            self.assertEqual(
                [effect.findtext("property[@name='mlt_service']") for effect in effects],
                ["kdenlive_motion_curve", "kdenlive_motion_vector_blur"],
            )
            curves = json.loads(effects[0].findtext("property[@name='native_curves']"))
            for name, endpoints in curves_expected.items():
                self.assertEqual((curves[name][0][1], curves[name][-1][1]), endpoints)
            rsmb = effects[1]
            self.assertEqual(rsmb.findtext("property[@name='blur_amount']"), "0.65")
        self.assertEqual(
            [(entry.get("producer"), entry.get("in"), entry.get("out"))
             for entry in root.find("playlist").findall("entry")],
            [("before", "22", "29"), ("outgoing_event", "30", "44"),
             ("incoming_event", "600", "614"), ("after", "615", "622")],
        )

    def test_single_axis_slide_v2_keeps_cut_motion_and_blur_coupled(self) -> None:
        tree = make_fixture(
            self.inventory,
            "3.1 Slide Down (1) 10k",
            "3.1 Slide Down (2) 10k",
            Path("first-scene.mp4"),
            Path("second-scene.mp4"),
            30, 3, 320, 180, 60, 1,
            event_frames=30,
            curve_policy="single-axis-slide-cut-acceleration-v2",
        )
        root = tree.getroot()
        expected = {
            "outgoing_event": ("outgoing", (0.0, -0.5), (0.0, 1.0)),
            "incoming_event": ("incoming", (0.5, 0.0), (1.0, 0.0)),
        }
        for producer_id, (role, shift_endpoints, shutter_endpoints) in expected.items():
            producer = root.find(f"producer[@id='{producer_id}']")
            filters = producer.findall("filter")
            self.assertEqual(
                [f.findtext("property[@name='mlt_service']") for f in filters],
                ["kdenlive_motion_curve"],
            )
            motion = filters[0]
            self.assertEqual(motion.findtext("property[@name='native_event_role']"), role)
            self.assertEqual(motion.findtext("property[@name='native_event_frames']"), "30")
            curves = json.loads(motion.findtext("property[@name='native_curves']"))
            self.assertEqual((curves["shift_y"][0][1], curves["shift_y"][-1][1]), shift_endpoints)
            self.assertEqual((curves["shutter_envelope"][0][1], curves["shutter_envelope"][-1][1]), shutter_endpoints)
            if role == "incoming":
                self.assertAlmostEqual(curves["shift_y"][-1][3], 0.025)
            self.assertEqual(motion.findtext("property[@name='quality_samples']"), "16")
            self.assertEqual(motion.findtext("property[@name='shutter_gain_adjust']"), "8.0")
            self.assertEqual(motion.findtext("property[@name='shutter_envelope_adjust']"), "1")
        self.assertEqual(
            [(entry.get("producer"), entry.get("in"), entry.get("out"))
             for entry in root.find("playlist").findall("entry")],
            [("before", "27", "29"), ("outgoing_event", "30", "59"),
             ("incoming_event", "30", "59"), ("after", "60", "62")],
        )

    def test_screen_space_candidate_fits_each_event_without_changing_the_cut(self) -> None:
        tree = make_fixture(*self.args, event_frames=62,
                            curve_policy="screen-space-arc-length-candidate")
        root = tree.getroot()
        self.assertEqual(
            [(entry.get("producer"), entry.get("in"), entry.get("out"))
             for entry in root.find("playlist").findall("entry")],
            [("before", "22", "29"), ("outgoing_event", "30", "91"),
             ("incoming_event", "30", "91"), ("after", "92", "99")],
        )
        for producer_id in ("outgoing_event", "incoming_event"):
            producer = root.find(f"producer[@id='{producer_id}']")
            for effect in producer.findall("filter"):
                encoded = effect.findtext("property[@name='native_curves']")
                if not encoded:
                    continue
                for points in json.loads(encoded).values():
                    self.assertEqual(len(points), 121)
                    self.assertEqual(points[0][0], 0.0)
                    self.assertEqual(points[-1][0], 1.0)

    def test_monotone_cubic_pair_candidate_keeps_10_2_intermediate_keys_and_full_chain(self) -> None:
        tree = make_fixture(
            self.inventory,
            "10.2 Zoom Out (1) 15k",
            "10.2 Zoom Out (2) 15k",
            Path("first-scene.mp4"),
            Path("second-scene.mp4"),
            30, 1, 320, 180, 60, 1,
            event_frames=30,
            curve_policy="monotone-cubic-candidate",
        )
        root = tree.getroot()
        expected_services = [
            "kdenlive_motion_curve",
            "kdenlive_pinch_punch",
            "kdenlive_motion_vector_blur",
        ]
        for producer_id in ("outgoing_event", "incoming_event"):
            producer = root.find(f"producer[@id='{producer_id}']")
            filters = producer.findall("filter")
            self.assertEqual(
                [f.findtext("property[@name='mlt_service']") for f in filters],
                expected_services,
            )
            self.assertTrue(all(f.findtext("property[@name='native_event_frames']") == "30"
                                for f in filters))

        incoming_motion = root.find("producer[@id='incoming_event']/filter")
        curves = json.loads(incoming_motion.findtext("property[@name='native_curves']"))
        self.assertEqual(len(curves["z_distance"]), 3)
        self.assertAlmostEqual(curves["z_distance"][0][0], 0.0)
        self.assertAlmostEqual(curves["z_distance"][0][1], 0.5)
        self.assertAlmostEqual(curves["z_distance"][1][0], 0.7540983767643257)
        self.assertAlmostEqual(curves["z_distance"][1][1], 0.5)
        self.assertAlmostEqual(curves["z_distance"][2][0], 1.0)
        self.assertAlmostEqual(curves["z_distance"][2][1], 1.0)

    def test_zoom_out_10_5_ease_out_candidate_spreads_incoming_recovery(self) -> None:
        tree = make_fixture(
            self.inventory,
            "10.5 Zoom Out Pinch (1) 15k",
            "10.5 Zoom Out Pinch (2) 15k",
            Path("first-scene.mp4"),
            Path("second-scene.mp4"),
            30, 1, 320, 180, 60, 1,
            event_frames=30,
            curve_policy="zoom-out-10-5-incoming-ease-out-v1",
        )
        root = tree.getroot()
        expected_chain = ["kdenlive_motion_curve", "kdenlive_pinch_punch"]
        for producer_id in ("outgoing_event", "incoming_event"):
            producer = root.find(f"producer[@id='{producer_id}']")
            filters = producer.findall("filter")
            self.assertEqual([f.findtext("property[@name='mlt_service']") for f in filters], expected_chain)
        incoming = root.find("producer[@id='incoming_event']")
        motion, pinch = incoming.findall("filter")
        motion_curves = json.loads(motion.findtext("property[@name='native_curves']"))
        pinch_curves = json.loads(pinch.findtext("property[@name='native_curves']"))
        for name, endpoints in (("z_distance", (0.5, 1.0)),
                                ("shutter_duration", (1.5, 1.0))):
            points = motion_curves[name]
            self.assertEqual(len(points), 2)
            self.assertEqual((points[0][0], points[0][1]), (0.0, endpoints[0]))
            self.assertEqual((points[-1][0], points[-1][1]), (1.0, endpoints[1]))
        self.assertEqual((pinch_curves["amount"][0][1], pinch_curves["amount"][-1][1]), (-1.0, 0.0))
        self.assertEqual(motion.findtext("property[@name='native_event_frames']"), "30")

    def test_zoom_out_10_5_ease_out_candidate_rejects_other_source_ids(self) -> None:
        with self.assertRaises(ValueError):
            make_fixture(
                self.inventory,
                "10.4 Zoom Out Right (1) 15k",
                "10.4 Zoom Out Right (2) 15k",
                Path("first-scene.mp4"),
                Path("second-scene.mp4"),
                30, 1, 320, 180, 60, 1,
                curve_policy="zoom-out-10-5-incoming-ease-out-v1",
            )

    def test_zoom_spin_10_6_eventwide_candidate_removes_incoming_hold(self) -> None:
        outgoing_name = "10.6 Zoom Out Spin ClockWise (1) 15k"
        incoming_name = "10.6 Zoom Out Spin ClockWise (2) 15k"
        baseline = make_fixture(
            self.inventory, outgoing_name, incoming_name,
            Path("first-scene.mp4"), Path("second-scene.mp4"),
            30, 3, 320, 180, 60, 1, event_frames=30, curve_policy="native-linear")
        candidate = make_fixture(
            self.inventory, outgoing_name, incoming_name,
            Path("first-scene.mp4"), Path("second-scene.mp4"),
            30, 3, 320, 180, 60, 1, event_frames=30,
            curve_policy="spin-10-6-incoming-eventwide-v1")
        for producer_id in ("outgoing_event", "incoming_event"):
            original = baseline.getroot().find(f"producer[@id='{producer_id}']")
            updated = candidate.getroot().find(f"producer[@id='{producer_id}']")
            original_motion = next(effect for effect in original.findall("filter")
                                   if effect.findtext("property[@name='mlt_service']") == "kdenlive_motion_curve")
            updated_motion = next(effect for effect in updated.findall("filter")
                                  if effect.findtext("property[@name='mlt_service']") == "kdenlive_motion_curve")
            before = json.loads(original_motion.findtext("property[@name='native_curves']"))
            after = json.loads(updated_motion.findtext("property[@name='native_curves']"))
            if producer_id == "outgoing_event":
                self.assertEqual(before, after)
                continue
            for name, endpoints in {
                    "z_distance": (0.5, 1.0),
                    "rotation": (45.0, 0.0),
                    "shutter_duration": (1.5, 1.0),
            }.items():
                self.assertEqual((after[name][0][0], after[name][-1][0]), (0.0, 1.0))
                self.assertEqual((after[name][0][1], after[name][-1][1]), endpoints)
                self.assertNotEqual([point[0] for point in after[name]],
                                    [point[0] for point in before[name]])
            self.assertEqual(updated_motion.findtext("property[@name='native_event_frames']"), "30")

    def test_zoom_spin_10_6_eventwide_candidate_rejects_other_source_pair(self) -> None:
        with self.assertRaisesRegex(ValueError, "exact 10.6 clockwise pair"):
            make_fixture(
                self.inventory,
                "10.7 Zoom Out Spin CounterClockWise (1) 15k",
                "10.7 Zoom Out Spin CounterClockWise (2) 15k",
                Path("first-scene.mp4"), Path("second-scene.mp4"),
                30, 3, 320, 180, 60, 1,
                curve_policy="spin-10-6-incoming-eventwide-v1",
            )

    def test_zoom_spin_rsmb_curve_candidate_preserves_source_keys_for_both_pairs(self) -> None:
        for outgoing, incoming in (
            ("10.8 Zoom Out CCW Spin (1) 15k", "10.8 Zoom Out CCW Spin (2) 15k"),
        ):
            baseline = make_fixture(
                self.inventory, outgoing, incoming, Path("first-scene.mp4"), Path("second-scene.mp4"),
                30, 3, 320, 180, 60, 1, event_frames=15, curve_policy="native-linear")
            candidate = make_fixture(
                self.inventory, outgoing, incoming, Path("first-scene.mp4"), Path("second-scene.mp4"),
                30, 3, 320, 180, 60, 1, event_frames=15,
                curve_policy="zoom-spin-rsmb-monotone-cubic-v1")
            for producer_id in ("outgoing_event", "incoming_event"):
                before = baseline.getroot().find(f"producer[@id='{producer_id}']").findall("filter")
                after = candidate.getroot().find(f"producer[@id='{producer_id}']").findall("filter")
                self.assertEqual([f.findtext("property[@name='mlt_service']") for f in after],
                                 ["kdenlive_motion_curve", "kdenlive_motion_vector_blur"])
                source_curves = json.loads(before[0].findtext("property[@name='native_curves']"))
                candidate_curves = json.loads(after[0].findtext("property[@name='native_curves']"))
                self.assertEqual(source_curves.keys(), candidate_curves.keys())
                for name, source_points in source_curves.items():
                    points = candidate_curves[name]
                    self.assertEqual([(p[0], p[1]) for p in points],
                                     [(p[0], p[1]) for p in source_points])
                    self.assertTrue(any(p[2] != p[0] or p[4] != p[0] for p in points[1:-1]))

    def test_zoom_spin_rsmb_curve_candidate_rejects_mixed_source_pair(self) -> None:
        with self.assertRaisesRegex(ValueError, "exact 10.8 counterclockwise pair"):
            make_fixture(
                self.inventory,
                "10.8 Zoom Out CCW Spin (1) 15k",
                "10.9 Zoom Out CW Spin (2) 15k",
                Path("first-scene.mp4"), Path("second-scene.mp4"),
                30, 3, 320, 180, 60, 1, event_frames=15,
                curve_policy="zoom-spin-rsmb-monotone-cubic-v1")

    def test_zoom_spin_rsmb_10_9_ease_out_removes_incoming_hold_and_keeps_source_endpoints(self) -> None:
        outgoing = "10.9 Zoom Out CW Spin (1) 15k"
        incoming = "10.9 Zoom Out CW Spin (2) 15k"
        candidate = make_fixture(
            self.inventory, outgoing, incoming, Path("first-scene.mp4"), Path("second-scene.mp4"),
            30, 3, 320, 180, 60, 1, event_frames=15,
            curve_policy="zoom-spin-rsmb-incoming-ease-out-v1")
        baseline = make_fixture(
            self.inventory, outgoing, incoming, Path("first-scene.mp4"), Path("second-scene.mp4"),
            30, 3, 320, 180, 60, 1, event_frames=15, curve_policy="native-linear")
        incoming_filters = candidate.getroot().find("producer[@id='incoming_event']").findall("filter")
        self.assertEqual([f.findtext("property[@name='mlt_service']") for f in incoming_filters],
                         ["kdenlive_motion_curve", "kdenlive_motion_vector_blur"])
        candidate_curves = json.loads(incoming_filters[0].findtext("property[@name='native_curves']"))
        source_curves = json.loads(baseline.getroot().find("producer[@id='incoming_event']")
                                   .find("filter").findtext("property[@name='native_curves']"))
        expected = {"z_distance": (0.5, 1.0), "rotation": (45.0, 0.0),
                    "shutter_duration": (1.5, 0.0), "brightness": (1.25, 1.0)}
        for name, (start, end) in expected.items():
            points = candidate_curves[name]
            self.assertEqual(len(points), 2)
            self.assertEqual((points[0][0], points[0][1]), (0.0, start))
            self.assertEqual((points[-1][0], points[-1][1]), (1.0, end))
            self.assertGreater(len(source_curves[name]), 2)
        self.assertEqual(candidate_curves["rotation"][0][5], 0.0)
        rsmb_curves = json.loads(incoming_filters[1].findtext("property[@name='native_curves']"))
        self.assertEqual(rsmb_curves["blur_envelope"][0][0:2], [0.0, 1.0])
        self.assertEqual(rsmb_curves["blur_envelope"][-1][0:2], [1.0, 0.0])

    def test_zoom_spin_rsmb_10_9_ease_out_rejects_other_pair(self) -> None:
        with self.assertRaisesRegex(ValueError, "exact 10.9 clockwise pair"):
            make_fixture(
                self.inventory,
                "10.8 Zoom Out CCW Spin (1) 15k",
                "10.8 Zoom Out CCW Spin (2) 15k",
                Path("first-scene.mp4"), Path("second-scene.mp4"),
                30, 3, 320, 180, 60, 1, event_frames=15,
                curve_policy="zoom-spin-rsmb-incoming-ease-out-v1")

    def test_11_2_and_11_3_incoming_spin_recovery_fits_whole_event(self) -> None:
        for outgoing, incoming in (
            ("11.2 Spin ClockWise (1) 15k", "11.2 Spin ClockWise (2) 15k"),
            ("11.3 Spin CounterClockWise (1) 15k", "11.3 Spin CounterClockWise (2) 15k"),
        ):
            source = make_fixture(
                self.inventory, outgoing, incoming, Path("first-scene.mp4"), Path("second-scene.mp4"),
                30, 3, 320, 180, 60, 1, event_frames=30, curve_policy="native-linear")
            candidate = make_fixture(
                self.inventory, outgoing, incoming, Path("first-scene.mp4"), Path("second-scene.mp4"),
                30, 3, 320, 180, 60, 1, event_frames=30,
                curve_policy="spin-11-2-11-3-incoming-recovery-v1")
            original = json.loads(source.getroot().find(
                "producer[@id='incoming_event']/filter/property[@name='native_curves']").text)
            curves = json.loads(candidate.getroot().find(
                "producer[@id='incoming_event']/filter/property[@name='native_curves']").text)
            self.assertEqual(len(original["rotation"]), 3)
            self.assertEqual((original["rotation"][0][1], original["rotation"][-1][1]), (45.0, 0.0))
            self.assertEqual([(point[0], point[1]) for point in curves["rotation"]], [(0.0, 45.0), (1.0, 0.0)])
            self.assertEqual([(point[0], point[1]) for point in curves["shutter_duration"]], [(0.0, 1.5), (1.0, 0.0)])
            self.assertLess(curves["rotation"][0][5], curves["rotation"][0][1])
            self.assertEqual(candidate.getroot().find(
                "producer[@id='incoming_event']/filter/property[@name='native_event_frames']").text, "30")

    def test_11_2_11_3_incoming_spin_recovery_rejects_mixed_pair(self) -> None:
        with self.assertRaisesRegex(ValueError, "exact 11.2 or 11.3 pair"):
            make_fixture(
                self.inventory, "11.2 Spin ClockWise (1) 15k", "11.3 Spin CounterClockWise (2) 15k",
                Path("first-scene.mp4"), Path("second-scene.mp4"), 30, 3, 320, 180, 60, 1,
                event_frames=30, curve_policy="spin-11-2-11-3-incoming-recovery-v1")


if __name__ == "__main__":
    unittest.main()
