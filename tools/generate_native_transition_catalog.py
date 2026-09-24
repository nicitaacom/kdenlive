#!/usr/bin/env python3
"""Generate non-applicable Effects Library entries from the audited inventory."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from xml.dom import minidom
from xml.etree import ElementTree as ET


def aliases_for_record(record: dict) -> list[str]:
    bare_name = re.sub(r"^\d+(?:\.\d+)?\s+", "", record["exact_name"])
    bare_name = re.sub(r"\s+\([12]\)\s+\d+k$", "", bare_name)
    vendor_ids = [component["vendor_id"].split(".")[-1].strip("}") for component in record["components"]]
    aliases = [record["exact_name"], bare_name]
    if record["nominal_frames"] is not None:
        aliases.append(bare_name + f" ({record['nominal_frames']}k)")
    aliases.extend(vendor_ids)
    return list(dict.fromkeys(aliases))


def build_catalog(inventory: dict) -> bytes:
    root = ET.Element("pendingeffects", {"xmlns": "https://www.kdenlive.org"})
    records = [record for package in inventory["packages"] for record in package["records"]
               if record["scope"] == "transition" and record["status"] == "Pending"]
    for record in records:
        source_id = record["source_identifier"]
        entry = ET.SubElement(root, "pendingeffect", {"id": "native.transition." + source_id.strip("{}").lower()})
        ET.SubElement(entry, "name").text = record["exact_name"]
        ET.SubElement(entry, "aliases").text = "; ".join(aliases_for_record(record))
        ET.SubElement(entry, "category").text = "Pending native transitions"
        ET.SubElement(entry, "description").text = (
            f"Source {source_id}; {record['event_variant']} event; nominal {record['nominal_frames']} frames. "
            "The complete animation is intended to fit the selected event. Native reconstruction and rendered "
            "validation are incomplete, so this preset cannot be applied."
        )
    xml = minidom.parseString(ET.tostring(root, encoding="utf-8")).toprettyxml(indent="  ", encoding="utf-8")
    return xml.replace(b"?>\n", b"?>\n<!DOCTYPE kpartgui>\n", 1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    args.output.write_bytes(build_catalog(inventory))


if __name__ == "__main__":
    main()
