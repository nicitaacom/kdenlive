#!/usr/bin/env python3
"""Tests that per-record curve policies produce the intended native groups."""

from __future__ import annotations

import copy
import json
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from create_supported_chain_fixture import build as build_fixture  # noqa: E402
from generate_native_transition_templates import (apply_record_curve_policy, build_templates)  # noqa: E402


class NativeTransitionTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = json.loads((ROOT / "plans/native-transition-inventory.json").read_text())

    def group(self, tree, exact_name):
        return next(group for group in tree.findall("{https://www.kdenlive.org}effectgroup")
                    if group.findtext("{https://www.kdenlive.org}name") == exact_name)

    def test_render_fixture_applies_the_same_curve_policy_as_the_editable_group(self):
        names = ("1.1 Smooth R to L (1) 10k", "2.7 Scroll Right (2) 20k",
                 "3.3 Slide Down (1) 15k", "10.6 Zoom Out Spin ClockWise (2) 15k",
                 "9.19 ZoomBubble (1) 20k", "9.20 TIMEZOOM (1) 20k",
                 "9.20 TIMEZOOM (2) 20k")
        inventory_records = {record["exact_name"]: record for package in self.inventory["packages"]
                             for record in package["records"]}
        template_tree = ET.fromstring(build_templates(self.inventory))
        ns = "{https://www.kdenlive.org}"
        for name in names:
            record = inventory_records[name]
            fixture = build_fixture(self.inventory, name, Path("/dev/null"), 30,
                                    record["nominal_frames"], 640, 360, 60, 1)
            apply_record_curve_policy(fixture, record)
            fixture_filters = fixture.getroot().find("producer").findall("filter")
            group = self.group(template_tree, name)
            group_effects = group.findall(ns + "effect")
            self.assertEqual(len(fixture_filters), len(group_effects), name)
            for fixture_filter, group_effect in zip(fixture_filters, group_effects):
                fixture_properties = {p.get("name"): p.text for p in fixture_filter.findall("property")}
                template_properties = {p.get("name"): p.text for p in group_effect.findall(ns + "property")}
                fixture_properties.pop("mlt_service")
                for derived in ("native_event_frames", "native_nominal_frames", "native_event_role"):
                    fixture_properties.pop(derived, None)
                self.assertEqual(group_effect.get("id"), fixture_filter.findtext("property[@name='mlt_service']"), name)
                self.assertEqual(template_properties, fixture_properties, name)

    def test_swish3d_clip_local_reconstructions_are_visible_and_caveated(self):
        ns = "{https://www.kdenlive.org}"
        templates = ET.fromstring(build_templates(self.inventory))
        expected = {
            "9.19 ZoomBubble (1) 20k": [
                "kdenlive_motion_curve", "kdenlive_fisheye_warp", "kdenlive_magnify_warp",
                "kdenlive_pinch_punch", "kdenlive_brightness_contrast",
            ],
            "9.20 TIMEZOOM (1) 20k": [
                "kdenlive_motion_curve", "kdenlive_fisheye_warp", "kdenlive_magnify_warp",
                "kdenlive_pinch_punch", "kdenlive_warp_chroma", "kdenlive_brightness_contrast",
            ],
            "9.20 TIMEZOOM (2) 20k": [
                "kdenlive_motion_curve", "kdenlive_fisheye_warp", "kdenlive_magnify_warp",
                "kdenlive_pinch_punch", "kdenlive_warp_chroma", "kdenlive_brightness_contrast",
            ],
        }
        groups = {group.findtext(ns + "name"): group for group in templates.findall(ns + "effectgroup")}
        for name, services in expected.items():
            with self.subTest(name=name):
                group = groups[name]
                self.assertEqual([effect.get("id") for effect in group.findall(ns + "effect")], services)
                description = group.findtext(ns + "description")
                self.assertIn("clip-local native reconstruction", description.lower())
                self.assertIn("two-input blend", description)
                self.assertEqual(group.get("fitToEvent"), "1")

    def test_opticalcom_rows_preserve_bubble_warp_and_disclose_opaque_component(self):
        ns = "{https://www.kdenlive.org}"
        templates = ET.fromstring(build_templates(self.inventory))
        by_name = {group.findtext(ns + "name"): group for group in templates.findall(ns + "effectgroup")}
        pending_tree = ET.parse(ROOT / "data/effects/templates/native_transition_presets.xml").getroot()
        pending = {entry.findtext(ns + "name"): entry for entry in pending_tree.findall(ns + "pendingeffect")}
        expected = {
            "9.23 OpticalCom (1) 20k": ("1.95918367347", "outgoing"),
            "9.23 OpticalCom (2) 20k": ("1.35", "incoming"),
        }
        for name, (amplitude, role) in expected.items():
            with self.subTest(name=name):
                record = next(record for package in self.inventory["packages"] for record in package["records"]
                              if record["exact_name"] == name)
                self.assertEqual(record["status"], "Partial")
                self.assertIn(name, by_name)
                self.assertNotIn(name, pending)
                group = by_name[name]
                self.assertEqual(group.findtext(ns + "category"), "Partial native transition approximations")
                self.assertIn("Partial native reconstruction", group.findtext(ns + "description"))
                self.assertIn("MBL2", group.findtext(ns + "description"))
                fixture = build_fixture(self.inventory, name, Path("/dev/null"), 30,
                                        record["nominal_frames"], 640, 360, 60, 1)
                apply_record_curve_policy(fixture, record)
                effects = fixture.getroot().find("producer").findall("filter")
                self.assertEqual([effect.findtext("property[@name='mlt_service']") for effect in effects],
                                 ["kdenlive_warp_bubble2"])
                properties = {prop.get("name"): prop.text for prop in effects[0].findall("property")}
                curves = json.loads(properties["native_curves"])
                curve_amplitude = curves["a_amplitude"][0][1] if role == "incoming" else float(properties["a_amplitude"])
                self.assertAlmostEqual(curve_amplitude, float(amplitude), places=8)
                exclusion = record["native_reconstruction_exclusions"][0]
                self.assertEqual(exclusion["component_index"], 0)
                self.assertEqual(exclusion["payload_bytes"], 146034)
                review = record["smoothness_review"]["opticalcom_bubble_partial_20261001"]
                self.assertEqual(review["identity_control_max_rgb_mae"], 0.0)
                self.assertEqual(review["final_incoming_rgb_mae"], 0.0)

    def test_candidate_curve_policies_are_scoped_to_their_source_pairs(self):
        candidate_inventory = copy.deepcopy(self.inventory)
        scroll_up_ids = {
            "{8924EE32-9F8C-4BD6-A133-E609D6E00CE8}",
            "{18926235-8042-4D31-B938-5237FF19EAD4}",
        }
        stretch_left_ids = {
            "{639387F3-0594-4FA0-AB1A-C3169A6EBFCB}",
            "{170D89A3-D025-4314-A407-EEA40C18868D}",
        }
        smooth_r_to_l_ids = {
            "{1AD8B510-4D09-4263-BEA1-FA45C59E7594}",
            "{7F0C983A-CA01-48EA-8430-079520B606D5}",
        }
        single_axis_slide_ids = {
            "{1E6B9A79-C7BA-44BF-A18F-8A978C341551}",
            "{E8A2B122-C1D9-4CC5-9144-BD50946E474E}",
        }
        slide_down_33_ids = {
            "{5CA7AF07-AEAC-4DC1-84FF-2ADDE18EDE37}",
            "{6198F889-3A81-4EB9-9064-294B1203958A}",
        }
        scroll_right_27_recovery_id = "{CEFDEE77-588E-4932-9CBD-5D707852264A}"
        scroll_right_27_pair_ids = {
            "{A00199B4-139C-420E-88BE-4189A635B769}",
            scroll_right_27_recovery_id,
        }
        scroll_down_34_recovery_id = "{95BA992E-E4B3-43A3-B4B9-872F2CD9D135}"
        scroll_left_14_outgoing_id = "{A3C456BE-54DE-4FC4-AB4C-8CFD7AA28A72}"
        scroll_left_14_recovery_id = "{286C285F-FCFD-4B86-BD12-398F6E99BC63}"
        scroll_family_recovery_ids = {
            "{7B7CC980-5669-44C9-A142-CE84AFA06957}",
            "{C7810381-0CC1-4888-BFD9-14428DDA5083}",
            "{12F189CB-AACF-47F1-9554-82886B4948D3}",
            "{49DF4B2D-390F-42DE-A52D-112AEF706028}",
            "{44907BDF-F91F-44F9-AE30-916C2E56D2F8}",
        }
        zoom_out_pinch_outgoing_id = "{C5FCEC32-DB49-47AF-9CDF-1580ED35F114}"
        zoom_out_pinch_recovery_id = "{B9BD2DB7-A2A8-4C60-BF31-93DFFDF9EF17}"
        zoom_spin_rsmb_ids = {
            "{93B540EF-2897-4212-8355-BF902EB0B43E}",
            "{E64E63EC-2395-41F9-985A-78CB5169E7E9}",
            "{2187A5C0-E3D7-4C41-A5B4-78CD7F0C7A50}",
        }
        zoom_spin_rsmb_incoming_id = "{9C289FCD-6DE1-4720-A57E-7D90E3A2307A}"
        spin_11_2_11_3_incoming_ids = {
            "{FE94B468-D68F-47F0-A99C-7F1D094D6279}",
            "{9F7C46F0-C4AA-46F0-BB51-A307971D2A19}",
        }
        spin_10_6_incoming_id = "{8251884A-4379-40BE-BBB4-A30EFC673140}"
        slide_right_ids = {
            "{9187509F-FBD1-493A-9C47-C246B8E86612}",
            "{7D4FCD4D-098C-4B7F-9302-3C04BECE3D70}",
            "{18709A02-705F-4E45-B4B7-E1D01EA36578}",
            "{80972334-1476-4E39-8F92-D515A72D12DE}",
            "{32933C16-A0F7-4BA7-87C2-83378F812014}",
            "{3C80FF58-684A-476F-B8F9-2170AB1A77B3}",
            "{1C375766-13C4-4AB1-B044-1D2103E82D55}",
            "{3C973FB1-C25B-4B6A-99BB-B4D289C81C99}",
            "{1C20987B-0546-4100-A634-2268B44980E1}",
            "{5AB3CCDD-8390-4134-963C-AF4A690084C8}",
            "{7F7933E8-BC6C-47A3-9826-C98A683D853F}",
            "{B177025D-7CA9-4697-A7F2-E14A2B3CA9EC}",
        }
        target_ids = scroll_up_ids | stretch_left_ids
        target_names = {"4.3 Scroll Up (1) 20k", "4.3 Scroll Up (2) 20k"}
        policy_records = [record for package in candidate_inventory["packages"]
                          for record in package["records"] if record.get("native_curve_policy")
                          and record["status"] in ("Implemented", "Equivalent", "Partial")]
        self.assertEqual({record["source_identifier"] for record in policy_records},
                         target_ids | smooth_r_to_l_ids | slide_right_ids | single_axis_slide_ids | slide_down_33_ids
                         | {scroll_right_27_recovery_id, scroll_down_34_recovery_id,
                            scroll_left_14_outgoing_id, scroll_left_14_recovery_id} | scroll_family_recovery_ids
                         | {zoom_out_pinch_outgoing_id, zoom_out_pinch_recovery_id}
                         | zoom_spin_rsmb_ids | {zoom_spin_rsmb_incoming_id}
                         | {"{10047522-1160-432F-883B-7B445D3B945F}", "{3DB970A1-D364-4360-AAB7-773304EE7CB8}"}
                         | spin_11_2_11_3_incoming_ids | scroll_right_27_pair_ids
                         | {spin_10_6_incoming_id})
        self.assertEqual({record["source_identifier"] for record in policy_records
                          if record["native_curve_policy"] == "zoom-spin-rsmb-monotone-cubic-v1"},
                         zoom_spin_rsmb_ids)
        self.assertEqual({record["source_identifier"] for record in policy_records
                          if record["native_curve_policy"] == "zoom-spin-rsmb-incoming-ease-out-v1"},
                         {zoom_spin_rsmb_incoming_id})
        self.assertEqual({record["source_identifier"] for record in policy_records
                          if record["native_curve_policy"] == "spin-11-2-11-3-incoming-recovery-v1"},
                         spin_11_2_11_3_incoming_ids)
        self.assertEqual({record["source_identifier"] for record in policy_records
                          if record["native_curve_policy"] == "spin-10-6-incoming-eventwide-v1"},
                         {spin_10_6_incoming_id})
        self.assertEqual({record["source_identifier"] for record in policy_records
                          if record["native_curve_policy"] == "whole-event-smoothstep-linear-floor-v1"},
                         scroll_up_ids)
        self.assertEqual({record["source_identifier"] for record in policy_records
                          if record["native_curve_policy"] == "whole-event-endpoint-preserving-smoothstep40-v1"},
                         stretch_left_ids)
        self.assertEqual({record["source_identifier"] for record in policy_records
                          if record["native_curve_policy"] == "smooth-r-to-l-role-ease-v1"},
                         smooth_r_to_l_ids)
        self.assertEqual({record["source_identifier"] for record in policy_records
                          if record["native_curve_policy"] == "slide-right-cut-acceleration-v1"},
                         slide_right_ids)
        self.assertEqual({record["source_identifier"] for record in policy_records
                          if record["native_curve_policy"] == "single-axis-slide-cut-acceleration-v2"},
                         single_axis_slide_ids)
        self.assertEqual({record["source_identifier"] for record in policy_records
                          if record["native_curve_policy"] == "slide-down-33-cut-peak-v1"},
                         slide_down_33_ids)
        self.assertEqual({record["source_identifier"] for record in policy_records
                          if record["native_curve_policy"] == "scroll-right-27-incoming-recovery-v1"},
                         set())
        self.assertEqual({record["source_identifier"] for record in policy_records
                          if record["native_curve_policy"] == "scroll-right-27-cut-peak-ease-out-v2"},
                         scroll_right_27_pair_ids)
        self.assertEqual({record["source_identifier"] for record in policy_records
                          if record["native_curve_policy"] == "scroll-down-34-incoming-recovery-v1"},
                         {scroll_down_34_recovery_id})
        self.assertEqual({record["source_identifier"] for record in policy_records
                          if record["native_curve_policy"] == "scroll-left-14-outgoing-shift-fit-v1"},
                         {scroll_left_14_outgoing_id})
        self.assertEqual({record["source_identifier"] for record in policy_records
                          if record["native_curve_policy"] == "scroll-left-14-incoming-recovery-v1"},
                         {scroll_left_14_recovery_id})
        self.assertEqual({record["source_identifier"] for record in policy_records
                          if record["native_curve_policy"] == "scroll-family-incoming-recovery-v1"},
                         scroll_family_recovery_ids)
        self.assertEqual({record["source_identifier"] for record in policy_records
                          if record["native_curve_policy"] == "zoom-out-10-5-incoming-ease-out-v1"},
                         {zoom_out_pinch_recovery_id})
        self.assertEqual({record["source_identifier"] for record in policy_records
                          if record["native_curve_policy"] == "zoom-out-10-5-outgoing-monotone-cubic-v1"},
                         {zoom_out_pinch_outgoing_id})
        baseline_inventory = copy.deepcopy(candidate_inventory)
        for package in baseline_inventory["packages"]:
            for record in package["records"]:
                record.pop("native_curve_policy", None)

        policy_ids = {record["source_identifier"]
                      for package in candidate_inventory["packages"]
                      for record in package["records"]
                      if record.get("native_curve_policy") == "whole-event-smoothstep-linear-floor-v1"}
        self.assertEqual(policy_ids, scroll_up_ids)

        candidate_tree = ET.fromstring(build_templates(candidate_inventory))
        baseline_tree = ET.fromstring(build_templates(baseline_inventory))

        for exact_name in target_names:
            candidate = self.group(candidate_tree, exact_name)
            baseline = self.group(baseline_tree, exact_name)
            self.assertEqual(candidate.attrib["sourceId"], baseline.attrib["sourceId"])
            self.assertEqual(candidate.attrib["transitionRole"], baseline.attrib["transitionRole"])
            self.assertIn("p(t)=0.35t+0.65", candidate.findtext("{https://www.kdenlive.org}description"))
            self.assertIn("Intermediate source keys are not preserved", candidate.findtext("{https://www.kdenlive.org}description"))
            self.assertNotIn("Intermediate source keys are not preserved", baseline.findtext("{https://www.kdenlive.org}description"))
            candidate_curves = [json.loads(effect.findtext("{https://www.kdenlive.org}property[@name='native_curves']"))
                                for effect in candidate.findall("{https://www.kdenlive.org}effect")]
            baseline_curves = [json.loads(effect.findtext("{https://www.kdenlive.org}property[@name='native_curves']"))
                               for effect in baseline.findall("{https://www.kdenlive.org}effect")]
            self.assertEqual(len(candidate_curves), len(baseline_curves))
            self.assertTrue(any(curve for curves in candidate_curves for curve in curves.values()))
            for curves in candidate_curves:
                for points in curves.values():
                    self.assertEqual(len(points), 2)
                    self.assertEqual(points[0][0], 0.0)
                    self.assertEqual(points[-1][0], 1.0)
                    self.assertEqual((points[0][2], points[0][4]), (0.0, 1.0 / 3.0))
                    self.assertEqual((points[-1][2], points[-1][4]), (2.0 / 3.0, 1.0))

        # An unrelated active preset is byte-for-byte equivalent at the group level.
        unchanged_candidate = self.group(candidate_tree, "1.2 Slide Left (1) 15k")
        unchanged_baseline = self.group(baseline_tree, "1.2 Slide Left (1) 15k")
        self.assertEqual(ET.tostring(unchanged_candidate), ET.tostring(unchanged_baseline))

    def test_scroll_right_27_incoming_recovery_uses_full_eased_event(self):
        source_id = "{CEFDEE77-588E-4932-9CBD-5D707852264A}"
        candidate_inventory = copy.deepcopy(self.inventory)
        incoming_record = next(record for package in candidate_inventory["packages"]
                               for record in package["records"]
                               if record["source_identifier"] == source_id)
        self.assertEqual(incoming_record["exact_name"], "2.7 Scroll Right (2) 20k")
        self.assertEqual(incoming_record["event_variant"], "incoming")
        incoming_record["native_curve_policy"] = "scroll-right-27-incoming-recovery-v1"
        baseline_inventory = copy.deepcopy(candidate_inventory)
        baseline_record = next(record for package in baseline_inventory["packages"]
                               for record in package["records"]
                               if record["source_identifier"] == source_id)
        baseline_record.pop("native_curve_policy")

        candidate_tree = ET.fromstring(build_templates(candidate_inventory))
        baseline_tree = ET.fromstring(build_templates(baseline_inventory))
        candidate = self.group(candidate_tree, "2.7 Scroll Right (2) 20k")
        baseline = self.group(baseline_tree, "2.7 Scroll Right (2) 20k")
        self.assertEqual(candidate.attrib["sourceId"], source_id)
        self.assertEqual(candidate.attrib["transitionRole"], "in")
        self.assertIn("full event", candidate.findtext("{https://www.kdenlive.org}description"))
        self.assertIn("50% linear-floor", candidate.findtext("{https://www.kdenlive.org}description"))

        namespace = "{https://www.kdenlive.org}"
        candidate_effects = candidate.findall(namespace + "effect")
        baseline_effects = baseline.findall(namespace + "effect")
        self.assertEqual([effect.attrib["id"] for effect in candidate_effects],
                         [effect.attrib["id"] for effect in baseline_effects])
        source_value_paths = {}
        fitted_paths = {}
        for effect in baseline_effects:
            curves = json.loads(effect.findtext(namespace + "property[@name='native_curves']"))
            source_value_paths.update({(effect.attrib["id"], name): [point[1] for point in points]
                                       for name, points in curves.items()})
        for effect in candidate_effects:
            curves = json.loads(effect.findtext(namespace + "property[@name='native_curves']"))
            for name, points in curves.items():
                self.assertEqual(points[0][0], 0.0)
                self.assertEqual(points[-1][0], 1.0)
                self.assertTrue(all(point[6] in (0, 1) for point in points))
                fitted_paths[(effect.attrib["id"], name)] = [point[0] for point in points]
                if effect.attrib["id"] == "kdenlive_motion_curve" and name == "shutter_duration":
                    self.assertEqual([point[1] for point in points], [1.0, 0.0])
                    continue
                self.assertEqual([point[1] for point in points],
                                 source_value_paths[(effect.attrib["id"], name)])
        self.assertAlmostEqual(fitted_paths[("kdenlive_motion_curve", "shift_x")][1],
                               0.28579447286604037 / 0.5239565335877407)
        self.assertEqual(fitted_paths[("kdenlive_motion_curve", "shift_x")][-1], 1.0)
        self.assertEqual(fitted_paths[("kdenlive_fisheye_warp", "amount")][-1], 1.0)
        # The outgoing partner remains on its source-derived timing.
        outgoing_candidate = self.group(candidate_tree, "2.7 Scroll Right (1) 20k")
        outgoing_baseline = self.group(baseline_tree, "2.7 Scroll Right (1) 20k")
        self.assertEqual(ET.tostring(outgoing_candidate), ET.tostring(outgoing_baseline))

    def test_10_6_incoming_policy_retimes_decoded_endpoints_without_losing_source_keys(self):
        record = next(record for package in self.inventory["packages"]
                      for record in package["records"]
                      if record["source_identifier"] == "{8251884A-4379-40BE-BBB4-A30EFC673140}")
        self.assertEqual(record["native_curve_policy"], "spin-10-6-incoming-eventwide-v1")
        source_positions = {
            parameter["name"]: [key["normalized_event_position"]
                                for key in parameter["animation"]["points"]]
            for component in record["components"]
            for parameter in component["parameters"]
            if parameter["name"] in ("Z Dist", "Rotate", "Shutter Duration")
        }
        self.assertTrue(all(any(position > 0.75 for position in positions)
                            for positions in source_positions.values()))

        templates = ET.fromstring(build_templates(self.inventory))
        group = self.group(templates, record["exact_name"])
        motion = group.find("{https://www.kdenlive.org}effect")
        native_curves = json.loads(
            motion.findtext("{https://www.kdenlive.org}property[@name='native_curves']"))
        for name, endpoints in {
                "z_distance": (0.5, 1.0),
                "rotation": (45.0, 0.0),
                "shutter_duration": (1.5, 1.0),
        }.items():
            with self.subTest(curve=name):
                points = native_curves[name]
                self.assertEqual((points[0][0], points[-1][0]), (0.0, 1.0))
                self.assertEqual((points[0][1], points[-1][1]), endpoints)

    def test_scroll_down_34_incoming_recovery_tapers_native_shake_and_shutter(self):
        source_id = "{95BA992E-E4B3-43A3-B4B9-872F2CD9D135}"
        candidate_inventory = copy.deepcopy(self.inventory)
        incoming_record = next(record for package in candidate_inventory["packages"]
                               for record in package["records"]
                               if record["source_identifier"] == source_id)
        self.assertEqual(incoming_record["exact_name"], "3.4 Scroll Down (2) 20k")
        self.assertEqual(incoming_record["event_variant"], "incoming")
        incoming_record["native_curve_policy"] = "scroll-down-34-incoming-recovery-v1"
        baseline_inventory = copy.deepcopy(candidate_inventory)
        baseline_record = next(record for package in baseline_inventory["packages"]
                               for record in package["records"]
                               if record["source_identifier"] == source_id)
        baseline_record.pop("native_curve_policy")

        candidate_tree = ET.fromstring(build_templates(candidate_inventory))
        baseline_tree = ET.fromstring(build_templates(baseline_inventory))
        candidate = self.group(candidate_tree, "3.4 Scroll Down (2) 20k")
        baseline = self.group(baseline_tree, "3.4 Scroll Down (2) 20k")
        outgoing_candidate = self.group(candidate_tree, "3.4 Scroll Down (1) 20k")
        outgoing_baseline = self.group(baseline_tree, "3.4 Scroll Down (1) 20k")
        self.assertEqual(candidate.attrib["sourceId"], source_id)
        self.assertEqual(candidate.attrib["transitionRole"], "in")
        self.assertEqual(ET.tostring(outgoing_candidate), ET.tostring(outgoing_baseline))
        self.assertIn("taper smoothly", candidate.findtext("{https://www.kdenlive.org}description"))
        self.assertIn("not decoded Sapphire animation", candidate.findtext("{https://www.kdenlive.org}description"))

        ns = "{https://www.kdenlive.org}"
        effects = {effect.attrib["id"]: effect for effect in candidate.findall(ns + "effect")}
        baseline_effects = {effect.attrib["id"]: effect for effect in baseline.findall(ns + "effect")}
        motion_curves = json.loads(effects["kdenlive_motion_curve"].findtext(ns + "property[@name='native_curves']"))
        baseline_motion = json.loads(baseline_effects["kdenlive_motion_curve"].findtext(ns + "property[@name='native_curves']"))
        self.assertEqual([point[1] for point in motion_curves["shift_y"]],
                         [point[1] for point in baseline_motion["shift_y"]])
        self.assertLess(baseline_motion["shift_y"][-1][0], 1.0)
        self.assertEqual(motion_curves["shift_y"][-1][0], 1.0)
        self.assertEqual([point[1] for point in motion_curves["shutter_duration"]], [1.0, 0.0])
        self.assertEqual(motion_curves["shutter_duration"][-1][0], 1.0)

        shake_curves = json.loads(effects["kdenlive_shake"].findtext(ns + "property[@name='native_curves']"))
        baseline_shake = json.loads(baseline_effects["kdenlive_shake"].findtext(ns + "property[@name='native_curves']"))
        source_amplitude = baseline_shake["amplitude"][0][1]
        self.assertEqual([point[1] for point in shake_curves["amplitude"]], [source_amplitude, 0.0])
        self.assertEqual(shake_curves["amplitude"][-1][0], 1.0)

    def test_scroll_left_14_incoming_recovery_fits_early_shift_and_shutter(self):
        source_id = "{286C285F-FCFD-4B86-BD12-398F6E99BC63}"
        candidate_inventory = copy.deepcopy(self.inventory)
        incoming_record = next(record for package in candidate_inventory["packages"]
                               for record in package["records"]
                               if record["source_identifier"] == source_id)
        self.assertEqual(incoming_record["exact_name"], "1.4 Scroll Left (2) 20k")
        self.assertEqual(incoming_record["event_variant"], "incoming")
        incoming_record["native_curve_policy"] = "scroll-left-14-incoming-recovery-v1"
        baseline_inventory = copy.deepcopy(candidate_inventory)
        baseline_record = next(record for package in baseline_inventory["packages"]
                               for record in package["records"]
                               if record["source_identifier"] == source_id)
        baseline_record.pop("native_curve_policy")
        candidate_tree = ET.fromstring(build_templates(candidate_inventory))
        baseline_tree = ET.fromstring(build_templates(baseline_inventory))
        candidate = self.group(candidate_tree, "1.4 Scroll Left (2) 20k")
        baseline = self.group(baseline_tree, "1.4 Scroll Left (2) 20k")
        self.assertEqual(candidate.attrib["sourceId"], source_id)
        self.assertEqual(candidate.attrib["transitionRole"], "in")
        self.assertIn("reaches neutral at 60%", candidate.findtext("{https://www.kdenlive.org}description"))
        ns = "{https://www.kdenlive.org}"
        cand_effects = {effect.attrib["id"]: effect for effect in candidate.findall(ns + "effect")}
        base_effects = {effect.attrib["id"]: effect for effect in baseline.findall(ns + "effect")}
        motion_curves = json.loads(cand_effects["kdenlive_motion_curve"].findtext(ns + "property[@name='native_curves']"))
        base_motion = json.loads(base_effects["kdenlive_motion_curve"].findtext(ns + "property[@name='native_curves']"))
        self.assertEqual([point[1] for point in motion_curves["shift_x"]],
                         [point[1] for point in base_motion["shift_x"]])
        self.assertLess(base_motion["shift_x"][-1][0], 1.0)
        self.assertEqual(motion_curves["shift_x"][-1][0], 1.0)
        self.assertEqual([point[1] for point in motion_curves["shutter_duration"]], [1.0, 0.0])
        shake = json.loads(cand_effects["kdenlive_shake"].findtext(ns + "property[@name='native_curves']"))
        self.assertEqual(shake["amplitude"][-1][1], 0.0)
        self.assertEqual(shake["amplitude"][-1][0], 1.0)

    def test_scroll_right_27_cut_peak_preserves_chain_and_exposes_editable_blur_controls(self):
        names = {
            "{A00199B4-139C-420E-88BE-4189A635B769}": "2.7 Scroll Right (1) 20k",
            "{CEFDEE77-588E-4932-9CBD-5D707852264A}": "2.7 Scroll Right (2) 20k",
        }
        candidate_inventory = copy.deepcopy(self.inventory)
        records = {record["source_identifier"]: record
                   for package in candidate_inventory["packages"] for record in package["records"]}
        for source_id, exact_name in names.items():
            self.assertEqual(records[source_id]["exact_name"], exact_name)
            records[source_id]["native_curve_policy"] = "scroll-right-27-cut-peak-v1"
        candidate_tree = ET.fromstring(build_templates(candidate_inventory))
        ns = "{https://www.kdenlive.org}"
        expected_services = {
            "2.7 Scroll Right (1) 20k": ["kdenlive_motion_curve", "kdenlive_fisheye_warp"],
            "2.7 Scroll Right (2) 20k": ["kdenlive_motion_curve", "kdenlive_shake", "kdenlive_fisheye_warp"],
        }
        expected_roles = {"2.7 Scroll Right (1) 20k": "out", "2.7 Scroll Right (2) 20k": "in"}
        expected_gains = {"2.7 Scroll Right (1) 20k": "8", "2.7 Scroll Right (2) 20k": "16"}
        for exact_name in names.values():
            group = self.group(candidate_tree, exact_name)
            self.assertEqual(group.attrib["transitionRole"], expected_roles[exact_name])
            effects = group.findall(ns + "effect")
            self.assertEqual([effect.attrib["id"] for effect in effects], expected_services[exact_name])
            self.assertIn("visual-fit settings", group.findtext(ns + "description"))
            motion = effects[0]
            properties = {prop.attrib["name"]: prop.text for prop in motion.findall(ns + "property")}
            self.assertEqual(properties["shutter_gain_adjust"], expected_gains[exact_name])
            self.assertEqual(properties["quality_samples"], "32")
            curves = json.loads(properties["native_curves"])
            self.assertTrue(all(points[0][0] == 0.0 and points[-1][0] == 1.0
                                for points in curves.values()))
            self.assertEqual([point[1] for point in curves["shutter_duration"]],
                             [0.0, 1.0] if expected_roles[exact_name] == "out" else [1.0, 0.0])

    def test_scroll_right_27_cut_peak_rejects_other_record_identity(self):
        candidate_inventory = copy.deepcopy(self.inventory)
        wrong_record = next(record for package in candidate_inventory["packages"]
                            for record in package["records"]
                            if record["exact_name"] == "2.8 Scroll Right (2) 45k")
        wrong_record["native_curve_policy"] = "scroll-right-27-cut-peak-v1"
        with self.assertRaisesRegex(ValueError, "exact 2.7 Scroll Right"):
            build_templates(candidate_inventory)

    def test_scroll_left_14_outgoing_fit_preserves_shift_values_and_fills_event(self):
        source_id = "{A3C456BE-54DE-4FC4-AB4C-8CFD7AA28A72}"
        candidate_inventory = copy.deepcopy(self.inventory)
        outgoing_record = next(record for package in candidate_inventory["packages"]
                               for record in package["records"]
                               if record["source_identifier"] == source_id)
        self.assertEqual(outgoing_record["exact_name"], "1.4 Scroll Left (1) 20k")
        self.assertEqual(outgoing_record["event_variant"], "outgoing")
        outgoing_record["native_curve_policy"] = "scroll-left-14-outgoing-shift-fit-v1"
        candidate_tree = ET.fromstring(build_templates(candidate_inventory))
        candidate = self.group(candidate_tree, outgoing_record["exact_name"])
        self.assertEqual(candidate.attrib["sourceId"], source_id)
        self.assertEqual(candidate.attrib["transitionRole"], "out")
        self.assertIn("idle interval before Shift X begins",
                      candidate.findtext("{https://www.kdenlive.org}description"))
        motion = next(effect for effect in candidate.findall("{https://www.kdenlive.org}effect")
                      if effect.attrib["id"] == "kdenlive_motion_curve")
        curves = json.loads(motion.findtext("{https://www.kdenlive.org}property[@name='native_curves']"))
        self.assertAlmostEqual(curves["shift_x"][0][0], 0.0490, places=3)
        self.assertAlmostEqual(curves["shift_x"][1][0], 0.1250, places=3)
        self.assertEqual(curves["shift_x"][2][0], 1.0)
        self.assertEqual([point[1] for point in curves["shift_x"]], [0.0, -0.2, 5.0])

    def test_scroll_family_recovery_is_limited_to_three_source_ids_and_preserves_values(self):
        candidate_inventory = copy.deepcopy(self.inventory)
        names = {
            "1.6 Scroll Left (2) 45k": "{7B7CC980-5669-44C9-A142-CE84AFA06957}",
            "2.8 Scroll Right (2) 45k": "{C7810381-0CC1-4888-BFD9-14428DDA5083}",
            "3.5 Scroll Down (2) 45k": "{12F189CB-AACF-47F1-9554-82886B4948D3}",
            "5.3 Scroll Bottom Left (2) 45k": "{49DF4B2D-390F-42DE-A52D-112AEF706028}",
            "7.3 Scroll Bottom Right (2) 45k": "{44907BDF-F91F-44F9-AE30-916C2E56D2F8}",
        }
        for package in candidate_inventory["packages"]:
            for record in package["records"]:
                if record["source_identifier"] in names.values():
                    record["native_curve_policy"] = "scroll-family-incoming-recovery-v1"
        baseline_inventory = copy.deepcopy(candidate_inventory)
        for package in baseline_inventory["packages"]:
            for record in package["records"]:
                if record["source_identifier"] in names.values():
                    record.pop("native_curve_policy")
        candidate_tree = ET.fromstring(build_templates(candidate_inventory))
        baseline_tree = ET.fromstring(build_templates(baseline_inventory))
        ns = "{https://www.kdenlive.org}"
        for name, source_id in names.items():
            candidate = self.group(candidate_tree, name)
            baseline = self.group(baseline_tree, name)
            self.assertEqual(candidate.attrib["sourceId"], source_id)
            self.assertEqual(candidate.attrib["transitionRole"], "in")
            self.assertIn("retimed across the full event", candidate.findtext(ns + "description"))
            candidate_effects = {effect.attrib["id"]: effect for effect in candidate.findall(ns + "effect")}
            baseline_effects = {effect.attrib["id"]: effect for effect in baseline.findall(ns + "effect")}
            self.assertEqual(list(candidate_effects), list(baseline_effects))
            motion = json.loads(candidate_effects["kdenlive_motion_curve"].findtext(ns + "property[@name='native_curves']"))
            source_motion = json.loads(baseline_effects["kdenlive_motion_curve"].findtext(ns + "property[@name='native_curves']"))
            for axis in ("shift_x", "shift_y"):
                if axis in source_motion:
                    self.assertEqual([point[1] for point in motion[axis]],
                                     [point[1] for point in source_motion[axis]])
                    self.assertEqual(motion[axis][-1][0], 1.0)
            self.assertEqual(motion["shutter_duration"][-1][0], 1.0)
            self.assertEqual(motion["shutter_duration"][-1][1], 0.0)
            for effect_id, effect in candidate_effects.items():
                curves = json.loads(effect.findtext(ns + "property[@name='native_curves']"))
                source_curves = json.loads(baseline_effects[effect_id].findtext(ns + "property[@name='native_curves']"))
                for parameter, points in curves.items():
                    self.assertEqual(points[-1][0], 1.0, (name, effect_id, parameter))
                    if parameter == "shutter_duration":
                        continue
                    self.assertEqual([point[1] for point in points],
                                     [point[1] for point in source_curves[parameter]],
                                     (name, effect_id, parameter))

    def test_slide_right_cut_acceleration_preserves_x_only_source_chains_and_controls(self):
        candidate_inventory = copy.deepcopy(self.inventory)
        names = {
            "2.1 Slide Right (1) 10k": "{9187509F-FBD1-493A-9C47-C246B8E86612}",
            "2.1 Slide Right (2) 10k": "{7D4FCD4D-098C-4B7F-9302-3C04BECE3D70}",
            "2.2 Slide Right (1) 15k": "{18709A02-705F-4E45-B4B7-E1D01EA36578}",
            "2.2 Slide Right (2) 15k": "{80972334-1476-4E39-8F92-D515A72D12DE}",
            "2.3 Slide Right (1) 15k": "{32933C16-A0F7-4BA7-87C2-83378F812014}",
            "2.3 Slide Right (2) 15k": "{3C80FF58-684A-476F-B8F9-2170AB1A77B3}",
            "2.4 Slide Right (1) 15k": "{1C375766-13C4-4AB1-B044-1D2103E82D55}",
            "2.4 Slide Right (2) 15k": "{3C973FB1-C25B-4B6A-99BB-B4D289C81C99}",
            "2.5 Slide Right (1) 15k": "{1C20987B-0546-4100-A634-2268B44980E1}",
            "2.5 Slide Right (2) 15k": "{5AB3CCDD-8390-4134-963C-AF4A690084C8}",
            "2.6 Slide Right (1) 15k": "{7F7933E8-BC6C-47A3-9826-C98A683D853F}",
            "2.6 Slide Right (2) 15k": "{B177025D-7CA9-4697-A7F2-E14A2B3CA9EC}",
        }
        for package in candidate_inventory["packages"]:
            for record in package["records"]:
                if record["exact_name"] in names:
                    record["native_curve_policy"] = "slide-right-cut-acceleration-v1"
        tree = ET.fromstring(build_templates(candidate_inventory))
        ns = "{https://www.kdenlive.org}"
        records = {record["exact_name"]: record
                   for package in candidate_inventory["packages"]
                   for record in package["records"]}
        for name, source_id in names.items():
            group = self.group(tree, name)
            self.assertEqual(group.attrib["sourceId"], source_id)
            expected_role = "out" if "(1)" in name else "in"
            self.assertEqual(group.attrib["transitionRole"], expected_role)
            effects = group.findall(ns + "effect")
            expected_components = [component["service"]
                                   for component in records[name]["native_component_mapping"]]
            for addition in records[name].get("native_reconstruction_additions", []):
                insert_before = addition.get("insert_before_service")
                if insert_before:
                    expected_components.insert(expected_components.index(insert_before), addition["service"])
                else:
                    expected_components.append(addition["service"])
            self.assertEqual([effect.attrib["id"] for effect in effects], expected_components)
            motion_effect = next(effect for effect in effects
                                 if effect.attrib["id"] == "kdenlive_motion_curve")
            motion_props = {prop.attrib["name"]: prop.text
                            for prop in motion_effect.findall(ns + "property")}
            motion_curves = json.loads(motion_props["native_curves"])
            self.assertEqual(motion_props["quality_samples"], "16")
            role = "outgoing" if expected_role == "out" else "incoming"
            if "shutter_duration" in motion_curves:
                self.assertEqual((motion_curves["shutter_duration"][0][1],
                                  motion_curves["shutter_duration"][-1][1]),
                                 (1.0, 1.5) if role == "outgoing" else (1.5, 1.0))
            else:
                self.assertAlmostEqual(float(motion_props["shutter_duration"]),
                                       1.8775510204081634 if role == "outgoing"
                                       else 1.9047619047619047)
            self.assertEqual((motion_curves["shutter_envelope"][0][1],
                              motion_curves["shutter_envelope"][-1][1]),
                             (0.0, 1.0) if role == "outgoing" else (1.0, 0.0))
            self.assertEqual(motion_props["shutter_gain_adjust"], "8.0")
            vector_effect = next((effect for effect in effects
                                  if effect.attrib["id"] == "kdenlive_motion_vector_blur"), None)
            if vector_effect is not None:
                vector_props = {prop.attrib["name"]: prop.text
                                for prop in vector_effect.findall(ns + "property")}
                vector_curves = json.loads(vector_props["native_curves"])
                self.assertEqual(vector_curves["blur_envelope"], motion_curves["shutter_envelope"])
                self.assertEqual(vector_props["blur_envelope_adjust"], "1")
            else:
                self.assertEqual([effect.attrib["id"] for effect in effects],
                                 ["kdenlive_motion_curve"])
            description = group.findtext(ns + "description")
            self.assertIn("gain of 8", description)
            self.assertIn("Source interpolation remains unresolved", description)
            self.assertIn("No extra sinusoidal warp is added", description)
            self.assertNotIn("Additional native visual reconstruction", description)
            self.assertNotIn("wave displacement", description.lower())

    def test_single_axis_cut_acceleration_preserves_slide_down_y_curves(self):
        candidate_inventory = copy.deepcopy(self.inventory)
        identifiers = {
            "{1E6B9A79-C7BA-44BF-A18F-8A978C341551}",
            "{E8A2B122-C1D9-4CC5-9144-BD50946E474E}",
        }
        for package in candidate_inventory["packages"]:
            for record in package["records"]:
                if record["source_identifier"] in identifiers:
                    record["native_curve_policy"] = "single-axis-slide-cut-acceleration-v2"

        tree = ET.fromstring(build_templates(candidate_inventory))
        ns = "{https://www.kdenlive.org}"
        for name, source_id, role, endpoints in (
                ("3.1 Slide Down (1) 10k", "{1E6B9A79-C7BA-44BF-A18F-8A978C341551}", "out", (0.0, -0.5)),
                ("3.1 Slide Down (2) 10k", "{E8A2B122-C1D9-4CC5-9144-BD50946E474E}", "in", (0.5, 0.0))):
            group = self.group(tree, name)
            self.assertEqual(group.attrib["sourceId"], source_id)
            self.assertEqual(group.attrib["transitionRole"], role)
            effect = group.find(ns + "effect")
            self.assertEqual(effect.attrib["id"], "kdenlive_motion_curve")
            props = {item.attrib["name"]: item.text for item in effect.findall(ns + "property")}
            curves = json.loads(props["native_curves"])
            self.assertIn("shift_y", curves)
            self.assertNotIn("shift_x", curves)
            self.assertEqual((curves["shift_y"][0][1], curves["shift_y"][-1][1]), endpoints)
            self.assertEqual(props["quality_samples"], "16")
            self.assertEqual((curves["shutter_envelope"][0][1],
                              curves["shutter_envelope"][-1][1]),
                             (0.0, 1.0) if role == "out" else (1.0, 0.0))
            if role == "in":
                # The floor keeps the last fitted parameter step above the
                # subpixel tail that produced an identical 60 fps grid frame.
                self.assertAlmostEqual(curves["shift_y"][-1][3], 0.025)
            self.assertIn("single-axis translation", group.findtext(ns + "description"))
        self.assertIn("15% linear velocity floor", self.group(tree, "3.1 Slide Down (2) 10k").findtext(ns + "description"))

    def test_scroll_up_smoothstep_candidate_is_eased_at_inclusive_event_frames(self):
        tree = ET.fromstring(build_templates(self.inventory))
        ns = "{https://www.kdenlive.org}"
        expected_names = {
            "4.3 Scroll Up (1) 20k": "out",
            "4.3 Scroll Up (2) 20k": "in",
        }

        def cubic(y0, y1, y2, y3, t):
            one_minus = 1.0 - t
            return (one_minus**3 * y0 + 3 * one_minus**2 * t * y1
                    + 3 * one_minus * t**2 * y2 + t**3 * y3)

        def profile(t):
            return 0.35 * t + 0.65 * (3 * t**2 - 2 * t**3)

        for name, role in expected_names.items():
            group = self.group(tree, name)
            self.assertEqual(group.attrib["transitionRole"], role)
            effects = group.findall(f"{ns}effect")
            self.assertGreaterEqual(len(effects), 2)
            animated_curves = []
            for effect in effects:
                prop = effect.find(f"{ns}property[@name='native_curves']")
                curves = json.loads(prop.text)
                for parameter, points in curves.items():
                    self.assertEqual(len(points), 2, (name, parameter))
                    self.assertEqual(points[0][0], 0.0)
                    self.assertEqual(points[-1][0], 1.0)
                    self.assertAlmostEqual(points[0][4], 1.0 / 3.0)
                    self.assertAlmostEqual(points[-1][2], 2.0 / 3.0)
                    animated_curves.append((parameter, points))

            self.assertTrue(animated_curves, name)
            for parameter, points in animated_curves:
                start, end = points[0][1], points[-1][1]
                self.assertNotEqual(start, end, (name, parameter))
                values_by_duration = {}
                for duration in (15, 62, 63):
                    values = []
                    for frame in range(duration):
                        t = frame / (duration - 1)
                        value = cubic(start, points[0][5], points[-1][3], end, t)
                        expected = start + (end - start) * profile(t)
                        self.assertAlmostEqual(value, expected, places=10,
                                               msg=f"{name} {parameter} frame {frame}/{duration}")
                        values.append(value)
                    normalized = [(value - start) / (end - start) for value in values]
                    self.assertEqual(normalized[0], 0.0)
                    self.assertAlmostEqual(normalized[-1], 1.0)
                    self.assertTrue(all(a < b for a, b in zip(normalized, normalized[1:])),
                                    (name, parameter, duration))
                    increments = [b - a for a, b in zip(normalized, normalized[1:])]
                    self.assertLess(increments[0], max(increments))
                    self.assertLess(increments[-1], max(increments))
                    values_by_duration[duration] = normalized
            self.assertEqual(len(values_by_duration[62]), 62)
            self.assertEqual(len(values_by_duration[63]), 63)

        # The package's complete decoded curves remain the inventory source of
        # truth even though this tested native candidate keeps only endpoints.
        incoming_record = next(record for package in self.inventory["packages"]
                               for record in package["records"]
                               if record["source_identifier"] ==
                               "{18926235-8042-4D31-B938-5237FF19EAD4}")
        decoded_shift_y = next(parameter for component in incoming_record["components"]
                               for parameter in component.get("parameters", [])
                               if parameter.get("name") == "Shift Y")
        self.assertEqual(len(decoded_shift_y["animation"]["points"]), 3)

    def test_smooth_r_to_l_candidate_preserves_source_id_and_expected_role_curves(self):
        candidate_tree = ET.fromstring(build_templates(self.inventory))
        ns = "{https://www.kdenlive.org}"
        outgoing = self.group(candidate_tree, "1.1 Smooth R to L (1) 10k")
        incoming = self.group(candidate_tree, "1.1 Smooth R to L (2) 10k")
        self.assertEqual(outgoing.attrib["sourceId"], "{1AD8B510-4D09-4263-BEA1-FA45C59E7594}")
        self.assertEqual(outgoing.attrib["transitionRole"], "out")
        self.assertEqual(incoming.attrib["sourceId"], "{7F0C983A-CA01-48EA-8430-079520B606D5}")
        self.assertEqual(incoming.attrib["transitionRole"], "in")

        def effect_curves(group, service):
            effect = next(effect for effect in group.findall(ns + "effect") if effect.attrib["id"] == service)
            prop = effect.find(ns + "property[@name='native_curves']")
            return json.loads(prop.text)

        outgoing_curves = effect_curves(outgoing, "kdenlive_motion_curve")
        self.assertEqual([outgoing_curves["shift_x"][0][0], outgoing_curves["shift_x"][0][1]], [0.0, 0.0])
        self.assertEqual([outgoing_curves["shift_x"][-1][0], outgoing_curves["shift_x"][-1][1]], [1.0, -0.5])
        shutter = outgoing_curves["shutter_duration"]
        self.assertEqual([shutter[0][0], shutter[0][1]], [0.0, 0.0])
        self.assertEqual(shutter[-1][0], 1.0)
        self.assertAlmostEqual(shutter[-1][1], 1.9047619047619047)
        self.assertAlmostEqual(outgoing_curves["shift_x"][0][5], -0.1)
        self.assertAlmostEqual(outgoing_curves["shift_x"][1][3], -0.26666666666666666)

        incoming_motion = effect_curves(incoming, "kdenlive_motion_curve")
        incoming_stretch = effect_curves(incoming, "kdenlive_axis_stretch")
        self.assertEqual((incoming_motion["shift_x"][0][1], incoming_motion["shift_x"][-1][1]), (0.2, 0.0))
        self.assertEqual((incoming_motion["shutter_duration"][0][1],
                          incoming_motion["shutter_duration"][-1][1]), (1.5, 0.0))
        self.assertEqual((incoming_stretch["scale_x"][0][1], incoming_stretch["scale_x"][-1][1]), (1.6, 1.0))
        self.assertIn("not decoded Sapphire interpolation", outgoing.findtext(ns + "description"))
        self.assertIn("not decoded Sapphire interpolation", incoming.findtext(ns + "description"))

        # The pilot must not alter another source row, including the Scroll Up trial.
        baseline_inventory = copy.deepcopy(self.inventory)
        for package in baseline_inventory["packages"]:
            for record in package["records"]:
                if record["source_identifier"] in {
                    "{1AD8B510-4D09-4263-BEA1-FA45C59E7594}",
                    "{7F0C983A-CA01-48EA-8430-079520B606D5}",
                }:
                    record.pop("native_curve_policy", None)
        baseline_tree = ET.fromstring(build_templates(baseline_inventory))
        baseline_other = self.group(baseline_tree, "1.4 Scroll Left (1) 20k")
        candidate_other = self.group(candidate_tree, "1.4 Scroll Left (1) 20k")
        self.assertEqual(ET.tostring(candidate_other), ET.tostring(baseline_other))

    def test_zoom_out_10_5_pair_policies_are_source_scoped_and_keep_complete_chains(self):
        ns = "{https://www.kdenlive.org}"
        tree = ET.fromstring(build_templates(self.inventory))
        incoming = self.group(tree, "10.5 Zoom Out Pinch (2) 15k")
        outgoing = self.group(tree, "10.5 Zoom Out Pinch (1) 15k")
        self.assertEqual(outgoing.attrib["sourceId"], "{C5FCEC32-DB49-47AF-9CDF-1580ED35F114}")
        self.assertEqual(outgoing.attrib["transitionRole"], "out")
        self.assertEqual([effect.attrib["id"] for effect in outgoing.findall(ns + "effect")],
                         ["kdenlive_motion_curve", "kdenlive_pinch_punch"])
        outgoing_motion, outgoing_pinch = outgoing.findall(ns + "effect")
        outgoing_motion_curves = json.loads(outgoing_motion.findtext(ns + "property[@name='native_curves']"))
        outgoing_pinch_curves = json.loads(outgoing_pinch.findtext(ns + "property[@name='native_curves']"))
        self.assertEqual(outgoing_motion_curves["z_distance"][0][0:2], [0.0, 1.0])
        self.assertEqual(outgoing_motion_curves["z_distance"][-1][0:2], [1.0, 1.5])
        self.assertEqual(outgoing_pinch_curves["amount"][0][1], 0.0)
        self.assertEqual(outgoing_pinch_curves["amount"][-1][1], -1.0)
        self.assertIn("monotone cubic native handles", outgoing.findtext(ns + "description"))
        self.assertEqual(incoming.attrib["sourceId"], "{B9BD2DB7-A2A8-4C60-BF31-93DFFDF9EF17}")
        self.assertEqual(incoming.attrib["transitionRole"], "in")
        self.assertEqual([effect.attrib["id"] for effect in incoming.findall(ns + "effect")],
                         ["kdenlive_motion_curve", "kdenlive_pinch_punch"])
        motion, pinch = incoming.findall(ns + "effect")
        motion_curves = json.loads(motion.findtext(ns + "property[@name='native_curves']"))
        pinch_curves = json.loads(pinch.findtext(ns + "property[@name='native_curves']"))
        self.assertEqual(motion_curves["z_distance"], [
            [0.0, 0.5, 0.0, 0.5, 1.0 / 3.0, 1.0, 1],
            [1.0, 1.0, 2.0 / 3.0, 1.0, 1.0, 1.0, 0],
        ])
        self.assertEqual(motion_curves["shutter_duration"][0][1], 1.5)
        self.assertEqual(motion_curves["shutter_duration"][-1][1], 1.0)
        self.assertEqual(pinch_curves["amount"][0][1], -1.0)
        self.assertEqual(pinch_curves["amount"][-1][1], 0.0)
        description = incoming.findtext(ns + "description")
        self.assertIn("replaces the decoded Z-distance hold", description)
        self.assertIn("not decoded Sapphire interpolation", description)

        baseline_inventory = copy.deepcopy(self.inventory)
        for package in baseline_inventory["packages"]:
            for record in package["records"]:
                if record["source_identifier"] in {
                        "{C5FCEC32-DB49-47AF-9CDF-1580ED35F114}",
                        "{B9BD2DB7-A2A8-4C60-BF31-93DFFDF9EF17}"}:
                    record.pop("native_curve_policy", None)
        baseline_tree = ET.fromstring(build_templates(baseline_inventory))
        baseline_incoming = self.group(baseline_tree, "10.5 Zoom Out Pinch (2) 15k")
        self.assertNotEqual(ET.tostring(incoming), ET.tostring(baseline_incoming))
        self.assertNotEqual(ET.tostring(outgoing), ET.tostring(self.group(baseline_tree, "10.5 Zoom Out Pinch (1) 15k")))
        self.assertEqual([effect.attrib["id"] for effect in baseline_incoming.findall(ns + "effect")],
                         ["kdenlive_motion_curve", "kdenlive_pinch_punch"])
        unrelated_name = "1.4 Scroll Left (1) 20k"
        self.assertEqual(ET.tostring(self.group(tree, unrelated_name)),
                         ET.tostring(self.group(baseline_tree, unrelated_name)))


if __name__ == "__main__":
    unittest.main()
