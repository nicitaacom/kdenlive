#!/usr/bin/env python3
"""Render-test included source-ordered components from an auditable native chain.

The fixture connects decoded key positions with explicitly *native linear*
segments. Every omitted source component must have an explicit inventory
exclusion with a user-facing explanation. Source interpolation codes and
Sapphire's exact kernels remain unknown, so this is a reconstruction test,
not an exact vendor render.
"""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from create_motion_curve_fixture import (base_fixture, motion_properties, native_linear_points,
                                          sapphire_center_to_raster)
from create_cornerpin_component_fixture import cornerpin_properties
from create_warpchroma_component_fixture import chroma_properties
from create_distortchroma_component_fixture import distortchroma_properties
from native_transition_curves import apply_curve_policy


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


def _apply_opticalcom_bubble_cut_fit(tree: ET.ElementTree, event_variant: str) -> None:
    """Use a documented native amplitude conversion to form a cut-side peak.

    Sapphire's amplitude units are unpublished. Native amplitudes are frame
    fractions, so the reconstruction scales the decoded outgoing curve by 3x
    and incoming by 5.4x. The resulting total amplitude at each side of the cut
    is 2.709 for the decoded .903 outgoing versus .5 incoming combined fields.
    This scale is a visual-fit setting, not a decoded Sapphire conversion.
    """
    factor = 3.0 if event_variant == "outgoing" else 5.4
    producer = tree.getroot().find("producer")
    if producer is None:
        raise ValueError("missing producer for OpticalCom Bubble2 cut fit")
    found = False
    for filter_element in producer.findall("filter"):
        if filter_element.findtext("property[@name='mlt_service']") != "kdenlive_warp_bubble2":
            continue
        found = True
        curves_property = filter_element.find("property[@name='native_curves']")
        curves = json.loads(curves_property.text or "{}") if curves_property is not None else {}
        for parameter in ("a_amplitude", "b_amplitude"):
            scalar = filter_element.find(f"property[@name='{parameter}']")
            if scalar is not None and scalar.text:
                scaled = float(scalar.text) * factor
                if abs(scaled) > 2.0:
                    raise ValueError(f"OpticalCom Bubble2 fit exceeds native amplitude range: {scaled}")
                scalar.text = f"{scaled:.12g}"
            for point in curves.get(parameter, []):
                for index in (1, 3, 5):
                    point[index] *= factor
                    if abs(point[index]) > 2.0:
                        raise ValueError(f"OpticalCom Bubble2 curve exceeds native amplitude range: {point[index]}")
        if curves_property is not None:
            curves_property.text = json.dumps(curves, separators=(",", ":"))
    if not found:
        raise ValueError("OpticalCom Bubble2 cut fit requires the mapped native bubble service")


