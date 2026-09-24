#!/usr/bin/env python3
"""Render an isolated decoded S_WarpChroma component with provisional key interpolation."""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from create_motion_curve_fixture import base_fixture, native_linear_points


PARAMETERS = {
    "From Z Dist": "from_z_distance", "To Z Dist": "to_z_distance",
    "From Rotate": "from_rotation", "To Rotate": "to_rotation",
    "From Shift X": "from_shift_x", "From Shift Y": "from_shift_y",
    "To Shift X": "to_shift_x", "To Shift Y": "to_shift_y",
    "Brightness": "brightness", "Steps": "spectrum_steps", "Warp Amount": "warp_amount",
}
COLORS = {"Color1": [1.0, 0.0, 0.0], "Color2": [0.0, 1.0, 0.0], "Color3": [0.0, 0.0, 1.0]}
DEFAULT_ONE = {"Mocha Opacity", "Resize Mocha", "Resize Rel X", "Resize Rel Y"}


def chroma_properties(record: dict, component: dict, frames: int) -> dict:
    if component["parameters"] is None:
        raise ValueError("the record has no decoded S_WarpChroma")
    timing = record["normalized_event_time_conversion"]
    if timing is None:
        raise ValueError("source animation span is unknown")
    first = timing["first_source_position"]
    span = timing["last_source_position"] - first
    properties = {"mlt_service": "kdenlive_warp_chroma", "native_event_frames": frames,
                  "native_nominal_frames": record["nominal_frames"], "native_event_role": record["event_variant"],
                  "warp_amount": 1}
    curves = {}
    for parameter in component["parameters"]:
        name = parameter["name"]
        value = parameter["value"]
        if name == "Center":
            if not isinstance(value, list) or len(value) != 2 or parameter["animation"]:
                raise ValueError("unhandled Chroma center")
            properties["center_x"], properties["center_y"] = value
        elif name in PARAMETERS:
            target = PARAMETERS[name]
            properties[target] = value
            if parameter["animation"]:
                curves[target] = native_linear_points(parameter, first, span)
        elif name in ("Wrap X", "Wrap Y"):
            properties[name.lower().replace(" ", "_")] = value
        elif name in COLORS:
            if value != COLORS[name] or parameter["animation"]:
                raise ValueError(f"nondefault {name} is not supported")
        elif name == "Mocha Project":
            # This ten-byte all-zero body follows a two-byte length marker in
            # the newer records. Treat only this exact sentinel as empty; any
            # other unknown project payload must block the component fixture.
            if parameter["raw_hex"] != "02000000000000000000":
                raise ValueError("nonempty or unknown Mocha project payload")
        elif name in DEFAULT_ONE:
            if value != 1 or parameter["animation"]:
                raise ValueError(f"nondefault Mocha control: {name}")
        elif name == "Filter":
            if value != 0 or parameter["animation"]:
                raise ValueError("Sapphire adaptive Filter is unsupported")
            properties["subpixel"] = 1
        elif name not in ("Enable GPU", "version", "version2") and (parameter["animation"] or value not in (0, 0.0)):
            raise ValueError(f"unhandled non-default S_WarpChroma control: {name}")
    properties["native_curves"] = json.dumps(curves, separators=(",", ":"))
    return properties


def build(inventory: dict, exact_name: str, footage: Path, source_in: int, frames: int,
          width: int, height: int, fps_num: int, fps_den: int) -> ET.ElementTree:
    record = next((r for package in inventory["packages"] for r in package["records"]
                   if r["exact_name"] == exact_name), None)
    if record is None:
        raise ValueError(f"unknown preset: {exact_name}")
    components = [c for c in record["components"] if c["vendor_id"].endswith("S_WarpChroma}")]
    if len(components) != 1:
        raise ValueError("the record has no unique S_WarpChroma")
    properties = chroma_properties(record, components[0], frames)
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
