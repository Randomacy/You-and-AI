"""Focused checks for gain verification and portable recording replay."""

import contextlib
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import eeg_cyton
import numpy as np


class FakeCyton:
    def __init__(self, register_1="68", register_2="68", hex_prefix="0x"):
        self.commands = []
        self.register_1 = register_1
        self.register_2 = register_2
        self.hex_prefix = hex_prefix

    def config_board(self, command):
        self.commands.append(command)
        if command == "?":
            return (
                f"CH1SET, {self.hex_prefix}05, {self.hex_prefix}{self.register_1}, 0, 1, 1, 0, 1, 0, 0, 0\n"
                f"CH2SET, {self.hex_prefix}06, {self.hex_prefix}{self.register_2}, 0, 1, 1, 0, 1, 0, 0, 0\n$$$"
            )
        return f"Success: Channel set for {command[1]}$$$"


class FakeShim(FakeCyton):
    last_instance = None

    def __init__(self, board_id, params):
        super().__init__()
        self.serial_port = params.serial_port
        self.released = False
        FakeShim.last_instance = self

    @staticmethod
    def get_eeg_channels(board_id):
        return [1, 2]

    @staticmethod
    def get_timestamp_channel(board_id):
        return 3

    @staticmethod
    def get_package_num_channel(board_id):
        return 0

    @staticmethod
    def get_sampling_rate(board_id):
        return 250

    def prepare_session(self):
        pass

    def start_stream(self):
        pass

    def get_board_data(self):
        return np.array([[0, 1], [5, 7], [6, 8], [100.0, 100.004]])

    def stop_stream(self):
        pass

    def release_session(self):
        self.released = True


class CytonTests(unittest.TestCase):
    def test_max_gain_commands_and_readback(self):
        board = FakeCyton()
        self.assertEqual(eeg_cyton.configure_max_gain(board), {1: 0x68, 2: 0x68})
        self.assertEqual(board.commands, ["x1060110X", "x2060110X", "?"])

    def test_register_dump_without_hex_prefix_from_connected_cyton(self):
        board = FakeCyton(hex_prefix="")
        self.assertEqual(eeg_cyton.configure_max_gain(board), {1: 0x68, 2: 0x68})

    def test_rejects_lower_gain(self):
        with self.assertRaisesRegex(RuntimeError, "not on with normal input and x24 gain"):
            eeg_cyton.configure_max_gain(FakeCyton(register_2="58"))

    def test_rejects_unverifiable_register(self):
        with self.assertRaisesRegex(RuntimeError, "Could not verify"):
            eeg_cyton.configure_max_gain(FakeCyton(register_1="not available"))

    def test_rail_check(self):
        self.assertEqual(eeg_cyton.signal_summary([0.0, eeg_cyton.FULL_SCALE_UV])["status"], "RAILED")
        self.assertEqual(eeg_cyton.signal_summary([1.0, 1.0])["status"], "FLAT")
        self.assertEqual(eeg_cyton.signal_summary([0.0, 0.8])["status"], "LOW AMP")

    def test_timebase_unwraps_counter_and_marks_gap(self):
        clock = eeg_cyton.CytonTimebase(250)
        first = clock.add_batch([100.1, 100.1, 100.1], [254, 255, 0])
        second = clock.add_batch([100.2], [2])
        self.assertEqual([row[0] for row in first + second], [0, 1, 2, 4])
        self.assertAlmostEqual(first[2][1] - first[0][1], 2 / 250)
        self.assertEqual(clock.missing_packets, 1)

    def test_csv_recording_replays(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / "sample.csv"
            path.with_suffix(".json").write_text(json.dumps({
                "schema": "commonground.eeg.csv.v1", "sample_rate_hz": 2,
                "gain": {"channel_1": 24, "channel_2": 24},
            }), encoding="utf-8")
            with path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(("timestamp", "fp1_uv", "fp2_uv"))
                writer.writerows(((1.0, 1, 2), (1.5, 3, 4), (2.0, 2, 3)))
            metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["gain"]["channel_1"], 24)
            output = io.StringIO()
            with patch("eeg_cyton.time.sleep"), contextlib.redirect_stdout(output):
                eeg_cyton.replay(path, 1)
            self.assertIn("Fp1", output.getvalue())
            self.assertIn("Fp2", output.getvalue())
            self.assertIn("2 samples in window", output.getvalue())

    def test_record_writes_samples_after_gain_verification(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / "live.csv"
            with (patch("brainflow.board_shim.BoardShim", FakeShim),
                  patch("eeg_cyton.time.sleep"),
                  patch("eeg_cyton.time.monotonic", side_effect=[0, 0, 2]),
                  contextlib.redirect_stdout(io.StringIO())):
                eeg_cyton.record("COM5", path, seconds=1, interval=0.01)
            with path.open(newline="", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["fp1_uv"], "5.0")
            self.assertEqual(rows[0]["sample_index"], "0")
            self.assertEqual(rows[1]["sample_index"], "1")
            metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["schema"], "commonground.eeg.csv.v2")
            self.assertEqual(FakeShim.last_instance.commands[:3], ["x1060110X", "x2060110X", "?"])
            self.assertTrue(FakeShim.last_instance.released)
            with patch("eeg_cyton.time.sleep"), contextlib.redirect_stdout(io.StringIO()):
                eeg_cyton.replay(path, 1)


if __name__ == "__main__":
    unittest.main()
