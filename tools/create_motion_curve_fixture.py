#!/usr/bin/env python3
"""Create a disposable MLT XML render fixture for one decoded motion component.

This is a component test, not a claim that a multi-component preset is complete.
"""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path


PARAMETERS = {
    "Z Dist": "z_distance", "Rotate": "rotation", "Shift X": "shift_x", "Shift Y": "shift_y",
    "Shutter Duration": "shutter_duration", "Shutter Shift": "shutter_shift",
    "Exposure Bias": "exposure_bias", "Brightness": "brightness",
}

# These source controls are inert for the decoded transition records: no Mocha
# project or mask is selected, and the corresponding modes are disabled. Keep
# their expected defaults explicit so future records cannot silently discard a
# newly used source operation.
INACTIVE_DEFAULTS = {
    "Mode": 0, "Mocha Project": None, "group_0": 0,
    "Blur Mocha": 0, "Mocha Opacity": 1, "Invert Mocha": 0,
    "Resize Mocha": 1, "Resize Rel X": 1, "Resize Rel Y": 1,
    "Shift Mocha X": 0, "Shift Mocha Y": 0, "Bypass Mocha": 0,
    "Show Mocha Only": 0, "Combine Masks": 0, "Blur Res": 0,
    "Mask Use": 0, "Blur Mask": 0.00625, "Invert Mask": 0,
    "Crop Input": 0, "Crop Left": 0, "Crop Right": 0,
    "Crop Top": 0, "Crop Bottom": 0,
}


def native_linear_points(parameter: dict, first: float, span: float) -> list[list[float]]:
    """Provisional linear reconstruction; these are not decoded source interpolation types."""
    return [[(point["time"] - first) / span, point["value"],
             (point["time"] - first) / span, point["value"],
             (point["time"] - first) / span, point["value"], 0]
            for point in parameter["animation"]["points"]]


def sapphire_center_to_raster(value: list[float]) -> tuple[float, float]:
    """Convert the package's normalized lower-left Center to raster coordinates.

    The supplied Vegas FX reference shows Center=(0.50, 0.50) for frame center;
    the corner-spin records use X=0 or X=1. Native raster sampling has its
    origin at top left, so flip only Y when converting the normalized point.
    """
    if len(value) < 2:
        raise ValueError("Sapphire Center must contain X and Y")
    return float(value[0]), 1.0 - float(value[1])


def base_fixture(footage: Path, source_in: int, frames: int,
                 width: int, height: int, fps_num: int, fps_den: int) -> tuple[ET.ElementTree, ET.Element]:
    root = ET.Element("mlt", {"LC_NUMERIC": "C", "version": "7.40.0", "producer": "event"})
    ET.SubElement(root, "profile", {"description": "Native motion fixture", "width": str(width), "height": str(height),
                                    "progressive": "1", "sample_aspect_num": "1", "sample_aspect_den": "1",
                                    "display_aspect_num": str(width), "display_aspect_den": str(height),
                                    "frame_rate_num": str(fps_num), "frame_rate_den": str(fps_den)})
    producer = ET.SubElement(root, "producer", {"id": "source"})
    ET.SubElement(producer, "property", {"name": "mlt_service"}).text = "avformat"
    ET.SubElement(producer, "property", {"name": "resource"}).text = str(footage.resolve())
    event = ET.SubElement(root, "playlist", {"id": "event"})
    ET.SubElement(event, "entry", {"producer": "source", "in": str(source_in),
                                   "out": str(source_in + frames - 1)})
    return ET.ElementTree(root), producer


def motion_properties(record: dict, component: dict, frames: int) -> dict:
    if not component["parameters"]:
        raise ValueError("no decoded S_BlurMoCurves component")
    timing = record["normalized_event_time_conversion"]
    if timing is None:
        raise ValueError("preset has no normalized curve span")
    first = timing["first_source_position"]
    span = timing["last_source_position"] - first
    curves = {}
    properties = {"mlt_service": "kdenlive_motion_curve"}
    for parameter in component["parameters"]:
        name = parameter["name"]
        if name == "Center" and isinstance(parameter["value"], list):
            properties["center_x"], properties["center_y"] = sapphire_center_to_raster(parameter["value"])
        elif name in PARAMETERS and parameter["value"] is not None:
            target = PARAMETERS[name]
            properties[target] = parameter["value"]
            if parameter["animation"]:
                # The source interpolation codes and auxiliary pairs are not
                # decoded. This disposable component fixture deliberately
                # connects decoded positions/values with a native linear
                # segment; it is not a faithful source-preset conversion.
                curves[target] = native_linear_points(parameter, first, span)
        elif name in ("Wrap X", "Wrap Y"):
            properties[name.lower().replace(" ", "_")] = parameter["value"]
        elif name == "Subpixel":
            properties["subpixel"] = parameter["value"]
        elif name in INACTIVE_DEFAULTS:
            if parameter["animation"] or parameter["value"] != INACTIVE_DEFAULTS[name]:
                raise ValueError(f"unsupported active BlurMoCurves control: {name}")
        elif name in ("Enable GPU", "version", "version2"):
            if parameter["animation"]:
                raise ValueError(f"unsupported animated BlurMoCurves metadata: {name}")
        else:
            raise ValueError(f"unhandled BlurMoCurves control: {name}")
    properties.update(native_curves=json.dumps(curves, separators=(",", ":")),
                      native_nominal_frames=record["nominal_frames"], native_event_frames=frames,
                      native_event_role=record["event_variant"], quality_samples=8)
    return properties


def fixture(inventory: dict, exact_name: str, footage: Path, source_in: int, frames: int,
            width: int, height: int, fps_num: int, fps_den: int) -> ET.ElementTree:
    record = next((r for package in inventory["packages"] for r in package["records"]
                   if r["exact_name"] == exact_name), None)
    if record is None:
        raise ValueError(f"source preset not found: {exact_name}")
    component = next((c for c in record["components"] if c["vendor_id"].endswith("S_BlurMoCurves}")), None)
    if component is None:
        raise ValueError("no decoded S_BlurMoCurves component")
    properties = motion_properties(record, component, frames)
    tree, producer = base_fixture(footage, source_in, frames, width, height, fps_num, fps_den)
    # A filter attached to the original source producer uses source-frame
    # coordinates. The playlist entry cuts that producer into a timed event.
    effect = ET.SubElement(producer, "filter", {"in": str(source_in),
                                                 "out": str(source_in + frames - 1)})
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
    doc = fixture(inventory, args.exact_name, args.footage, args.source_in, args.frames,
                  args.width, args.height, args.fps_num, args.fps_den)
    ET.indent(doc)
    doc.write(args.output, encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    main()
