#!/usr/bin/env python3
"""Tests for the conservative transition frame-distinctness audit."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.audit_native_transition_frame_progress import collect_candidates


def result(identifier: str, profile: str, differences: list[bool]) -> dict:
    return {
        "source_identifier": identifier,
        "profile": profile,
        "rendered_frames": len(differences),
        "video": "/tmp/fixture.mkv",
        "measurements": [
            {"frame": index, "differs_from_previous": differs}
            for index, differs in enumerate(differences)
        ],
    }


class NativeTransitionFrameProgressTest(unittest.TestCase):
    def make_record(self, directory: Path, results: list[dict]) -> dict:
        record = {
            "source_identifier": "{12345678-1234-1234-1234-123456789ABC}",
            "nominal_frames": 3,
            "validation_evidence": [],
        }
        for index, data in enumerate(results):
            path = directory / f"results-{index}.json"
            path.write_text(json.dumps([data]), encoding="utf-8")
            record["validation_evidence"].append({
                "kind": "Complete nominal marked-grid render",
                "results": str(path),
            })
        return record

    def test_records_exact_repeated_adjacent_frame(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            record = self.make_record(Path(temporary), [
                result("{12345678-1234-1234-1234-123456789ABC}", "640x360 60/1", [False, True, False])
            ])
            audit = collect_candidates(record)[0]
            self.assertEqual(audit["state"], "repeated-frame-found")
            self.assertEqual(audit["repeated_frame_indices"], [2])

    def test_prefers_full_hd_result_when_multiple_nominal_renders_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            record = self.make_record(Path(temporary), [
                result("12345678-1234-1234-1234-123456789abc", "640x360 60/1", [False, True, True]),
                result("12345678-1234-1234-1234-123456789abc", "1920x1080 60/1", [False, True, True]),
            ])
            self.assertEqual(collect_candidates(record)[0]["fps_profile"], "1920x1080 60/1")

    def test_ignores_one_frame_endpoint_as_nominal_progress_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            record = self.make_record(Path(temporary), [
                result("12345678-1234-1234-1234-123456789abc", "1920x1080 60/1", [False])
            ])
            record["nominal_frames"] = 15
            record["validation_evidence"][0]["kind"] = "One-frame incoming endpoint on marked grid"
            self.assertEqual(collect_candidates(record), [])


if __name__ == "__main__":
    unittest.main()
