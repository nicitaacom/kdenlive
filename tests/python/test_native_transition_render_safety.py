#!/usr/bin/env python3
"""Safety gates for long-running native transition render validation."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from validate_native_transition_renders import render, run


class NativeTransitionRenderSafetyTest(unittest.TestCase):
    def test_cli_requires_an_explicit_small_selection_or_all_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "must-not-be-created"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "validate_native_transition_renders.py"),
                    str(ROOT / "plans" / "native-transition-inventory.json"),
                    str(Path(temporary) / "unused.mp4"),
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
                env={**__import__("os").environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("--names --all is required", completed.stderr)
            self.assertFalse(output.exists())

    def test_child_render_command_is_terminated_at_its_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "sleep.log"
            started = time.monotonic()
            with self.assertRaises(subprocess.TimeoutExpired):
                run(
                    [sys.executable, "-c", "import time; time.sleep(2)"],
                    log,
                    timeout_seconds=0.1,
                )
            self.assertLess(time.monotonic() - started, 1.5)
            self.assertTrue(log.exists())

    def test_dotted_pilot_stem_keeps_its_full_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            stem = Path(temporary) / "2.1-slide-right"
            calls = []

            def record_call(command, log, env=None, timeout_seconds=600):
                calls.append((command, timeout_seconds))

            with patch("validate_native_transition_renders.run", side_effect=record_call):
                render(ET.ElementTree(ET.Element("mlt")), stem, Path(temporary), 17)

            self.assertEqual(Path(calls[0][0][1]), Path(f"{stem}.mlt"))
            self.assertEqual(calls[0][1], 17)
            self.assertIn(str(Path(f"{stem}.mkv")), calls[1][0])
            self.assertEqual(calls[1][1], 17)


if __name__ == "__main__":
    unittest.main()
