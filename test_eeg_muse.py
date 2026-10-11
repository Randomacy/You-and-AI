"""Muse SDK bridge OSC parsing, recording, and avatar handoff."""

import contextlib
import csv
import io
import json
from pathlib import Path
import socket
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np

import eeg_muse
from focus_eeg import FocusThresholds


def encode_osc(address, values):
    def osc_string(value):
        encoded = value.encode("ascii") + b"\0"
        return encoded + b"\0" * (-len(encoded) % 4)
    return (osc_string(address) + osc_string("," + "f" * len(values))
            + struct.pack(">" + "f" * len(values), *values))


def eeg_samples(seconds=4):
    clock = np.arange(seconds * eeg_muse.SAMPLE_RATE) / eeg_muse.SAMPLE_RATE
    wave = (12 * np.sin(2 * np.pi * 18 * clock)
            + 6 * np.sin(2 * np.pi * 6 * clock)
            + 6 * np.sin(2 * np.pi * 10 * clock))
    for value in wave:
        yield (value * 0.5, value, value * 0.9, value * 0.5)


def fake_receiver(port, seconds, on_eeg, on_idle=None, forward_port=None):
    for i, values in enumerate(eeg_samples()):
        on_eeg(values, 1000 + i / 256, i / 256, 1 / 256)
    return 4 * eeg_muse.SAMPLE_RATE


class MuseBridgeTests(unittest.TestCase):
    def test_thresholded_focus_sends_to_default_avatar_port(self):
        with patch("eeg_muse.live_focus") as live:
            self.assertEqual(eeg_muse.main(["focus", "--focus-on", "0.5",
                                             "--focus-off", "0.2"]), 0)
        self.assertEqual(live.call_args.args[3], 5005)

    def test_bridge_packet_format(self):
        packet = encode_osc("/muse/eeg", (1.0, 2.0, 3.0, 4.0))
        self.assertEqual(eeg_muse.parse_osc_packet(packet),
                         ("/muse/eeg", (1.0, 2.0, 3.0, 4.0)))
        self.assertEqual(eeg_muse.parse_osc_packet(
            encode_osc("/muse/acc", (0.1, 0.2, 0.3)))[0], "/muse/acc")
        with self.assertRaises(ValueError):
            eeg_muse.parse_osc_packet(packet[:-1])

    def test_loopback_receiver_forwards_bridge_packets(self):
        forward = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        forward.bind(("127.0.0.1", 0))
        forward.settimeout(1)
        port = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        port.bind(("127.0.0.1", 0))
        listen_port = port.getsockname()[1]
        port.close()
        packet = encode_osc("/muse/eeg", (1.0, 2.0, 3.0, 4.0))
        seen = []
        def sender():
            time.sleep(0.1)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                for _ in range(10):
                    sock.sendto(packet, ("127.0.0.1", listen_port))
                    time.sleep(0.005)
        thread = threading.Thread(target=sender)
        thread.start()
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                count = eeg_muse.receive_eeg(
                    listen_port, 0.4,
                    lambda values, arrival, now, gap: seen.append(values),
                    forward_port=forward.getsockname()[1])
            self.assertEqual(count, 10)
            forwarded, _ = forward.recvfrom(512)
        finally:
            thread.join()
            forward.close()
        self.assertEqual(len(seen), 10)
        self.assertEqual(forwarded, packet)

    def test_bridge_record_replay_and_avatar(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / "muse.csv"
            with patch("eeg_muse.receive_eeg", fake_receiver), contextlib.redirect_stdout(io.StringIO()):
                eeg_muse.record(7000, 4, path)
            with path.open(newline="", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 1024)
            self.assertAlmostEqual(float(rows[1]["af7_uv"]), list(eeg_samples())[1][1])
            metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["schema"], eeg_muse.SCHEMA)
            output = io.StringIO()
            with patch("eeg_muse.time.sleep"), contextlib.redirect_stdout(output):
                eeg_muse.replay(path, speed=100)
            self.assertIn("Engagement index", output.getvalue())

        sent = []
        class FakeSocket:
            def sendto(self, payload, address):
                sent.append((json.loads(payload), address))
            def close(self):
                pass
        monitor = eeg_muse.MuseFocusMonitor(FocusThresholds(1.5, 1.0), FakeSocket(), 5005)
        with contextlib.redirect_stdout(io.StringIO()):
            fake_receiver(7000, 4, monitor.ingest)
        self.assertEqual(sent[0][0]["state"], "focus-like")
        self.assertEqual(sent[0][0]["device"], "Muse 2 SDK bridge")
        self.assertEqual(sent[0][1], ("127.0.0.1", 5005))
        with contextlib.redirect_stdout(io.StringIO()):
            monitor.idle()
        self.assertEqual(sent[-1][0]["state"], "unavailable")


if __name__ == "__main__":
    unittest.main()
