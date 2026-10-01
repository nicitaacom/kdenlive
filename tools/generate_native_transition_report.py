#!/usr/bin/env python3
"""Generate a human-readable per-record view from the inventory source of truth."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from generate_native_transition_catalog import aliases_for_record
from generate_native_transition_render_index import strict_smoothness_counts


def table(inventory: dict) -> str:
    records = [record for package in inventory["packages"] for record in package["records"]]
    counts = {status: sum(record["status"] == status and record["scope"] == "transition"
                          for record in records) for status in ("Implemented", "Equivalent", "Partial", "Pending")}
    strict = strict_smoothness_counts([record for record in records if record["scope"] == "transition"])
    lines = [
        "# Native transition source catalog",
        "",
        "Generated from [native-transition-inventory.json](native-transition-inventory.json). Do not edit statuses here; regenerate after updating the inventory.",
        "",
        f"Completed under the current frame-by-frame easing, endpoint, paired-cut, and delivery criteria: **{strict['passed']}/{strict['total']} transitions**. "
        f"The inventory's renderer/editability labels are **{counts['Implemented']} Implemented, {counts['Equivalent']} Equivalent, "
        f"{counts['Partial']} Partial, {counts['Pending']} Pending**; they are not completion counts under the current criteria. "
        f"Nominal real-footage candidate MP4s and all-frame contacts are available for **{sum(isinstance(record.get('catalog_nominal_render'), dict) for record in records if record['scope'] == 'transition')}/{strict['total']}** identities; this is render coverage, not completed/total. "
        "Records without a numbered event role or nominal duration are classified as standalone effects/looks and remain inventoried outside transition implementation scope.",
        "",
        "Equivalent rows are editable native reconstructions with nominal grid and real-footage renders. Partial rows are applicable, "
        "clearly disclosed reconstructions with one or more source components omitted; they are not full-chain equivalents. "
        "No row has passed the current full smoothness and coordinated-cut acceptance gate. Source interpolation codes and proprietary "
        "kernels remain unresolved; see the [validation report]"
        "(native-transition-validation.md) for shared editing and export checks. Pending rows can be searched "
        "and dragged, but a drag gesture does not imply the stack was inserted. The source-chain identifiers do "
        "not imply that proprietary plugins are installed.",
        "",
        "| Package / index | Original name | Source UUID | Frames / role | Ordered source chain | Native services | Status / scope | Evidence | Browser search terms |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for package in inventory["packages"]:
        for record in package["records"]:
            chain = " → ".join(component["vendor_id"].rsplit(".", 1)[-1].rstrip("}")
                               for component in record["components"])
            native = " → ".join(component["native_component"]["service"] if component["native_component"] else "?"
                                for component in record["components"])
            aliases = "; ".join(aliases_for_record(record)) if record["scope"] == "transition" else "—"
            evidence_links = [
                f"[{item['kind']}]({item['contact_sheet']})" for item in record["validation_evidence"]
                if isinstance(item, dict) and item.get("contact_sheet")
            ]
            current_render = record.get("catalog_nominal_render")
            if isinstance(current_render, dict):
                if current_render.get("mp4"):
                    evidence_links.insert(0, f"[60 fps nominal candidate MP4]({current_render['mp4']})")
                if current_render.get("contact_sheet"):
                    evidence_links.insert(1, f"[all-frame contact]({current_render['contact_sheet']})")
            evidence = " ".join(evidence_links) or "—"
            cells = [f"{package['package']} #{record['record_index']}", record["exact_name"],
                     record["source_identifier"],
                     f"{record['nominal_frames'] if record['nominal_frames'] is not None else '?'} / {record['event_variant'] or '?'}",
                     chain, native, f"{record['status']} / {record['scope']}", evidence, aliases]
            lines.append("| " + " | ".join(str(cell).replace("|", "\\|") for cell in cells) + " |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    args.output.write_text(table(inventory), encoding="utf-8")


if __name__ == "__main__":
    main()
