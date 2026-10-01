"""Boundary and identity checks for the read-only SFPD inventory parser."""

import importlib.util
import copy
import json
import struct
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("native_transition_inventory", ROOT / "tools/native_transition_inventory.py")
PARSER = importlib.util.module_from_spec(SPEC)
import sys
sys.path.insert(0, str(ROOT / "tools"))
sys.modules[SPEC.name] = PARSER
SPEC.loader.exec_module(PARSER)

from create_supported_chain_fixture import build as build_native_chain
from create_paired_native_transition_fixture import make_fixture as build_paired_fixture
from generate_native_transition_templates import build_templates


class ChunkBoundaryTests(unittest.TestCase):
    def test_rejects_chunk_overrun(self):
        data = b"DATA" + struct.pack("<I", 10) + b"ab"
        with self.assertRaises(PARSER.FormatError):
            PARSER.chunks(data, 0, len(data))

    def test_rejects_missing_alignment(self):
        data = b"DATA" + struct.pack("<I", 1) + b"x"
        with self.assertRaises(PARSER.FormatError):
            PARSER.chunks(data, 0, len(data))

    def test_respects_odd_chunk_padding(self):
        data = b"DATA" + struct.pack("<I", 1) + b"x\0" + b"NEXT" + struct.pack("<I", 0)
        parsed = PARSER.chunks(data, 0, len(data))
        self.assertEqual([chunk.tag for chunk in parsed], ["DATA", "NEXT"])

    def test_rejects_unterminated_utf16(self):
        with self.assertRaises(PARSER.FormatError):
            PARSER.utf16z("Name".encode("utf-16le"), 0, 8, 8)


