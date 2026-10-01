#!/usr/bin/env python3
"""Render one disposable curve-policy pilot without activating a preset."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from create_supported_chain_fixture import build  # noqa: E402
from native_transition_curves import (apply_curve_policy,
                                      apply_effect_strength_ease_candidate,
                                      apply_endpoint_progress_candidate,
                                      apply_endpoint_progress_bezier_candidate,
                                      apply_smoothstep_endpoint_bezier_candidate,
                                      apply_reverse_time_monotone_candidate,
                                      apply_screen_space_arc_length_candidate,
                                      apply_shared_arc_length_time_candidate,
                                      apply_vegas_enum_order_candidate,
                                      apply_vegas_zero_hold_destination_candidate)  # noqa: E402
from validate_native_transition_renders import render  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("preset")
    parser.add_argument("footage", type=Path)
    parser.add_argument("output_stem", type=Path,
                        help="output path without extension; keep large renders outside the checkout")
    parser.add_argument("--inventory", type=Path, default=ROOT / "plans/native-transition-inventory.json")
    parser.add_argument("--source-in", type=int, default=30)
    parser.add_argument("--frames", type=int, default=63)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=360)
    parser.add_argument("--fps-num", type=int, default=60)
    parser.add_argument("--fps-den", type=int, default=1)
    parser.add_argument("--repository", type=Path,
                        default=Path("/home/kali/.local/kdenlive-compact/lib/mlt-7"))
    parser.add_argument("--command-timeout-seconds", type=int, default=600,
                        help="maximum runtime for each melt render and frame decode (default: 600)")
    parser.add_argument("--nice", type=int, choices=range(0, 20), default=10,
                        help="lower the validator's CPU scheduling priority (default: 10)")
    parser.add_argument("--smoothstep-ease-weight", type=float, default=0.65,
                        help="smoothstep share for endpoint-smoothstep-bezier-candidate (default: 0.65)")
    parser.add_argument("--fit-shutter-shift", action="store_true",
                        help="pilot an endpoint-tapered Shutter Shift curve; this changes the source's static behavior")
    parser.add_argument("--curve-policy", choices=("monotone-cubic-equivalent",
                                                     "shared-arc-length-ease-candidate",
                                                     "screen-space-arc-length-candidate",
                                                     "effect-strength-ease-candidate",
                                                     "endpoint-progress-fit-candidate",
                                                     "endpoint-progress-bezier-candidate",
                                                     "endpoint-smoothstep-bezier-candidate",
                                                     "reverse-time-monotone-candidate",
                                                     "vegas-enum-order-candidate",
                                                     "vegas-zero-hold-candidate",
                                                     "vegas-zero-hold-incoming-key-candidate"),
                        default="monotone-cubic-equivalent")
    args = parser.parse_args()
    if args.command_timeout_seconds < 1:
        parser.error("--command-timeout-seconds must be positive")
    if args.nice:
        os.nice(args.nice)

    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    tree = build(inventory, args.preset, args.footage, args.source_in, args.frames,
                 args.width, args.height, args.fps_num, args.fps_den)
    if args.curve_policy == "monotone-cubic-equivalent":
        apply_curve_policy(tree, args.curve_policy)
    elif args.curve_policy == "shared-arc-length-ease-candidate":
        apply_shared_arc_length_time_candidate(tree)
    elif args.curve_policy == "screen-space-arc-length-candidate":
        apply_screen_space_arc_length_candidate(tree, args.width, args.height)
    elif args.curve_policy == "effect-strength-ease-candidate":
        apply_effect_strength_ease_candidate(tree, args.width, args.height)
    elif args.curve_policy == "endpoint-progress-fit-candidate":
        apply_endpoint_progress_candidate(tree)
    elif args.curve_policy == "endpoint-progress-bezier-candidate":
        apply_endpoint_progress_bezier_candidate(tree)
    elif args.curve_policy == "endpoint-smoothstep-bezier-candidate":
        apply_smoothstep_endpoint_bezier_candidate(
            tree, ease_weight=args.smoothstep_ease_weight, fit_shutter_shift=args.fit_shutter_shift)
    elif args.curve_policy == "reverse-time-monotone-candidate":
        record = next(r for package in inventory["packages"] for r in package["records"]
                      if r["exact_name"] == args.preset)
        apply_reverse_time_monotone_candidate(tree, record)
    elif args.curve_policy == "vegas-zero-hold-incoming-key-candidate":
        record = next(r for package in inventory["packages"] for r in package["records"]
                      if r["exact_name"] == args.preset)
        apply_vegas_zero_hold_destination_candidate(tree, record)
    else:
        record = next(r for package in inventory["packages"] for r in package["records"]
                      if r["exact_name"] == args.preset)
        apply_vegas_enum_order_candidate(
            tree, record, zero_hold=args.curve_policy == "vegas-zero-hold-candidate")
    frames = render(tree, args.output_stem, args.repository, args.command_timeout_seconds)
    print(f"Rendered {len(frames)} frames to {args.output_stem.with_suffix('.mkv')}")


if __name__ == "__main__":
    main()
