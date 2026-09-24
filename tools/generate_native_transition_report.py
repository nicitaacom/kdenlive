#!/usr/bin/env python3
"""Generate a human-readable per-record view from the inventory source of truth."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from generate_native_transition_catalog import aliases_for_record


def table(inventory: dict) -> str:
    lines = [
        "# Native transition source catalog",
        "",
        "Generated from [native-transition-inventory.json](native-transition-inventory.json). Do not edit statuses here; regenerate after updating the inventory.",
        "",
        "**Pending** means the record cannot be applied. No source record below has passed full-stack rendering, native editing, save/reopen, preview, and final-export validation. Components mentioned in the source-chain column are decoded vendor identifiers, not installed proprietary plugins. Candidate native services are partial reconstructions, not certified equivalents. Browser search terms are shown only for registered transition records. Native component rows are individually selectable; no complete source preset is yet editable.",
        "",
        "| Package / index | Original name | Source UUID | Frames / role | Ordered source chain | Candidate native services | Status / scope | Browser search terms |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for package in inventory["packages"]:
        for record in package["records"]:
            chain = " → ".join(component["vendor_id"].rsplit(".", 1)[-1].rstrip("}")
                               for component in record["components"])
            native = " → ".join(component["native_component"]["service"] if component["native_component"] else "?"
                                for component in record["components"])
            aliases = "; ".join(aliases_for_record(record)) if record["scope"] == "transition" else "—"
            cells = [f"{package['package']} #{record['record_index']}", record["exact_name"],
                     record["source_identifier"],
                     f"{record['nominal_frames'] if record['nominal_frames'] is not None else '?'} / {record['event_variant'] or '?'}",
                     chain, native, f"{record['status']} / {record['scope']}", aliases]
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
