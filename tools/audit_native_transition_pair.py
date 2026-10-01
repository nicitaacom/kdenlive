#!/usr/bin/env python3
"""Compare a paired native transition render with its matched clean baseline.

This audit measures every decoded frame and writes a labeled all-frame JPEG.
It distinguishes a frame-distinctness screen from source fidelity and easing;
the latter still requires the marked-grid contact sheets and human review.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat, ImageDraw


def frames_for(stem: Path) -> list[Path]:
    return sorted(stem.parent.glob(stem.name + "-[0-9][0-9][0-9].png"))


def validate_frame_sequence(paths: list[Path], label: str) -> None:
    """Require zero-based contiguous names so timeline labels match frames."""
    indices = [int(path.stem.rsplit("-", 1)[1]) for path in paths]
    expected = list(range(len(paths)))
    if indices != expected:
        first = indices[0] if indices else None
        raise ValueError(
            f"{label} frame sequence must start at 000 and be contiguous; "
            f"found {len(indices)} frames starting at {first}"
        )


def rgb_mae(left: Image.Image, right: Image.Image) -> float:
    stats = ImageStat.Stat(ImageChops.difference(left.convert("RGB"), right.convert("RGB")))
    return sum(stats.mean) / 3.0


def changed_fraction(left: Image.Image, right: Image.Image, threshold: int = 20) -> float:
    diff = ImageChops.difference(left.convert("RGB"), right.convert("RGB"))
    pixels = diff.get_flattened_data()
    changed = sum(1 for pixel in pixels if max(pixel) > threshold)
    return changed / max(1, diff.width * diff.height)


def black_edge_fraction(image: Image.Image, edge_width: int = 8) -> float:
    rgb = image.convert("RGB")
    width, height = rgb.size
    edge = min(edge_width, width // 4)
    pixels = rgb.load()
    black = sum(
        1
        for y in range(height)
        for x in (*range(edge), *range(width - edge, width))
        if max(pixels[x, y]) < 8
    )
    return black / max(1, 2 * edge * height)


def continuous_black_edge_columns(image: Image.Image, threshold: float = 0.95) -> dict[str, int]:
    """Count consecutive near-black columns touching each edge."""
    rgb = image.convert("RGB")
    width, height = rgb.size
    pixels = rgb.load()
    ratios = [sum(max(pixels[x, y]) < 8 for y in range(height)) / height for x in range(width)]
    result = {}
    for side, indices in (("left", range(width)), ("right", range(width - 1, -1, -1))):
        count = 0
        for x in indices:
            if ratios[x] < threshold:
                break
            count += 1
        result[side] = count
    return result


def summarize(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "median": None, "max": None}
    ordered = sorted(values)
    middle = len(ordered) // 2
    median = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    return {"min": ordered[0], "median": median, "max": ordered[-1]}


def audit(candidate_stem: Path, baseline_stem: Path, outgoing_start: int,
          event_frames: int, output_json: Path, contact_sheet_path: Path,
          incoming_event_frames: int | None = None,
          fps_num: int = 60, fps_den: int = 1) -> dict:
    incoming_frames = event_frames if incoming_event_frames is None else incoming_event_frames
    if outgoing_start < 0 or event_frames < 1 or incoming_frames < 1 or fps_num < 1 or fps_den < 1:
        raise ValueError("context must be nonnegative and both event lengths must be positive")
    candidate_paths = frames_for(candidate_stem)
    baseline_paths = frames_for(baseline_stem)
    validate_frame_sequence(candidate_paths, "candidate")
    validate_frame_sequence(baseline_paths, "baseline")
    if len(candidate_paths) != len(baseline_paths):
        raise ValueError(f"candidate/baseline frame-count mismatch: {len(candidate_paths)} vs {len(baseline_paths)}")
    incoming_start = outgoing_start + event_frames
    post_context_start = incoming_start + incoming_frames
    expected = post_context_start + outgoing_start
    if len(candidate_paths) != expected:
        raise ValueError(f"expected {expected} frames (context + pair + context), got {len(candidate_paths)}")
    candidate = [Image.open(path).convert("RGB") for path in candidate_paths]
    baseline = [Image.open(path).convert("RGB") for path in baseline_paths]
    if any(image.size != candidate[0].size for image in (*candidate, *baseline)):
        raise ValueError("all candidate and baseline frames must have the same dimensions")

    per_frame = []
    for index, (actual, clean) in enumerate(zip(candidate, baseline)):
        prev_mae = rgb_mae(actual, candidate[index - 1]) if index else None
        prev_changed_fraction = changed_fraction(actual, candidate[index - 1]) if index else None
        candidate_black_columns = continuous_black_edge_columns(actual)
        baseline_black_columns = continuous_black_edge_columns(clean)
        per_frame.append({
            "timeline_frame": index,
            "time_seconds": index * fps_den / fps_num,
            "region": ("pre-context" if index < outgoing_start else
                       "outgoing" if index < incoming_start else
                       "incoming" if index < post_context_start else "post-context"),
            "candidate_vs_baseline_rgb_mae": rgb_mae(actual, clean),
            "changed_pixel_fraction_over_20_rgb": changed_fraction(actual, clean),
            "candidate_black_edge_fraction": black_edge_fraction(actual),
            "baseline_black_edge_fraction": black_edge_fraction(clean),
            "candidate_continuous_black_edge_columns": candidate_black_columns,
            "baseline_continuous_black_edge_columns": baseline_black_columns,
            "adjacent_candidate_rgb_mae": prev_mae,
            "adjacent_changed_pixel_fraction_over_20_rgb": prev_changed_fraction,
            "differs_from_previous": None if index == 0 else ImageChops.difference(actual, candidate[index - 1]).getbbox() is not None,
        })

    event_summaries = {}
    for role, start, length in (("outgoing", outgoing_start, event_frames),
                                ("incoming", incoming_start, incoming_frames)):
        end = start + length
        records = per_frame[start:end]
        adjacent = records[1:]
        event_summaries[role] = {
            "first_timeline_frame": start,
            "last_timeline_frame": end - 1,
            "rendered_frames": len(records),
            "adjacent_pairs": len(adjacent),
            "identical_adjacent_pairs": sum(not item["differs_from_previous"] for item in adjacent),
            "all_adjacent_pairs_differ": all(item["differs_from_previous"] for item in adjacent),
            "adjacent_rgb_mae": summarize([item["adjacent_candidate_rgb_mae"] for item in adjacent]),
            "adjacent_changed_pixel_fraction_over_20_rgb": summarize(
                [item["adjacent_changed_pixel_fraction_over_20_rgb"] for item in adjacent]),
            "changed_pixel_fraction_over_20_rgb": summarize([item["changed_pixel_fraction_over_20_rgb"] for item in records]),
            "candidate_vs_baseline_rgb_mae": {
                "start": records[0]["candidate_vs_baseline_rgb_mae"],
                "middle": records[len(records) // 2]["candidate_vs_baseline_rgb_mae"],
                "end": records[-1]["candidate_vs_baseline_rgb_mae"],
                "all_frames": summarize([item["candidate_vs_baseline_rgb_mae"] for item in records]),
            },
            "max_added_black_edge_fraction": max(
                item["candidate_black_edge_fraction"] - item["baseline_black_edge_fraction"] for item in records),
            "max_added_continuous_black_edge_columns": max(
                max(item["candidate_continuous_black_edge_columns"][side]
                    - item["baseline_continuous_black_edge_columns"][side] for item in records)
                for side in ("left", "right")),
        }

    context_checks = {
        "pre_context_frames_identical_to_baseline": all(
            per_frame[index]["candidate_vs_baseline_rgb_mae"] == 0 for index in range(outgoing_start)),
        "post_context_frames_identical_to_baseline": all(
            per_frame[index]["candidate_vs_baseline_rgb_mae"] == 0
            for index in range(post_context_start, expected)),
    }

    tile_w, tile_h, columns, label_h, title_h = 160, 90, 10, 18, 28
    rows = (expected + columns - 1) // columns
    sheet = Image.new("RGB", (columns * tile_w, title_h + rows * (tile_h + label_h)), (25, 25, 25))
    draw = ImageDraw.Draw(sheet)
    cut_left = incoming_start - 1
    cut_right = incoming_start
    cut_text = (f"{fps_num}/{fps_den} fps | {event_frames} outgoing + {incoming_frames} incoming frames | "
                f"cut between f{cut_left:03d} ({cut_left * fps_den / fps_num:.3f}s) and "
                f"f{cut_right:03d} ({cut_right * fps_den / fps_num:.3f}s)")
    draw.text((4, 4), cut_text, fill=(240, 240, 240))
    for index, image in enumerate(candidate):
        x = (index % columns) * tile_w
        y = title_h + (index // columns) * (tile_h + label_h)
        if outgoing_start <= index < outgoing_start + event_frames:
            color = (255, 194, 40)
            label = f"OUT {index - outgoing_start + 1:02d}/{event_frames:02d} f{index:03d} {per_frame[index]['time_seconds']:.3f}s"
        elif incoming_start <= index < post_context_start:
            color = (60, 220, 220)
            label = f"IN {index - incoming_start + 1:02d}/{incoming_frames:02d} f{index:03d} {per_frame[index]['time_seconds']:.3f}s"
        else:
            color = (180, 180, 180)
            context_index = index + 1 if index < outgoing_start else index - post_context_start + 1
            region_label = "PRE" if index < outgoing_start else "POST"
            label = f"{region_label} {context_index:02d}/{outgoing_start:02d} f{index:03d} {per_frame[index]['time_seconds']:.3f}s"
        sheet.paste(image.resize((tile_w, tile_h), Image.Resampling.LANCZOS), (x, y + label_h))
        draw.rectangle((x, y, x + tile_w - 1, y + label_h - 1), fill=(35, 35, 35))
        draw.text((x + 3, y + 3), label, fill=color)
        if index in (cut_left, cut_right):
            draw.rectangle((x, y, x + tile_w - 1, y + label_h + tile_h - 1), outline=(255, 45, 45), width=2)
    contact_sheet_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(contact_sheet_path, quality=88, optimize=True)

    result = {
        "candidate_stem": str(candidate_stem.resolve()),
        "baseline_stem": str(baseline_stem.resolve()),
        "rendered_frames": expected,
        "resolution": list(candidate[0].size),
        "fps": {"numerator": fps_num, "denominator": fps_den},
        "context_frames_each_side": outgoing_start,
        "event_frames_each": event_frames,
        "incoming_event_frames": incoming_frames,
        "event_frame_mapping": {
            "outgoing": [outgoing_start, outgoing_start + event_frames - 1],
            "incoming": [incoming_start, post_context_start - 1],
        },
        "cut_location": {
            "between_timeline_frames": [cut_left, cut_right],
            "times_seconds": [cut_left * fps_den / fps_num, cut_right * fps_den / fps_num],
        },
        "context_checks": context_checks,
        "events": event_summaries,
        "frames": per_frame,
        "contact_sheet": str(contact_sheet_path.resolve()),
        "limitation": "Distinct frames and baseline differences do not prove source interpolation, perceptual easing, Sapphire pixel fidelity, Kdenlive UI application, or final-export parity.",
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_stem", type=Path, help="decoded frame path prefix, excluding -NNN.png")
    parser.add_argument("baseline_stem", type=Path, help="matched baseline frame path prefix")
    parser.add_argument("output_json", type=Path)
    parser.add_argument("contact_sheet", type=Path)
    parser.add_argument("--context-frames", type=int, default=8)
    parser.add_argument("--event-frames", type=int, default=62)
    parser.add_argument("--incoming-event-frames", type=int,
                        help="incoming event length when it differs from --event-frames")
    parser.add_argument("--fps-num", type=int, default=60)
    parser.add_argument("--fps-den", type=int, default=1)
    args = parser.parse_args()
    result = audit(args.candidate_stem, args.baseline_stem, args.context_frames,
                   args.event_frames, args.output_json, args.contact_sheet,
                   args.incoming_event_frames, args.fps_num, args.fps_den)
    for role, metrics in result["events"].items():
        print(f"{role}: {metrics['rendered_frames']} frames, "
              f"{metrics['identical_adjacent_pairs']} identical adjacent pairs, "
              f"adjacent RGB MAE median {metrics['adjacent_rgb_mae']['median']:.3f}")
    print(f"wrote {args.output_json} and {args.contact_sheet}")


if __name__ == "__main__":
    main()
