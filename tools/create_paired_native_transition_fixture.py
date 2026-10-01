#!/usr/bin/env python3
"""Build a two-event MLT fixture with real footage on both sides of the cut.

The supplied preset groups are attached to their respective events. The clips
before and after the cut stay unfiltered so endpoint framing is visible.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from xml.etree import ElementTree as ET

from create_supported_chain_fixture import build
from native_transition_curves import (apply_endpoint_preserving_smoothstep_candidate,
                                      apply_curve_policy,
                                      apply_scroll_down_34_incoming_recovery_v1,
                                      apply_slide_down_33_cut_peak_candidate,
                                      apply_scroll_family_incoming_recovery_v1,
                                      apply_scroll_left_14_outgoing_shift_fit_v1,
                                      apply_scroll_left_14_incoming_recovery_v1,
                                      apply_scroll_right_27_incoming_recovery_v1,
                                      apply_scroll_right_27_cut_peak_candidate,
                                      apply_scroll_right_27_incoming_cubic_ease_out_v2,
                                      apply_screen_space_arc_length_candidate,
                                      apply_smoothstep_endpoint_bezier_candidate,
                                      apply_smooth_r_to_l_pair_candidate,
                                      apply_slide_right_phase_shutter_candidate,
                                      apply_zoom_spin_rsmb_incoming_ease_out_v1,
                                      apply_zoom_spin_rsmb_monotone_cubic_v1,
                                      apply_spin_11_2_11_3_incoming_recovery_v1,
                                      apply_spin_10_6_incoming_eventwide_v1,
                                      apply_zoom_out_10_5_incoming_ease_out_v1)


def make_fixture(inventory: dict, outgoing: str, incoming: str, first_media: Path,
                 second_media: Path, source_in: int, context: int, width: int,
                 height: int, fps_num: int, fps_den: int,
                 event_frames: int | None = None,
                 curve_policy: str = "native-linear",
                 ease_weight: float = 0.65,
                 fit_shutter_shift: bool = False,
                 effects_enabled: bool = True,
                 second_source_in: int | None = None,
                 incoming_event_frames: int | None = None) -> ET.ElementTree:
    records = {record["exact_name"]: record for package in inventory["packages"]
               for record in package["records"]}
    out_record = records[outgoing]
    in_record = records[incoming]
    if out_record["event_variant"] != "outgoing" or in_record["event_variant"] != "incoming":
        raise ValueError("choose an outgoing (1) preset followed by an incoming (2) preset")
    second_source_in = source_in if second_source_in is None else second_source_in
    if source_in < context or second_source_in < context or context < 1:
        raise ValueError("both source in-points must leave enough preceding context")
    outgoing_duration = (event_frames if event_frames is not None
                         else out_record["nominal_frames"])
    incoming_duration = (incoming_event_frames if incoming_event_frames is not None
                         else event_frames if event_frames is not None
                         else in_record["nominal_frames"])
    if outgoing_duration < 1 or incoming_duration < 1:
        raise ValueError("the event duration must be at least one project frame")
    if curve_policy not in ("native-linear", "endpoint-smoothstep-bezier-candidate",
                            "monotone-cubic-candidate",
                            "endpoint-preserving-smoothstep-candidate",
                            "screen-space-arc-length-candidate",
                            "slide-right-phase-shutter-candidate",
                            "slide-right-cut-acceleration-candidate",
                            "single-axis-slide-cut-acceleration-v1",
                            "single-axis-slide-cut-acceleration-v2",
                            "scroll-right-27-incoming-recovery-v1",
                            "scroll-right-27-cut-peak-v1",
                            "scroll-right-27-cut-peak-ease-out-v2",
                            "scroll-down-34-incoming-recovery-v1",
                            "slide-down-33-cut-peak-v1",
                            "scroll-left-14-incoming-recovery-v1",
                            "scroll-left-14-full-event-pair-v1",
                            "scroll-family-incoming-recovery-v1",
                            "zoom-spin-rsmb-monotone-cubic-v1",
                            "zoom-spin-rsmb-incoming-ease-out-v1",
                            "spin-11-2-11-3-incoming-recovery-v1",
                            "spin-10-6-incoming-eventwide-v1",
                            "smooth-r-to-l-role-ease-v1",
                            "zoom-out-10-5-incoming-ease-out-v1"):
        raise ValueError(f"unsupported curve policy: {curve_policy}")
    if fit_shutter_shift and curve_policy != "endpoint-smoothstep-bezier-candidate":
        raise ValueError("--fit-shutter-shift is only available for endpoint-smoothstep-bezier-candidate")

    first = build(inventory, outgoing, first_media, source_in,
                  outgoing_duration, width, height, fps_num, fps_den)
    second = build(inventory, incoming, second_media, second_source_in,
                   incoming_duration, width, height, fps_num, fps_den)
    if curve_policy == "endpoint-smoothstep-bezier-candidate":
        apply_smoothstep_endpoint_bezier_candidate(
            first, ease_weight=ease_weight, fit_shutter_shift=fit_shutter_shift)
        apply_smoothstep_endpoint_bezier_candidate(
            second, ease_weight=ease_weight, fit_shutter_shift=fit_shutter_shift)
    elif curve_policy == "monotone-cubic-candidate":
        # Keep every decoded normalized key time and value; only infer smooth,
        # shape-preserving Bezier handles between them for this diagnostic.
        apply_curve_policy(first, "monotone-cubic-equivalent")
        apply_curve_policy(second, "monotone-cubic-equivalent")
    elif curve_policy == "endpoint-preserving-smoothstep-candidate":
        apply_endpoint_preserving_smoothstep_candidate(first, ease_weight=ease_weight)
        apply_endpoint_preserving_smoothstep_candidate(second, ease_weight=ease_weight)
    elif curve_policy == "screen-space-arc-length-candidate":
        # The outgoing and incoming clips have separate curves and event-local
        # timing maps even though they share one timeline project.
        apply_screen_space_arc_length_candidate(first, width, height)
        apply_screen_space_arc_length_candidate(second, width, height)
    elif curve_policy == "slide-right-phase-shutter-candidate":
        apply_slide_right_phase_shutter_candidate(first)
        apply_slide_right_phase_shutter_candidate(second)
    elif curve_policy == "slide-right-cut-acceleration-candidate":
        apply_slide_right_phase_shutter_candidate(first, cut_acceleration=True)
        apply_slide_right_phase_shutter_candidate(second, cut_acceleration=True)
    elif curve_policy == "single-axis-slide-cut-acceleration-v1":
        apply_slide_right_phase_shutter_candidate(first, cut_acceleration=True)
        apply_slide_right_phase_shutter_candidate(second, cut_acceleration=True)
    elif curve_policy == "single-axis-slide-cut-acceleration-v2":
        apply_slide_right_phase_shutter_candidate(
            first, cut_acceleration=True, incoming_ease_weight=0.85)
        apply_slide_right_phase_shutter_candidate(
            second, cut_acceleration=True, incoming_ease_weight=0.85)
    elif curve_policy == "scroll-right-27-incoming-recovery-v1":
        if incoming != "2.7 Scroll Right (2) 20k":
            raise ValueError("this recovery policy is scoped to 2.7 Scroll Right (2) 20k")
        apply_scroll_right_27_incoming_recovery_v1(second, in_record)
    elif curve_policy == "scroll-right-27-cut-peak-v1":
        if (outgoing, incoming) != ("2.7 Scroll Right (1) 20k", "2.7 Scroll Right (2) 20k"):
            raise ValueError("the cut-peak policy requires the exact 2.7 Scroll Right pair")
        apply_scroll_right_27_cut_peak_candidate(first, out_record)
        apply_scroll_right_27_cut_peak_candidate(second, in_record)
    elif curve_policy == "scroll-right-27-cut-peak-ease-out-v2":
        if (outgoing, incoming) != ("2.7 Scroll Right (1) 20k", "2.7 Scroll Right (2) 20k"):
            raise ValueError("the cut-peak ease-out policy requires the exact 2.7 Scroll Right pair")
        apply_scroll_right_27_cut_peak_candidate(first, out_record)
        apply_scroll_right_27_cut_peak_candidate(second, in_record)
        apply_scroll_right_27_incoming_cubic_ease_out_v2(second, in_record)
    elif curve_policy == "smooth-r-to-l-role-ease-v1":
        if (outgoing, incoming) != ("1.1 Smooth R to L (1) 10k", "1.1 Smooth R to L (2) 10k"):
            raise ValueError("the role-easing policy requires the exact 1.1 Smooth R to L pair")
        apply_smooth_r_to_l_pair_candidate(first, out_record)
        apply_smooth_r_to_l_pair_candidate(second, in_record)
    elif curve_policy == "scroll-down-34-incoming-recovery-v1":
        if incoming != "3.4 Scroll Down (2) 20k":
            raise ValueError("this recovery policy is scoped to 3.4 Scroll Down (2) 20k")
        apply_scroll_down_34_incoming_recovery_v1(second, in_record)
    elif curve_policy == "slide-down-33-cut-peak-v1":
        if (outgoing, incoming) != ("3.3 Slide Down (1) 15k", "3.3 Slide Down (2) 15k"):
            raise ValueError("this peak fit requires the exact 3.3 Slide Down pair")
        apply_slide_down_33_cut_peak_candidate(first, out_record)
        apply_slide_down_33_cut_peak_candidate(second, in_record)
    elif curve_policy == "scroll-left-14-incoming-recovery-v1":
        if incoming != "1.4 Scroll Left (2) 20k":
            raise ValueError("this recovery policy is scoped to 1.4 Scroll Left (2) 20k")
        apply_scroll_left_14_incoming_recovery_v1(second, in_record)
    elif curve_policy == "scroll-left-14-full-event-pair-v1":
        if (outgoing, incoming) != ("1.4 Scroll Left (1) 20k", "1.4 Scroll Left (2) 20k"):
            raise ValueError("this timing fit requires the exact 1.4 Scroll Left pair")
        apply_scroll_left_14_outgoing_shift_fit_v1(first, out_record)
        apply_scroll_left_14_incoming_recovery_v1(second, in_record)
    elif curve_policy == "scroll-family-incoming-recovery-v1":
        apply_scroll_family_incoming_recovery_v1(second, in_record)
    elif curve_policy == "zoom-spin-rsmb-monotone-cubic-v1":
        supported_pairs = {
            ("10.8 Zoom Out CCW Spin (1) 15k", "10.8 Zoom Out CCW Spin (2) 15k"),
        }
        if (outgoing, incoming) not in supported_pairs:
            raise ValueError("the monotone RSMB policy requires the exact 10.8 counterclockwise pair")
        apply_zoom_spin_rsmb_monotone_cubic_v1(first, out_record)
        apply_zoom_spin_rsmb_monotone_cubic_v1(second, in_record)
    elif curve_policy == "zoom-spin-rsmb-incoming-ease-out-v1":
        if (outgoing, incoming) != (
                "10.9 Zoom Out CW Spin (1) 15k", "10.9 Zoom Out CW Spin (2) 15k"):
            raise ValueError("the ease-out RSMB policy requires the exact 10.9 clockwise pair")
        apply_zoom_spin_rsmb_monotone_cubic_v1(first, out_record)
        apply_zoom_spin_rsmb_incoming_ease_out_v1(second, in_record)
    elif curve_policy == "spin-11-2-11-3-incoming-recovery-v1":
        supported_pairs = {
            ("11.2 Spin ClockWise (1) 15k", "11.2 Spin ClockWise (2) 15k"),
            ("11.3 Spin CounterClockWise (1) 15k", "11.3 Spin CounterClockWise (2) 15k"),
        }
        if (outgoing, incoming) not in supported_pairs:
            raise ValueError("incoming spin recovery requires the exact 11.2 or 11.3 pair")
        apply_spin_11_2_11_3_incoming_recovery_v1(second, in_record)
    elif curve_policy == "spin-10-6-incoming-eventwide-v1":
        if (outgoing, incoming) != (
                "10.6 Zoom Out Spin ClockWise (1) 15k",
                "10.6 Zoom Out Spin ClockWise (2) 15k"):
            raise ValueError("event-wide spin recovery requires the exact 10.6 clockwise pair")
        apply_spin_10_6_incoming_eventwide_v1(second, in_record)
    elif curve_policy == "zoom-out-10-5-incoming-ease-out-v1":
        apply_curve_policy(first, "monotone-cubic-equivalent")
        apply_curve_policy(second, "monotone-cubic-equivalent")
        apply_zoom_out_10_5_incoming_ease_out_v1(second, in_record)
    if not effects_enabled:
        for producer in (first.getroot().find("producer"), second.getroot().find("producer")):
            if producer is not None:
                for effect in list(producer.findall("filter")):
                    producer.remove(effect)
    root = first.getroot()
    playlist = root.find("playlist")
    first_producer = root.find("producer")
    second_producer = second.getroot().find("producer")
    if playlist is None or first_producer is None or second_producer is None:
        raise ValueError("incomplete component fixture")
    first_producer.set("id", "outgoing_event")
    second_producer.set("id", "incoming_event")
    root.insert(list(root).index(playlist), second_producer)
    for name, footage in (("before", first_media), ("after", second_media)):
        producer = ET.Element("producer", {"id": name})
        ET.SubElement(producer, "property", {"name": "mlt_service"}).text = "avformat"
        ET.SubElement(producer, "property", {"name": "resource"}).text = str(footage.resolve())
        root.insert(list(root).index(playlist), producer)
    playlist.clear()
    for producer, first_frame, duration in (
        ("before", source_in - context, context),
        ("outgoing_event", source_in, outgoing_duration),
        ("incoming_event", second_source_in, incoming_duration),
        ("after", second_source_in + incoming_duration, context),
    ):
        ET.SubElement(playlist, "entry", {"producer": producer,
                                          "in": str(first_frame),
                                          "out": str(first_frame + duration - 1)})
    playlist.set("id", "event")
    return first


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("outgoing")
    parser.add_argument("incoming")
    parser.add_argument("first_media", type=Path)
    parser.add_argument("second_media", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source-in", type=int, default=30)
    parser.add_argument("--second-source-in", type=int,
                        help="incoming media in-point; defaults to --source-in")
    parser.add_argument("--context", type=int, default=5)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=360)
    parser.add_argument("--fps-num", type=int, default=60)
    parser.add_argument("--fps-den", type=int, default=1)
    parser.add_argument("--event-frames", type=int,
                        help="fit the outgoing animation and, unless separately set, the incoming animation across this many displayed project frames")
    parser.add_argument("--incoming-event-frames", type=int,
                        help="fit the incoming animation across a different displayed frame count")
    parser.add_argument("--curve-policy", choices=("native-linear", "endpoint-smoothstep-bezier-candidate",
                                                     "monotone-cubic-candidate",
                                                     "endpoint-preserving-smoothstep-candidate",
                                                     "screen-space-arc-length-candidate",
                                                     "slide-right-phase-shutter-candidate",
                                                     "slide-right-cut-acceleration-candidate",
                                                     "single-axis-slide-cut-acceleration-v1",
                                                     "single-axis-slide-cut-acceleration-v2",
                                                     "scroll-right-27-incoming-recovery-v1",
                                                     "scroll-right-27-cut-peak-v1",
                                                     "scroll-right-27-cut-peak-ease-out-v2",
                                                     "smooth-r-to-l-role-ease-v1",
                                                     "scroll-down-34-incoming-recovery-v1",
                                                     "slide-down-33-cut-peak-v1",
                                                     "scroll-left-14-incoming-recovery-v1",
                                                     "scroll-left-14-full-event-pair-v1",
                                                     "scroll-family-incoming-recovery-v1",
                                                     "zoom-spin-rsmb-monotone-cubic-v1",
                                                     "zoom-spin-rsmb-incoming-ease-out-v1",
                                                     "spin-11-2-11-3-incoming-recovery-v1",
                                                     "spin-10-6-incoming-eventwide-v1",
                                                     "zoom-out-10-5-incoming-ease-out-v1"),
                        default="native-linear")
    parser.add_argument("--smoothstep-ease-weight", type=float, default=0.65)
    parser.add_argument("--fit-shutter-shift", action="store_true",
                        help="pilot an endpoint-tapered Shutter Shift curve; this changes the source's static behavior")
    parser.add_argument("--no-effects", action="store_true",
                        help="write a matched clean two-scene baseline with only the two transition stacks removed")
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    fixture = make_fixture(inventory, args.outgoing, args.incoming, args.first_media,
                           args.second_media, args.source_in, args.context,
                           args.width, args.height, args.fps_num, args.fps_den,
                           args.event_frames, args.curve_policy,
                           args.smoothstep_ease_weight, args.fit_shutter_shift,
                           effects_enabled=not args.no_effects,
                           second_source_in=args.second_source_in,
                           incoming_event_frames=args.incoming_event_frames)
    ET.indent(fixture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fixture.write(args.output, encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    main()
