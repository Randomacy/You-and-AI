"""Checks that calibration and quality gates behave on known signals."""

import contextlib
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from eeg_cyton import CSV_COLUMNS, write_metadata
import focus_eeg


RATE = 250


def waveform(seconds, dominant_hz):
    t = np.arange(seconds * RATE) / RATE
    return (
        12 * np.sin(2 * np.pi * dominant_hz * t)
        + 1.5 * np.sin(2 * np.pi * 6 * t)
        + 0.5 * np.sin(2 * np.pi * 10 * t)
        + 0.5 * np.sin(2 * np.pi * 18 * t)
    )


def write_recording(path, dominant_hz):
    values = waveform(24, dominant_hz)
    write_metadata(path, RATE)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(CSV_COLUMNS)
        for index, value in enumerate(values):
            writer.writerow((index, 100 + index / RATE, 100 + index / RATE,
                             index % 256, value, value * 0.9))


class FocusTests(unittest.TestCase):
    def test_focus_calibration_and_scores(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            rest = Path(folder) / "rest.csv"
            focus = Path(folder) / "focus.csv"
            write_recording(rest, 10)
            write_recording(focus, 18)
            model = focus_eeg.build_calibration(rest, focus)
            self.assertEqual(model["rest_clean_windows"], 6)
            self.assertGreater(model["focus_median"], model["rest_median"])
            rest_result = focus_eeg.analyze_window(
                waveform(4, 10), waveform(4, 10) * 0.9, RATE)
            focus_result = focus_eeg.analyze_window(
                waveform(4, 18), waveform(4, 18) * 0.9, RATE)
            self.assertEqual(focus_eeg.score_window(rest_result, model)["state"], "rest-like")
            self.assertEqual(focus_eeg.score_window(focus_result, model)["state"], "focus-like")
            with patch("focus_eeg.time.sleep"), contextlib.redirect_stdout(io.StringIO()):
                focus_eeg.replay_focus(focus, model, speed=100)

    def test_low_amplitude_blocks_focus_score(self):
        low = np.sin(2 * np.pi * 10 * np.arange(4 * RATE) / RATE) * 0.2
        result = focus_eeg.analyze_window(low, low, RATE)
        self.assertEqual(result["quality"], "LOW AMP")
        self.assertGreater(result["engagement_index"], 0)
        self.assertEqual(focus_eeg.raw_result(result)["state"], "unclassified")
        model = {"rest_median": -1, "focus_median": 1}
        self.assertIsNone(focus_eeg.score_window(result, model)["score"])

    def test_manual_thresholds_have_hysteresis_and_show_quality(self):
        thresholds = focus_eeg.FocusThresholds(1.5, 1.0)
        def window(ratio, quality="GOOD"):
            return {"engagement_index": ratio, "quality": quality,
                    "theta_power": 1.0, "alpha_power": 1.0, "beta_power": ratio * 2}
        self.assertEqual(thresholds.classify(window(1.2))["state"], "uncertain")
        self.assertEqual(thresholds.classify(window(1.6, "LOW AMP"))["state"], "focus-like")
        self.assertEqual(thresholds.classify(window(1.2))["state"], "focus-like")
        self.assertEqual(thresholds.classify(window(0.9))["state"], "rest-like")
        self.assertEqual(thresholds.classify({"quality": "PACKET GAP"})["state"], "unavailable")
        self.assertEqual(thresholds.classify(window(1.2))["state"], "uncertain")
        with self.assertRaisesRegex(ValueError, "focus-on > focus-off"):
            focus_eeg.FocusThresholds(1.0, 1.0)

    def test_raw_replay_without_calibration(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            recording = Path(folder) / "focus.csv"
            write_recording(recording, 18)
            output = io.StringIO()
            with patch("focus_eeg.time.sleep"), contextlib.redirect_stdout(output):
                self.assertEqual(focus_eeg.main(["replay", str(recording), "--speed", "100"]), 0)
            self.assertIn("Engagement index", output.getvalue())
            self.assertIn("unclassified", output.getvalue())

    def test_live_thresholds_pass_to_avatar_path(self):
        with patch("focus_eeg.live_focus") as live:
            self.assertEqual(focus_eeg.main(["live", "--port", "COM8", "--focus-on", "1.5",
                                             "--focus-off", "1.0", "--avatar-port", "5005"]), 0)
        args, _ = live.call_args
        self.assertEqual(args[:3], ("COM8", None, 5005))
        self.assertIsInstance(args[3], focus_eeg.FocusThresholds)

    def test_packet_gap_rejected_when_excessive(self):
        signal = waveform(4, 18)
        indices = np.arange(4 * RATE)
        indices[500:] += 20
        result = focus_eeg.analyze_window(signal, signal, RATE, indices)
        self.assertEqual(result["quality"], "PACKET GAP")

    def test_similar_conditions_refuse_calibration(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            rest = Path(folder) / "rest.csv"
            focus = Path(folder) / "focus.csv"
            write_recording(rest, 10)
            write_recording(focus, 10)
            with self.assertRaisesRegex(ValueError, "do not separate"):
                focus_eeg.build_calibration(rest, focus)


if __name__ == "__main__":
    unittest.main()
