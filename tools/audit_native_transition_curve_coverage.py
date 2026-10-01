#!/usr/bin/env python3
"""Inventory normalized key-time coverage without changing preset behavior.

This is a source-data screen only. An early-ending parameter may be intentional
while other components continue; the result is not a visual smoothness verdict.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EPSILON = 1e-6


def audit_record(record: dict) -> dict:
    tracks = []
    for component_index, component in enumerate(record.get("components") or []):
        for parameter in component.get("parameters") or []:
            animation = parameter.get("animation")
            points = (animation or {}).get("points") or []
            if len(points) < 2:
                continue
            positions = [float(point["normalized_event_position"]) for point in points]
            if any(not math.isfinite(position) or not 0.0 <= position <= 1.0 for position in positions):
                raise ValueError(f"{record.get('exact_name')}: invalid normalized position in {parameter.get('name')}")
            if any(right < left for left, right in zip(positions, positions[1:])):
                raise ValueError(f"{record.get('exact_name')}: unsorted key positions in {parameter.get('name')}")

            equal_key_value_segments = []
            for index, (left, right) in enumerate(zip(points, points[1:])):
                if left.get("value") == right.get("value"):
                    equal_key_value_segments.append({
                        "start": positions[index],
                        "end": positions[index + 1],
                        "normalized_span": positions[index + 1] - positions[index],
                    })

            first = positions[0]
            last = positions[-1]
            tracks.append({
                "component_index": component_index,
                "source_component": component.get("vendor_id"),
                "parameter": parameter.get("name"),
                "key_count": len(points),
                "first_key_position": first,
                "last_key_position": last,
                "leading_hold_fraction": first,
                "trailing_hold_fraction": max(0.0, 1.0 - last),
                "ends_at_event_endpoint": last >= 1.0 - EPSILON,
                "equal_key_value_segments": equal_key_value_segments,
            })

    latest = max((track["last_key_position"] for track in tracks), default=None)
    return {
        "schema_version": 1,
        "scope": "normalized source key positions; no rendering performed",
        "animated_parameter_curve_count": len(tracks),
        "curves_ending_before_event_endpoint": sum(not track["ends_at_event_endpoint"] for track in tracks),
        "curves_ending_at_least_10_percent_early": sum(track["trailing_hold_fraction"] >= 0.10 for track in tracks),
        "curves_with_equal_adjacent_key_values": sum(bool(track["equal_key_value_segments"]) for track in tracks),
        "equal_key_value_segment_count": sum(len(track["equal_key_value_segments"]) for track in tracks),
        "latest_animated_key_position": latest,
        "has_animated_key_at_event_endpoint": any(track["ends_at_event_endpoint"] for track in tracks),
        "all_animated_curves_end_at_event_endpoint": bool(tracks) and all(track["ends_at_event_endpoint"] for track in tracks),
        "tracks": tracks,
        "limitation": "An early-ending or flat parameter track can be deliberate while other source components continue. This audit is not rendered-motion evidence.",
    }


def audit_inventory(inventory: dict, write: bool = False) -> Counter:
    totals: Counter = Counter()
    for package in inventory.get("packages", []):
        for record in package.get("records", []):
            if record.get("scope") != "transition":
                continue
            result = audit_record(record)
            if write:
                record["curve_coverage_audit"] = result
            totals["records"] += 1
            totals["curves"] += result["animated_parameter_curve_count"]
            totals["early_curves"] += result["curves_ending_before_event_endpoint"]
            totals["early_10pct_curves"] += result["curves_ending_at_least_10_percent_early"]
            totals["equal_value_tracks"] += result["curves_with_equal_adjacent_key_values"]
            totals["equal_value_segments"] += result["equal_key_value_segment_count"]
            totals["records_with_any_early_track"] += result["curves_ending_before_event_endpoint"] > 0
            totals["records_without_endpoint_key"] += not result["has_animated_key_at_event_endpoint"]
    return totals


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-inventory", action="store_true",
                        help="store per-record source-curve measurements; never changes curves, templates, or implementation status")
    args = parser.parse_args()
    path = ROOT / "plans/native-transition-inventory.json"
    inventory = json.loads(path.read_text(encoding="utf-8"))
    totals = audit_inventory(inventory, write=args.write_inventory)
    if args.write_inventory:
        path.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Transition records scanned: {totals['records']}")
    print(f"Animated parameter curves: {totals['curves']}")
    print(f"Curves ending before event progress 1: {totals['early_curves']}")
    print(f"Curves ending at least 10% early: {totals['early_10pct_curves']}")
    print(f"Curves with equal adjacent key values: {totals['equal_value_tracks']} ({totals['equal_value_segments']} segments)")
    print(f"Records with any early-ending parameter track: {totals['records_with_any_early_track']}")
    print(f"Records with no animated key at event progress 1: {totals['records_without_endpoint_key']}")
    print("Audit scope: decoded source key positions only; no render or preset behavior changed.")
    if args.write_inventory:
        print(f"Updated {path}")


if __name__ == "__main__":
    main()
