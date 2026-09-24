#!/usr/bin/env python3
"""Render-test a source-ordered chain only when every component is supported.

The fixture connects decoded key positions with explicitly *native linear*
segments. Source interpolation codes and Sapphire's exact fisheye kernel remain
unknown, so this is a reconstruction test, not a validated source preset.
"""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from create_motion_curve_fixture import base_fixture, fixture as motion_fixture, native_linear_points
from create_cornerpin_component_fixture import cornerpin_properties
from create_warpchroma_component_fixture import chroma_properties


FISHEYE_PARAMETERS = {
    "Amount": "amount", "Z Dist": "z_distance", "Rotate": "rotation",
    "Shift Orig X": "shift_orig_x", "Shift Orig Y": "shift_orig_y",
}
SHAKE_PARAMETERS = {
    "Amplitude": "amplitude", "Frequency": "frequency", "Phase": "phase", "Seed": "seed",
    "Z Dist": "z_distance", "Motion Blur": "motion_blur", "Mo Blur Length": "mo_blur_length",
}
STRETCH_PARAMETERS = {
    "Scale X": "scale_x", "Scale Y": "scale_y", "Shift X": "shift_x",
    "Shift Y": "shift_y", "Z Dist": "z_distance",
}
for _axis in ("X", "Y", "Z", "Tilt"):
    for _source, _native in (("Rand Amp", "rand_amp"), ("Rand Freq", "rand_freq"),
                             ("Wave Amp", "wave_amp"), ("Wave Freq", "wave_freq"),
                             ("Phase", "phase")):
        SHAKE_PARAMETERS[f"{_axis} {_source}"] = f"{_axis.lower()}_{_native}"


def build(inventory: dict, exact_name: str, footage: Path, source_in: int, frames: int,
          width: int, height: int, fps_num: int, fps_den: int) -> ET.ElementTree:
    record = next((r for package in inventory["packages"] for r in package["records"]
                   if r["exact_name"] == exact_name), None)
    if record is None:
        raise ValueError(f"unknown preset: {exact_name}")
    chain = [component["vendor_id"].rsplit(".", 1)[-1].rstrip("}") for component in record["components"]]
    if chain not in (["S_BlurMoCurves", "S_WarpFishEye"],
                     ["S_BlurMoCurves", "S_Shake", "S_WarpFishEye"],
                     ["S_BlurMoCurves", "S_WarpTransform"], ["S_WarpTransform"],
                     ["S_WarpCornerPin", "S_WarpChroma"]):
        raise ValueError(f"unsupported ordered chain {chain}; no component may be omitted")
    if chain[0] == "S_BlurMoCurves":
        tree = motion_fixture(inventory, exact_name, footage, source_in, frames, width, height, fps_num, fps_den)
        producer = tree.getroot().find("producer")
        assert producer is not None
        remaining = zip(chain[1:], record["components"][1:])
    else:
        tree, producer = base_fixture(footage, source_in, frames, width, height, fps_num, fps_den)
        remaining = zip(chain, record["components"])
    timing = record["normalized_event_time_conversion"]
    if timing is None:
        raise ValueError("source animation span is unknown")
    first = timing["first_source_position"]
    span = timing["last_source_position"] - first
    for kind, component in remaining:
        if component["parameters"] is None:
            raise ValueError(f"{kind} parameter table was not decoded")
        if kind in ("S_WarpCornerPin", "S_WarpChroma"):
            properties = (cornerpin_properties(record, component, frames) if kind == "S_WarpCornerPin"
                          else chroma_properties(record, component, frames))
            effect = ET.SubElement(producer, "filter", {"in": str(source_in), "out": str(source_in + frames - 1)})
            for key, value in properties.items():
                ET.SubElement(effect, "property", {"name": key}).text = str(value)
            continue
        services = {"S_WarpFishEye": "kdenlive_fisheye_warp", "S_Shake": "kdenlive_shake",
                    "S_WarpTransform": "kdenlive_axis_stretch"}
        properties = {"mlt_service": services[kind],
                      "native_event_frames": frames, "native_nominal_frames": record["nominal_frames"],
                      "native_event_role": record["event_variant"]}
        curves = {}
        names = {"S_WarpFishEye": FISHEYE_PARAMETERS, "S_Shake": SHAKE_PARAMETERS,
                 "S_WarpTransform": STRETCH_PARAMETERS}[kind]
        for parameter in component["parameters"]:
            name = parameter["name"]
            if name == "Center" and isinstance(parameter["value"], list):
                properties["center_x"], properties["center_y"] = parameter["value"][:2]
            elif name in names and parameter["value"] is not None:
                target = names[name]
                properties[target] = parameter["value"]
                if parameter["animation"]:
                    curves[target] = native_linear_points(parameter, first, span)
            elif name in ("Wrap X", "Wrap Y"):
                properties[name.lower().replace(" ", "_")] = parameter["value"]
            elif name == "Filter":
                properties["subpixel"] = parameter["value"]
            elif kind == "S_WarpTransform" and name in ("Rotate", "Swivel", "Tilt", "Shear X", "Shear Y"):
                if parameter["value"] != 0 or parameter["animation"]:
                    raise ValueError(f"unimplemented WarpTransform control: {name}")
            elif kind == "S_WarpTransform" and name == "Perspective Amount":
                if parameter["value"] != 1 or parameter["animation"]:
                    raise ValueError("unimplemented WarpTransform perspective")
            elif kind == "S_WarpTransform" and name not in ("version", "version2", "Enable GPU"):
                if parameter["animation"] or parameter["value"] not in (0, 0.0):
                    raise ValueError(f"unimplemented WarpTransform control: {name}")
            elif name.endswith(" Shake.group") and parameter["value"] != 0:
                raise ValueError(f"unsupported {kind} group control: {name}")
        properties["native_curves"] = json.dumps(curves, separators=(",", ":"))
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
