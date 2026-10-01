#!/usr/bin/env python3
"""Create source-ordered, whole-event native effect groups for validated records.

The inventory is the only authority for applicability. A record becomes active
only after its status and per-record render evidence are updated there.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from xml.dom import minidom
from xml.etree import ElementTree as ET

from create_supported_chain_fixture import build as build_fixture
from generate_native_transition_catalog import aliases_for_record
from native_transition_curves import (
    apply_curve_policy,
    apply_scroll_down_34_incoming_recovery_v1,
    apply_scroll_left_14_outgoing_shift_fit_v1,
    apply_slide_down_33_cut_peak_candidate,
    apply_scroll_left_14_incoming_recovery_v1,
    apply_scroll_family_incoming_recovery_v1,
    apply_scroll_right_27_cut_peak_candidate,
    apply_scroll_right_27_incoming_cubic_ease_out_v2,
    apply_scroll_right_27_incoming_recovery_v1,
    apply_zoom_out_10_5_incoming_ease_out_v1,
    apply_endpoint_progress_bezier_candidate,
    apply_endpoint_preserving_smoothstep_candidate,
    apply_slide_right_phase_shutter_candidate,
    apply_smooth_r_to_l_pair_candidate,
    apply_smoothstep_endpoint_bezier_candidate,
    apply_zoom_out_10_5_outgoing_monotone_cubic_v1,
    apply_zoom_spin_rsmb_incoming_ease_out_v1,
    apply_zoom_spin_rsmb_monotone_cubic_v1,
    apply_spin_11_2_11_3_incoming_recovery_v1,
    apply_spin_10_6_incoming_eventwide_v1,
)


def active_records(inventory: dict) -> list[dict]:
    return [record for package in inventory["packages"] for record in package["records"]
            if record["scope"] == "transition" and record["status"] in ("Implemented", "Equivalent", "Partial")]


def apply_record_curve_policy(fixture: ET.ElementTree, record: dict) -> None:
    """Apply the same record-scoped native curve policy used by active rows."""
    curve_policy = record.get("native_curve_policy")
    if curve_policy == "whole-event-endpoint-bezier-v1":
        apply_endpoint_progress_bezier_candidate(fixture)
    elif curve_policy == "whole-event-smoothstep-linear-floor-v1":
        apply_smoothstep_endpoint_bezier_candidate(fixture)
    elif curve_policy == "whole-event-endpoint-preserving-smoothstep40-v1":
        apply_endpoint_preserving_smoothstep_candidate(fixture, ease_weight=0.4)
    elif curve_policy == "smooth-r-to-l-role-ease-v1":
        apply_smooth_r_to_l_pair_candidate(fixture, record)
    elif curve_policy == "slide-right-phase-shutter-v1":
        apply_slide_right_phase_shutter_candidate(fixture)
    elif curve_policy == "slide-right-cut-acceleration-v1":
        apply_slide_right_phase_shutter_candidate(fixture, cut_acceleration=True)
    elif curve_policy == "single-axis-slide-cut-acceleration-v1":
        apply_slide_right_phase_shutter_candidate(fixture, cut_acceleration=True)
    elif curve_policy == "single-axis-slide-cut-acceleration-v2":
        apply_slide_right_phase_shutter_candidate(
            fixture, cut_acceleration=True, incoming_ease_weight=0.85)
    elif curve_policy == "scroll-right-27-incoming-recovery-v1":
        apply_scroll_right_27_incoming_recovery_v1(fixture, record)
    elif curve_policy == "scroll-right-27-cut-peak-v1":
        apply_scroll_right_27_cut_peak_candidate(fixture, record)
    elif curve_policy == "scroll-right-27-cut-peak-ease-out-v2":
        apply_scroll_right_27_cut_peak_candidate(fixture, record)
        if record["event_variant"] == "incoming":
            apply_scroll_right_27_incoming_cubic_ease_out_v2(fixture, record)
    elif curve_policy == "scroll-down-34-incoming-recovery-v1":
        apply_scroll_down_34_incoming_recovery_v1(fixture, record)
    elif curve_policy == "slide-down-33-cut-peak-v1":
        apply_slide_down_33_cut_peak_candidate(fixture, record, local_animation_keys=True)
    elif curve_policy == "scroll-left-14-incoming-recovery-v1":
        apply_scroll_left_14_incoming_recovery_v1(fixture, record)
    elif curve_policy == "scroll-left-14-outgoing-shift-fit-v1":
        apply_scroll_left_14_outgoing_shift_fit_v1(fixture, record)
    elif curve_policy == "scroll-family-incoming-recovery-v1":
        apply_scroll_family_incoming_recovery_v1(fixture, record)
    elif curve_policy == "zoom-out-10-5-outgoing-monotone-cubic-v1":
        apply_zoom_out_10_5_outgoing_monotone_cubic_v1(fixture, record)
    elif curve_policy == "zoom-out-10-5-incoming-ease-out-v1":
        apply_curve_policy(fixture, "monotone-cubic-equivalent")
        apply_zoom_out_10_5_incoming_ease_out_v1(fixture, record)
    elif curve_policy == "zoom-spin-rsmb-monotone-cubic-v1":
        apply_zoom_spin_rsmb_monotone_cubic_v1(fixture, record)
    elif curve_policy == "zoom-spin-rsmb-incoming-ease-out-v1":
        apply_zoom_spin_rsmb_incoming_ease_out_v1(fixture, record)
    elif curve_policy == "spin-11-2-11-3-incoming-recovery-v1":
        apply_spin_11_2_11_3_incoming_recovery_v1(fixture, record)
    elif curve_policy == "spin-10-6-incoming-eventwide-v1":
        apply_spin_10_6_incoming_eventwide_v1(fixture, record)
    elif curve_policy == "opticalcom-bubble-cut-fit-v1":
        # create_supported_chain_fixture applies this role-specific amplitude
        # scale while constructing the editable Bubble2 filter.
        pass
    elif curve_policy is not None:
        raise ValueError(f"unsupported native curve policy {curve_policy!r}: {record['exact_name']}")


def build_templates(inventory: dict) -> bytes:
    root = ET.Element("effecttemplates", {"xmlns": "https://www.kdenlive.org"})
    for record in active_records(inventory):
        name = record["exact_name"]
        if not record["validation_evidence"]:
            raise ValueError(f"active preset has no per-record evidence: {name}")
        nominal = record["nominal_frames"]
        if not isinstance(nominal, int) or nominal < 1:
            raise ValueError(f"invalid nominal duration: {name}")
        fixture = build_fixture(inventory, name, Path("/dev/null"), 30, nominal, 640, 360, 60, 1)
        apply_record_curve_policy(fixture, record)
        producer = fixture.getroot().find("producer")
        if producer is None:
            raise ValueError(f"missing producer: {name}")
        filters = producer.findall("filter")
        additions = record.get("native_reconstruction_additions", [])
        exclusions = record.get("native_reconstruction_exclusions", [])
        expected_filters = len(record["components"]) - len(exclusions) + len(additions)
        if len(filters) != expected_filters:
            raise ValueError(f"incomplete component chain: {name}: expected {expected_filters}, got {len(filters)}")
        role = "out" if record["event_variant"] == "outgoing" else "in"
        group = ET.SubElement(root, "effectgroup", {
            "id": "native.transition." + record["source_identifier"].strip("{}").lower(),
            "sourceId": record["source_identifier"],
            "nativePresetVersion": "1", "fitToEvent": "1",
            "transitionFrames": str(nominal), "transitionRole": role,
        })
        ET.SubElement(group, "name").text = name
        ET.SubElement(group, "aliases").text = "; ".join(aliases_for_record(record))
        ET.SubElement(group, "category").text = (
            "Partial native transition approximations" if record["status"] == "Partial" else "Native transitions"
        )
        curve_policy = record.get("native_curve_policy")
        interpolation = record.get("native_curve_interpolation", "linear-equivalent")
        if curve_policy == "opticalcom-bubble-cut-fit-v1":
            curve_description = (
                "Partial native reconstruction: applies the decoded S_WarpBubble2 field as an editable seeded bubble warp. "
                "The opaque preceding MBL2 component is omitted, so this stack does not reproduce its motion blur or finish. "
                "The 3x outgoing and 5.4x incoming amplitude scales are visual-fit values in native units, not decoded "
                "Sapphire controls."
            )
        elif curve_policy == "whole-event-endpoint-bezier-v1":
            curve_description = (
                "Uses a whole-event native Bezier progression for the decoded source endpoints. "
                "Intermediate source keys are not preserved; source interpolation remains unresolved."
            )
        elif curve_policy == "whole-event-smoothstep-linear-floor-v1":
            curve_description = (
                "Uses the candidate whole-event profile p(t)=0.35t+0.65(3t²−2t³) for the decoded "
                "endpoints. This keeps every frame moving while easing near both ends. Intermediate "
                "source keys are not preserved; source interpolation remains unresolved."
            )
        elif curve_policy == "whole-event-endpoint-preserving-smoothstep40-v1":
            curve_description = (
                "Preserves the decoded endpoint values and uses p(t)=0.6t+0.4(3t²−2t³), which eases "
                "while keeping a 60% motion floor. This is a native approximation; source interpolation "
                "and auxiliary tangent meanings remain unresolved."
            )
        elif curve_policy == "smooth-r-to-l-role-ease-v1":
            curve_description = (
                "Uses a per-record Smooth R to L easing trial: outgoing starts at neutral and moves toward "
                "the decoded Shift X endpoint while its fitted shutter opens; incoming preserves the decoded "
                "transform endpoints and eases toward normal framing while fitted shutter duration tapers to zero "
                "for a sharp final frame. The shutter taper is a native reconstruction because the decoded endpoint "
                "is one frame. This is not decoded Sapphire interpolation."
            )
        elif curve_policy == "slide-right-phase-shutter-v1":
            curve_description = (
                "Keeps the decoded Slide Right endpoints and source shutter-duration range, with generated quadratic "
                "event easing and a normalized shutter envelope peaking at the cut. A separately editable native "
                "motion-path blur gain of 8 amplifies the source shutter curve. Motion-path integration uses 16 "
                "subframe transform samples per output frame to create a more continuous smear; both values are "
                "native visual-fit settings, not decoded Sapphire controls. The source interpolation is unresolved. "
                "No warp is decoded in the source chain; any added native warp reconstruction is described separately."
            )
        elif curve_policy == "slide-right-cut-acceleration-v1":
            curve_description = (
                "Preserves the decoded horizontal-transform endpoints and source shutter-duration settings. "
                "Outgoing X motion remains accelerating into the cut; incoming X motion starts strongly and "
                "settles to the decoded endpoint. A shared normalized shutter envelope peaks at the cut. "
                "The editable native motion-path blur gain of 8 and 16 transform-path samples are visual-fit "
                "settings, not decoded Sapphire controls. Source interpolation remains unresolved; any RSMB "
                "component is reconstructed with native CPU block-flow blur. No extra sinusoidal warp is added."
            )
        elif curve_policy == "single-axis-slide-cut-acceleration-v1":
            curve_description = (
                "Preserves the decoded single-axis translation endpoints and source shutter-duration settings. "
                "Outgoing movement remains accelerating into the cut; incoming movement starts strongly and "
                "settles to the decoded endpoint. A shared normalized shutter envelope peaks at the cut. "
                "The editable native motion-path blur gain of 8 and 16 transform-path samples are visual-fit "
                "settings, not decoded Sapphire controls. Source interpolation remains unresolved."
            )
        elif curve_policy == "single-axis-slide-cut-acceleration-v2":
            curve_description = (
                "Preserves the decoded single-axis translation endpoints and source shutter-duration settings. "
                "Outgoing movement accelerates into the cut; incoming movement starts strongly and decelerates "
                "to the decoded endpoint with a 15% linear velocity floor to prevent a quantized still-frame "
                "tail. A shared normalized shutter envelope peaks at the cut. The editable native motion-path "
                "blur gain of 8 and 16 transform-path samples are visual-fit settings, not decoded Sapphire "
                "controls. Source interpolation remains unresolved."
            )
        elif curve_policy == "slide-down-33-cut-peak-v1":
            curve_description = (
                "Preserves the decoded vertical-motion curve and adds an editable vertical offset that builds to one "
                "frame height before the cut. The source shutter adjustment grows with that motion to produce broad "
                "vertical streaks; the incoming half starts at a matching displaced, blurred state and eases to its "
                "untreated endpoint. The offset and shutter adjustments are native visual-fit values, not decoded "
                "Sapphire settings. Curves are fitted over the complete event, and the renderer reflects source pixels "
                "at exposed borders. Source interpolation and exact Sapphire shutter behavior remain unresolved."
            )
        elif curve_policy == "scroll-right-27-incoming-recovery-v1":
            curve_description = (
                "Retimes the incoming decoded curve keys to span the full event and uses a 50% linear-floor / "
                "50% smoothstep native Bezier blend per segment. Decoded key values and their order are preserved; "
                "the source interpolation and auxiliary tangent meanings remain unresolved. This prevents the "
                "horizontal shift and fisheye recovery from reaching neutral early and holding through the final frames. "
                "Motion-path shutter duration eases from the decoded value at the cut to zero on the final incoming frame."
            )
        elif curve_policy == "scroll-right-27-cut-peak-v1":
            gain = 8 if record["event_variant"] == "outgoing" else 16
            curve_description = (
                "Uses the native 65% smoothstep endpoint profile to build decoded Scroll Right motion and Fisheye from "
                "neutral framing toward a cut-side peak; the incoming variant starts at its decoded displaced state and "
                "recovers to identity. Intermediate source keys are replaced because their serialized interpolation "
                "caused holds and reversals. The editable motion-path blur gain is " + str(gain) + " and the shutter uses "
                "32 samples. Those are visual-fit settings, not decoded Sapphire values. The renderer reflects actual "
                "source pixels, and the incoming Shake row remains in source order. Exact proprietary interpolation and "
                "tangent meanings remain unresolved."
            )
        elif curve_policy == "scroll-right-27-cut-peak-ease-out-v2":
            gain = 8 if record["event_variant"] == "outgoing" else 16
            curve_description = (
                "Uses the native 65% smoothstep endpoint profile to build decoded Scroll Right motion and Fisheye from "
                "neutral framing toward a cut-side peak. The incoming variant starts at its decoded displaced state, "
                "then uses a monotone cubic ease-out on every animated native control so it begins recovering immediately "
                "and settles gradually into identity on its final frame. Intermediate source keys are replaced because "
                "their serialized interpolation caused holds and reversals. The editable motion-path blur gain is " + str(gain) +
                " and the shutter uses 32 samples. These are native visual-fit settings, not decoded Sapphire values. "
                "The renderer reflects source pixels, and incoming Shake remains in source order. Exact proprietary "
                "interpolation and tangent meanings remain unresolved."
            )
        elif curve_policy == "scroll-down-34-incoming-recovery-v1":
            curve_description = (
                "Retimes the decoded incoming transform, shake-frequency, and fisheye curves across the full event, "
                "preserving decoded key values and order with a 50% linear-floor / 50% smoothstep native Bezier blend. "
                "The decoded Shift Y curve otherwise reaches neutral at 60% and holds. Native shake amplitude and "
                "motion-path shutter duration taper smoothly from their decoded static values to zero at the final "
                "incoming frame so the endpoint returns to untreated footage. Those two tapers are native visual-fit "
                "controls, not decoded Sapphire animation; source interpolation and auxiliary tangent meanings remain unresolved."
            )
        elif curve_policy == "scroll-left-14-incoming-recovery-v1":
            curve_description = (
                "Retimes the decoded incoming transform, animated shake, and fisheye curves across the full event, "
                "preserving decoded key values/order with a 50% linear-floor / 50% smoothstep native Bezier blend. "
                "The decoded Shift X curve otherwise reaches neutral at 60% and holds. The decoded static motion-path "
                "shutter duration tapers smoothly to zero at the final incoming frame. That taper and interpolation "
                "are native visual-fit choices, not decoded Sapphire animation; auxiliary tangent meanings remain unresolved."
            )
        elif curve_policy == "scroll-left-14-outgoing-shift-fit-v1":
            curve_description = (
                "Retimes the decoded outgoing transform and warp keys along a shared screen-space motion path, preserving "
                "their values and sparse editable keyframes while removing the idle interval before Shift X begins at "
                "normalized .4. This is an explicit native timing fit; source interpolation and tangent meanings remain unresolved."
            )
        elif curve_policy == "scroll-family-incoming-recovery-v1":
            curve_description = (
                "Applies a source-ID-scoped incoming scroll fit: decoded transform, shake, and fisheye key values/order "
                "are retained and retimed across the full event with a 50% linear-floor / 50% smoothstep native Bezier "
                "blend. Static motion-path shutter duration and any static Shake amplitude ease to zero on the final "
                "incoming frame. These timing changes are native visual-fit choices; Sapphire interpolation and tangent "
                "meanings remain unresolved."
            )
        elif curve_policy == "zoom-out-10-5-incoming-ease-out-v1":
            curve_description = (
                "Applies a source-ID-scoped native recovery fit to the incoming 10.5 Zoom Out Pinch variant. It preserves "
                "the decoded Z-distance, shutter-duration, and Pinch amount endpoints, but replaces the decoded Z-distance "
                "hold at normalized position 0.7541 with a whole-event cubic ease-out and spreads shutter recovery over "
                "the same interval. This is a visual reconstruction, not decoded Sapphire interpolation; source timing and "
                "tangent meanings remain unresolved. The source-ordered Motion Transform and Pinch/Punch components "
                "remain separately editable."
            )
        elif curve_policy == "zoom-out-10-5-outgoing-monotone-cubic-v1":
            curve_description = (
                "Uses monotone cubic native handles between the decoded outgoing Zoom Out Pinch key positions and values. "
                "This is the interpolation used by the paired 30/60 fps candidate; Sapphire interpolation and tangent "
                "meanings remain unresolved. The source-ordered Motion Transform and Pinch/Punch components remain "
                "separately editable."
            )
        elif curve_policy == "zoom-spin-rsmb-monotone-cubic-v1":
            curve_description = (
                "Uses shape-preserving monotone cubic native handles between all decoded Zoom Out Spin transform keys; "
                "source key positions and values are retained, while Sapphire interpolation and tangent meanings remain "
                "unresolved. The ordered RSMB component is reconstructed with the native CPU motion-vector blur service, "
                "which can differ from proprietary RSMB around occlusions, fine detail, and low-contrast motion. "
                "Motion Transform and motion-vector blur remain separate editable stack components."
            )
        elif curve_policy == "zoom-spin-rsmb-incoming-ease-out-v1":
            curve_description = (
                "For this 10.9 incoming variant, preserves the decoded Z-distance, rotation, and brightness endpoints but "
                "replaces the long decoded holds and intermediate keys with whole-event cubic ease-out curves. Shutter "
                "duration and the native RSMB blur envelope both taper to zero on the final event frame; the decoded "
                "shutter endpoint was 1.0. These timing and endpoint changes are a visual reconstruction, not decoded "
                "Sapphire interpolation; tangent meanings remain unresolved. The ordered RSMB component uses the native "
                "CPU motion-vector blur reconstruction, and both stack components remain separately editable."
            )
        elif curve_policy == "spin-11-2-11-3-incoming-recovery-v1":
            curve_description = (
                "For the 11.2/11.3 incoming spin rows, replaces the decoded late hold with a full-event ease-out from "
                "the source's 45-degree start to its neutral rotation, and tapers motion-path shutter duration to zero "
                "on the final frame. The 11.3 intermediate -45-degree key is retained in the inventory but omitted "
                "from the active curve because it creates a second rotation peak after the cut. This is an explicit "
                "visual-fit reconstruction; source interpolation and tangent meanings remain unresolved."
            )
        elif curve_policy == "spin-10-6-incoming-eventwide-v1":
            curve_description = (
                "For the 10.6 clockwise incoming spin, keeps the decoded zoom, rotation, and shutter endpoints but "
                "spreads them over the full selected event with a linear-floor smoothstep. The source's animated zoom "
                "and shutter start at normalized position 0.7541, which leaves the incoming event nearly still until "
                "late in playback. This event-wide retime is an explicit native visual fit; the original key positions "
                "remain in the inventory, and Sapphire interpolation and tangent meanings are unresolved."
            )
        elif interpolation == "monotone-cubic-equivalent":
            curve_description = (
                "Decoded key times and values are preserved; monotone cubic easing is used "
                "because the source interpolation codes remain unverified."
            )
        else:
            curve_description = (
                "Native reconstruction uses decoded values and linear segments because "
                "the source interpolation codes remain unverified."
            )
        if additions:
            addition_descriptions = [item.get("description", "") for item in additions]
            addition_descriptions = [item for item in addition_descriptions if item]
            if not addition_descriptions:
                raise ValueError(f"native reconstruction additions need a visible description: {name}")
            curve_description += " Additional native visual reconstruction: " + " ".join(addition_descriptions)
        reconstruction_note = record.get("native_reconstruction_note")
        if reconstruction_note:
            curve_description += " Native reconstruction note: " + reconstruction_note
        if exclusions:
            descriptions = [item.get("description", "") for item in exclusions]
            if any(not description.strip() for description in descriptions):
                raise ValueError(f"excluded native components need a visible description: {name}")
            curve_description += " Omitted source components: " + " ".join(descriptions)
        ET.SubElement(group, "description").text = (
            f"{record['event_variant'].capitalize()} event; nominal {nominal} project frames. "
            f"Fits the whole selected event. {curve_description} "
            "The source blur, warp, and shake algorithms have documented native differences."
        )
        for fixture_filter in filters:
            properties = {prop.attrib["name"]: prop.text for prop in fixture_filter.findall("property")}
            service = properties.pop("mlt_service")
            for derived in ("native_event_frames", "native_nominal_frames", "native_event_role"):
                properties.pop(derived, None)
            effect = ET.SubElement(group, "effect", {"id": service})
            for key, value in properties.items():
                if value is None:
                    raise ValueError(f"empty property {key}: {name}")
                ET.SubElement(effect, "property", {"name": key}).text = value
    xml = minidom.parseString(ET.tostring(root, encoding="utf-8")).toprettyxml(indent="  ", encoding="utf-8")
    return xml.replace(b"?>\n", b"?>\n<!DOCTYPE kpartgui>\n", 1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    args.output.write_bytes(build_templates(inventory))


if __name__ == "__main__":
    main()
