#!/usr/bin/env python3
"""Create an isolated MLT fixture for testing the native bubble component.

This fixture deliberately removes sibling effects after requiring and decoding
the complete preset source chain. It verifies the renderer independently; it is
not a whole-transition fixture and must never be used as preset delivery proof.
"""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from create_supported_chain_fixture import build as build_full_chain


def build(inventory: dict, exact_name: str, footage: Path, source_in: int, frames: int,
          width: int, height: int, fps_num: int, fps_den: int) -> ET.ElementTree:
    tree = build_full_chain(inventory, exact_name, footage, source_in, frames,
                            width, height, fps_num, fps_den)
    producer = next(item for item in tree.getroot().findall("producer") if item.get("id") == "source")
    retained = []
    for child in list(producer):
        if child.tag != "filter":
            continue
        service = child.find("property[@name='mlt_service']")
        if service is not None and service.text == "kdenlive_warp_bubble2":
            retained.append(child)
        else:
            producer.remove(child)
    if len(retained) != 1:
        raise ValueError(f"expected exactly one decoded Bubble Pattern Warp component, found {len(retained)}")
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
    parser.add_argument("--fps-num", type=int, default=60)
    parser.add_argument("--fps-den", type=int, default=1)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    tree = build(inventory, args.exact_name, args.footage, args.source_in, args.frames,
                 args.width, args.height, args.fps_num, args.fps_den)
    ET.indent(tree)
    tree.write(args.output, encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    main()
