#!/usr/bin/env python3
"""Render only a decoded S_WarpCornerPin component, never a complete transition.

The source packages use this component before S_WarpChroma, which is not yet
implemented. Source key positions are connected with provisional native linear
segments; this fixture is explicitly insufficient to validate either preset.
"""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from create_motion_curve_fixture import base_fixture, native_linear_points


POINT_NAMES = {
    "Top Left": ("tl_x", "tl_y"), "Top Right": ("tr_x", "tr_y"),
    "Bottom Left": ("bl_x", "bl_y"), "Bottom Right": ("br_x", "br_y"),
}
SCALAR_NAMES = {"Bulge X": "bulge_x", "Bulge Y": "bulge_y",
                "Shutter Angle": "shutter_angle", "Samples": "quality_samples"}


def cornerpin_properties(record: dict, component: dict, frames: int) -> dict:
    if component["parameters"] is None:
        raise ValueError("the record has no decoded S_WarpCornerPin")
    timing = record["normalized_event_time_conversion"]
    if timing is None:
        raise ValueError("source animation span is unknown")
    first = timing["first_source_position"]
    span = timing["last_source_position"] - first
    properties = {"mlt_service": "kdenlive_corner_pin", "native_event_frames": frames,
                  "native_nominal_frames": record["nominal_frames"], "native_event_role": record["event_variant"]}
    curves = {}
    blur_flags = {}
    for parameter in component["parameters"]:
        name = parameter["name"]
        value = parameter["value"]
        if name in POINT_NAMES:
            if not isinstance(value, list) or len(value) != 2 or parameter["animation"]:
                raise ValueError(f"unhandled animated or malformed corner: {name}")
            properties[POINT_NAMES[name][0]], properties[POINT_NAMES[name][1]] = value
        elif name in SCALAR_NAMES:
            target = SCALAR_NAMES[name]
            properties[target] = value
            if parameter["animation"]:
                curves[target] = native_linear_points(parameter, first, span)
        elif name in ("Wrap X", "Wrap Y"):
            properties[name.lower().replace(" ", "_")] = value
        elif name == "Filter":
            properties["subpixel"] = value
        elif name in ("Motion Blur", "Enable Motion Blur"):
            blur_flags[name] = value
        elif name not in ("Enable GPU", "version", "version2") and (parameter["animation"] or value not in (0, 0.0)):
            raise ValueError(f"unhandled non-default S_WarpCornerPin control: {name}")
    if blur_flags != {"Motion Blur": 0, "Enable Motion Blur": 0}:
        raise ValueError(f"unknown source motion-blur enable combination: {blur_flags}")
    properties["motion_blur_enable"] = 0
    properties["native_curves"] = json.dumps(curves, separators=(",", ":"))
    return properties


def build(inventory: dict, exact_name: str, footage: Path, source_in: int, frames: int,
          width: int, height: int, fps_num: int, fps_den: int) -> ET.ElementTree:
    record = next((r for package in inventory["packages"] for r in package["records"]
                   if r["exact_name"] == exact_name), None)
    if record is None:
        raise ValueError(f"unknown preset: {exact_name}")
    components = [c for c in record["components"] if c["vendor_id"].endswith("S_WarpCornerPin}")]
    if len(components) != 1:
        raise ValueError("the record has no unique S_WarpCornerPin")
    properties = cornerpin_properties(record, components[0], frames)
    tree, producer = base_fixture(footage, source_in, frames, width, height, fps_num, fps_den)
    effect = ET.SubElement(producer, "filter", {"in": str(source_in), "out": str(source_in + frames - 1)})
    for key, value in properties.items():
        ET.SubElement(effect, "property", {"name": key}).text = str(value)
    return tree


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("exact_name")
    parser.add_argument("footage", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source-in", type=int, default=30)
    parser.add_argument("--frames", type=int, default=20)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=360)
    parser.add_argument("--fps-num", type=int, default=60000)
    parser.add_argument("--fps-den", type=int, default=1001)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    tree = build(inventory, args.exact_name, args.footage, args.source_in, args.frames,
                 args.width, args.height, args.fps_num, args.fps_den)
    ET.indent(tree)
    tree.write(args.output, encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    main()
