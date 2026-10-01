#!/usr/bin/env python3
"""Audit nominal renders and attach their evidence to the source inventory.

This never changes a record's status. A complete MLT fixture render is useful
evidence, but browser application, editing, and source fidelity have separate
gates. Large videos remain outside the checkout.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


RENDER_SETS = {
    "grid": ("supported-121/grid", "rsmb-catalog/grid", "new-sixteen/grid", "new-eighteen/grid"),
    "real": ("supported-121/real", "rsmb-catalog/real", "new-eighteen/real"),
}


def audit(inventory: dict, render_root: Path) -> dict:
    records = {record["source_identifier"]: record for package in inventory["packages"]
               for record in package["records"] if record["scope"] == "transition"}
    if len(records) != 194:
        raise ValueError(f"expected 194 distinct transition identities, got {len(records)}")
    results = {}
    for medium, folders in RENDER_SETS.items():
        medium_results = {}
        for folder in folders:
            index = render_root / folder / "results.json"
            for item in json.loads(index.read_text(encoding="utf-8")):
                source_id = item["source_identifier"]
                if source_id in medium_results:
                    raise ValueError(f"duplicate {medium} render for {source_id}")
                record = records.get(source_id)
                if record is None or item["name"] != record["exact_name"]:
                    raise ValueError(f"render identity mismatch in {index}: {source_id}")
                expected_services = [component["native_component"]["service"]
                                     for component in record["components"]]
                if item["services"] != expected_services:
                    raise ValueError(f"incomplete or reordered source chain: {item['name']}")
                if item["nominal_frames"] != record["nominal_frames"] or item["rendered_frames"] != record["nominal_frames"]:
                    raise ValueError(f"frame-count mismatch: {item['name']}")
                measurements = item["measurements"]
                if [frame["frame"] for frame in measurements] != list(range(record["nominal_frames"])):
                    raise ValueError(f"missing measured frame: {item['name']}")
                for key in ("video", "contact_sheet"):
                    if not Path(item[key]).is_file():
                        raise ValueError(f"missing {key}: {item['name']}")
                if medium == "grid":
                    if not all(frame["differs_from_previous"] for frame in measurements[1:]):
                        raise ValueError(f"frozen diagnostic frame: {item['name']}")
                    if max(frame["changed_source_pixel_fraction"] for frame in measurements) < 0.05:
                        raise ValueError(f"no visible diagnostic change: {item['name']}")
                if any(frame["black_edge_fraction"] - frame["baseline_black_edge_fraction"] > 0.01
                       for frame in measurements):
                    raise ValueError(f"new black side border: {item['name']}")
                medium_results[source_id] = (item, index)
        results[medium] = medium_results
    if set(results["grid"]) != set(results["real"]):
        raise ValueError("grid and real nominal render identities differ")
    for source_id, record in records.items():
        if source_id not in results["grid"]:
            continue
        if record["status"] in ("Implemented", "Equivalent", "Partial"):
            # Preserve the already reviewed active-set artifacts.
            continue
        record["validation_evidence"] = [
            {"kind": f"provisional {medium} nominal MLT render",
             "video": item["video"], "contact_sheet": item["contact_sheet"],
             "results": str(index),
             "limitation": "Direct native MLT fixture; Kdenlive browser application and source fidelity remain unvalidated."}
            for medium in ("grid", "real")
            for item, index in (results[medium][source_id],)
        ]
    return {"transition_records": len(records), "rendered_grid_and_real": len(results["grid"]),
            "without_nominal_render": len(records) - len(results["grid"])}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("render_root", type=Path)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    summary = audit(inventory, args.render_root)
    args.inventory.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