class SourcePackageTests(unittest.TestCase):
    PACKAGE = Path("/home/kali/Documents/GitHub/kdenlive-plugins/Переходы/Переходы.sfpreset")
    OTHER = Path("/home/kali/Documents/GitHub/kdenlive-plugins/Переходы/Other.sfpreset")

    def test_native_template_identity_and_component_order(self):
        inventory = json.loads((ROOT / "plans/native-transition-inventory.json").read_text(encoding="utf-8"))
        source_records = {record["source_identifier"]: record for package in inventory["packages"]
                          for record in package["records"]}
        active = ET.parse(ROOT / "data/effects/templates/native_transition_active.xml").getroot()
        pending = ET.parse(ROOT / "data/effects/templates/native_transition_presets.xml").getroot()
        self.assertEqual(len(active) + len(pending), 194)
        active_ids = {group.attrib["id"] for group in active}
        pending_ids = {entry.attrib["id"] for entry in pending}
        self.assertFalse(active_ids & pending_ids)
        self.assertEqual(len(active_ids), sum(record["scope"] == "transition" and
                                              record["status"] in ("Implemented", "Equivalent", "Partial")
                                              for record in source_records.values()))
        self.assertEqual(len(pending_ids), sum(record["scope"] == "transition" and
                                               record["status"] == "Pending"
                                               for record in source_records.values()))
        for group in active:
            with self.subTest(preset=group.find("{*}name").text):
                record = source_records[group.attrib["sourceId"]]
                self.assertIn(record["status"], ("Implemented", "Equivalent", "Partial"))
                self.assertTrue(record["validation_evidence"])
                self.assertEqual(group.attrib["transitionFrames"], str(record["nominal_frames"]))
                self.assertEqual(group.attrib["transitionRole"],
                                 "out" if record["event_variant"] == "outgoing" else "in")
                self.assertEqual(group.attrib["fitToEvent"], "1")
                services = [effect.attrib["id"] for effect in group.findall("{*}effect")]
                expected_services = []
                additions = record.get("native_reconstruction_additions", [])
                excluded_indices = {item["component_index"]
                                    for item in record.get("native_reconstruction_exclusions", [])}
                inserted = set()
                for component_index, component in enumerate(record["components"]):
                    if component_index in excluded_indices:
                        continue
                    source_service = component["native_component"]["service"]
                    for addition in additions:
                        if addition.get("insert_before_service") == source_service:
                            expected_services.append(addition["service"])
                            inserted.add(addition["service"])
                    expected_services.append(source_service)
                expected_services.extend(addition["service"] for addition in additions
                                         if addition["service"] not in inserted)
                self.assertEqual(services, expected_services)
                self.assertEqual(len(services), len(record["components"]) - len(excluded_indices) + len(additions))
                for item in record.get("native_reconstruction_exclusions", []):
                    self.assertTrue(item.get("description", "").strip())
                for effect in group.findall("{*}effect"):
                    curves = next((prop.text for prop in effect.findall("{*}property")
                                   if prop.attrib["name"] == "native_curves"), None)
                    if curves is None:
                        continue
                    for keys in json.loads(curves).values():
                        self.assertTrue(all(0 <= key[0] <= 1 for key in keys))
                        self.assertEqual(keys, sorted(keys, key=lambda key: key[0]))
        for entry in pending:
            source_id = "{" + entry.attrib["id"].split("native.transition.", 1)[1].upper() + "}"
            self.assertEqual(source_records[source_id]["status"], "Pending")

    def test_slide_down_33_peak_adjustments_are_editable_and_whole_event(self):
        inventory = json.loads((ROOT / "plans/native-transition-inventory.json").read_text(encoding="utf-8"))
        names = ("3.3 Slide Down (1) 15k", "3.3 Slide Down (2) 15k")
        templates = ET.fromstring(build_templates(inventory))
        by_name = {group.find("{*}name").text: group for group in templates}
        expected_templates = {
            names[0]: {"shift_y_adjust": "0=0;14=0.75", "shutter_duration_adjust": "0=-1;14=16"},
            names[1]: {"shift_y_adjust": "0=-0.75;14=0", "shutter_duration_adjust": "0=16;14=-1"},
        }
        for name, expected in expected_templates.items():
            with self.subTest(name=name):
                motion = by_name[name].find("{*}effect[@id='kdenlive_motion_curve']")
                props = {p.get("name"): p.text for p in motion.findall("{*}property")}
                self.assertEqual({key: props[key] for key in expected}, expected)
                self.assertEqual(props["quality_samples"], "32")

        fixture = build_paired_fixture(
            inventory, *names, Path("/tmp/unused-a.mp4"), Path("/tmp/unused-b.mp4"),
            source_in=30, second_source_in=120, context=3, width=640, height=360,
            fps_num=30, fps_den=1, event_frames=15,
            curve_policy="slide-down-33-cut-peak-v1")
        event_filters = {}
        for producer in fixture.getroot().findall("producer"):
            if producer.get("id") in {"outgoing_event", "incoming_event"}:
                event_filters[producer.get("id")] = {
                    prop.get("name"): prop.text for prop in producer.findall("filter/property")
                }
        self.assertEqual(event_filters["outgoing_event"]["shift_y_adjust"], "30=0;44=0.75")
        self.assertEqual(event_filters["outgoing_event"]["shutter_duration_adjust"], "30=-1;44=16")
        self.assertEqual(event_filters["incoming_event"]["shift_y_adjust"], "120=-0.75;134=0")
        self.assertEqual(event_filters["incoming_event"]["shutter_duration_adjust"], "120=16;134=-1")

        single = build_paired_fixture(
            inventory, *names, Path("/tmp/unused-a.mp4"), Path("/tmp/unused-b.mp4"),
            source_in=30, second_source_in=120, context=3, width=640, height=360,
            fps_num=30, fps_den=1, event_frames=1,
            curve_policy="slide-down-33-cut-peak-v1")
        single_props = {}
        for producer in single.getroot().findall("producer"):
            if producer.get("id") in {"outgoing_event", "incoming_event"}:
                single_props[producer.get("id")] = {
                    prop.get("name"): prop.text for prop in producer.findall("filter/property")
                }
        self.assertEqual(single_props["outgoing_event"]["shift_y_adjust"], "30=0.75")
        self.assertEqual(single_props["incoming_event"]["shift_y_adjust"], "120=-0.75")

    def test_stretch_left_eased_template_preserves_source_endpoints(self):
        from native_transition_curves import smoothstep_endpoint_bezier_points

        active = ET.parse(ROOT / "data/effects/templates/native_transition_active.xml").getroot()
        cases = {
            "{639387F3-0594-4FA0-AB1A-C3169A6EBFCB}": {
                "role": "outgoing", "shift_x": (0.0, -0.2), "shutter_duration": (1.0, 1.5),
                "scale_x": (1.0, 1.6),
            },
            "{170D89A3-D025-4314-A407-EEA40C18868D}": {
                "role": "incoming", "shift_x": (0.2, 0.0), "shutter_duration": (1.5, 1.0),
                "scale_x": (1.6, 1.0),
            },
        }
        groups = {group.attrib["sourceId"]: group for group in active
                  if group.attrib.get("sourceId") in cases}
        self.assertEqual(set(groups), set(cases))
        for source_id, expected in cases.items():
            with self.subTest(source_id=source_id):
                group = groups[source_id]
                self.assertEqual(group.attrib["transitionRole"], "out" if expected["role"] == "outgoing" else "in")
                motion = next(effect for effect in group.findall("{*}effect")
                              if effect.attrib["id"] == "kdenlive_motion_curve")
                stretch = next(effect for effect in group.findall("{*}effect")
                               if effect.attrib["id"] == "kdenlive_axis_stretch")
                motion_curves = json.loads(next(prop.text for prop in motion.findall("{*}property")
                                                if prop.attrib["name"] == "native_curves"))
                stretch_curves = json.loads(next(prop.text for prop in stretch.findall("{*}property")
                                                 if prop.attrib["name"] == "native_curves"))
                for key, target in (("shift_x", motion_curves), ("shutter_duration", motion_curves),
                                    ("scale_x", stretch_curves)):
                    start, end = expected[key]
                    self.assertEqual(target[key], smoothstep_endpoint_bezier_points(start, end, 0.4))
                    self.assertEqual(target[key][0][0], 0.0)
                    self.assertEqual(target[key][-1][0], 1.0)
                    self.assertAlmostEqual(target[key][0][1], start)
                    self.assertAlmostEqual(target[key][-1][1], end)

    def test_swish3d_chain_conversion_preserves_each_source_component(self):
        inventory = json.loads((ROOT / "plans/native-transition-inventory.json").read_text(encoding="utf-8"))
        swish_names = ("9.19 ZoomBubble (1) 20k", "9.20 TIMEZOOM (1) 20k", "9.20 TIMEZOOM (2) 20k")
        for name in swish_names:
            with self.subTest(preset=name):
                record = next(row for package in inventory["packages"] for row in package["records"]
                              if row["exact_name"] == name)
                fixture = build_native_chain(inventory, name, Path("/tmp/source-test.mp4"), 30, 20, 640, 360, 60, 1)
                filters = fixture.getroot().find("producer").findall("filter")
                services = [next(prop.text for prop in effect.findall("property")
                                 if prop.get("name") == "mlt_service") for effect in filters]
                self.assertEqual(len(filters), len(record["components"]))
                self.assertEqual(services[0], "kdenlive_motion_curve")
                self.assertEqual(services[-1], "kdenlive_brightness_contrast")
                curves = json.loads(next(prop.text for prop in filters[0].findall("property")
                                         if prop.get("name") == "native_curves"))
                self.assertIn("z_distance", curves)
                self.assertIn("scale_x", curves)
                self.assertEqual(curves["z_distance"][0][0], 0.0)
                self.assertLessEqual(curves["z_distance"][-1][0], 1.0)
                expected_z = 0.1 if record["event_variant"] == "outgoing" else 1.0
                self.assertAlmostEqual(curves["z_distance"][-1][1], expected_z)
                self.assertEqual(curves["scale_x"][-1][0], 1.0)
                color_curves = json.loads(next(prop.text for prop in filters[-1].findall("property")
                                               if prop.get("name") == "native_curves"))
                self.assertEqual(set(color_curves), {"brightness", "contrast"})

    def test_slide_right_is_horizontal_motion_and_blur_without_wave_warp(self):
        from generate_native_transition_templates import build_templates

        inventory = json.loads((ROOT / "plans/native-transition-inventory.json").read_text(encoding="utf-8"))
        expected = {
            "2.1 Slide Right (1) 10k": ("outgoing", 0.0, -0.5),
            "2.1 Slide Right (2) 10k": ("incoming", 0.5, 0.0),
            "2.2 Slide Right (1) 15k": ("outgoing", 0.0, -0.25),
            "2.2 Slide Right (2) 15k": ("incoming", 0.25, 0.0),
            "2.3 Slide Right (1) 15k": ("outgoing", 0.0, -0.25),
            "2.3 Slide Right (2) 15k": ("incoming", 0.25, 0.0),
            "2.4 Slide Right (1) 15k": ("outgoing", 0.0, -0.25),
            "2.4 Slide Right (2) 15k": ("incoming", 0.25, 0.0),
        }
        records = {record["exact_name"]: record for package in inventory["packages"]
                   for record in package["records"]}
        active = ET.fromstring(build_templates(inventory))
        groups = {group.get("sourceId"): group for group in active.findall("{*}effectgroup")}
        for name, (role, shift_start, shift_end) in expected.items():
            with self.subTest(preset=name):
                record = records[name]
                fixture = build_native_chain(inventory, name, Path("/tmp/unused-slide-right.mp4"),
                                             30, 15, 320, 180, 30, 1)
                filters = fixture.getroot().find("producer").findall("filter")
                services = [next(prop.text for prop in effect.findall("property")
                                 if prop.get("name") == "mlt_service") for effect in filters]
                expected_services = ["kdenlive_motion_curve"]
                if any(component["vendor_id"].endswith("RSMB}")
                       for component in record["components"]):
                    expected_services.append("kdenlive_motion_vector_blur")
                self.assertEqual(services, expected_services)
                self.assertFalse(record.get("native_reconstruction_additions"))
                motion = {prop.get("name"): prop.text for prop in filters[0].findall("property")}
                self.assertEqual(motion["native_event_role"], role)
                curves = json.loads(motion["native_curves"])
                self.assertEqual((curves["shift_x"][0][1], curves["shift_x"][-1][1]),
                                 (shift_start, shift_end))
                self.assertEqual(motion["shift_y"], "0.0")
                self.assertEqual((filters[0].get("in"), filters[0].get("out")), ("30", "44"))

                group = groups[record["source_identifier"]]
                group_services = [effect.get("id") for effect in group.findall("{*}effect")]
                self.assertEqual(group_services, services)
                description = group.findtext("{*}description")
                self.assertFalse(record.get("native_reconstruction_additions"))
                self.assertNotIn("wave", description.lower())

    @unittest.skipUnless(PACKAGE.exists(), "read-only source package is unavailable")
    def test_record_count_and_slide_identities(self):
        package = PARSER.parse_package(self.PACKAGE)
        self.assertEqual(package["record_count"], 194)
        self.assertEqual(len({record["source_identifier"] for record in package["records"]}), 194)
        slides = [record for record in package["records"] if "Slide Right (1) 15k" in record["exact_name"]]
        self.assertEqual(len(slides), 5)
        self.assertEqual(len({record["source_identifier"] for record in slides}), 5)

    @unittest.skipUnless(PACKAGE.exists(), "read-only source package is unavailable")
    def test_opaque_opticalcom_component_retains_literal_mbl2_offsets(self):
        package = PARSER.parse_package(self.PACKAGE)
        record = next(record for record in package["records"]
                      if record["exact_name"] == "9.23 OpticalCom (1) 20k")
        component = record["components"][0]
        self.assertIsNone(component["native_component"])
        self.assertEqual(component["payload_size"], 146034)
        self.assertEqual(component["opaque_payload_signatures"], [
            {"signature_ascii": "MBL2", "relative_offsets": [106, 48758, 97410]},
        ])

    @unittest.skipUnless(PACKAGE.exists(), "read-only source package is unavailable")
    def test_animation_points_and_ordered_components(self):
        records = PARSER.parse_package(self.PACKAGE)["records"]
        scroll = next(record for record in records if record["exact_name"] == "1.4 Scroll Left (1) 20k")
        self.assertEqual([component["vendor_id"].split(".")[-1] for component in scroll["components"]],
                         ["S_BlurMoCurves}", "S_WarpFishEye}"])
        self.assertEqual([mapping["service"] for mapping in scroll["native_component_mapping"]],
                         ["kdenlive_motion_curve", "kdenlive_fisheye_warp"])
        slide = next(record for record in records if record["exact_name"] == "2.2 Slide Right (1) 15k")
        self.assertEqual(slide["native_component_mapping"][-1]["service"], "kdenlive_motion_vector_blur")
        shift = next(parameter for parameter in scroll["components"][0]["parameters"] if parameter["name"] == "Shift X")
        self.assertEqual([round(point["value"], 1) for point in shift["animation"]["points"]], [0.0, -0.2, 5.0])
        self.assertAlmostEqual(shift["animation"]["points"][-1]["normalized_event_position"], 1.0)

    @unittest.skipUnless(PACKAGE.exists(), "read-only source package is unavailable")
    def test_vegas_pinch_payload_controls_and_event_curves(self):
        package = PARSER.parse_package(self.PACKAGE)
        records = package["records"]
        pinch_records = [record for record in records
                         if any(component["vendor_id"] == PARSER.VEGAS_PINCH_PUNCH_ID
                                for component in record["components"])]
        self.assertEqual(len(pinch_records), 16)
        for record in pinch_records:
            with self.subTest(source_id=record["source_identifier"]):
                component = next(item for item in record["components"]
                                 if item["vendor_id"] == PARSER.VEGAS_PINCH_PUNCH_ID)
                self.assertEqual(component["native_component"]["service"], "kdenlive_pinch_punch")
                self.assertIn(component["vendor_preset"]["preset_label"],
                              ("Maximum Pinch", "Maximum Punch", "Reset to None", "BP2", "BP 24", "BP 33"))
                params = {parameter["name"]: parameter for parameter in component["parameters"]}
                self.assertEqual(params["Center"]["value"], [0.0, 0.0])
                self.assertGreater(params["Horizontal"]["value"], 0.0)
                self.assertEqual(params["Horizontal"]["value"], params["Vertical"]["value"])
                self.assertEqual(params["Proportional"]["value"], 1)
                amount = params["Amount"]
                self.assertGreaterEqual(len(amount["animation"]["points"]), 2)
                self.assertEqual(amount["animation"]["points"][0]["normalized_event_position"], 0.0)
                self.assertEqual(amount["animation"]["points"][-1]["normalized_event_position"], 1.0)
                self.assertEqual(amount["animation"]["original_timing_units"],
                                 "VEGAS signed 64-bit serialized ticks; scale and interpolation meanings unverified")

        outgoing = next(record for record in pinch_records if record["exact_name"] == "9.4 Zoom In Pinch (1) 15k")
        incoming = next(record for record in pinch_records if record["exact_name"] == "9.4 Zoom In Pinch (2) 15k")
        for record, expected in ((outgoing, [0.0, -1.0]), (incoming, [-1.0, 0.0])):
            component = next(item for item in record["components"] if item["vendor_id"] == PARSER.VEGAS_PINCH_PUNCH_ID)
            amount = next(parameter for parameter in component["parameters"] if parameter["name"] == "Amount")
            self.assertEqual([point["value"] for point in amount["animation"]["points"]], expected)
            self.assertEqual([point["normalized_event_position"] for point in amount["animation"]["points"]], [0.0, 1.0])

        shifted = next(record for record in pinch_records
                       if record["exact_name"] == "9.16 RGB ZOOM-IN (2) 15k")
        shifted_component = next(item for item in shifted["components"]
                                 if item["vendor_id"] == PARSER.VEGAS_PINCH_PUNCH_ID)
        self.assertEqual(len(shifted_component["vendor_preset"]["ignored_negative_time_points"]), 1)
        self.assertEqual([point["time"] for point in
                          next(item for item in shifted_component["parameters"] if item["name"] == "Amount")["animation"]["points"]],
                         [0, 2919581])

        raw = self.PACKAGE.read_bytes()
        truncated = next(item for item in shifted["components"]
                         if item["vendor_id"] == PARSER.VEGAS_PINCH_PUNCH_ID)
        with self.assertRaises(PARSER.FormatError):
            PARSER._vegas_pinch_parameters(raw, truncated["payload_offset"],
                                           truncated["payload_offset"] + truncated["payload_size"] - 1)

    @unittest.skipUnless(PACKAGE.exists(), "read-only source package is unavailable")
    def test_pinch_pair_fixture_uses_full_event_native_chain(self):
        sys.path.insert(0, str(ROOT / "tools"))
        from create_supported_chain_fixture import build
        package = PARSER.parse_package(self.PACKAGE)
        inventory = {"packages": [package]}
        for name, role, expected in (
            ("9.4 Zoom In Pinch (1) 15k", "outgoing", [0.0, -1.0]),
            ("9.4 Zoom In Pinch (2) 15k", "incoming", [-1.0, 0.0]),
        ):
            with self.subTest(preset=name):
                fixture = build(inventory, name, Path("/tmp/unused.mp4"), 31, 120, 640, 360, 60, 1)
                filters = fixture.getroot().findall("producer/filter")
                self.assertEqual(len(filters), 2)
                props = [{item.get("name"): item.text for item in effect.findall("property")}
                         for effect in filters]
                self.assertEqual([item["mlt_service"] for item in props],
                                 ["kdenlive_motion_curve", "kdenlive_pinch_punch"])
                self.assertEqual([(effect.get("in"), effect.get("out")) for effect in filters],
                                 [("31", "150"), ("31", "150")])
                self.assertEqual(props[1]["native_event_frames"], "120")
                self.assertEqual(props[1]["native_event_role"], role)
                self.assertEqual((props[1]["horizontal"], props[1]["vertical"], props[1]["proportional"]),
                                 ("1.0", "1.0", "1"))
                keys = json.loads(props[1]["native_curves"])["amount"]
                self.assertEqual([key[0] for key in keys], [0.0, 1.0])
                self.assertEqual([key[1] for key in keys], expected)

    @unittest.skipUnless(PACKAGE.exists(), "read-only source package is unavailable")
    def test_supported_fixture_rejects_omitted_components(self):
        sys.path.insert(0, str(ROOT / "tools"))
        from create_supported_chain_fixture import build
        inventory = {"packages": [PARSER.parse_package(self.PACKAGE)]}
        slide = build(inventory, "1.2 Slide Left (1) 15k", Path("/tmp/unused.mp4"), 30, 15, 640, 360, 60, 1)
        self.assertEqual([f.find("property").text for f in slide.getroot().findall("producer/filter")],
                         ["kdenlive_motion_curve", "kdenlive_motion_vector_blur"])
        tree = build(inventory, "1.4 Scroll Left (1) 20k", Path("/tmp/unused.mp4"), 30, 20, 640, 360, 60, 1)
        filters = tree.getroot().findall("producer/filter")
        self.assertEqual([f.find("property").text for f in filters],
                         ["kdenlive_motion_curve", "kdenlive_fisheye_warp"])
        self.assertEqual([(f.attrib["in"], f.attrib["out"]) for f in filters], [("30", "49"), ("30", "49")])
        incoming = build(inventory, "1.4 Scroll Left (2) 20k", Path("/tmp/unused.mp4"), 30, 20, 640, 360, 60, 1)
        incoming_filters = incoming.getroot().findall("producer/filter")
        self.assertEqual([f.find("property").text for f in incoming_filters],
                         ["kdenlive_motion_curve", "kdenlive_shake", "kdenlive_fisheye_warp"])

    @unittest.skipUnless(PACKAGE.exists(), "read-only source package is unavailable")
    def test_click_pair_blur_motion_keeps_transform_space_curves_in_source_order(self):
        sys.path.insert(0, str(ROOT / "tools"))
        from create_supported_chain_fixture import build
        package = PARSER.parse_package(self.PACKAGE)
        for name in ("9.18 Click (1) 20k", "9.18 Click (2) 20k"):
            with self.subTest(preset=name):
                record = next(r for r in package["records"] if r["exact_name"] == name)
                self.assertEqual(record["components"][-1]["native_component"]["service"], "kdenlive_blur_motion")
                fixture = build({"packages": [package]}, name, Path("/tmp/unused.mp4"), 30, 120, 640, 360, 60, 1)
                filters = fixture.getroot().findall("producer/filter")
                self.assertEqual([f.find("property").text for f in filters], [
                    "kdenlive_pinch_punch", "kdenlive_motion_curve", "kdenlive_fisheye_warp", "kdenlive_blur_motion"])
                props = {p.get("name"): p.text for p in filters[-1].findall("property")}
                self.assertEqual((props["in"], props["out"]) if "in" in props else (filters[-1].get("in"), filters[-1].get("out")),
                                 ("30", "149"))
                self.assertEqual(props["native_event_frames"], "120")
                self.assertEqual(props["wrap_x"], "0")
                keys = json.loads(props["native_curves"])["to_z_dist"]
                timing = record["normalized_event_time_conversion"]
                span = timing["last_source_position"] - timing["first_source_position"]
                source_points = record["components"][-1]["parameters"]
                source_to = next(p for p in source_points if p["name"] == "To Z Dist")["animation"]["points"]
                expected_positions = [(point["time"] - timing["first_source_position"]) / span
                                      for point in source_to]
                self.assertEqual([round(key[0], 9) for key in keys],
                                 [round(position, 9) for position in expected_positions])
                self.assertNotEqual(keys[0][1], keys[-1][1])

    @unittest.skipUnless(PACKAGE.exists(), "read-only source package is unavailable")
    def test_zoombubble_keeps_both_animated_bubble_fields_in_order(self):
        sys.path.insert(0, str(ROOT / "tools"))
        from create_supported_chain_fixture import build
        from create_bubblewarp_component_fixture import build as build_bubble_component
        package = PARSER.parse_package(self.PACKAGE)
        record = next(r for r in package["records"] if r["exact_name"] == "9.19 ZoomBubble (2) 20k")
        fixture = build({"packages": [package]}, record["exact_name"], Path("/tmp/unused.mp4"),
                        31, 120, 640, 360, 60, 1)
        filters = fixture.getroot().findall("producer/filter")
        self.assertEqual([f.find("property[@name='mlt_service']").text for f in filters], [
            "kdenlive_motion_curve", "kdenlive_shake", "kdenlive_warp_bubble2", "kdenlive_fisheye_warp"])
        bubble = {p.get("name"): p.text for p in filters[2].findall("property")}
        self.assertEqual((filters[2].get("in"), filters[2].get("out")), ("31", "150"))
        self.assertEqual(bubble["native_event_frames"], "120")
        self.assertEqual(bubble["native_nominal_frames"], "20")
        curves = json.loads(bubble["native_curves"])
        for source_name, native_name in (("A Shift Start Y", "a_shift_start_y"),
                                         ("B Amplitude", "b_amplitude"),
                                         ("B Frequency", "b_frequency"),
                                         ("B Shift Start Y", "b_shift_start_y")):
            source = next(p for p in record["components"][2]["parameters"] if p["name"] == source_name)
            expected = [point["normalized_event_position"] for point in source["animation"]["points"]]
            self.assertEqual([round(key[0], 9) for key in curves[native_name]],
                             [round(position, 9) for position in expected])
        self.assertEqual(bubble["wrap_x"], "2")
        self.assertEqual(bubble["wrap_y"], "2")
        component_fixture = build_bubble_component({"packages": [package]}, record["exact_name"],
                                                   Path("/tmp/unused.mp4"), 31, 120, 640, 360, 60, 1)
        isolated = component_fixture.getroot().findall("producer/filter")
        self.assertEqual(len(isolated), 1)
        self.assertEqual(isolated[0].find("property[@name='mlt_service']").text,
                         "kdenlive_warp_bubble2")
        self.assertEqual(json.loads(isolated[0].find("property[@name='native_curves']").text), curves)

    @unittest.skipUnless(PACKAGE.exists(), "read-only source package is unavailable")
    def test_motion_converter_rejects_newly_active_source_controls(self):
        sys.path.insert(0, str(ROOT / "tools"))
        from create_motion_curve_fixture import motion_properties
        record = next(r for r in PARSER.parse_package(self.PACKAGE)["records"]
                      if r["exact_name"] == "1.1 Smooth R to L (1) 10k")
        component = copy.deepcopy(record["components"][0])
        mask_use = next(p for p in component["parameters"] if p["name"] == "Mask Use")
        mask_use["value"] = 1
        with self.assertRaisesRegex(ValueError, "Mask Use"):
            motion_properties(record, component, 10)

    @unittest.skipUnless(PACKAGE.exists(), "read-only source package is unavailable")
    def test_warptransform_source_usage_and_ordered_fixtures(self):
        sys.path.insert(0, str(ROOT / "tools"))
        from create_supported_chain_fixture import build
        package = PARSER.parse_package(self.PACKAGE)
        inventory = {"packages": [package]}
        records = [record for record in package["records"]
                   if any("S_WarpTransform}" in component["vendor_id"] for component in record["components"])]
        self.assertEqual(len(records), 11)
        for record in records:
            with self.subTest(source_identifier=record["source_identifier"]):
                component = next(component for component in record["components"]
                                 if "S_WarpTransform}" in component["vendor_id"])
                animated = {parameter["name"] for parameter in component["parameters"] if parameter["animation"]}
                self.assertTrue(animated and animated <= {"Scale X", "Scale Y"})
                self.assertIn("kdenlive_axis_stretch",
                              [mapping["service"] for mapping in record["native_component_mapping"]])
                fixture = build(inventory, record["exact_name"], Path("/tmp/unused.mp4"),
                                30, 15, 640, 360, 60000, 1001)
                services = [next(property_.text for property_ in filter_.findall("property")
                                 if property_.get("name") == "mlt_service")
                            for filter_ in fixture.getroot().findall("producer/filter")]
                self.assertEqual(services[-1], "kdenlive_axis_stretch")
                self.assertEqual(len(services), len(record["components"]))

    @unittest.skipUnless(PACKAGE.exists(), "read-only source package is unavailable")
    def test_cornerpin_component_fixtures_preserve_source_controls(self):
        sys.path.insert(0, str(ROOT / "tools"))
        from create_cornerpin_component_fixture import build
        package = PARSER.parse_package(self.PACKAGE)
        inventory = {"packages": [package]}
        records = [record for record in package["records"]
                   if any("S_WarpCornerPin}" in component["vendor_id"] for component in record["components"])]
        self.assertEqual(len(records), 4)
        for record in records:
            with self.subTest(source_identifier=record["source_identifier"]):
                self.assertIn("kdenlive_corner_pin",
                              [mapping["service"] if mapping else None
                               for mapping in record["native_component_mapping"]])
                fixture = build(inventory, record["exact_name"], Path("/tmp/unused.mp4"),
                                30, 20, 640, 360, 60000, 1001)
                properties = {property_.get("name"): property_.text
                              for property_ in fixture.getroot().findall("producer/filter/property")}
                self.assertEqual(properties["mlt_service"], "kdenlive_corner_pin")
                self.assertEqual(properties["motion_blur_enable"], "0")
                self.assertIn("bulge_x", properties["native_curves"])
                self.assertIn("bulge_y", properties["native_curves"])

    @unittest.skipUnless(PACKAGE.exists(), "read-only source package is unavailable")
    def test_warpchroma_controls_and_warppin_source_order(self):
        sys.path.insert(0, str(ROOT / "tools"))
        from create_warpchroma_component_fixture import chroma_properties
        from create_supported_chain_fixture import build
        package = PARSER.parse_package(self.PACKAGE)
        records = [record for record in package["records"]
                   if any("S_WarpChroma}" in component["vendor_id"] for component in record["components"])]
        self.assertEqual(len(records), 18)
        for record in records:
            with self.subTest(source_identifier=record["source_identifier"]):
                component = next(component for component in record["components"]
                                 if "S_WarpChroma}" in component["vendor_id"])
                properties = chroma_properties(record, component, record["nominal_frames"])
                self.assertEqual(properties["mlt_service"], "kdenlive_warp_chroma")
                self.assertEqual(properties["spectrum_steps"],
                                 next(parameter["value"] for parameter in component["parameters"]
                                      if parameter["name"] == "Steps"))
        fixture = build({"packages": [package]}, "5.5 A WarpPin (1) 20k",
                        Path("/tmp/unused.mp4"), 30, 20, 640, 360, 60000, 1001)
        services = [next(property_.text for property_ in filter_.findall("property")
                         if property_.get("name") == "mlt_service")
                    for filter_ in fixture.getroot().findall("producer/filter")]
        self.assertEqual(services, ["kdenlive_corner_pin", "kdenlive_warp_chroma"])

    @unittest.skipUnless(PACKAGE.exists(), "read-only source package is unavailable")
    def test_distortchroma_pair_preserves_source_order_and_normalized_amount(self):
        sys.path.insert(0, str(ROOT / "tools"))
        from create_supported_chain_fixture import build
        package = PARSER.parse_package(self.PACKAGE)
        records = {record["exact_name"]: record for record in package["records"]
                   if record["exact_name"] in ("3.9 DropDown Distor (1) 15k", "3.9 DropDown Distor (2) 15k")}
        self.assertEqual(len(records), 2)
        for name, role in (("3.9 DropDown Distor (1) 15k", "outgoing"),
                           ("3.9 DropDown Distor (2) 15k", "incoming")):
            with self.subTest(preset=name):
                record = records[name]
                fixture = build({"packages": [package]}, name, Path("/tmp/unused.mp4"),
                                30, 120, 640, 360, 60, 1)
                filters = fixture.getroot().findall("producer/filter")
                self.assertEqual(len(filters), 2)
                properties = [{prop.get("name"): prop.text for prop in effect.findall("property")}
                              for effect in filters]
                self.assertEqual([item["mlt_service"] for item in properties],
                                 ["kdenlive_motion_curve", "kdenlive_distort_chroma"])
                self.assertEqual(properties[1]["native_event_role"], role)
                self.assertEqual(properties[1]["native_event_frames"], "120")
                self.assertEqual((properties[1]["wrap_x"], properties[1]["wrap_y"]), ("2", "2"))
                curves = json.loads(properties[1]["native_curves"])
                self.assertEqual((curves["amount"][0][0], curves["amount"][-1][0]), (0.0, 1.0))
                amount = next(parameter for parameter in record["components"][1]["parameters"]
                              if parameter["name"] == "Amount")
                self.assertEqual((curves["amount"][0][1], curves["amount"][-1][1]),
                                 (amount["animation"]["points"][0]["value"],
                                  amount["animation"]["points"][-1]["value"]))
                self.assertEqual(properties[1]["warp_red"], "-0.9931972789115646" if role == "outgoing" else "-0.9")

    @unittest.skipUnless(PACKAGE.exists(), "read-only source package is unavailable")
    def test_warpmagnify_pair_preserves_curves_edges_and_role_when_fitted(self):
        sys.path.insert(0, str(ROOT / "tools"))
        from create_supported_chain_fixture import build

        package = PARSER.parse_package(self.PACKAGE)
        records = {record["exact_name"]: record for record in package["records"]
                   if record["exact_name"] in ("14.1 Squeeze (1) 15k", "14.1 Squeeze (2) 15k")}
        expected = {
            "14.1 Squeeze (1) 15k": ("outgoing", (1.0, 1.5), (1.0, 0.5)),
            "14.1 Squeeze (2) 15k": ("incoming", (0.5, 1.0), (1.5, 1.0)),
        }
        self.assertEqual(set(records), set(expected))
        for name, (role, x_values, y_values) in expected.items():
            with self.subTest(preset=name):
                fixture = build({"packages": [package]}, name, Path("/tmp/unused.mp4"),
                                30, 120, 640, 360, 60, 1)
                filters = fixture.getroot().findall("producer/filter")
                self.assertEqual(len(filters), 1)
                properties = {prop.get("name"): prop.text
                              for prop in filters[0].findall("property")}
                self.assertEqual(properties["mlt_service"], "kdenlive_magnify_warp")
                self.assertEqual(properties["native_event_frames"], "120")
                self.assertEqual(properties["native_nominal_frames"], "15")
                self.assertEqual(properties["native_event_role"], role)
                self.assertEqual((properties["wrap_x"], properties["wrap_y"]), ("2", "2"))
                self.assertEqual(properties["subpixel"], "1")
                curves = json.loads(properties["native_curves"])
                self.assertEqual(curves["magnify_rel_x"][0][0], 0.0)
                self.assertEqual(curves["magnify_rel_x"][-1][0], 1.0)
                self.assertEqual(curves["magnify_rel_y"][0][0], 0.0)
                self.assertEqual(curves["magnify_rel_y"][-1][0], 1.0)
                self.assertEqual((curves["magnify_rel_x"][0][1], curves["magnify_rel_x"][-1][1]), x_values)
                self.assertEqual((curves["magnify_rel_y"][0][1], curves["magnify_rel_y"][-1][1]), y_values)

        unsupported = copy.deepcopy(package)
        outgoing = next(record for record in unsupported["records"]
                        if record["exact_name"] == "14.1 Squeeze (1) 15k")
        mask_use = next(parameter for parameter in outgoing["components"][0]["parameters"]
                        if parameter["name"] == "Mask Use")
        mask_use["value"] = 1
        with self.assertRaisesRegex(ValueError, "Mask Use"):
            build({"packages": [unsupported]}, outgoing["exact_name"], Path("/tmp/unused.mp4"),
                  30, 15, 640, 360, 60, 1)

    @unittest.skipUnless(PACKAGE.exists(), "read-only source package is unavailable")
    def test_sapphire_center_y_is_converted_from_lower_left_to_raster(self):
        sys.path.insert(0, str(ROOT / "tools"))
        from create_supported_chain_fixture import build

        package = PARSER.parse_package(self.PACKAGE)
        cases = {
            "11.2 Spin ClockWise (1) 15k": (0.5, 0.5),
            "11.4 Bottom Left Corner Spin (1) 15k": (0.0, 1.0),
            "11.5 Bottom Right Corner Spin (1) 15k": (1.0, 1.0),
        }
        for name, expected in cases.items():
            with self.subTest(preset=name):
                fixture = build({"packages": [package]}, name, Path("/tmp/unused.mp4"),
                                30, 15, 640, 360, 60, 1)
                properties = {prop.get("name"): prop.text
                              for prop in fixture.getroot().findall("producer/filter/property")}
                self.assertAlmostEqual(float(properties["center_x"]), expected[0])
                self.assertAlmostEqual(float(properties["center_y"]), expected[1])

    @unittest.skipUnless(PACKAGE.exists() and OTHER.exists(), "read-only source packages are unavailable")
    def test_all_213_records_reconcile_with_pending_browser(self):
        sys.path.insert(0, str(ROOT / "tools"))
        from generate_native_transition_catalog import build_catalog
        packages = [PARSER.parse_package(self.PACKAGE), PARSER.parse_package(self.OTHER)]
        records = [record for package in packages for record in package["records"]]
        self.assertEqual([package["record_count"] for package in packages], [194, 19])
        self.assertEqual(len(records), 213)
        self.assertEqual(len({record["source_identifier"] for record in records}), 213)
        self.assertEqual(sum(record["scope"] == "transition" for record in records), 194)
        self.assertEqual(sum(record["scope"] == "standalone_effect" for record in records), 19)
        self.assertTrue(all(record["nominal_frames"] is None and record["event_variant"] is None
                            for record in records if record["scope"] == "standalone_effect"))
        from xml.etree import ElementTree as ET
        catalog = ET.fromstring(build_catalog({"packages": packages}))
        browser_entries = catalog.findall("{https://www.kdenlive.org}pendingeffect")
        self.assertEqual(len(browser_entries), 194)
        self.assertEqual(len({entry.attrib["id"] for entry in browser_entries}), 194)


if __name__ == "__main__":
    unittest.main()
