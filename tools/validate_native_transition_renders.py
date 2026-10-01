#!/usr/bin/env python3
"""Render reviewed native transition chains and collect per-frame evidence.

All video files and contact sheets are written outside the checkout. The MLT
fixture uses the same project-owned services and source-ordered properties as
the installed effect groups. GUI application and final delivery are separate
checks documented in the validation report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image, ImageChops, ImageDraw

from create_motion_curve_fixture import base_fixture
from create_supported_chain_fixture import build as build_fixture
from generate_native_transition_templates import active_records, apply_record_curve_policy


def run(command: list[str], log: Path, env: dict[str, str] | None = None,
        timeout_seconds: int = 600) -> None:
    with log.open("wb") as output:
        subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, env=env, check=True,
                       timeout=timeout_seconds)


def render(tree: ET.ElementTree, stem: Path, repository: Path,
           timeout_seconds: int) -> list[Path]:
    stem.parent.mkdir(parents=True, exist_ok=True)
    # A preset name or pilot stem can contain dots (for example "2.1-slide").
    # Append the media suffix instead of replacing the last dotted segment.
    fixture = Path(f"{stem}.mlt")
    video = Path(f"{stem}.mkv")
    tree.write(fixture, encoding="utf-8", xml_declaration=True)
    environment = os.environ.copy()
    environment["MLT_REPOSITORY"] = str(repository)
    run(["melt", str(fixture), "-consumer", f"avformat:{video}",
         "vcodec=ffv1", "an=1", "real_time=-1", "threads=1"],
        stem.with_suffix(".melt.log"), environment, timeout_seconds)
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
         "-threads", "1", "-fps_mode", "passthrough", "-start_number", "0",
         str(stem) + "-%03d.png"],
        stem.with_suffix(".decode.log"), timeout_seconds=timeout_seconds)
    return sorted(stem.parent.glob(stem.name + "-[0-9][0-9][0-9].png"))


def black_edge_fraction(image: Image.Image) -> float:
    rgb = image.convert("RGB")
    width, height = rgb.size
    edge = min(8, width // 4)
    pixels = rgb.load()
    count = 0
    for y in range(height):
        for x in list(range(edge)) + list(range(width - edge, width)):
            if max(pixels[x, y]) < 8:
                count += 1
    return count / max(1, 2 * edge * height)


def contact_sheet(frames: list[Path], output: Path) -> None:
    columns = min(5, len(frames))
    rows = (len(frames) + columns - 1) // columns
    size = (320, 180)
    sheet = Image.new("RGB", (columns * size[0], rows * size[1]), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(frames):
        frame = Image.open(path).convert("RGB")
        position = ((index % columns) * size[0], (index // columns) * size[1])
        sheet.paste(frame.resize(size), position)
        draw.text((position[0] + 6, position[1] + 6), str(index),
                  fill="white", stroke_width=1, stroke_fill="black")
    sheet.save(output)


def compare_frames(actual: list[Path], baseline: list[Path]) -> list[dict]:
    if len(actual) != len(baseline):
        raise ValueError(f"frame-count mismatch: {len(actual)} versus {len(baseline)}")
    measurements = []
    previous = None
    for index, (path, source_path) in enumerate(zip(actual, baseline)):
        frame = Image.open(path).convert("RGB")
        source = Image.open(source_path).convert("RGB")
        difference = ImageChops.difference(frame, source)
        changed = sum(1 for pixel in difference.get_flattened_data() if max(pixel) > 20)
        measurements.append({
            "frame": index,
            "changed_source_pixel_fraction": changed / (frame.width * frame.height),
            "black_edge_fraction": black_edge_fraction(frame),
            "baseline_black_edge_fraction": black_edge_fraction(source),
            "differs_from_previous": previous is not None and bool(ImageChops.difference(frame, previous).getbbox()),
        })
        previous = frame
    return measurements


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("media", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--repository", type=Path, default=Path("/home/kali/.local/kdenlive-compact/lib/mlt-7"))
    parser.add_argument("--source-in", type=int, default=30)
    parser.add_argument("--event-frames", type=int,
                        help="render this selected-event duration; defaults to each preset's nominal duration")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=360)
    parser.add_argument("--fps-num", type=int, default=60)
    parser.add_argument("--fps-den", type=int, default=1)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--names", nargs="+", help="render only these exact preset names")
    selection.add_argument("--all", action="store_true",
                           help="explicitly render every active preset, sequentially")
    parser.add_argument("--command-timeout-seconds", type=int, default=600,
                        help="maximum time for each melt render or ffmpeg decode (default: 600)")
    parser.add_argument("--nice", type=int, choices=range(0, 20), default=10,
                        help="lower the validator's CPU scheduling priority (default: 10)")
    args = parser.parse_args()
    if args.command_timeout_seconds < 1:
        parser.error("--command-timeout-seconds must be positive")
    if args.nice:
        os.nice(args.nice)
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    records = {record["exact_name"]: record for package in inventory["packages"] for record in package["records"]}
    names = args.names if args.names is not None else [record["exact_name"] for record in active_records(inventory)]
    args.output.mkdir(parents=True, exist_ok=True)
    baseline_frames: dict[int, list[Path]] = {}
    results = []
    for name in names:
        record = records[name]
        count = args.event_frames if args.event_frames is not None else record["nominal_frames"]
        if count < 1:
            raise ValueError("event duration must be at least one project frame")
        if count not in baseline_frames:
            tree, _ = base_fixture(args.media, args.source_in, count, args.width, args.height,
                                   args.fps_num, args.fps_den)
            baseline_frames[count] = render(tree, args.output / f"baseline-{count}", args.repository,
                                            args.command_timeout_seconds)
        tree = build_fixture(inventory, name, args.media, args.source_in, count,
                             args.width, args.height, args.fps_num, args.fps_den)
        apply_record_curve_policy(tree, record)
        stem = args.output / record["source_identifier"].strip("{}").lower()
        frames = render(tree, stem, args.repository, args.command_timeout_seconds)
        if len(frames) != count:
            raise ValueError(f"{name}: expected {count} frames, got {len(frames)}")
        sheet = stem.with_name(stem.name + "-contact.png")
        contact_sheet(frames, sheet)
        results.append({
            "source_identifier": record["source_identifier"], "name": name,
            "source_media": str(args.media), "source_sha256": sha256(args.media),
            "source_in": args.source_in, "profile": f"{args.width}x{args.height} {args.fps_num}/{args.fps_den}",
            "nominal_frames": record["nominal_frames"], "event_frames": count,
            "rendered_frames": len(frames),
            "services": [component["native_component"]["service"]
                         for index, component in enumerate(record["components"])
                         if index not in {item["component_index"]
                                          for item in record.get("native_reconstruction_exclusions", [])}],
            "excluded_source_components": record.get("native_reconstruction_exclusions", []),
            "video": str(stem.with_suffix(".mkv")), "contact_sheet": str(sheet),
            "measurements": compare_frames(frames, baseline_frames[count]),
        })
        (args.output / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"rendered {name}: {len(frames)} frames")


if __name__ == "__main__":
    main()
