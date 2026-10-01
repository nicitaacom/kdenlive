"""Tests that generated render tracking includes delivered Kdenlive videos."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "native_transition_render_index", ROOT / "tools/generate_native_transition_render_index.py"
)
INDEX = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INDEX)


class RenderIndexTests(unittest.TestCase):
    def test_nominal_change_probe_uses_final_outgoing_and_initial_incoming_windows(self):
        with tempfile.TemporaryDirectory() as directory:
            results = Path(directory) / "results.json"
            results.write_text(json.dumps([{
                "source_identifier": "{source-id}",
                "measurements": [
                    {"changed_source_pixel_fraction": value}
                    for value in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
                ],
            }]))
            shared = {
                "source_identifier": "{SOURCE-ID}",
                "catalog_nominal_render": {"results": str(results)},
            }

            outgoing = INDEX.catalog_change_probe({**shared, "event_variant": "outgoing"})
            incoming = INDEX.catalog_change_probe({**shared, "event_variant": "incoming"})

        self.assertAlmostEqual(outgoing["near_cut_mean_changed_fraction"], 0.85)
        self.assertEqual(outgoing["near_cut_max_changed_fraction"], 0.9)
        self.assertAlmostEqual(incoming["near_cut_mean_changed_fraction"], 0.05)
        self.assertEqual(incoming["final_changed_fraction"], 0.9)

    def test_change_screen_labels_measurement_as_triage_not_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            results = Path(directory) / "results.json"
            results.write_text(json.dumps([{
                "source_identifier": "{source-id}",
                "measurements": [
                    {"changed_source_pixel_fraction": value}
                    for value in (0.0, 0.1, 0.2, 0.3, 0.4)
                ],
            }]))
            report = INDEX.catalog_change_screen([{
                "source_identifier": "{source-id}",
                "exact_name": "Example (1) 5k",
                "event_variant": "outgoing",
                "catalog_nominal_render": {"results": str(results)},
            }])

        text = "\n".join(report)
        self.assertIn("Nominal near-cut pixel-change screen (triage only)", text)
        self.assertIn("not a blur measure", text)
        self.assertIn("Example (1) 5k", text)

    def test_strict_smoothness_counts_do_not_inherit_old_equivalent_status(self):
        records = [
            {"status": "Equivalent", "smoothness_review": {"state": "candidate-not-accepted"}},
            {"status": "Equivalent", "smoothness_review": {"state": "passed"}},
            {"status": "Pending", "smoothness_review": {"state": "not-reviewed"}},
        ]
        self.assertEqual(INDEX.strict_smoothness_counts(records), {
            "total": 3,
            "reviewed": 2,
            "passed": 1,
            "not_accepted": 1,
            "not_reviewed": 1,
        })

    def test_completed_two_scene_pilot_counts_as_reviewed_but_not_accepted(self):
        records = [{
            "status": "Equivalent",
            "smoothness_review": {
                "two_scene_ease04_capture_pilot": {
                    "acceptance_status": "not-accepted",
                    "native_filter_render_metrics": {"rendered_frames": 140},
                }
            },
        }]
        self.assertEqual(INDEX.strict_smoothness_counts(records), {
            "total": 1,
            "reviewed": 1,
            "passed": 0,
            "not_accepted": 1,
            "not_reviewed": 0,
        })

    def test_full_kdenlive_delivery_reaudit_without_root_state_counts_as_reviewed(self):
        records = [{
            "status": "Equivalent",
            "smoothness_review": {
                "kdenlive_delivery_frame_progress_reaudit": {
                    "review_scope": "full-kdenlive-delivery-frame-progress-reaudit",
                    "state": "candidate-not-accepted",
                    "rendered_frames": 151,
                }
            },
        }]
        self.assertEqual(INDEX.strict_smoothness_counts(records), {
            "total": 1,
            "reviewed": 1,
            "passed": 0,
            "not_accepted": 1,
            "not_reviewed": 0,
        })

    def test_summary_discloses_that_review_count_includes_partial_cut_probes(self):
        text = INDEX.build_index({"packages": [{"records": [{
            "scope": "transition",
            "status": "Equivalent",
            "exact_name": "sample pair",
            "source_identifier": "sample-id",
            "nominal_frames": 15,
            "event_variant": "outgoing",
            "smoothness_review": {
                "state": "not-reviewed",
                "two_scene_cut_probe": {"rendered_frames": 12},
            },
        }]}]})
        self.assertIn("Completed under the current frame-by-frame easing, endpoint, and delivery acceptance criteria: 0/1.", text)
        self.assertIn("Review metadata or a targeted probe exists for **1/1**", text)
        self.assertIn("This count includes partial diagnostic slices; it does not mean full-event coverage.", text)
        self.assertIn("0 accepted", text)

    def test_kdenlive_rendered_video_field_is_linked(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "delivery.mp4"
            video.write_bytes(b"test")
            rendered, frames = INDEX.evidence_assets({
                "validation_evidence": [{
                    "kind": "Kdenlive Render Project final export",
                    "rendered_video": str(video),
                }]
            })

        self.assertEqual(rendered, [("Kdenlive MP4", video.resolve())])
        self.assertEqual(frames, [])

    def test_renderjob_fixture_is_not_mislabeled_as_project_delivery(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "renderjob-fixture.mp4"
            video.write_bytes(b"fixture")
            rendered, _ = INDEX.evidence_assets({
                "validation_evidence": [{
                    "kind": "Installed Kdenlive RenderJob helper fixture, not a project export",
                    "video": str(video),
                }]
            })

        self.assertEqual(rendered, [("Kdenlive RenderJob fixture MP4", video.resolve())])

    def test_pair_evidence_links_candidate_and_clean_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "effects.mp4"
            baseline = Path(directory) / "clean.mp4"
            candidate.write_bytes(b"candidate")
            baseline.write_bytes(b"baseline")
            rendered, frames = INDEX.evidence_assets({
                "validation_evidence": [{
                    "kind": "Direct native MLT paired candidate",
                    "video": str(candidate),
                    "baseline_video": str(baseline),
                }]
            })

        self.assertEqual(rendered, [
            ("MP4", candidate.resolve()),
            ("Baseline MP4", baseline.resolve()),
        ])
        self.assertEqual(frames, [])

    def test_full_catalog_nominal_candidate_is_the_row_media_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "source-id.mp4"
            contact = Path(directory) / "source-id-contact.png"
            old_video = Path(directory) / "old-render.mkv"
            old_contact = Path(directory) / "old-contact.png"
            for path in (video, contact, old_video, old_contact):
                path.write_bytes(b"test")
            rendered, frames = INDEX.evidence_assets({
                "catalog_nominal_render": {
                    "mp4": str(video),
                    "contact_sheet": str(contact),
                },
                "validation_evidence": [{
                    "kind": "older render",
                    "video": str(old_video),
                    "contact_sheet": str(old_contact),
                }],
            })

        self.assertEqual(rendered, [
            ("60 fps nominal candidate MP4", video.resolve()),
            ("MKV", old_video.resolve()),
        ])
        self.assertEqual(frames, [
            ("old-contact.png", old_contact.resolve()),
            ("source-id-contact.png", contact.resolve()),
        ])

    def test_user_accepted_candidate_supersedes_older_delivery_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            older = Path(directory) / "older-wave.mp4"
            accepted = Path(directory) / "accepted-x-motion.mp4"
            older.write_bytes(b"old")
            accepted.write_bytes(b"accepted")
            rendered, frames = INDEX.evidence_assets({
                "validation_evidence": [{
                    "kind": "Kdenlive final delivery",
                    "video": str(older),
                    "superseded_by": "accepted X-motion candidate",
                }],
                "smoothness_review": {
                    "user_visual_acceptance_20260930": {
                        "candidate_video_30fps": str(accepted),
                    }
                },
            })

        self.assertEqual(rendered, [
            ("User-accepted approximation MP4", accepted.resolve()),
        ])
        self.assertEqual(frames, [])

    def test_swish3d_candidate_stays_explicitly_unaccepted_and_clip_local(self):
        text = INDEX.progress_review_text({
            "event_variant": "incoming",
            "smoothness_review": {
                "swish3d_paired_two_scene_candidate_20261001": {
                    "rates": {
                        "30": {"outgoing_frames": 15, "incoming_frames": 15},
                        "60": {
                            "outgoing_frames": 30,
                            "incoming_frames": 30,
                            "reviewed_role": "incoming",
                            "role_baseline_distance_start_middle_end_rgb_mae": [90.0, 50.0, 1.1],
                        },
                    }
                }
            },
        })
        self.assertIn("clip-local reconstruction", text)
        self.assertIn("15+15 affected frames at 30 fps", text)
        self.assertIn("30+30 at 60 fps", text)
        self.assertIn("not GUI project-export acceptance", text)

    def test_playable_mp4_copy_is_linked_without_claiming_it_was_the_render_output(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "playable-copy.mp4"
            video.write_bytes(b"test")
            rendered, frames = INDEX.evidence_assets({
                "smoothness_review": {
                    "kdenlive_delivery_pair": {"playable_mp4": str(video)}
                }
            })

        self.assertEqual(rendered, [("Playable MP4 copy", video.resolve())])
        self.assertEqual(frames, [])

    def test_baseline_mp4_copy_is_linked_as_a_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "baseline-copy.mp4"
            video.write_bytes(b"test")
            rendered, frames = INDEX.evidence_assets({
                "smoothness_review": {
                    "candidate": {
                        "video_label": "Candidate render",
                        "baseline_mp4": str(video),
                    }
                }
            })

        self.assertEqual(rendered, [("Baseline MP4 copy", video.resolve())])
        self.assertEqual(frames, [])

    def test_candidate_mp4_is_linked_as_a_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "candidate.mp4"
            video.write_bytes(b"test")
            rendered, frames = INDEX.evidence_assets({
                "smoothness_review": {
                    "candidate": {"candidate_mp4": str(video)}
                }
            })

        self.assertEqual(rendered, [("Candidate MP4", video.resolve())])
        self.assertEqual(frames, [])

    def test_baseline_mkv_is_not_labeled_as_an_mp4_or_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "baseline.mkv"
            video.write_bytes(b"test")
            rendered, frames = INDEX.evidence_assets({
                "smoothness_review": {
                    "candidate": {
                        "video_label": "Candidate render",
                        "baseline_video": str(video),
                    }
                }
            })

        self.assertEqual(rendered, [("Baseline MKV", video.resolve())])
        self.assertEqual(frames, [])

    def test_two_scene_candidate_is_not_misreported_as_unreviewed(self):
        label = INDEX.progress_review_text({
            "smoothness_review": {
                "two_scene_ease04_capture_pilot": {
                    "acceptance_status": "not-accepted",
                    "native_filter_render_metrics": {
                        "rendered_frames": 62,
                        "all_adjacent_pairs_differ": True,
                    },
                }
            }
        })
        self.assertEqual(label, "62-frame MLT pilot; no repeats, not accepted")

    def test_paired_native_curve_candidate_reports_both_project_rates_and_open_gates(self):
        label = INDEX.progress_review_text({
            "event_variant": "incoming",
            "smoothness_review": {
                "paired_native_curve_candidate_20260930": {
                    "rates": {
                        "30": {"outgoing_frames": 15, "incoming_frames": 15},
                        "60": {
                            "outgoing_frames": 30,
                            "incoming_frames": 30,
                            "event_metrics": {"incoming": {"exact_adjacent_repeats": 0}},
                        },
                    },
                },
            },
        })
        self.assertIn("15+15 affected frames at 30 fps", label)
        self.assertIn("30+30 at 60 fps (1 s each)", label)
        self.assertIn("0 repeated incoming frames", label)
        self.assertIn("Kdenlive pair editing/export and source interpolation fidelity remain open", label)

    def test_paired_native_curve_candidate_counts_as_reviewed_but_not_accepted(self):
        records = [{
            "status": "Equivalent",
            "smoothness_review": {
                "state": "candidate-not-accepted",
                "paired_native_curve_candidate_20260930": {"rates": {"30": {}, "60": {}}},
            },
        }]
        self.assertEqual(INDEX.strict_smoothness_counts(records), {
            "total": 1,
            "reviewed": 1,
            "passed": 0,
            "not_accepted": 1,
            "not_reviewed": 0,
        })

    def test_slide_down_cut_peak_summary_reports_installed_helper_parity(self):
        label = INDEX.progress_review_text({
            "event_variant": "incoming",
            "smoothness_review": {
                "slide_down_33_cut_peak_candidate_20261001": {
                    "rates": {
                        "30": {"outgoing_frames": 15, "incoming_frames": 15},
                        "60": {
                            "outgoing_frames": 30,
                            "incoming_frames": 30,
                            "events": {"incoming": {
                                "exact_adjacent_repeats": 0,
                                "clean_baseline_distance_start_middle_end": [53.7, 49.8, 0.0],
                            }},
                        },
                    },
                    "installed_kdenlive_render_helper_20261001": {
                        "helper_vs_direct_decoded_rgb_mae": {"30": 1.96, "60": 2.0},
                    },
                }
            },
        })
        self.assertIn("one-second 30 fps 15+15 and 60 fps 30+30 frame pairs", label)
        self.assertIn("Installed kdenlive_render helper output was checked at both rates", label)
        self.assertIn("mean RGB MAE 1.96/2.0", label)
        self.assertIn("saved-project editing, persistence, preview, and Render Project checks remain open", label)

    def test_slide_down_helper_videos_are_labeled_as_helper_output(self):
        with tempfile.TemporaryDirectory() as directory:
            videos = [Path(directory) / "helper-30.mp4", Path(directory) / "helper-60.mp4"]
            for video in videos:
                video.write_bytes(b"candidate")
            rendered, frames = INDEX.evidence_assets({
                "smoothness_review": {
                    "slide_down_33_cut_peak_candidate_20261001": {
                        "installed_kdenlive_render_helper_20261001": {
                            "candidate_video_30fps": str(videos[0]),
                            "candidate_video_60fps": str(videos[1]),
                            "video_label": "Installed kdenlive_render helper output",
                        }
                    }
                }
            })
        self.assertEqual(rendered, [
            ("Installed kdenlive_render helper output", videos[0].resolve()),
            ("Installed kdenlive_render helper output", videos[1].resolve()),
        ])
        self.assertEqual(frames, [])

    def test_peak_intensity_trial_is_reported_before_older_pair_candidate(self):
        label = INDEX.progress_review_text({
            "event_variant": "outgoing",
            "smoothness_review": {
                "peak_intensity_trial_20260930": {
                    "outgoing_frames": 30,
                    "incoming_frames": 30,
                    "curve_policy": "Mo Blur Length 0.5→16; incoming 16→0",
                    "event_metrics": {
                        "outgoing": {"candidate_vs_baseline_rgb_mae": {"end": 46.7}},
                        "incoming": {"candidate_vs_baseline_rgb_mae": {"start": 35.9}},
                    },
                },
                "paired_native_curve_candidate_20260930": {"rates": {"30": {}, "60": {}}},
            },
        })
        self.assertIn("Peak-smear intensity trial, not accepted; 60 fps only", label)
        self.assertIn("30+30 affected frames (1 s total)", label)
        self.assertIn("RGB MAE 46.7/35.9", label)
        self.assertIn("30 fps, marked-grid, Kdenlive edit/persistence, and final-export checks remain open", label)

    def test_paired_curve_candidate_reports_progression_and_cut_metrics(self):
        label = INDEX.progress_review_text({
            "event_variant": "outgoing",
            "smoothness_review": {
                "paired_native_curve_candidate_20260930": {
                    "rates": {
                        "30": {"outgoing_frames": 15, "incoming_frames": 15},
                        "60": {
                            "outgoing_frames": 30,
                            "incoming_frames": 30,
                            "outgoing": {"expected_direction_intervals": 22, "total_intervals": 29},
                            "incoming": {"expected_direction_intervals": 19, "total_intervals": 29},
                            "event_metrics": {"outgoing": {"exact_adjacent_repeats": 0}},
                            "cut_boundary": {
                                "candidate_rgb_mae_at_320x180": 52.1,
                                "clean_baseline_rgb_mae_at_320x180": 65.9,
                            },
                        },
                    },
                },
            },
        })
        self.assertIn("60 fps source-distance trend 22/29 outgoing, 19/29 incoming intervals", label)
        self.assertIn("cut step 52.1 vs 65.9 clean RGB MAE", label)

    def test_checkerboard_clean_input_is_reported_as_invalid_fixture(self):
        label = INDEX.progress_review_text({
            "event_variant": "incoming",
            "smoothness_review": {
                "paired_kdenlive_render_fixture_diagnostic_60fps_20260930": {
                    "evidence": {"incoming_identical_adjacent_pairs": 29},
                },
            },
        })
        self.assertIn("Invalid 60 fps two-scene fixture, not a transition result", label)
        self.assertIn("incoming clean baseline is a checkerboard placeholder", label)
        self.assertIn("29/29 repeated incoming pairs", label)
        self.assertIn("do not accept", label)

    def test_cut_acceleration_v2_reports_actual_30_and_60_fps_candidate_counts(self):
        label = INDEX.progress_review_text({
            "event_variant": "incoming",
            "smoothness_review": {
                "paired_cut_acceleration_candidate_v2_20260930": {
                    "rates": {
                        "60": {
                            "real": {
                                "outgoing_frames": 30,
                                "incoming_frames": 30,
                                "events": {"incoming": {
                                    "exact_adjacent_repeats": 0,
                                    "clean_baseline_distance_start_middle_end": [11.7, 8.0, 0.0],
                                }},
                            },
                            "grid": {
                                "events": {"incoming": {"exact_adjacent_repeats": 0}},
                            },
                        },
                        "30": {
                            "real": {"outgoing_frames": 15, "incoming_frames": 15},
                        },
                    }
                }
            },
        })
        self.assertIn("15+15 affected frames at 30 fps", label)
        self.assertIn("30+30 at 60 fps", label)
        self.assertIn("0 real-source and 0 static-grid repeated incoming frames", label)
        self.assertIn("Baseline-distance reversals remain", label)

    def test_wave_candidate_precedes_older_rejected_candidate_label(self):
        label = INDEX.progress_review_text({
            "smoothness_review": {
                "state": "candidate-not-accepted",
                "latest_visual_review": {"outcome": "visually-rejected"},
                "wave_active_group_pair_30fps_candidate_20260929": {
                    "event_frame_counts": {"outgoing": 15, "incoming": 15},
                    "frame_evidence": {
                        "outgoing_first_and_last_mean_abs_rgb_mae_vs_clean": [2.252, 74.512],
                        "incoming_first_and_last_mean_abs_rgb_mae_vs_clean": [60.837, 1.331],
                    },
                },
                "wave_active_group_pair_60fps_candidate_20260929": {
                    "event_frame_counts": {"outgoing": 30, "incoming": 30},
                    "frame_evidence": {
                        "outgoing_first_and_last_mean_abs_rgb_mae_vs_clean": [1.752, 74.332],
                        "incoming_first_and_last_mean_abs_rgb_mae_vs_clean": [60.841, 1.265],
                        "outgoing_increasing_mae_intervals": 28,
                        "incoming_decreasing_mae_intervals": 26,
                    },
                },
            }
        })
        self.assertIn("30/60 fps paired curved-band candidates, not accepted", label)
        self.assertIn("28/29 and 26/29", label)
        self.assertIn("Kdenlive edit/render and visual peak checks remain open", label)

    def test_recent_two_scene_smoothstep_candidate_reports_cut_limitation(self):
        label = INDEX.progress_review_text({
            "event_variant": "incoming",
            "smoothness_review": {
                "state": "candidate-not-accepted",
                "latest_visual_review": {
                    "outcome": "candidate-kdenlive-effects-and-render-project-verified; strict-source-fidelity-gates-open"
                },
                "two_scene_smoothstep_candidate_20260929": {
                    "events": {
                        "incoming": {
                            "rendered_frames": 63,
                            "identical_adjacent_pairs": 0,
                        }
                    },
                    "cut_boundary": {
                        "candidate_adjacent_rgb_mae": 70.936,
                        "clean_baseline_adjacent_rgb_mae": 71.934,
                    },
                },
            },
        })
        self.assertEqual(
            label,
            "Two-scene render candidate, not accepted; 63 incoming frames, "
            "0 repeated pairs; cut step 70.9 vs clean 71.9 RGB MAE; "
            "cut concealment not demonstrated",
        )

    def test_event_length_matched_pair_candidate_reports_the_remaining_cut_failure(self):
        label = INDEX.progress_review_text({
            "event_variant": "incoming",
            "smoothness_review": {
                "two_effect_event_only_excerpt_20260929": {
                    "user_visual_review_20260929": {
                        "outcome": "rejected-four-perceptual-transition-beats",
                    },
                },
                "two_scene_ui_curve_and_event_length_candidate_20260929": {
                    "event_frame_counts": {"outgoing": 62, "incoming": 63},
                    "event_metrics": {
                        "incoming": {"frames": 63, "identical_adjacent_pairs": 0},
                    },
                    "cut_boundary": {
                        "candidate_adjacent_rgb_mae": 70.654,
                        "clean_baseline_adjacent_rgb_mae": 71.913,
                    },
                },
            },
        })
        self.assertEqual(
            label,
            "Event-length-matched two-scene helper candidate, not accepted; "
            "62 outgoing + 63 incoming frames, one role stack per clip, "
            "0 repeated incoming pairs; cut step 70.7 vs clean 71.9 RGB MAE; "
            "cut concealment and source interpolation remain unresolved",
        )

    def test_latest_source_key_two_scene_diagnostic_overrides_older_candidate(self):
        label = INDEX.progress_review_text({
            "event_variant": "outgoing",
            "smoothness_review": {
                "two_scene_ui_curve_and_event_length_candidate_20260929": {
                    "event_frame_counts": {"outgoing": 62, "incoming": 63},
                    "event_metrics": {
                        "outgoing": {"frames": 62, "identical_adjacent_pairs": 0},
                    },
                    "cut_boundary": {
                        "candidate_adjacent_rgb_mae": 70.65,
                        "clean_baseline_adjacent_rgb_mae": 71.91,
                    },
                },
                "source_key_vegas_enum_order_two_scene_20260929": {
                    "events": {
                        "outgoing": {"frames": 62, "exact_adjacent_repeats": 1},
                    },
                    "cut_boundary": {
                        "candidate_adjacent_rgb_mae": 71.068565,
                        "clean_baseline_adjacent_rgb_mae": 72.194633,
                    },
                },
            },
        })
        self.assertEqual(
            label,
            "Rejected two-scene source-key enum-order diagnostic; 62 outgoing frames, "
            "1 exact repeated pair; cut step 71.1 vs clean 72.2 RGB MAE; "
            "reflected imagery and cut remain unaccepted",
        )

    def test_slide_right_source_curve_pair_reports_hard_cut_regression(self):
        label = INDEX.progress_review_text({
            "event_variant": "incoming",
            "smoothness_review": {
                "reference_shaped_two_scene_hard_cut_20260929": {
                    "events": {
                        "incoming": {"frames": 15, "exact_adjacent_repeats": 0},
                    },
                    "cut_boundary": {
                        "candidate_adjacent_rgb_mae": 84.490392,
                        "clean_baseline_adjacent_rgb_mae": 68.272031,
                    },
                },
            },
        })
        self.assertEqual(
            label,
            "Rejected two-scene Slide Right source-curve hypothesis; 15 incoming frames, "
            "0 repeated pairs; hard-cut step 84.5 vs clean 68.3 RGB MAE; "
            "unlike-scene cut metric is confounded, perceptual concealment unresolved",
        )

    def test_aborted_candidate_is_visible_without_a_fake_video_link(self):
        record = {
            "smoothness_review": {
                "state": "candidate-not-accepted",
                "candidate_trials": {
                    "two_scene": {
                        "outcome": "aborted-before-complete-render",
                        "last_reported_frame": 13,
                        "expected_total_frames": 46,
                        "mp4": None,
                    }
                },
            }
        }
        self.assertEqual(
            INDEX.progress_review_text(record),
            "Candidate, not accepted; candidate render aborted at frame 13/46 (no video)",
        )
        videos, frames = INDEX.evidence_assets(record)
        self.assertEqual(videos, [])
        self.assertEqual(frames, [])

    def test_targeted_two_scene_cut_probe_is_summarized_and_linked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "effect.mp4"
            baseline = root / "baseline.mp4"
            contact = root / "contact.jpg"
            measurements = root / "measurements.json"
            for path in (video, baseline, contact, measurements):
                path.write_bytes(b"artifact")
            shared = {
                "review_scope": "targeted-diagnostic-only",
                "video": str(video),
                "baseline_video": str(baseline),
                "contact_sheet": str(contact),
                "measurements_file": str(measurements),
                "rendered_frames": 12,
                "resolution": "640x360",
                "fps": "60/1",
                "cut_frame": 88,
            }
            outgoing = {
                "scope": "transition",
                "status": "Equivalent",
                "exact_name": "4.3 Scroll Up (1) 20k",
                "source_identifier": "out-id",
                "nominal_frames": 20,
                "event_variant": "outgoing",
                "smoothness_review": {
                    "state": "candidate-not-accepted",
                    "review_scope": "full-pair-diagnostic",
                    "two_scene_cut_probe": {
                        **shared,
                        "event_metrics": {
                            "outgoing": {
                                "timeline_frames": [82, 87],
                                "expected_direction_intervals": 5,
                                "total_intervals": 5,
                                "expected_distance_direction": "increased",
                                "effect_vs_baseline_rgb_mae_first_last": [63.949, 75.515],
                            }
                        },
                    },
                },
            }
            incoming = {
                **outgoing,
                "exact_name": "4.3 Scroll Up (2) 20k",
                "source_identifier": "in-id",
                "event_variant": "incoming",
                "smoothness_review": {
                    **outgoing["smoothness_review"],
                    "two_scene_cut_probe": {
                        **shared,
                        "event_metrics": {
                            "incoming": {
                                "timeline_frames": [88, 93],
                                "expected_direction_intervals": 5,
                                "total_intervals": 5,
                                "expected_distance_direction": "decreased",
                                "effect_vs_baseline_rgb_mae_first_last": [16.916, 15.097],
                            }
                        },
                    },
                },
            }
            text = INDEX.build_index({"packages": [{"records": [outgoing, incoming]}]})

        self.assertIn("targeted two-scene cut sample", text)
        self.assertIn("63.949→75.515 outgoing", text)
        self.assertIn("16.916→15.097 incoming", text)
        self.assertIn("cut slice, increased on 5/5 intervals", text)
        self.assertIn("cut slice, decreased on 5/5 intervals", text)
        self.assertIn("effects-on MP4", text)
        self.assertIn("matched clean baseline MP4", text)
        self.assertIn("12-frame cut contact sheet", text)
        self.assertIn("per-frame measurements", text)

    def test_latest_kdenlive_smoothness_result_is_not_hidden_by_cut_slice(self):
        label = INDEX.progress_review_text({
            "event_variant": "incoming",
            "smoothness_review": {
                "state": "candidate-not-accepted",
                "latest_visual_review": {
                    "outcome": "candidate-kdenlive-effects-and-render-project-verified; strict-source-fidelity-gates-open",
                    "application_render_record": {
                        "user_reported_frame_range_recheck": {
                            "timeline_frames_inclusive": [105, 150],
                            "adjacent_intervals": 45,
                            "adjacent_exact_repeats": 0,
                            "adjacent_pixel_fraction_changed_gt3_min_median_max": [0.7501, 0.87, 0.9689],
                        }
                    },
                },
                "two_scene_cut_probe": {
                    "review_scope": "targeted-diagnostic-only",
                    "event_metrics": {"incoming": {
                        "expected_direction_intervals": 5,
                        "total_intervals": 5,
                        "expected_distance_direction": "decreased",
                    }},
                },
            },
        })
        self.assertIn("frames 105–150", label)
        self.assertIn("0 repeats/45 intervals", label)
        self.assertIn("source fidelity open", label)
        self.assertNotIn("cut slice", label)

    def test_full_kdenlive_event_progress_takes_precedence_over_cut_slice(self):
        label = INDEX.progress_review_text({
            "event_variant": "outgoing",
            "smoothness_review": {
                "state": "candidate-not-accepted",
                "kdenlive_delivery_pair": {
                    "review_scope": "full-delivery-event-frame-progress",
                    "event_metrics": {
                        "expected_progression_intervals": 61,
                        "total_intervals": 61,
                        "exact_repeated_adjacent_frames": 0,
                    },
                },
                "two_scene_cut_probe": {
                    "review_scope": "targeted-diagnostic-only",
                    "event_metrics": {"outgoing": {
                        "expected_direction_intervals": 5,
                        "total_intervals": 5,
                        "expected_distance_direction": "increased",
                    }},
                },
            },
        })
        self.assertIn("Kdenlive full-event progression 61/61", label)
        self.assertIn("source easing unresolved", label)
        self.assertNotIn("cut slice", label)

    def test_full_event_progress_discloses_reversals_and_near_flat_intervals(self):
        label = INDEX.progress_review_text({
            "event_variant": "incoming",
            "smoothness_review": {
                "state": "candidate-not-accepted",
                "kdenlive_delivery_pair": {
                    "review_scope": "full-delivery-event-frame-progress",
                    "event_metrics": {
                        "incoming": {
                            "expected_progression_intervals": 52,
                            "total_intervals": 62,
                            "reversed_intervals": 9,
                            "near_flat_intervals_abs_step_le_0_05": 1,
                            "exact_repeated_adjacent_frames": 0,
                        },
                    },
                },
            },
        })
        self.assertIn("52/62", label)
        self.assertIn("9 reversed", label)
        self.assertIn("1 near-flat", label)
        self.assertIn("no repeated frames", label)
        self.assertIn("source easing unresolved", label)

    def test_full_pair_narrative_does_not_hide_progression_reversals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "delivery.mkv"
            baseline = root / "baseline.mkv"
            contact = root / "contact.jpg"
            measurements = root / "measurements.json"
            for path in (video, baseline, contact, measurements):
                path.write_bytes(b"artifact")
            shared = {
                "review_scope": "full-delivery-event-frame-progress",
                "pair_video": str(video),
                "matched_baseline_video": str(baseline),
                "all_frames_contact_sheet": str(contact),
                "measurements_file": str(measurements),
                "pair_frames": 125,
                "profile": "1920x1080 at 60/1 fps",
                "event_metrics": {
                    "outgoing": {
                        "expected_progression_intervals": 50,
                        "total_intervals": 61,
                        "reversed_intervals": 0,
                        "near_flat_intervals_abs_step_le_0_05": 11,
                        "exact_repeated_adjacent_frames": 0,
                    },
                    "incoming": {
                        "expected_progression_intervals": 52,
                        "total_intervals": 62,
                        "reversed_intervals": 9,
                        "near_flat_intervals_abs_step_le_0_05": 1,
                        "exact_repeated_adjacent_frames": 0,
                    },
                },
            }
            records = []
            for role, name in (("outgoing", "Zoom A (1)"), ("incoming", "Zoom B (2)")):
                records.append({
                    "scope": "transition",
                    "status": "Equivalent",
                    "exact_name": name,
                    "source_identifier": name,
                    "nominal_frames": 10,
                    "event_variant": role,
                    "smoothness_review": {
                        "state": "candidate-not-accepted",
                        "kdenlive_delivery_pair": shared,
                    },
                })
            text = INDEX.build_index({"packages": [{"records": records}]})
            _, indexed_frames = INDEX.evidence_assets(records[0])

        self.assertIn("50/61 (0 reversed; 11 near-flat at |Δ|≤0.05 RGB MAE; no exact repeats)", text)
        self.assertIn("52/62 (9 reversed; 1 near-flat at |Δ|≤0.05 RGB MAE; no exact repeats)", text)
        self.assertIn("This is frame-progress evidence, not source-faithful ease validation", text)
        self.assertIn("[effects-on render]", text)
        self.assertIn("[matched no-effect render]", text)
        self.assertIn("[per-frame measurements]", text)
        self.assertEqual(indexed_frames, [(contact.name, contact.resolve())])


if __name__ == "__main__":
    unittest.main()
