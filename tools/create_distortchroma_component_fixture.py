#!/usr/bin/env python3
"""Build a fixture for decoded S_DistortChroma using source-luminance lensing."""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from create_motion_curve_fixture import base_fixture, native_linear_points

COLORS = {"Color1": [1.0, 0.0, 0.0], "Color2": [0.0, 1.0, 0.0], "Color3": [0.0, 0.0, 1.0]}

def distortchroma_properties(record: dict, component: dict, frames: int) -> dict:
    parameters = component.get("parameters")
    if parameters is None:
        raise ValueError("the record has no decoded S_DistortChroma parameter table")
    timing = record.get("normalized_event_time_conversion")
    if timing is None:
        raise ValueError("source animation span is unknown")
    first = timing["first_source_position"]
    span = timing["last_source_position"] - first
    props = {"mlt_service": "kdenlive_distort_chroma", "native_event_frames": frames,
             "native_nominal_frames": record["nominal_frames"], "native_event_role": record["event_variant"],
             "amount": 0.0, "amount_adjust": 1.0, "blur_lens": 0.0,
             "rotate_warp_dir": 0.0, "warp_red": 0.5, "warp_blue": 1.0,
             "amount_rel_x": 1.0, "amount_rel_y": 1.0, "steps": 8,
             "wrap_x": 2, "wrap_y": 2, "subpixel": 1}
    curves = {}
    mapping = {"Amount": "amount", "Blur Lens": "blur_lens", "Rotate Warp Dir": "rotate_warp_dir",
               "Warp Red": "warp_red", "Warp Blue": "warp_blue", "Steps": "steps",
               "Amount Rel X": "amount_rel_x", "Amount Rel Y": "amount_rel_y"}
    for parameter in parameters:
        name = parameter["name"]
        value = parameter["value"]
        if name in mapping:
            target = mapping[name]
            if value is None:
                raise ValueError(f"unknown {name} value")
            props[target] = value
            if parameter.get("animation"):
                curves[target] = native_linear_points(parameter, first, span)
        elif name in ("Wrap X", "Wrap Y") and not parameter.get("animation"):
            props[name.lower().replace(" ", "_")] = value
        elif name == "Filter" and not parameter.get("animation") and value in (0, 1):
            props["subpixel"] = value
        elif name in ("Enable GPU", "version", "version2"):
            continue
        elif name in COLORS and value == COLORS[name] and not parameter.get("animation"):
            continue
        elif name in ("White Balance", "Blur Mask", "Invert Mask", "Mask Use") and not parameter.get("animation") and value in (0, 0.0):
            continue
        elif name in ("Crop Input", "Crop Left", "Crop Right", "Crop Top", "Crop Bottom") and not parameter.get("animation") and value in (0, 0.0):
            continue
        elif name in ("Lens", "Lens Input"):
            # The Vegas component has no separate input connection. The native
            # service therefore derives its optional lens from source luma.
            continue
        elif parameter.get("animation") or value not in (None, 0, 0.0, 1, 1.0):
            raise ValueError(f"unhandled nondefault S_DistortChroma parameter: {name}={value}")
    props["native_curves"] = json.dumps(curves, separators=(",", ":"))
    return props


def build(inventory: dict, exact_name: str, footage: Path, source_in: int, frames: int,
          width: int, height: int, fps_num: int, fps_den: int) -> ET.ElementTree:
    record = next((r for package in inventory["packages"] for r in package["records"]
                   if r["exact_name"] == exact_name), None)
    if record is None:
        raise ValueError(f"unknown preset: {exact_name}")
    matches = [component for component in record["components"]
               if component["vendor_id"].endswith("S_DistortChroma}")]
    if len(matches) != 1:
        raise ValueError("the record has no unique S_DistortChroma")
    properties = distortchroma_properties(record, matches[0], frames)
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
    parser.add_argument("--frames", type=int, default=15)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=360)
    parser.add_argument("--fps-num", type=int, default=60)
    parser.add_argument("--fps-den", type=int, default=1)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    tree = build(inventory, args.exact_name, args.footage, args.source_in, args.frames,
                 args.width, args.height, args.fps_num, args.fps_den)
    ET.indent(tree)
    tree.write(args.output, encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    main()
