"""Boundary and identity checks for the read-only SFPD inventory parser."""

import importlib.util
import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("native_transition_inventory", ROOT / "tools/native_transition_inventory.py")
PARSER = importlib.util.module_from_spec(SPEC)
import sys
sys.modules[SPEC.name] = PARSER
SPEC.loader.exec_module(PARSER)


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

    @unittest.skipUnless(PACKAGE.exists(), "read-only source package is unavailable")
    def test_record_count_and_slide_identities(self):
        package = PARSER.parse_package(self.PACKAGE)
        self.assertEqual(package["record_count"], 194)
        self.assertEqual(len({record["source_identifier"] for record in package["records"]}), 194)
        slides = [record for record in package["records"] if "Slide Right (1) 15k" in record["exact_name"]]
        self.assertEqual(len(slides), 5)
        self.assertEqual(len({record["source_identifier"] for record in slides}), 5)

    @unittest.skipUnless(PACKAGE.exists(), "read-only source package is unavailable")
    def test_animation_points_and_ordered_components(self):
        records = PARSER.parse_package(self.PACKAGE)["records"]
        scroll = next(record for record in records if record["exact_name"] == "1.4 Scroll Left (1) 20k")
        self.assertEqual([component["vendor_id"].split(".")[-1] for component in scroll["components"]],
                         ["S_BlurMoCurves}", "S_WarpFishEye}"])
        self.assertEqual([mapping["service"] for mapping in scroll["native_component_mapping"]],
                         ["kdenlive_motion_curve", "kdenlive_fisheye_warp"])
        slide = next(record for record in records if record["exact_name"] == "2.2 Slide Right (1) 15k")
        self.assertIsNone(slide["native_component_mapping"][-1])  # No motion-vector service for RSMB.
        shift = next(parameter for parameter in scroll["components"][0]["parameters"] if parameter["name"] == "Shift X")
        self.assertEqual([round(point["value"], 1) for point in shift["animation"]["points"]], [0.0, -0.2, 5.0])
        self.assertAlmostEqual(shift["animation"]["points"][-1]["normalized_event_position"], 1.0)

    @unittest.skipUnless(PACKAGE.exists(), "read-only source package is unavailable")
    def test_supported_fixture_rejects_omitted_components(self):
        sys.path.insert(0, str(ROOT / "tools"))
        from create_supported_chain_fixture import build
        inventory = {"packages": [PARSER.parse_package(self.PACKAGE)]}
        with self.assertRaisesRegex(ValueError, "no component may be omitted"):
            build(inventory, "1.2 Slide Left (1) 15k", Path("/tmp/unused.mp4"), 30, 15, 640, 360, 60, 1)
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
        self.assertEqual(sum(record["scope"] == "undetermined" for record in records), 19)
        from xml.etree import ElementTree as ET
        catalog = ET.fromstring(build_catalog({"packages": packages}))
        browser_entries = catalog.findall("{https://www.kdenlive.org}pendingeffect")
        self.assertEqual(len(browser_entries), 194)
        self.assertEqual(len({entry.attrib["id"] for entry in browser_entries}), 194)


if __name__ == "__main__":
    unittest.main()