def build(inventory: dict, exact_name: str, footage: Path, source_in: int, frames: int,
          width: int, height: int, fps_num: int, fps_den: int) -> ET.ElementTree:
    record = next((r for package in inventory["packages"] for r in package["records"]
                   if r["exact_name"] == exact_name), None)
    if record is None:
        raise ValueError(f"unknown preset: {exact_name}")
    excluded = {}
    for exclusion in record.get("native_reconstruction_exclusions", []):
        index = exclusion.get("component_index")
        description = exclusion.get("description")
        if not isinstance(index, int) or index < 0 or index >= len(record["components"]):
            raise ValueError(f"invalid native reconstruction exclusion in {exact_name}: {index!r}")
        if index in excluded or not isinstance(description, str) or not description.strip():
            raise ValueError(f"duplicate exclusion or missing description in {exact_name}: {index!r}")
        excluded[index] = description.strip()
    mapped_components = [
        (index, component)
        for index, component in enumerate(record["components"])
        if index not in excluded
    ]
    chain = [component["vendor_id"].rsplit(".", 1)[-1].rstrip("}") for _, component in mapped_components]
    vegas_pinch = "{C8E20570-4059-4EDF-9CAE-EEF966DF3B19"
    supported = {"S_BlurMoCurves", "S_WarpFishEye", "S_Shake", "RSMB",
                 "S_WarpTransform", "S_WarpCornerPin", "S_WarpChroma",
                 "S_WarpWaves", "S_BlurMotion", "sonycreativesoftware:linearblur", "vegascreativesoftware:linearblur",
                 "sonycreativesoftware:radialblur", "S_WarpMagnify", "S_WarpBubble2", "S_DistortChroma", "S_Swish3D",
                 "sonycreativesoftware:brightnessandcontrast", vegas_pinch}
    if not chain or any(kind not in supported for kind in chain):
        raise ValueError(f"unsupported ordered chain {chain}; no component may be omitted")
    tree, producer = base_fixture(footage, source_in, frames, width, height, fps_num, fps_den)
    timing = record["normalized_event_time_conversion"]
    first = timing["first_source_position"] if timing else None
    span = timing["last_source_position"] - first if timing else None
    for kind, component in zip(chain, (component for _, component in mapped_components)):
        if component["parameters"] is None:
            raise ValueError(f"{kind} parameter table was not decoded")
        if kind == "S_BlurMoCurves":
            if timing is None:
                raise ValueError("S_BlurMoCurves source animation span is unknown")
            properties = motion_properties(record, component, frames)
            effect = ET.SubElement(producer, "filter", {"in": str(source_in), "out": str(source_in + frames - 1)})
            for key, value in properties.items():
                ET.SubElement(effect, "property", {"name": key}).text = str(value)
            continue
        if kind == "S_Swish3D":
            if timing is None:
                raise ValueError("S_Swish3D source animation span is unknown")
            properties = {"mlt_service": "kdenlive_motion_curve", "native_event_frames": frames,
                          "native_nominal_frames": record["nominal_frames"],
                          "native_event_role": record["event_variant"], "native_curve_start": 0,
                          "native_curve_end": 1, "quality_samples": 8, "shutter_duration": 0.5,
                          "shutter_shift": 0, "exposure_bias": 0.5, "brightness": 1,
                          "wrap_x": 2, "wrap_y": 2, "center_x": 0.5, "center_y": 0.5,
                          "shift_x": 0, "shift_y": 0, "rotation": 0}
            curves = {}
            values = {}
            animations = {}
            for parameter in component["parameters"]:
                name, value, animation = parameter["name"], parameter["value"], parameter["animation"]
                if name in ("Z Dist", "Scale", "Scale Rel X", "Scale Rel Y", "Shift X", "Shift Y", "Rotate"):
                    values[name] = value
                    animations[name] = animation
                elif name == "Center" and isinstance(value, list) and not animation:
                    properties["center_x"], properties["center_y"] = sapphire_center_to_raster(value)
                elif name == "Motion Blur" and not animation:
                    if value is None or value < 0:
                        raise ValueError("invalid S_Swish3D Motion Blur value")
                    # Sapphire's documented default shutter is 180 degrees (half a frame).
                    properties["shutter_duration"] = 0.5 * value
                elif name == "Steps" and not animation:
                    properties["quality_samples"] = max(1, min(64, int(value)))
                elif name in ("Wrap From X", "Wrap To X") and not animation:
                    if name.startswith("Wrap From") == (record["event_variant"] == "outgoing"):
                        properties["wrap_x"] = value
                elif name in ("Wrap From Y", "Wrap To Y") and not animation:
                    if name.startswith("Wrap From") == (record["event_variant"] == "outgoing"):
                        properties["wrap_y"] = value
                elif name in ("Mode", "autotrans_keyframe_state", "Wipe Amount", "Rel Amp From",
                              "Rel Amp To", "Fade", "Fade Mid Time", "Slow In", "Slow Out",
                              "Perspective Amount", "Shear X", "Shear Y", "Swivel", "Tilt",
                              "group_0", "group_1", "Filter", "Brightness", "Mid Brightness",
                              "Swish Auto Trans", "Color1", "Color2", "Color3", "White Balance",
                              "Enable GPU", "version", "version2"):
                    if name in ("Swivel", "Tilt", "Shear X", "Shear Y") and (animation or value not in (0, 0.0)):
                        raise ValueError(f"S_Swish3D 3D perspective control is not supported: {name}={value}")
                    if name == "Mode" and value != 0:
                        raise ValueError(f"unsupported S_Swish3D mode: {value}")
                else:
                    raise ValueError(f"unhandled S_Swish3D control: {name}={value}")

            # The output event follows the From transform from identity to its
            # decoded endpoint, driven by Wipe Amount. Incoming records carry
            # explicit To-side parameter curves; retain those curves directly.
            if record["event_variant"] == "outgoing":
                wipe = next((p for p in component["parameters"] if p["name"] == "Wipe Amount"), None)
                if not wipe or not wipe["animation"]:
                    raise ValueError("outgoing S_Swish3D requires an animated Wipe Amount")
                wipe_points = native_linear_points(wipe, first, span)
                for source_name, target_name, neutral, target_value in (
                    ("Z Dist", "z_distance", 1.0, values["Z Dist"]),
                    ("Scale Rel X", "scale_x", 1.0, values["Scale"] * values["Scale Rel X"]),
                    ("Scale Rel Y", "scale_y", 1.0, values["Scale"] * values["Scale Rel Y"]),
                    ("Shift X", "shift_x", 0.0, values["Shift X"]),
                    ("Shift Y", "shift_y", 0.0, values["Shift Y"]),
                    ("Rotate", "rotation", 0.0, values["Rotate"]),
                ):
                    curves[target_name] = [[point[0], neutral + (target_value - neutral) * point[1],
                                            point[0], neutral + (target_value - neutral) * point[1],
                                            point[0], neutral + (target_value - neutral) * point[1], 0]
                                           for point in wipe_points]
                properties.update(z_distance=1, scale_x=1, scale_y=1)
            else:
                mapping = {"Z Dist": "z_distance", "Shift X": "shift_x", "Shift Y": "shift_y",
                           "Rotate": "rotation"}
                for source_name, target_name in mapping.items():
                    value = values[source_name]
                    if value is None:
                        value = 1.0 if source_name == "Z Dist" else 0.0
                    properties[target_name] = value
                    if animations[source_name]:
                        curves[target_name] = native_linear_points(
                            {"animation": animations[source_name]}, first, span)
                for source_name, target_name in (("Scale Rel X", "scale_x"), ("Scale Rel Y", "scale_y")):
                    value = (values["Scale"] or 1.0) * (values[source_name] or 1.0)
                    properties[target_name] = value
                    if animations[source_name]:
                        raw = native_linear_points({"animation": animations[source_name]}, first, span)
                        curves[target_name] = [[point[0], point[1] * (values["Scale"] or 1.0),
                                                point[2], point[3] * (values["Scale"] or 1.0),
                                                point[4], point[5] * (values["Scale"] or 1.0), point[6]]
                                               for point in raw]
            properties["native_curves"] = json.dumps(curves, separators=(",", ":"))
            effect = ET.SubElement(producer, "filter", {"in": str(source_in), "out": str(source_in + frames - 1)})
            for key, value in properties.items():
                ET.SubElement(effect, "property", {"name": key}).text = str(value)
            continue
        if kind == "sonycreativesoftware:brightnessandcontrast":
            if timing is None:
                raise ValueError("brightness/contrast source animation span is unknown")
            names = {"Brightness": "brightness", "Contrast": "contrast", "ContrastCenter": "contrast_center"}
            properties = {"mlt_service": "kdenlive_brightness_contrast", "native_event_frames": frames,
                          "native_nominal_frames": record["nominal_frames"],
                          "native_event_role": record["event_variant"],
                          "native_curve_start": 0, "native_curve_end": 1}
            curves = {}
            for parameter in component["parameters"]:
                name, value = parameter["name"], parameter["value"]
                if name not in names:
                    raise ValueError(f"unhandled VEGAS brightness/contrast control: {name}")
                target = names[name]
                properties[target] = value
                if parameter["animation"]:
                    curves[target] = native_linear_points(parameter, first, span)
            if set(properties) & set(names.values()) != set(names.values()):
                raise ValueError("incomplete VEGAS brightness/contrast controls")
            properties["native_curves"] = json.dumps(curves, separators=(",", ":"))
            effect = ET.SubElement(producer, "filter", {"in": str(source_in), "out": str(source_in + frames - 1)})
            for key, value in properties.items():
                ET.SubElement(effect, "property", {"name": key}).text = str(value)
            continue
        if kind in ("sonycreativesoftware:linearblur", "vegascreativesoftware:linearblur",
                    "sonycreativesoftware:radialblur"):
            radial = kind.endswith(":radialblur")
            properties = {"mlt_service": "kdenlive_spatial_blur", "mode": int(radial),
                          "native_event_frames": frames, "native_nominal_frames": record["nominal_frames"],
                          "native_event_role": record["event_variant"], "quality_samples": 17}
            curves = {}
            for parameter in component["parameters"]:
                name = parameter["name"]
                if name in ("Amount", "Strength"):
                    if (name == "Strength") != radial:
                        raise ValueError(f"unexpected spatial blur amount: {name}")
                    properties["amount"] = parameter["value"]
                    if parameter["animation"]:
                        curves["amount"] = native_linear_points(parameter, first, span)
                elif name == "Angle" and not radial:
                    properties["angle"] = parameter["value"]
                    if parameter["animation"]:
                        curves["angle"] = native_linear_points(parameter, first, span)
                elif name == "Center" and radial and isinstance(parameter["value"], list):
                    if parameter["animation"]:
                        raise ValueError("animated radial blur center needs two-axis conversion")
                    properties["center_x"], properties["center_y"] = parameter["value"]
                elif name == "Type" and radial and not parameter["animation"]:
                    if parameter["value"] not in (0, 1, 2):
                        raise ValueError("unsupported radial blur type")
                    properties["radial_type"] = parameter["value"]
                else:
                    raise ValueError(f"unhandled spatial blur control: {name}")
            properties["native_curves"] = json.dumps(curves, separators=(",", ":"))
            effect = ET.SubElement(producer, "filter", {"in": str(source_in), "out": str(source_in + frames - 1)})
            for key, value in properties.items():
                ET.SubElement(effect, "property", {"name": key}).text = str(value)
            continue
        if kind == "S_WarpMagnify":
            if timing is None:
                raise ValueError("S_WarpMagnify source animation span is unknown")
            names = {"Magnify Amount": "magnify_amount", "Magnify Rel X": "magnify_rel_x",
                     "Magnify Rel Y": "magnify_rel_y", "Lens Radius": "lens_radius",
                     "Lens Edge Width": "lens_edge_width", "Lens Rel Width": "lens_rel_width",
                     "Lens Rel Height": "lens_rel_height", "Lens Rotate": "lens_rotate",
                     "Lens Edge Shape": "lens_edge_shape"}
            properties = {"mlt_service": "kdenlive_magnify_warp", "native_event_frames": frames,
                          "native_nominal_frames": record["nominal_frames"],
                          "native_event_role": record["event_variant"]}
            curves = {}
            inactive_defaults = {
                "Mocha Project": (None,), "group_0": (0,), "group_1": (0,),
                "Blur Mocha": (0, 0.0), "Mocha Opacity": (1, 1.0), "Invert Mocha": (0,),
                "Resize Mocha": (1, 1.0), "Resize Rel X": (1, 1.0), "Resize Rel Y": (1, 1.0),
                "Shift Mocha X": (0, 0.0), "Shift Mocha Y": (0, 0.0), "Bypass Mocha": (0,),
                "Show Mocha Only": (0,), "Combine Masks": (0,), "Blur Mask": (0, 0.0),
                "Invert Mask": (0,), "Mask Use": (0,), "Crop Input": (0,),
                "Crop Left": (0, 0.0), "Crop Right": (0, 0.0), "Crop Top": (0, 0.0),
                "Crop Bottom": (0, 0.0),
            }
            for parameter in component["parameters"]:
                name = parameter["name"]
                value = parameter["value"]
                if name in names:
                    target = names[name]
                    properties[target] = value
                    if parameter["animation"]:
                        curves[target] = native_linear_points(parameter, first, span)
                elif name == "Lens Center" and isinstance(value, list) and not parameter["animation"]:
                    properties["center_x"], properties["center_y"] = value
                elif name in ("Wrap X", "Wrap Y") and not parameter["animation"]:
                    properties[name.lower().replace(" ", "_")] = value
                elif name == "Filter" and value in (0, 1) and not parameter["animation"]:
                    properties["subpixel"] = value
                elif name in ("Enable GPU", "version", "version2") and not parameter["animation"]:
                    continue
                elif name == "Mocha Project" and value is None and not parameter["animation"]:
                    continue
                elif name in inactive_defaults and not parameter["animation"] and value in inactive_defaults[name]:
                    continue
                elif parameter["animation"] or value not in (0, 0.0):
                    raise ValueError(f"unhandled non-default S_WarpMagnify control: {name}")
            properties["native_curves"] = json.dumps(curves, separators=(",", ":"))
            effect = ET.SubElement(producer, "filter", {"in": str(source_in), "out": str(source_in + frames - 1)})
            for key, value in properties.items():
                ET.SubElement(effect, "property", {"name": key}).text = str(value)
            continue
        if kind == "S_WarpWaves":
            if timing is None:
                raise ValueError("S_WarpWaves source animation span is unknown")
            names = {"Amplitude": "amplitude", "Frequency": "frequency", "Angle": "angle",
                     "Displace Angle": "displace_angle", "Phase Start": "phase_start",
                     "Phase Speed": "phase_speed", "Z Dist": "z_distance"}
            properties = {"mlt_service": "kdenlive_warp_waves", "native_event_frames": frames,
                          "native_nominal_frames": record["nominal_frames"],
                          "native_event_role": record["event_variant"],
                          "native_curve_start": 0, "native_curve_end": 1,
                          "center_x": 0.5, "center_y": 0.5}
            curves = {}
            ignored_defaults = {
                "Mocha Project": (None,), "group_0": (0,), "Blur Mocha": (0,),
                "Mocha Opacity": (1,), "Invert Mocha": (0,), "Resize Mocha": (1,),
                "Resize Rel X": (1,), "Resize Rel Y": (1,), "Shift Mocha X": (0,),
                "Shift Mocha Y": (0,), "Bypass Mocha": (0,), "Show Mocha Only": (0,),
                "Combine Masks": (0,), "Blur Mask": (0,), "Invert Mask": (0,),
                "Mask Use": (0,), "Crop Input": (0,), "Crop Left": (0,),
                "Crop Right": (0,), "Crop Top": (0,), "Crop Bottom": (0,),
                "Enable GPU": (0, 1), "version": (None, 6.1), "version2": (None,),
            }
            for parameter in component["parameters"]:
                name = parameter["name"]
                value = parameter["value"]
                if name in names:
                    target = names[name]
                    properties[target] = value
                    if parameter["animation"]:
                        curves[target] = native_linear_points(parameter, first, span)
                elif name in ("Wrap X", "Wrap Y") and not parameter["animation"]:
                    properties[name.lower().replace(" ", "_")] = value
                elif name == "Filter" and not parameter["animation"] and value in (0, 1):
                    properties["subpixel"] = value
                elif name in ("version", "version2") and not parameter["animation"]:
                    continue
                elif name in ignored_defaults and not parameter["animation"] and value in ignored_defaults[name]:
                    continue
                else:
                    raise ValueError(f"unhandled S_WarpWaves control: {name}={value}")
            properties["native_curves"] = json.dumps(curves, separators=(",", ":"))
            effect = ET.SubElement(producer, "filter", {"in": str(source_in), "out": str(source_in + frames - 1)})
            for key, value in properties.items():
                ET.SubElement(effect, "property", {"name": key}).text = str(value)
            continue
        if kind == "S_WarpBubble2":
            if timing is None:
                raise ValueError("S_WarpBubble2 source animation span is unknown")
            names = {
                "A Amplitude": "a_amplitude", "A Frequency": "a_frequency", "A Octaves": "a_octaves",
                "A Seed": "a_seed", "A Shift Start X": "a_shift_start_x", "A Shift Start Y": "a_shift_start_y",
                "A Speed X": "a_speed_x", "A Speed Y": "a_speed_y",
                "B Amplitude": "b_amplitude", "B Frequency": "b_frequency", "B Octaves": "b_octaves",
                "B Seed": "b_seed", "B Shift Start X": "b_shift_start_x", "B Shift Start Y": "b_shift_start_y",
                "B Speed X": "b_speed_x", "B Speed Y": "b_speed_y", "Z Dist": "z_distance",
            }
            properties = {"mlt_service": "kdenlive_warp_bubble2", "native_event_frames": frames,
                          "native_nominal_frames": record["nominal_frames"],
                          "native_event_role": record["event_variant"],
                          "native_curve_start": 0, "native_curve_end": 1}
            curves = {}
            inactive_defaults = {
                "group_0": (0,), "group_1": (1,), "group_2": (1,),
                "Blur Mocha": (0, 0.0), "Mocha Opacity": (1, 1.0), "Invert Mocha": (0,),
                "Resize Mocha": (1, 1.0), "Resize Rel X": (1, 1.0), "Resize Rel Y": (1, 1.0),
                "Shift Mocha X": (0, 0.0), "Shift Mocha Y": (0, 0.0),
                "Bypass Mocha": (0,), "Show Mocha Only": (0,), "Combine Masks": (0,),
                "Blur Mask": (0, 0.0), "Invert Mask": (0,), "Mask Use": (0,),
                "Crop Input": (0,), "Crop Left": (0, 0.0), "Crop Right": (0, 0.0),
                "Crop Top": (0, 0.0), "Crop Bottom": (0, 0.0),
                "Enable GPU": (0, 1), "version": (None, 6.1), "version2": (None, 11599099),
                "Mocha Project": (None,),
            }
            for parameter in component["parameters"]:
                name = parameter["name"]
                value = parameter["value"]
                if name in names:
                    target = names[name]
                    properties[target] = value
                    if parameter["animation"]:
                        curves[target] = native_linear_points(parameter, first, span)
                elif name in ("Wrap X", "Wrap Y") and not parameter["animation"]:
                    properties[name.lower().replace(" ", "_")] = value
                elif name == "Filter" and not parameter["animation"] and value in (0, 1):
                    properties["subpixel"] = value
                elif name in ("Enable GPU", "version", "version2") and not parameter["animation"]:
                    continue
                elif name in ("A Octaves", "B Octaves") and not parameter["animation"]:
                    properties[names[name]] = value
                elif name in inactive_defaults and not parameter["animation"] and value in inactive_defaults[name]:
                    continue
                else:
                    raise ValueError(f"unhandled S_WarpBubble2 control: {name}={value}")
            properties["native_curves"] = json.dumps(curves, separators=(",", ":"))
            effect = ET.SubElement(producer, "filter", {"in": str(source_in), "out": str(source_in + frames - 1)})
            for key, value in properties.items():
                ET.SubElement(effect, "property", {"name": key}).text = str(value)
            continue
        if kind == "S_BlurMotion":
            if timing is None:
                raise ValueError("S_BlurMotion source animation span is unknown")
            names = {"From Z Dist": "from_z_dist", "To Z Dist": "to_z_dist",
                     "From Rotate": "from_rotate", "To Rotate": "to_rotate",
                     "From Shift X": "from_shift_x", "From Shift Y": "from_shift_y",
                     "To Shift X": "to_shift_x", "To Shift Y": "to_shift_y",
                     "Brightness": "brightness", "Exposure Bias": "exposure_bias"}
            properties = {"mlt_service": "kdenlive_blur_motion", "native_event_frames": frames,
                          "native_nominal_frames": record["nominal_frames"],
                          "native_event_role": record["event_variant"],
                          "native_curve_start": 0, "native_curve_end": 1,
                          "quality_samples": 17, "native_curves": "{}"}
            curves = {}
            ignored_defaults = {
                "Mocha Project": (None,), "group_0": (0,), "Blur Mocha": (0, 0.0),
                "Mocha Opacity": (1, 1.0), "Invert Mocha": (0,), "Resize Mocha": (1, 1.0),
                "Resize Rel X": (1, 1.0), "Resize Rel Y": (1, 1.0),
                "Shift Mocha X": (0, 0.0), "Shift Mocha Y": (0, 0.0),
                "Bypass Mocha": (0,), "Show Mocha Only": (0,), "Combine Masks": (0,),
                "Blur Mask": (0, 0.0), "Invert Mask": (0,), "Mask Use": (0,),
                "Crop Input": (0,), "Crop Left": (0, 0.0), "Crop Right": (0, 0.0),
                "Crop Top": (0, 0.0), "Crop Bottom": (0, 0.0),
                "Enable GPU": (0, 1), "version": (None, 11.02), "version2": (None,),
            }
            for parameter in component["parameters"]:
                name, value = parameter["name"], parameter["value"]
                if name == "Mode" and not parameter["animation"] and value == 0:
                    continue
                if name in names and value is not None:
                    target = names[name]
                    properties[target] = value
                    if parameter["animation"]:
                        curves[target] = native_linear_points(parameter, first, span)
                elif name == "Center" and isinstance(value, list) and len(value) >= 2 and not parameter["animation"]:
                    properties["center_x"], properties["center_y"] = value[:2]
                elif name in ("Wrap X", "Wrap Y") and not parameter["animation"] and value in (0, 1, 2):
                    properties[name.lower().replace(" ", "_")] = value
                elif name == "Subpixel" and not parameter["animation"] and value in (0, 1):
                    properties["subpixel"] = value
                elif name == "Blur Res" and not parameter["animation"] and value == 0:
                    # Full-resolution CPU sampling. Half/quarter-resolution modes
                    # are not translated because they alter the spatial kernel.
                    continue
                elif name in ("version", "version2") and not parameter["animation"]:
                    continue
                elif name in ignored_defaults and not parameter["animation"] and value in ignored_defaults[name]:
                    continue
                else:
                    raise ValueError(f"unhandled S_BlurMotion control: {name}={value}")
            properties["native_curves"] = json.dumps(curves, separators=(",", ":"))
            effect = ET.SubElement(producer, "filter", {"in": str(source_in), "out": str(source_in + frames - 1)})
            for key, value in properties.items():
                ET.SubElement(effect, "property", {"name": key}).text = str(value)
            continue
        if kind == "RSMB":
            values = {parameter["name"]: parameter["value"] for parameter in component["parameters"]}
            if any(parameter["animation"] for parameter in component["parameters"]):
                raise ValueError("animated RSMB parameters need explicit conversion")
            if (values["menuTrackFrame"] != 0 or values["menuDisplay"] != 0 or
                values["menuFG1MatteChannel"] != 3 or values["valFG1InvMatteShrink"] != 0 or
                values["valMBAmountFG1"] != values["valMBAmount"] or
                values["valMBSensitivityFG1"] != values["valMBSensitivity"]):
                raise ValueError("unsupported RSMB foreground or tracking setting")
            properties = {"mlt_service": "kdenlive_motion_vector_blur",
                          "blur_amount": values["valMBAmount"],
                          "motion_sensitivity": values["valMBSensitivity"],
                          "quality_samples": 8,
                          "native_event_frames": frames,
                          "native_nominal_frames": record["nominal_frames"],
                          "native_event_role": record["event_variant"],
                          "native_curve_start": 0, "native_curve_end": 1}
            effect = ET.SubElement(producer, "filter", {"in": str(source_in), "out": str(source_in + frames - 1)})
            for key, value in properties.items():
                ET.SubElement(effect, "property", {"name": key}).text = str(value)
            continue
        if kind in ("S_WarpCornerPin", "S_WarpChroma"):
            if timing is None:
                raise ValueError(f"{kind} source animation span is unknown")
            properties = (cornerpin_properties(record, component, frames) if kind == "S_WarpCornerPin"
                          else chroma_properties(record, component, frames))
            effect = ET.SubElement(producer, "filter", {"in": str(source_in), "out": str(source_in + frames - 1)})
            for key, value in properties.items():
                ET.SubElement(effect, "property", {"name": key}).text = str(value)
            continue
        if kind == "S_DistortChroma":
            if timing is None:
                raise ValueError("S_DistortChroma source animation span is unknown")
            properties = distortchroma_properties(record, component, frames)
            effect = ET.SubElement(producer, "filter", {"in": str(source_in), "out": str(source_in + frames - 1)})
            for key, value in properties.items():
                ET.SubElement(effect, "property", {"name": key}).text = str(value)
            continue
        if kind == vegas_pinch:
            properties = {"mlt_service": "kdenlive_pinch_punch", "native_event_frames": frames,
                          "native_nominal_frames": record["nominal_frames"],
                          "native_event_role": record["event_variant"],
                          "native_curve_start": 0, "native_curve_end": 1,
                          # VEGAS does not expose an edge mode for this filter;
                          # reflected sampling is an explicit native equivalent.
                          "wrap_x": 2, "wrap_y": 2, "subpixel": 1}
            curves = {}
            for parameter in component["parameters"]:
                name = parameter["name"]
                value = parameter["value"]
                if name == "Amount":
                    properties["amount"] = value
                    if parameter["animation"]:
                        curves["amount"] = [[point["normalized_event_position"], point["value"],
                                             point["normalized_event_position"], point["value"],
                                             point["normalized_event_position"], point["value"], 0]
                                            for point in parameter["animation"]["points"]]
                elif name == "Center" and isinstance(value, list) and len(value) >= 2:
                    properties["center_x"], properties["center_y"] = value[:2]
                elif name == "Horizontal":
                    properties["horizontal"] = value
                elif name == "Vertical":
                    properties["vertical"] = value
                elif name == "Proportional":
                    properties["proportional"] = value
                else:
                    raise ValueError(f"unhandled VEGAS Pinch/Punch control: {name}")
            if "amount" not in properties or "amount" not in curves:
                raise ValueError("VEGAS Pinch/Punch Amount animation is unresolved")
            properties["native_curves"] = json.dumps(curves, separators=(",", ":"))
            effect = ET.SubElement(producer, "filter", {"in": str(source_in), "out": str(source_in + frames - 1)})
            for key, value in properties.items():
                ET.SubElement(effect, "property", {"name": key}).text = str(value)
            continue
        services = {"S_WarpFishEye": "kdenlive_fisheye_warp", "S_Shake": "kdenlive_shake",
                    "S_WarpTransform": "kdenlive_axis_stretch"}
        if kind in services and timing is None:
            raise ValueError(f"{kind} source animation span is unknown")
        properties = {"mlt_service": services[kind],
                      "native_event_frames": frames, "native_nominal_frames": record["nominal_frames"],
                      "native_event_role": record["event_variant"]}
        curves = {}
        names = {"S_WarpFishEye": FISHEYE_PARAMETERS, "S_Shake": SHAKE_PARAMETERS,
                 "S_WarpTransform": STRETCH_PARAMETERS}[kind]
        for parameter in component["parameters"]:
            name = parameter["name"]
            if name == "Center" and isinstance(parameter["value"], list):
                if kind == "S_WarpFishEye":
                    properties["center_x"], properties["center_y"] = sapphire_center_to_raster(parameter["value"])
                else:
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
    curve_policy = record.get("native_curve_interpolation")
    if curve_policy:
        apply_curve_policy(tree, curve_policy)
    additions = record.get("native_reconstruction_additions", [])
    if additions:
        producer = tree.getroot().find("producer")
        if producer is None:
            raise ValueError(f"missing producer for reconstruction additions: {exact_name}")
        for addition in additions:
            service = addition.get("service")
            properties = addition.get("properties")
            if not isinstance(service, str) or not service.startswith("kdenlive_") or not isinstance(properties, dict):
                raise ValueError(f"invalid native reconstruction addition: {exact_name}")
            filter_element = ET.Element("filter", {"in": str(source_in), "out": str(source_in + frames - 1)})
            all_properties = {
                "mlt_service": service,
                "native_event_frames": frames,
                "native_nominal_frames": record["nominal_frames"],
                "native_event_role": record["event_variant"],
                "native_curve_start": 0,
                "native_curve_end": 1,
                **properties,
            }
            for key, value in all_properties.items():
                text = json.dumps(value, separators=(",", ":")) if key == "native_curves" and isinstance(value, dict) else str(value)
                ET.SubElement(filter_element, "property", {"name": key}).text = text
            insert_before = addition.get("insert_before_service")
            if insert_before:
                target = next((index for index, node in enumerate(producer.findall("filter"))
                               if next((prop.text for prop in node.findall("property")
                                        if prop.get("name") == "mlt_service"), None) == insert_before), None)
                if target is None:
                    raise ValueError(f"reconstruction insertion service {insert_before} is absent: {exact_name}")
                producer.insert(target, filter_element)
            else:
                producer.append(filter_element)
    if record.get("native_curve_policy") == "opticalcom-bubble-cut-fit-v1":
        _apply_opticalcom_bubble_cut_fit(tree, record["event_variant"])
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
