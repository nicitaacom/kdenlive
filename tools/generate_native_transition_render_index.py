#!/usr/bin/env python3
"""Generate one clickable index of native-transition renders and frame sheets."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]


def resolve_artifact(value: str) -> Path | None:
    path = Path(value)
    candidates = [path] if path.is_absolute() else [ROOT / path, ROOT / "plans" / path]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    # Older inventory entries may describe a generated sequence as
    # "contact-000-024.jpg through contact-150-150.jpg". Resolve that range
    # into the concrete sheets that are present on disk.
    if " through " in value:
        first = value.split(" through ", 1)[0]
        for candidate in ([Path(first)] if Path(first).is_absolute() else [ROOT / first, ROOT / "plans" / first]):
            parent = candidate.parent
            if parent.is_dir():
                matches = sorted(parent.glob("contact-*.jpg")) + sorted(parent.glob("contact-*.png"))
                if matches:
                    return parent.resolve()
    return None


def markdown_link(path: Path, label: str) -> str:
    resolved = path.resolve()
    try:
        target = resolved.relative_to(ROOT / "plans")
        link = quote(target.as_posix(), safe="/._-()")
    except ValueError:
        # Absolute links let the local Markdown viewer open the generated
        # cache artifact directly without copying large renders into the tree.
        link = quote(str(resolved), safe="/._-(){}")
    return f"[{label}]({link})"


def catalog_change_probe(record: dict) -> dict | None:
    """Read a nominal render's matched-clean pixel-change measurements.

    This is a prioritization screen only. The changed-pixel fraction is not a
    blur, perceptual-recognition, or acceptance metric.
    """
    render = record.get("catalog_nominal_render")
    if not isinstance(render, dict) or not isinstance(render.get("results"), str):
        return None
    results_path = resolve_artifact(render["results"])
    if results_path is None or not results_path.is_file():
        return None
    try:
        data = json.loads(results_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    rows = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
    expected_id = str(record.get("source_identifier", "")).strip("{}").lower()
    result = next((item for item in rows
                   if isinstance(item, dict)
                   and str(item.get("source_identifier", "")).strip("{}").lower() == expected_id), None)
    if not result:
        return None
    measurements = result.get("measurements")
    if not isinstance(measurements, list) or not measurements:
        return None
    try:
        values = [float(item["changed_source_pixel_fraction"]) for item in measurements]
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in values):
        return None
    sample_count = max(1, math.ceil(len(values) * 0.2))
    role = record.get("event_variant")
    if role == "outgoing":
        near_cut = values[-sample_count:]
    elif role == "incoming":
        near_cut = values[:sample_count]
    else:
        return None
    return {
        "role": role,
        "frames": len(values),
        "near_cut_mean_changed_fraction": sum(near_cut) / len(near_cut),
        "near_cut_max_changed_fraction": max(near_cut),
        "final_changed_fraction": values[-1],
    }


def catalog_change_screen(records: list[dict]) -> list[str]:
    """Render cautious late/early phase triage for available nominal candidates."""
    candidates = [(record, catalog_change_probe(record)) for record in records]
    candidates = [(record, probe) for record, probe in candidates if probe]
    outgoing = [(record, probe) for record, probe in candidates if probe["role"] == "outgoing"]
    incoming = [(record, probe) for record, probe in candidates if probe["role"] == "incoming"]
    if not candidates:
        return []
    mean_out = sum(p["near_cut_mean_changed_fraction"] for _, p in outgoing) / max(1, len(outgoing))
    mean_in = sum(p["near_cut_mean_changed_fraction"] for _, p in incoming) / max(1, len(incoming))
    lines = [
        "## Nominal near-cut pixel-change screen (triage only)",
        "",
        (f"The existing single-event real-footage renders contain matched-clean per-frame measurements for "
         f"{len(outgoing)} outgoing and {len(incoming)} incoming records. The average share of pixels that "
         f"differ from the same-time untreated frame by more than 20 RGB levels in the last/first 20% is "
         f"{mean_out:.1%}/{mean_in:.1%}, respectively. This helps prioritize weak-looking candidates; it is "
         "not a blur measure, recognition score, paired-cut result, or acceptance test. Source motion and the "
         "effect family can change this number substantially."),
        "",
        "The table lists the five lowest measured near-cut changes for each role. Incoming rows also show the "
        "last-frame difference from clean footage; a nonzero endpoint is a cue to inspect, not a judgment by itself.",
        "",
        "| Role | Source identity | Near-cut changed pixels | Incoming final-frame change | Render | Frames |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    for role, values in (("outgoing", outgoing), ("incoming", incoming)):
        for record, probe in sorted(values, key=lambda pair: pair[1]["near_cut_mean_changed_fraction"])[:5]:
            render = record["catalog_nominal_render"]
            video_path = resolve_artifact(render.get("mp4", ""))
            contact_path = resolve_artifact(render.get("contact_sheet", ""))
            video_link = markdown_link(video_path, "MP4") if video_path and video_path.is_file() else "—"
            contact_link = markdown_link(contact_path, "contact") if contact_path and contact_path.is_file() else "—"
            endpoint = (f"{probe['final_changed_fraction']:.1%}"
                        if role == "incoming" else "—")
            lines.append(
                f"| {role} | `{record.get('exact_name', 'unnamed')}` | "
                f"{probe['near_cut_mean_changed_fraction']:.1%} mean / "
                f"{probe['near_cut_max_changed_fraction']:.1%} max | {endpoint} | "
                f"{video_link} | {contact_link} ({probe['frames']} frames) |"
            )
    lines.append("")
    return lines


def evidence_assets(record: dict) -> tuple[list[tuple[str, Path]], list[tuple[str, Path]]]:
    current = record.get("catalog_nominal_render")
    videos: dict[str, tuple[int, str, Path]] = {}
    frames: dict[str, Path] = {}

    def add_video(value: object, label: str, priority: int) -> None:
        if not isinstance(value, str):
            return
        path = resolve_artifact(value)
        if path is None or not path.is_file() or path.suffix.lower() not in {".mp4", ".mkv", ".webm", ".mov"}:
            return
        if path.suffix.lower() != ".mp4" and label in {
                "MP4", "Kdenlive MP4", "Kdenlive preview MP4", "Candidate MP4",
                "Baseline MP4", "Source-linear MP4"}:
            label = path.suffix[1:].upper()
        previous = videos.get(str(path))
        if previous is None or priority < previous[0]:
            videos[str(path)] = (priority, label, path)

    def add_frames(value: object) -> None:
        values = [value] if isinstance(value, str) else value if isinstance(value, list) else []
        for item in values:
            if not isinstance(item, str):
                continue
            path = resolve_artifact(item)
            if path is None:
                continue
            if path.is_dir():
                for sheet in sorted(path.glob("contact-*.jpg")) + sorted(path.glob("contact-*.png")):
                    frames[str(sheet)] = sheet.resolve()
            elif path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                frames[str(path)] = path.resolve()

    if isinstance(current, dict):
        add_video(current.get("mp4"), "60 fps nominal candidate MP4", 0)
        add_frames(current.get("contact_sheet"))

    for evidence in record.get("validation_evidence", []):
        if evidence.get("superseded_by"):
            continue
        kind = evidence.get("kind", "render")
        kind_lower = kind.lower()
        is_renderjob_fixture = "renderjob helper" in kind_lower
        is_final_delivery = not is_renderjob_fixture and (
            "render project" in kind_lower or "installed kdenlive" in kind_lower or
            ("kdenlive" in kind_lower and ("final" in kind_lower or "delivery" in kind_lower)))
        priority = 0 if is_final_delivery else 1
        if is_renderjob_fixture:
            video_label = "Kdenlive RenderJob fixture MP4"
        elif "kdenlive" in kind_lower and "preview" in kind_lower:
            video_label = "Kdenlive preview MP4"
        elif is_final_delivery:
            video_label = "Kdenlive MP4"
        else:
            video_label = "MP4"
        add_video(evidence.get("video") or evidence.get("rendered_video") or evidence.get("rendered_mp4"),
                  video_label, priority)
        add_video(evidence.get("baseline_video") or evidence.get("baseline_mp4"),
                  "Baseline MP4", priority + 1)
        add_frames(evidence.get("contact_sheet"))
        add_frames(evidence.get("contact_sheets"))

    # Candidate and preview renders belong in the same master index even when
    # they have not been promoted to validation_evidence or accepted.
    review = record.get("smoothness_review", {})

    def collect_review(node: object, context: tuple[str, ...] = ()) -> None:
        if isinstance(node, dict):
            if node.get("superseded_by"):
                return
            for key, value in node.items():
                if key in {"video", "rendered_video", "rendered_mp4", "playable_mp4", "source_video", "baseline_video",
                           "baseline_mp4", "candidate_video", "candidate_video_30fps", "candidate_video_60fps",
                           "candidate_mp4", "source_linear_video"}:
                    custom_label = node.get(f"{key}_label")
                    if not custom_label and key not in {"baseline_video", "baseline_mp4"}:
                        custom_label = node.get("video_label") or node.get("asset_label")
                    user_accepted = "user_visual_acceptance_20260930" in context
                    if user_accepted:
                        label = "User-accepted approximation MP4"
                    elif isinstance(custom_label, str) and custom_label:
                        label = custom_label
                    elif key == "baseline_video":
                        label = "Baseline MP4" if Path(value).suffix.lower() == ".mp4" else "Baseline MKV" if Path(value).suffix.lower() == ".mkv" else "Baseline video"
                    elif key == "baseline_mp4":
                        label = "Baseline MP4 copy"
                    elif key == "source_linear_video":
                        label = "Source-linear MP4"
                    elif key == "playable_mp4":
                        label = "Playable MP4 copy"
                    elif key == "candidate_mp4":
                        label = "Candidate MP4"
                    elif "kdenlive_project_preview" in context:
                        label = "Kdenlive preview MP4"
                    elif key == "source_video":
                        label = "Candidate MP4"
                    else:
                        label = "Candidate MP4"
                    add_video(value, label, -1 if user_accepted else 2)
                elif key in {"contact_sheet", "contact_sheets", "all_frames_contact_sheet", "source_linear_contact_sheet"}:
                    add_frames(value)
                elif isinstance(value, (dict, list)):
                    collect_review(value, context + (key,))
        elif isinstance(node, list):
            for value in node:
                collect_review(value, context)

    collect_review(review)

    ordered_videos = [(label, path) for _, label, path in
                      sorted(videos.values(), key=lambda item: (item[0], str(item[2])))]
    ordered_frames = [(p.name, p) for p in sorted(frames.values(), key=lambda p: str(p))]
    return ordered_videos, ordered_frames


def progress_review_text(record: dict) -> str:
    smoothness = record.get("smoothness_review", {})
    review = smoothness.get("state", "not-reviewed")
    screen = record.get("frame_progress_audit", {}).get("state", "not-screened")
    visual_review = smoothness.get("latest_visual_review", {})
    review_text = {
        "candidate-not-accepted": "Candidate, not accepted",
        "passed": "Passed",
        "failed": "Failed",
        "not-reviewed": "Not reviewed",
    }.get(review, review)
    invalid_fixture = smoothness.get("paired_kdenlive_render_fixture_diagnostic_60fps_20260930", {})
    if invalid_fixture:
        incoming = invalid_fixture.get("evidence", {}).get("incoming_identical_adjacent_pairs", "?")
        return (
            f"Invalid 60 fps two-scene fixture, not a transition result; incoming clean baseline is a "
            f"checkerboard placeholder and the candidate has {incoming}/29 repeated incoming pairs. "
            "Fixture cause unresolved; do not accept or interpret the incoming effect"
        )
    user_acceptance = smoothness.get("user_visual_acceptance_20260930", {})
    if user_acceptance:
        return (
            "User accepted the horizontal X-motion + blur approximation; sine-wave warp removed. "
            "Kdenlive application-level edit, preview, persistence, and final-render checks remain open"
        )
    swish3d_pair = smoothness.get("swish3d_paired_two_scene_candidate_20261001", {})
    if swish3d_pair:
        role = record.get("event_variant")
        rates = swish3d_pair.get("rates", {})
        r30 = rates.get("30", {})
        r60 = rates.get("60", {})
        r60_distances = r60.get("role_baseline_distance_start_middle_end_rgb_mae", [])
        cut_distance = (r60_distances[-1] if role == "outgoing" and r60_distances else
                        r60_distances[0] if r60_distances else None)
        distance_text = f"; this role's cut-side baseline distance is {cut_distance:.1f} RGB MAE" if cut_distance is not None else ""
        wrapper = swish3d_pair.get("kdenlive_renderer_wrapper", {})
        wrapper_mae = wrapper.get("rgb_mae_against_direct_native_candidate", {}).get("mean")
        wrapper_text = (
            f"; installed Kdenlive RenderJob output matches the direct candidate at {wrapper_mae:.2f} mean RGB MAE"
            if isinstance(wrapper_mae, (int, float)) else ""
        )
        return (
            "Source-derived clip-local reconstruction; direct native MLT paired candidate, not GUI project-export acceptance; "
            f"{r30.get('outgoing_frames', '?')}+{r30.get('incoming_frames', '?')} affected frames at 30 fps and "
            f"{r60.get('outgoing_frames', '?')}+{r60.get('incoming_frames', '?')} at 60 fps (one second total); "
            f"zero repeated adjacent frames for this {role} role{distance_text}{wrapper_text}. "
            "The proprietary two-input blend/camera kernel and GUI-applied .kdenlive save/reopen/export parity remain unverified"
        )
    swish3d_single = smoothness.get("swish3d_local_approx_20261001", {})
    if swish3d_single:
        wrapper = swish3d_single.get("kdenlive_renderer_wrapper", {})
        metrics = wrapper.get("rgb_mae_against_direct_native_candidate", {})
        mae = metrics.get("mean")
        wrapper_text = f"; installed RenderJob output matches direct MLT at {mae:.2f} mean RGB MAE" if isinstance(mae, (int, float)) else ""
        return (
            f"Source-derived clip-local candidate, {wrapper.get('rendered_frames', '?')} nominal frames at 60 fps{wrapper_text}; "
            "the native group inserts and undoes through the EffectStackModel test. Kdenlive GUI project save/reopen/export remains unverified"
        )
    cut_acceleration_v2 = smoothness.get("paired_cut_acceleration_candidate_v2_20260930", {})
    if cut_acceleration_v2:
        role = record.get("event_variant")
        rates = cut_acceleration_v2.get("rates", {})
        real30 = rates.get("30", {}).get("real", {})
        real60 = rates.get("60", {}).get("real", {})
        grid60 = rates.get("60", {}).get("grid", {})
        event60 = real60.get("events", {}).get(role, {})
        grid_event = grid60.get("events", {}).get(role, {})
        end_values = event60.get("clean_baseline_distance_start_middle_end", [])
        end_text = (
            f"; real-source baseline distance {end_values[0]:.1f}/{end_values[1]:.1f}/{end_values[2]:.1f} RGB MAE"
            if len(end_values) == 3 else ""
        )
        return (
            f"Kdenlive RenderJob paired candidate, not accepted; "
            f"{real30.get('outgoing_frames', '?')}+{real30.get('incoming_frames', '?')} affected frames at 30 fps, "
            f"{real60.get('outgoing_frames', '?')}+{real60.get('incoming_frames', '?')} at 60 fps; "
            f"{event60.get('exact_adjacent_repeats', '?')} real-source and "
            f"{grid_event.get('exact_adjacent_repeats', '?')} static-grid repeated {role} frames{end_text}. "
            "Baseline-distance reversals remain; Effects UI application and edit/persistence checks are open"
        )
    diagonal_scroll = smoothness.get("paired_scroll_diagonal_candidate_20260930", {})
    if diagonal_scroll:
        role = record.get("event_variant")
        rate30 = diagonal_scroll.get("rates", {}).get("30", {})
        rate60 = diagonal_scroll.get("rates", {}).get("60", {})
        event60 = rate60.get("events", {}).get(role, {})
        endpoints = event60.get("clean_baseline_distance_start_middle_end", [])
        endpoint_text = (
            f"; 60 fps clean-baseline distance {endpoints[0]:.1f}/{endpoints[1]:.1f}/{endpoints[2]:.1f} RGB MAE"
            if len(endpoints) == 3 else ""
        )
        return (
            f"Direct native MLT paired scroll candidate, not accepted; "
            f"{rate30.get('outgoing_frames', '?')}+{rate30.get('incoming_frames', '?')} affected frames at 30 fps, "
            f"{rate60.get('outgoing_frames', '?')}+{rate60.get('incoming_frames', '?')} at 60 fps; "
            f"{event60.get('exact_adjacent_repeats', '?')} repeated {role} frames{endpoint_text}. "
            "The baseline-distance progression is non-monotone; Kdenlive editing and export checks remain open"
        )
    source_aligned_slide_right = smoothness.get("source_time_aligned_kdenlive_render_candidate_20260930", {})
    if source_aligned_slide_right:
        counts_30 = source_aligned_slide_right.get("event_frame_counts_30fps", {})
        counts_60 = source_aligned_slide_right.get("event_frame_counts", {})
        ui_drop_export = smoothness.get("effects_tab_drop_export_20260930", {})
        ui_note = (
            "Effects-tab drag/save and Kdenlive final export verified for nonzero source in-points; "
            "render matches the source-aligned candidate; parameter editing, undo/redo, reopen, "
            "preview, and source fidelity remain open"
            if ui_drop_export
            else "Effects editing and source fidelity remain open"
        )
        return (
            f"Kdenlive two-scene 30/60 fps candidates, not accepted; "
            f"30 fps {counts_30.get('outgoing', '?')}+{counts_30.get('incoming', '?')}, "
            f"60 fps {counts_60.get('outgoing', '?')}+{counts_60.get('incoming', '?')} affected frames (1 s each); "
            f"source-time ranges render visible motion and blur; {ui_note}"
        )
    peak_intensity_trial = smoothness.get("peak_intensity_trial_20260930", {})
    if peak_intensity_trial:
        metrics = peak_intensity_trial.get("event_metrics", {})
        outgoing = metrics.get("outgoing", {}).get("candidate_vs_baseline_rgb_mae", {})
        incoming = metrics.get("incoming", {}).get("candidate_vs_baseline_rgb_mae", {})
        out_peak = outgoing.get("end")
        in_peak = incoming.get("start")
        peak_text = (
            f"; last-outgoing/first-incoming clean-baseline RGB MAE {out_peak:.1f}/{in_peak:.1f}"
            if isinstance(out_peak, (int, float)) and isinstance(in_peak, (int, float))
            else ""
        )
        return (
            "Peak-smear intensity trial, not accepted; 60 fps only, "
            f"{peak_intensity_trial.get('outgoing_frames', '?')}+"
            f"{peak_intensity_trial.get('incoming_frames', '?')} affected frames (1 s total), "
            f"{peak_intensity_trial.get('curve_policy', 'peak shutter envelope')}"
            f"{peak_text}. 30 fps, marked-grid, Kdenlive edit/persistence, and final-export checks remain open"
        )
    slide_down_peak = smoothness.get("slide_down_33_cut_peak_candidate_20261001", {})
    if slide_down_peak:
        role = record.get("event_variant")
        rates = slide_down_peak.get("rates", {})
        helper = slide_down_peak.get("installed_kdenlive_render_helper_20261001", {})
        rate30 = rates.get("30", {})
        rate60 = rates.get("60", {})
        event60 = rate60.get("events", {}).get(role, {})
        peak = event60.get("clean_baseline_distance_start_middle_end", [])
        peak_text = (
            f"; 60 fps {role} clean-frame distance {peak[0]:.1f}/{peak[1]:.1f}/{peak[2]:.1f} RGB MAE"
            if len(peak) == 3 else ""
        )
        return (
            "Direct native MLT visual-fit candidate, not accepted; "
            f"one-second 30 fps {rate30.get('outgoing_frames', '?')}+{rate30.get('incoming_frames', '?')} and "
            f"60 fps {rate60.get('outgoing_frames', '?')}+{rate60.get('incoming_frames', '?')} frame pairs; "
            f"{event60.get('exact_adjacent_repeats', '?')} repeated {role} frames{peak_text}. "
            f"Installed kdenlive_render helper output was checked at both rates with mean RGB MAE "
            f"{helper.get('helper_vs_direct_decoded_rgb_mae', {}).get('30', '?')}/"
            f"{helper.get('helper_vs_direct_decoded_rgb_mae', {}).get('60', '?')} against direct MLT. "
            "The vertical offset and shutter controls are native approximations; saved-project editing, persistence, preview, and Render Project checks remain open"
        )
    wave_candidate = smoothness.get("wave_active_group_pair_30fps_candidate_20260929", {})
    if wave_candidate:
        counts = wave_candidate.get("event_frame_counts", {})
        evidence = wave_candidate.get("frame_evidence", {})
        outgoing = evidence.get("outgoing_first_and_last_mean_abs_rgb_mae_vs_clean", [])
        incoming = evidence.get("incoming_first_and_last_mean_abs_rgb_mae_vs_clean", [])
        if len(outgoing) == 2 and len(incoming) == 2:
            wave_candidate_60 = smoothness.get("wave_active_group_pair_60fps_candidate_20260929", {})
            if wave_candidate_60:
                counts_60 = wave_candidate_60.get("event_frame_counts", {})
                evidence_60 = wave_candidate_60.get("frame_evidence", {})
                outgoing_60 = evidence_60.get("outgoing_first_and_last_mean_abs_rgb_mae_vs_clean", [])
                incoming_60 = evidence_60.get("incoming_first_and_last_mean_abs_rgb_mae_vs_clean", [])
                if len(outgoing_60) == 2 and len(incoming_60) == 2:
                    return (
                        f"30/60 fps paired curved-band candidates, not accepted; "
                        f"{counts.get('outgoing', '?')}+{counts.get('incoming', '?')} frames at 30 and "
                        f"{counts_60.get('outgoing', '?')}+{counts_60.get('incoming', '?')} at 60; "
                        f"no exact repeats; MAE out {outgoing_60[0]:.1f}→{outgoing_60[1]:.1f}, "
                        f"in {incoming_60[0]:.1f}→{incoming_60[1]:.1f}; outgoing/incoming monotonic checks "
                        f"{evidence_60.get('outgoing_increasing_mae_intervals', '?')}/29 and "
                        f"{evidence_60.get('incoming_decreasing_mae_intervals', '?')}/29; "
                        "Kdenlive edit/render and visual peak checks remain open"
                    )
            return (
                f"30 fps paired curved-band candidate, not accepted; "
                f"{counts.get('outgoing', '?')} outgoing + {counts.get('incoming', '?')} incoming frames, "
                f"no exact repeats; baseline MAE out {outgoing[0]:.1f}→{outgoing[1]:.1f}, "
                f"in {incoming[0]:.1f}→{incoming[1]:.1f}; cut integration, 60 fps and Kdenlive edit/render checks remain open"
            )
    paired_curve_candidate = smoothness.get("paired_native_curve_candidate_20260930", {})
    if paired_curve_candidate:
        role = record.get("event_variant")
        rates = paired_curve_candidate.get("rates", {})
        rate30 = rates.get("30", {})
        rate60 = rates.get("60", {})
        event60 = rate60.get("event_metrics", {}).get(role, {})
        role_metrics = rate60.get(role, {})
        direction_counts = []
        for phase in ("outgoing", "incoming"):
            metrics = rate60.get(phase, {})
            expected = metrics.get("expected_direction_intervals")
            total = metrics.get("total_intervals")
            if expected is None or total is None:
                metrics = rate60.get("event_metrics", {}).get(phase, {})
                expected = metrics.get("expected_direction_intervals")
                total = metrics.get("total_intervals")
            if expected is not None and total is not None:
                direction_counts.append(f"{expected}/{total} {phase}")
        progression_text = (
            "; 60 fps source-distance trend " + ", ".join(direction_counts) + " intervals"
            if direction_counts else ""
        )
        cut = rate60.get("cut_boundary", {})
        cut_candidate = cut.get("candidate_adjacent_rgb_mae", cut.get("candidate_rgb_mae_at_320x180"))
        cut_baseline = cut.get("clean_baseline_adjacent_rgb_mae", cut.get("clean_baseline_rgb_mae_at_320x180"))
        cut_text = (
            f"; cut step {cut_candidate:.1f} vs {cut_baseline:.1f} clean RGB MAE"
            if isinstance(cut_candidate, (int, float)) and isinstance(cut_baseline, (int, float))
            else ""
        )
        return (
            "Direct MLT paired curve candidate, not accepted; "
            f"{rate30.get('outgoing_frames', '?')}+{rate30.get('incoming_frames', '?')} affected frames at 30 fps and "
            f"{rate60.get('outgoing_frames', '?')}+{rate60.get('incoming_frames', '?')} at 60 fps (1 s each); "
            f"{event60.get('exact_adjacent_repeats', role_metrics.get('exact_adjacent_repeats', '?'))} repeated {role} frames"
            f"{progression_text}{cut_text}. "
            "Kdenlive pair editing/export and source interpolation fidelity remain open"
        )
    if visual_review.get("outcome") == "visually-rejected":
        return "Visual candidate rejected"
    if review == "not-reviewed":
        review_text = {
            "distinct-frames-screened": "Distinct frames only; easing not reviewed",
            "repeated-frame-found": "Repeated frame found; not accepted",
            "not-screened": "Not reviewed",
        }.get(screen, review_text)

    slide_right_pair = smoothness.get("reference_shaped_two_scene_hard_cut_20260929", {})
    if slide_right_pair:
        role = record.get("event_variant")
        event = slide_right_pair.get("events", {}).get(role, {})
        cut = slide_right_pair.get("cut_boundary", {})
        candidate_delta = cut.get("candidate_adjacent_rgb_mae")
        baseline_delta = cut.get("clean_baseline_adjacent_rgb_mae")
        frames = event.get("frames")
        repeats = event.get("exact_adjacent_repeats")
        if frames is not None and repeats is not None:
            cut_text = (f"; hard-cut step {candidate_delta:.1f} vs clean {baseline_delta:.1f} RGB MAE"
                        if isinstance(candidate_delta, (int, float)) and isinstance(baseline_delta, (int, float))
                        else "")
            return (f"Rejected two-scene Slide Right source-curve hypothesis; {frames} {role} frames, "
                    f"{repeats} repeated pairs{cut_text}; unlike-scene cut metric is confounded, "
                    "perceptual concealment unresolved")

    source_key_pair = smoothness.get("source_key_vegas_enum_order_two_scene_20260929", {})
    if source_key_pair:
        role = record.get("event_variant")
        event = source_key_pair.get("events", {}).get(role, {})
        frames = event.get("frames")
        repeats = event.get("exact_adjacent_repeats")
        cut = source_key_pair.get("cut_boundary", {})
        cut_delta = cut.get("candidate_adjacent_rgb_mae")
        baseline_delta = cut.get("clean_baseline_adjacent_rgb_mae")
        if frames is not None and repeats is not None:
            cut_text = (f"; cut step {cut_delta:.1f} vs clean {baseline_delta:.1f} RGB MAE"
                        if isinstance(cut_delta, (int, float)) and isinstance(baseline_delta, (int, float))
                        else "")
            repeat_word = "pair" if repeats == 1 else "pairs"
            return (f"Rejected two-scene source-key enum-order diagnostic; {frames} {role} frames, "
                    f"{repeats} exact repeated {repeat_word}{cut_text}; reflected imagery and cut remain unaccepted")

    two_effect_excerpt = smoothness.get("two_effect_event_only_excerpt_20260929", {})
    user_excerpt_review = two_effect_excerpt.get("user_visual_review_20260929", {})
    event_length_candidate = smoothness.get("two_scene_ui_curve_and_event_length_candidate_20260929", {})
    if event_length_candidate:
        role = record.get("event_variant")
        events = event_length_candidate.get("event_metrics", {})
        event = events.get(role, {})
        frames = event.get("frames")
        repeats = event.get("identical_adjacent_pairs")
        counts = event_length_candidate.get("event_frame_counts", {})
        cut = event_length_candidate.get("cut_boundary", {})
        cut_delta = cut.get("candidate_adjacent_rgb_mae")
        baseline_delta = cut.get("clean_baseline_adjacent_rgb_mae")
        if frames is not None and repeats is not None:
            cut_text = (f"; cut step {cut_delta:.1f} vs clean {baseline_delta:.1f} RGB MAE"
                        if isinstance(cut_delta, (int, float)) and isinstance(baseline_delta, (int, float))
                        else "")
            lengths = f"{counts.get('outgoing', '?')} outgoing + {counts.get('incoming', '?')} incoming"
            return (f"Event-length-matched two-scene helper candidate, not accepted; {lengths} frames, "
                    f"one role stack per clip, {repeats} repeated {role} pairs{cut_text}; "
                    "cut concealment and source interpolation remain unresolved")
    if user_excerpt_review.get("outcome") == "rejected-four-perceptual-transition-beats":
        two_scene_candidate = smoothness.get("two_scene_smoothstep_candidate_20260929", {})
        role = record.get("event_variant")
        event = two_scene_candidate.get("events", {}).get(role, {})
        frames = event.get("rendered_frames")
        repeats = event.get("identical_adjacent_pairs")
        cut = two_scene_candidate.get("cut_boundary", {})
        cut_delta = cut.get("candidate_adjacent_rgb_mae")
        baseline_delta = cut.get("clean_baseline_adjacent_rgb_mae")
        if frames is not None and repeats is not None:
            cut_text = (f"; cut step {cut_delta:.1f} vs clean {baseline_delta:.1f} RGB MAE"
                        if isinstance(cut_delta, (int, float)) and isinstance(baseline_delta, (int, float))
                        else "")
            return (f"Separate active-template render also not accepted: {frames} {role} frames, "
                    f"{repeats} repeated pairs{cut_text}; cut not concealed. User separately rejected the "
                    "source-key excerpt for four perceived beats")
        return ("User rejected the two-event excerpt: four perceived motion beats; keep the outgoing cut frame blurred, "
                "then recover the incoming event continuously")

    two_scene_candidate = smoothness.get("two_scene_smoothstep_candidate_20260929", {})
    if two_scene_candidate:
        role = record.get("event_variant")
        event = two_scene_candidate.get("events", {}).get(role, {})
        frames = event.get("rendered_frames")
        repeats = event.get("identical_adjacent_pairs")
        cut = two_scene_candidate.get("cut_boundary", {})
        cut_delta = cut.get("candidate_adjacent_rgb_mae")
        baseline_delta = cut.get("clean_baseline_adjacent_rgb_mae")
        if frames is not None and repeats is not None:
            cut_text = (f"; cut step {cut_delta:.1f} vs clean {baseline_delta:.1f} RGB MAE"
                        if isinstance(cut_delta, (int, float)) and isinstance(baseline_delta, (int, float))
                        else "")
            return (f"Two-scene render candidate, not accepted; {frames} {role} frames, "
                    f"{repeats} repeated pairs{cut_text}; cut concealment not demonstrated")

    # Prefer the latest full Kdenlive delivery evidence over a later narrow
    # cut-slice probe. The cut probe remains linked in the narrative section,
    # but it must not hide the per-event review in each source row.
    outcome = visual_review.get("outcome", "")
    if outcome.startswith("candidate-kdenlive-effects-and-render-project-verified"):
        application = visual_review.get("application_render_record", {})
        user_span = application.get("user_reported_frame_range_recheck", {})
        start, end = user_span.get("timeline_frames_inclusive", (None, None))
        intervals = user_span.get("adjacent_intervals")
        repeats = user_span.get("adjacent_exact_repeats")
        changed = user_span.get("adjacent_pixel_fraction_changed_gt3_min_median_max")
        if start is not None and end is not None and intervals is not None:
            changed_text = (f"; >3 RGB changes on {changed[0]:.0%}–{changed[-1]:.0%} of pixels"
                            if isinstance(changed, list) and len(changed) == 3 else "")
            return (f"Kdenlive candidate, not accepted; frames {start}–{end}: "
                    f"{repeats} repeats/{intervals} intervals{changed_text}; source fidelity open")
        return "Kdenlive candidate, not accepted; full Render Project; source fidelity open"

    delivery = smoothness.get("kdenlive_delivery_pair", {})
    if delivery.get("review_scope") == "full-delivery-event-frame-progress":
        event = delivery.get("event_metrics", {})
        if isinstance(event, dict) and record.get("event_variant") in event:
            event = event[record["event_variant"]]
        intervals = event.get("expected_progression_intervals")
        total = event.get("total_intervals")
        repeats = event.get("exact_repeated_adjacent_frames")
        if intervals is not None and total is not None:
            details = []
            reversed_intervals = event.get("reversed_intervals")
            near_flat = event.get("near_flat_intervals_abs_step_le_0_05")
            if reversed_intervals is not None:
                details.append(f"{reversed_intervals} reversed")
            if near_flat is not None:
                details.append(f"{near_flat} near-flat (|Δ|≤0.05 RGB MAE)")
            if repeats == 0:
                details.append("no repeated frames")
            detail_text = f" ({'; '.join(details)})" if details else ""
            return (f"Candidate, not accepted; Kdenlive full-event progression "
                    f"{intervals}/{total}{detail_text}; source easing unresolved")

    pilot = smoothness.get("two_scene_ease04_capture_pilot", {})
    metrics = pilot.get("native_filter_render_metrics", {})
    if pilot and pilot.get("acceptance_status") != "accepted":
        if metrics.get("all_adjacent_pairs_differ"):
            return f"{metrics.get('rendered_frames', 'Two-scene')}-frame MLT pilot; no repeats, not accepted"
        return "Two-scene MLT pilot; not accepted"
    cut_probe = smoothness.get("two_scene_cut_probe", {})
    if cut_probe:
        event = cut_probe.get("event_metrics", {}).get(record.get("event_variant"), {})
        intervals = event.get("expected_direction_intervals")
        total = event.get("total_intervals")
        direction = event.get("expected_distance_direction")
        if intervals is not None and total is not None and direction:
            return f"Candidate, not accepted; cut slice, {direction} on {intervals}/{total} intervals"
        return "Candidate, not accepted; targeted two-scene cut slice"
    aborted = [trial for trial in smoothness.get("candidate_trials", {}).values()
               if isinstance(trial, dict) and trial.get("outcome") == "aborted-before-complete-render"]
    if aborted:
        trial = aborted[-1]
        rendered = trial.get("last_reported_frame")
        expected = trial.get("expected_total_frames")
        progress = f" at frame {rendered}/{expected}" if rendered is not None and expected is not None else ""
        return f"{review_text}; candidate render aborted{progress} (no video)"
    return review_text


def strict_smoothness_counts(records: list[dict]) -> dict[str, int]:
    """Count records with any smoothness review data, including partial probes.

    The generated summary explicitly distinguishes this metadata count from
    complete full-event visual acceptance.
    """
    reviews = [record.get("smoothness_review", {}) for record in records]
    states = [review.get("state", "not-reviewed") for review in reviews]
    passed = sum(state in {"passed", "accepted"} for state in states)
    reviewed = []
    for state, review in zip(states, reviews):
        delivery_reaudit = review.get("kdenlive_delivery_frame_progress_reaudit", {}) or {}
        reviewed.append(
            state != "not-reviewed"
            or bool((review.get("two_scene_ease04_capture_pilot", {}) or {}).get("native_filter_render_metrics"))
            or bool((review.get("two_scene_cut_probe", {}) or {}).get("rendered_frames"))
            or (delivery_reaudit.get("review_scope") == "full-kdenlive-delivery-frame-progress-reaudit"
                and isinstance(delivery_reaudit.get("rendered_frames"), int)
                and delivery_reaudit["rendered_frames"] > 0)
        )
    unreviewed = sum(not value for value in reviewed)
    return {
        "total": len(states),
        "reviewed": sum(reviewed),
        "passed": passed,
        "not_accepted": sum(reviewed) - passed,
        "not_reviewed": unreviewed,
    }


def build_index(inventory: dict) -> str:
    records = [record for package in inventory["packages"] for record in package["records"]
               if record.get("scope") == "transition"]
    strict_counts = strict_smoothness_counts(records)
    active_count = sum(record.get("status") in {"Implemented", "Equivalent", "Partial"} for record in records)
    partial_count = sum(record.get("status") == "Partial" for record in records)
    pending_count = sum(record.get("status") == "Pending" for record in records)
    catalog_rendered = sum(isinstance(record.get("catalog_nominal_render"), dict) for record in records)
    screen_counts: dict[str, int] = {}
    for record in records:
        state = record.get("frame_progress_audit", {}).get("state", "not-screened")
        screen_counts[state] = screen_counts.get(state, 0) + 1
    screened = sum(screen_counts.get(state, 0) for state in
                   ("distinct-frames-screened", "repeated-frame-found"))
    full_pair_reviews = sum(record.get("smoothness_review", {}).get("review_scope") == "full-pair-diagnostic"
                            for record in records)
    targeted_reviews = sum(
        record.get("smoothness_review", {}).get("review_scope") == "targeted-diagnostic-only"
        or record.get("smoothness_review", {}).get(
            "full_event_interpolation_candidate_review", {}).get("review_scope") == "targeted-diagnostic-only"
        or record.get("smoothness_review", {}).get(
            "two_scene_cut_probe", {}).get("review_scope") == "targeted-diagnostic-only"
        for record in records)
    nominal_variant_reviews = sum(record.get("smoothness_review", {}).get("review_scope") == "full-nominal-source-variant-diagnostic-candidate"
                                  for record in records)
    delivery_event_reviews = sum(record.get("smoothness_review", {}).get("review_scope") == "full-delivery-event-frame-progress"
                                 for record in records)
    delivery_pair_reviews: dict[str, list[dict]] = {}
    nominal_two_scene_reviews: dict[str, list[dict]] = {}
    targeted_cut_probes: dict[str, list[dict]] = {}
    kdenlive_delivery_reaudits: dict[str, list[dict]] = {}
    for record in records:
        pair_review = record.get("smoothness_review", {}).get("kdenlive_delivery_pair", {})
        pair_video = pair_review.get("pair_video")
        if pair_review.get("review_scope") == "full-delivery-event-frame-progress" and isinstance(pair_video, str):
            delivery_pair_reviews.setdefault(pair_video, []).append(record)
        moving_review = record.get("smoothness_review", {}).get("moving_two_scene_nominal_sample", {})
        moving_video = moving_review.get("rendered_mp4")
        if moving_review.get("review_scope") == "full-nominal-two-scene-event-frame-screen" and isinstance(moving_video, str):
            nominal_two_scene_reviews.setdefault(moving_video, []).append(record)
        cut_probe = record.get("smoothness_review", {}).get("two_scene_cut_probe", {})
        cut_video = cut_probe.get("video")
        if cut_probe.get("review_scope") == "targeted-diagnostic-only" and isinstance(cut_video, str):
            targeted_cut_probes.setdefault(cut_video, []).append(record)
        re_audit = record.get("smoothness_review", {}).get("kdenlive_delivery_frame_progress_reaudit", {})
        re_audit_video = re_audit.get("video")
        if re_audit.get("review_scope") == "full-kdenlive-delivery-frame-progress-reaudit" and isinstance(re_audit_video, str):
            kdenlive_delivery_reaudits.setdefault(re_audit_video, []).append(record)
    curve_audits = [record["curve_coverage_audit"] for record in records
                    if isinstance(record.get("curve_coverage_audit"), dict)]
    audited_curves = sum(item.get("animated_parameter_curve_count", 0) for item in curve_audits)
    early_curves = sum(item.get("curves_ending_before_event_endpoint", 0) for item in curve_audits)
    early_curves_10 = sum(item.get("curves_ending_at_least_10_percent_early", 0) for item in curve_audits)
    early_track_records = sum(item.get("curves_ending_before_event_endpoint", 0) > 0 for item in curve_audits)
    records_without_endpoint = sum(not item.get("has_animated_key_at_event_endpoint", False) for item in curve_audits)
    equal_key_segments = sum(item.get("equal_key_value_segment_count", 0) for item in curve_audits)
    lines = [
        "# Native transition render index",
        "",
        "Generated from `plans/native-transition-inventory.json`. Full-catalog review MP4s are in `/home/kali/Documents/kdenlive-native-transition-validation/catalog-nominal-60fps-20261001/`; lossless sources and large paired renders remain in the validation cache. Generated `.mp4` and `.mkv` files are gitignored.",
        "",
        "## Current 60 fps visual review",
        "",
        (f"**Completed under the current frame-by-frame easing, endpoint, and delivery acceptance criteria: "
         f"{strict_counts['passed']}/{strict_counts['total']}.** "
         f"Review metadata or a targeted probe exists for **{strict_counts['reviewed']}/{strict_counts['total']}** records: "
         f"**{strict_counts['passed']} accepted**, **{strict_counts['not_accepted']} remain unaccepted**, and "
         f"**{strict_counts['not_reviewed']} have no strict review entry**. This count includes partial diagnostic slices; it does not mean full-event coverage. "
         "An older `Equivalent` implementation status does not count as a smoothness pass."),
        "",
        (f"**Nominal real-footage render coverage: {catalog_rendered}/{strict_counts['total']} source records.** Each available record has an H.264 MP4 and an all-frame contact sheet at 640x360/60 fps, rendered through the installed project-owned MLT services; source-order component chains are preserved. These are per-record candidate renders, not paired-cut or source-fidelity acceptance. {pending_count} records remain Pending because their source operation, mapping, or endpoint behavior is unresolved. The 1.1 Smooth R to L and 2.7 Scroll Right paired cases have separate 30/60 fps candidate renders and reports; their progression/endpoint and application-level gates remain open."),
        "",
        (f"Practical application check: the C++ EffectStackModel regression test applies each of the {active_count} active native transition groups to a timeline clip, checks stack consistency and unchanged clip duration, then undoes the complete group. This includes {partial_count} explicitly Partial rows whose omitted source components are disclosed in the effect descriptions. Together with the per-record MLT videos, this verifies that the active catalog has editable clip-stack entries and source-derived renderer output. It does not establish Kdenlive Render Project output for every identity; {pending_count} Pending entries remain non-applicable."),
        "",
        (f"The completion gate still requires a frame-by-frame perceptual progression, a compatible peak on both sides of the cut, a clean incoming endpoint, and verification in Kdenlive editing, save/reopen, preview, undo/redo, and final export. Repeated frames, a changing control value, or a renderable effect group do not count on their own. The current overall completed count is {strict_counts['passed']}/{strict_counts['total']}; the {catalog_rendered} nominal candidate renders are coverage evidence only. {active_count}/{strict_counts['total']} records currently have an applicable native approximation in the Effects catalog."),
        "",
        "The screenshot-backed `2.2 Slide Right` and `2.4 Slide Right` pairs have separate installed Kdenlive application, save/reopen, and Render Project evidence at 1920x1080/60. Their decoded settings and resulting videos are identical, and the supplied screenshots cannot identify which numbered pair they show. Per-frame comparison finds increasing outgoing motion on all 61 intervals (timeline frames 26–87) and recovery on 60/62 incoming intervals (frames 88–150); every adjacent event frame changes. The final incoming frame nevertheless differs from its no-effect baseline on 23.08% of comparison pixels by more than 12 RGB levels. This leaves the sharp recovered endpoint unverified, so all four source rows remain unaccepted under the new gate.",
        "",
        "The 2026-09-28 `1.1 Smooth R to L (1)/(2)` candidate was re-rendered through Kdenlive Render Project on moving real footage and a marked grid at 640x360/60 (actual output 638x358). The grid project has fresh producer IDs, but a later media audit found that its replacement 640x360/30 source was paired with stale Kdenlive metadata from 1920x1080/60 and 640x360/60000/1001 clips. Keep those grid MP4s and measurements for traceability, but treat their frame-cadence and timing conclusions as provisional until a cleanly imported fixture is rendered. The real-footage MP4 decodes all 151 frames and its timeline producer metadata matches the actual 1920x1080/60 source, but it is a single scene and cannot establish grid geometry or a two-scene cut. Both candidate roles remain unaccepted: source interpolation/tangents and outgoing event-time orientation are unresolved, and the strict easing, endpoint, two-scene, preview, save/reopen, edit, and undo checks are incomplete.",
        "",
        f"A read-only exact-pixel adjacency screen found nominal diagnostic-grid measurements for **{screened}/{len(records)}** records. Its result only detects byte-identical neighboring frames; it does not establish visible easing. The stricter 60 fps review currently covers **{delivery_event_reviews}** full delivery-event records (1.1 Smooth R to L, 1.6 Scroll Left, 10.2 Zoom Out, and two Slide Right pairs), **{full_pair_reviews}** Scroll Up source rows, **{nominal_variant_reviews}** nominal Scroll Left/Right candidates, **{len(delivery_pair_reviews)}** full-pair Kdenlive delivery reviews, **{len(nominal_two_scene_reviews)}** two-scene nominal pair screens, **{len(kdenlive_delivery_reaudits)}** Kdenlive delivery frame-progress re-audits, and **{targeted_reviews}** targeted records. None has passed the new easing-and-endpoint gate. Other records remain unreviewed regardless of their prior implementation status."
        "",
        (f"A source-key coverage census measured **{audited_curves}** animated parameter curves across **{len(curve_audits)}/{len(records)}** records: **{early_curves}** curves end before progress 1.0 (**{early_curves_10}** by at least 10%); **{early_track_records}** records have one or more early-ending tracks, while **{records_without_endpoint}** records have no animated key at progress 1.0. It also found **{equal_key_segments}** adjacent equal-value key segments. This is decoded-input timing metadata only: it does not prove that a rendered track holds, because interpolation and tangents are unresolved.") if curve_audits else "The normalized source-key coverage census has not been recorded yet.",
        "",
        "The table links every source transition record to its available rendered video and contact-sheet artifacts. `MP4` identifies a playable render (including the Kdenlive preview renderer); `Kdenlive MP4` identifies a Render Project delivery; `MKV` identifies a native component render. Missing links mean that no matching artifact is currently recorded on disk. This file is the master tracker; per-preset notes explain review methods and limitations.",
        "",
    ]
    lines.extend(catalog_change_screen(records))
    for pair_video, pair_records in sorted(delivery_pair_reviews.items()):
        review = pair_records[0]["smoothness_review"]["kdenlive_delivery_pair"]
        events = {}
        for record in pair_records:
            role = record.get("event_variant")
            role_metrics = record["smoothness_review"]["kdenlive_delivery_pair"].get("event_metrics", {})
            events[role] = role_metrics.get(role, role_metrics) if isinstance(role_metrics, dict) else {}
        outgoing = events.get("outgoing", {})
        incoming = events.get("incoming", {})
        source_names = " / ".join(sorted(record.get("exact_name", "unnamed") for record in pair_records))
        video_path = resolve_artifact(pair_video)
        baseline_path = resolve_artifact(review.get("matched_baseline_video", ""))
        contact_path = resolve_artifact(review.get("all_frames_contact_sheet", ""))
        video_link = markdown_link(video_path, "effects-on render") if video_path else "effects-on render missing"
        baseline_link = markdown_link(baseline_path, "matched no-effect render") if baseline_path else "matched no-effect render missing"
        contact_link = markdown_link(contact_path, "all-frame contact sheet") if contact_path else "all-frame contact sheet missing"
        measurements_value = review.get("measurements_file")
        measurements_path = resolve_artifact(measurements_value) if isinstance(measurements_value, str) and measurements_value else None
        measurements_link = markdown_link(measurements_path, "per-frame measurements") if measurements_path else "per-frame measurements missing"
        def event_progress(event: dict) -> str:
            expected = event.get("expected_progression_intervals")
            total = event.get("total_intervals")
            if expected is None or total is None:
                return "not measured"
            details = []
            reversed_intervals = event.get("reversed_intervals")
            near_flat = event.get("near_flat_intervals_abs_step_le_0_05")
            if reversed_intervals is not None:
                details.append(f"{reversed_intervals} reversed")
            if near_flat is not None:
                details.append(f"{near_flat} near-flat at |Δ|≤0.05 RGB MAE")
            if event.get("exact_repeated_adjacent_frames") == 0:
                details.append("no exact repeats")
            suffix = f" ({'; '.join(details)})" if details else ""
            return f"{expected}/{total}{suffix}"
        lines.extend([
            "",
            (f"The Kdenlive full-pair delivery review for **{source_names}** rendered {review.get('pair_frames')} frames at "
             f"{review.get('profile')}. Outgoing progress moved in the expected direction on "
             f"{event_progress(outgoing)} intervals; incoming progress moved on {event_progress(incoming)} intervals. "
             f"This is frame-progress evidence, not source-faithful ease validation; the rows remain unaccepted: "
             f"{video_link}, {baseline_link}, {contact_link}, {measurements_link}.")
        ])
    for pair_video, pair_records in sorted(nominal_two_scene_reviews.items()):
        review = pair_records[0]["smoothness_review"]["moving_two_scene_nominal_sample"]
        events = {record.get("event_variant"): record["smoothness_review"]["moving_two_scene_nominal_sample"].get("event_metrics", {})
                  for record in pair_records}
        outgoing = events.get("outgoing", {})
        incoming = events.get("incoming", {})
        source_names = " / ".join(sorted(record.get("exact_name", "unnamed") for record in pair_records))
        video_path = resolve_artifact(pair_video)
        contact_path = resolve_artifact(review.get("contact_sheet", ""))
        video_link = markdown_link(video_path, "two-scene MP4") if video_path else "two-scene MP4 missing"
        contact_link = markdown_link(contact_path, "all-frame contact sheet") if contact_path else "all-frame contact sheet missing"
        lines.extend([
            "",
            (f"The nominal two-scene Kdenlive sample for **{source_names}** contains 15 outgoing and 15 incoming "
             f"transition frames at 60 fps. The outgoing event has {outgoing.get('identical_adjacent_frame_pairs')} "
             f"identical adjacent pairs; incoming has {incoming.get('identical_adjacent_frame_pairs')}. Three duplicates "
             "occur only in the pre-roll, where the 30 fps source is shown in a 60 fps project. This is an output-frame "
             f"screen, not a matched clean-source progression test: {video_link}, {contact_link}.")
        ])
    for pair_video, pair_records in sorted(targeted_cut_probes.items()):
        probe = pair_records[0]["smoothness_review"]["two_scene_cut_probe"]
        events = {}
        for record in pair_records:
            role = record.get("event_variant")
            role_metrics = record["smoothness_review"]["two_scene_cut_probe"].get("event_metrics", {})
            events[role] = role_metrics.get(role, role_metrics)
        outgoing = events.get("outgoing", {})
        incoming = events.get("incoming", {})
        source_names = " / ".join(sorted(record.get("exact_name", "unnamed") for record in pair_records))
        video_path = resolve_artifact(pair_video)
        baseline_path = resolve_artifact(probe.get("baseline_video", ""))
        contact_path = resolve_artifact(probe.get("contact_sheet", ""))
        measurements_path = resolve_artifact(probe.get("measurements_file", ""))
        video_link = markdown_link(video_path, "effects-on MP4") if video_path else "effects-on MP4 missing"
        baseline_link = markdown_link(baseline_path, "matched clean baseline MP4") if baseline_path else "matched baseline missing"
        contact_link = markdown_link(contact_path, "12-frame cut contact sheet") if contact_path else "contact sheet missing"
        measurements_link = markdown_link(measurements_path, "per-frame measurements") if measurements_path else "measurements missing"
        out_distance = outgoing.get("effect_vs_baseline_rgb_mae_first_last", [])
        in_distance = incoming.get("effect_vs_baseline_rgb_mae_first_last", [])
        out_span = f"{out_distance[0]:.3f}→{out_distance[-1]:.3f}" if len(out_distance) == 2 else "unmeasured"
        in_span = f"{in_distance[0]:.3f}→{in_distance[-1]:.3f}" if len(in_distance) == 2 else "unmeasured"
        lines.extend([
            "",
            (f"The targeted two-scene cut sample for **{source_names}** rendered {probe.get('rendered_frames')} frames at "
             f"{probe.get('resolution')} and {probe.get('fps')} through the installed Kdenlive MLT delivery helper. "
             f"It covers outgoing frames {outgoing.get('timeline_frames')} and incoming frames "
             f"{incoming.get('timeline_frames')}, with the hard cut at frame {probe.get('cut_frame')}. "
             f"No adjacent event frames repeat; matched effect-to-baseline RGB MAE moves {out_span} outgoing and "
             f"{in_span} incoming, in the expected directions on "
             f"{outgoing.get('expected_direction_intervals')}/{outgoing.get('total_intervals')} and "
             f"{incoming.get('expected_direction_intervals')}/{incoming.get('total_intervals')} sampled intervals. "
             f"This is six frames from each event, not full-event acceptance; source interpolation remains unresolved. "
             f"{video_link}, {baseline_link}, {contact_link}, {measurements_link}.")
        ])
    for pair_video, pair_records in sorted(kdenlive_delivery_reaudits.items()):
        review = pair_records[0]["smoothness_review"]["kdenlive_delivery_frame_progress_reaudit"]
        events = {record.get("event_variant"): record["smoothness_review"]["kdenlive_delivery_frame_progress_reaudit"].get("event_metrics", {})
                  for record in pair_records}
        outgoing = events.get("outgoing", {})
        incoming = events.get("incoming", {})
        names = " / ".join(sorted(record.get("exact_name", "unnamed") for record in pair_records))
        video_path = resolve_artifact(pair_video)
        baseline_value = review.get("baseline_video")
        baseline_path = resolve_artifact(baseline_value) if isinstance(baseline_value, str) and baseline_value else None
        baseline_metrics = resolve_artifact(review.get("measurements_file", "")) if not baseline_path else None
        video_link = markdown_link(video_path, "Kdenlive effect output") if video_path else "Kdenlive output missing"
        baseline_link = markdown_link(baseline_path, "matched baseline") if baseline_path else (
            markdown_link(baseline_metrics, "matched-baseline measurements") if baseline_metrics
            else "matched baseline path not recorded")
        lines.extend([
            "",
            (f"The Kdenlive delivery re-audit for **{names}** decoded all {review.get('rendered_frames')} frames at "
             f"60 fps. Outgoing baseline distance follows its expected direction on "
             f"{outgoing.get('distance_direction_intervals')}/{outgoing.get('total_intervals')} intervals; incoming "
             f"does so on {incoming.get('distance_direction_intervals')}/{incoming.get('total_intervals')}. "
             f"There are no repeated adjacent output frames within either event, but the candidate remains unaccepted "
             f"because distance is not a perceptual easing metric and source tangents remain unresolved: {video_link}, {baseline_link}.")
        ])
    timing_pilots = [
        (record, record.get("smoothness_review", {}).get("active_interval_timing_pilot"))
        for record in records
        if record.get("smoothness_review", {}).get("active_interval_timing_pilot")
    ]
    for record, pilot in timing_pilots:
        best = next((item for item in pilot.get("interpolation_candidates", [])
                     if "to-key-fast" in item.get("interpretation", "")), None)
        metrics = best.get("metrics", {}) if best else {}
        falling = metrics.get("distance_falls_intervals")
        near_flat = metrics.get("near_flat_distance_intervals")
        frame_total = max(0, metrics.get("frames", 1) - 1)
        delivery = pilot.get("kdenlive_project_delivery_candidate", {})
        outgoing = delivery.get("outgoing", {})
        incoming = delivery.get("incoming", {})
        lines.extend([
            "",
            (f"The 2026-09-28 active-interval timing pilot for {record['exact_name']} retained the complete "
             f"three-component chain. Its destination-key interpolation candidate moved toward its clean-source "
             f"endpoint on {falling}/{frame_total} intervals, with {near_flat} near-flat intervals. The source "
             "integer mapping and key association remain inferred, and this direct MLT candidate is unaccepted.")
        ])
        if delivery:
            lines.extend([
                "",
                (f"A separate installed Kdenlive Render export of the two-event project retained its original "
                 f"timeline entries: outgoing {outgoing.get('expected_direction_intervals')}/"
                 f"{outgoing.get('total_intervals')} intervals and incoming "
                 f"{incoming.get('expected_direction_intervals')}/{incoming.get('total_intervals')} intervals "
                 "followed the expected progression at 640x360/60. The candidate was edited in an external "
                 "project copy and was not applied or reopened through the Effects UI; its enum interpretation "
                 "remains inferred.")
            ])
    lines.extend([
        "",
        "| Source record | Implementation status | Frame-progress review | Direction / nominal | Video renders | Frame sheets | Review notes |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ])
    for record in records:
        videos, frames = evidence_assets(record)
        video_links = " · ".join(markdown_link(path, label) for label, path in videos) or "—"
        frame_links = " · ".join(markdown_link(path, label) for label, path in frames) or "—"
        variant = record.get("event_variant") or "unknown role"
        direction = record.get("direction") or "unknown direction"
        nominal = record.get("nominal_frames")
        nominal_text = f"{nominal} frames" if nominal is not None else "duration unknown"
        review_text = progress_review_text(record)
        review_doc_value = record.get("smoothness_review", {}).get("review_document")
        review_doc = resolve_artifact(review_doc_value) if isinstance(review_doc_value, str) else None
        review_doc_link = markdown_link(review_doc, "details") if review_doc else "—"
        lines.append(
            f"| `{record.get('exact_name', 'unnamed')}`  <br>`{record.get('source_identifier', 'no source ID')}` | "
            f"{record.get('status', 'unknown')} | {review_text} | {variant}, {direction}; {nominal_text} | {video_links} | {frame_links} | {review_doc_link} |"
        )
    lines.extend(["", f"Source transition records indexed: **{len(records)}**.", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", nargs="?", type=Path, default=ROOT / "plans/native-transition-inventory.json")
    parser.add_argument("output", nargs="?", type=Path, default=ROOT / "plans/native-transition-render-index.md")
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    args.output.write_text(build_index(inventory), encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
