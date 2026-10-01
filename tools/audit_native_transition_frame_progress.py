#!/usr/bin/env python3
"""Record a conservative exact-adjacent-frame screen from existing grid renders.

This audit only looks for byte-identical adjacent output frames in previously
measured nominal diagnostic-grid renders. Distinct frames do not prove that the
animation is perceptibly smooth or follows its source interpolation.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source_id(value: str | None) -> str:
    return (value or "").strip().strip("{}").lower()


def profile_score(profile: str) -> tuple[int, int, int]:
    match = re.search(r"(\d+)x(\d+).*?(\d+)/(\d+)", profile)
    if not match:
        return (0, 0, 0)
    width, height, fps_num, fps_den = map(int, match.groups())
    return (width * height, int(fps_den == 1 and fps_num == 60), width + height)


def result_records(path: Path) -> list[dict]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return [value] if isinstance(value, dict) else []


def collect_candidates(record: dict) -> list[dict]:
    candidates = []
    expected_frames = record.get("nominal_frames")
    for evidence in record.get("validation_evidence", []):
        kind = evidence.get("kind", "").lower()
        results_value = evidence.get("results")
        if "grid" not in kind or "nominal" not in kind or not isinstance(results_value, str):
            continue
        result_path = Path(results_value)
        if not result_path.is_absolute():
            result_path = ROOT / result_path
        for item in result_records(result_path):
            if source_id(item.get("source_identifier")) != source_id(record.get("source_identifier")):
                continue
            measurements = item.get("measurements")
            frame_count = item.get("rendered_frames")
            if not isinstance(measurements, list) or not isinstance(frame_count, int) or frame_count < 2:
                continue
            sequential = [m.get("frame") == i for i, m in enumerate(measurements) if isinstance(m, dict)]
            if len(measurements) != frame_count or not all(sequential):
                continue
            adjacent = measurements[1:]
            repeated = [m.get("frame") for m in adjacent if m.get("differs_from_previous") is False]
            score = profile_score(item.get("profile", ""))
            candidates.append({
                "state": "repeated-frame-found" if repeated else "distinct-frames-screened",
                "check": "exact-adjacent-output-pixel-equality",
                "frame_count": frame_count,
                "fps_profile": item.get("profile"),
                "nominal_frame_count_matches": frame_count == expected_frames,
                "all_adjacent_pairs_differ": not repeated,
                "repeated_frame_indices": repeated,
                "source_identifier": record.get("source_identifier"),
                "evidence_kind": evidence.get("kind"),
                "results_file": str(result_path.resolve()),
                "video": item.get("video"),
                "contact_sheet": item.get("contact_sheet"),
                "limitation": "Exact pixel inequality is only a frame-distinctness screen; it is not a perceptual easing or fidelity pass.",
                "_score": (score, int(frame_count == expected_frames), frame_count),
            })
    candidates.sort(key=lambda item: item["_score"], reverse=True)
    for candidate in candidates:
        del candidate["_score"]
    return candidates


def audit(inventory: dict, write: bool = False) -> Counter:
    totals: Counter = Counter()
    for package in inventory.get("packages", []):
        for record in package.get("records", []):
            if record.get("scope") != "transition":
                continue
            candidates = collect_candidates(record)
            if candidates:
                record["frame_progress_audit"] = candidates[0]
                totals[candidates[0]["state"]] += 1
            else:
                record.pop("frame_progress_audit", None)
                totals["not-screened"] += 1
    if write:
        output = ROOT / "plans/native-transition-inventory.json"
        output.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return totals


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-inventory", action="store_true",
                        help="store only the audit measurements in the machine inventory; never changes preset data or implementation status")
    args = parser.parse_args()
    inventory_path = ROOT / "plans/native-transition-inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    totals = audit(inventory, write=args.write_inventory)
    print(f"Transition records screened: {sum(totals.values())}")
    for state, count in sorted(totals.items()):
        print(f"{state}: {count}")
    if args.write_inventory:
        print(f"Updated audit metadata in {inventory_path}")
    else:
        print("Dry run only; use --write-inventory to persist per-record screen results.")


if __name__ == "__main__":
    main()
