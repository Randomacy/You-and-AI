"""Muse 2 SDK bridge OSC receiver for recording and avatar focus feedback.

Run the existing Muse SDK bridge first. It sends /muse/eeg packets containing
TP9, AF7, AF8, TP10 as four big-endian OSC floats to 127.0.0.1:7000.
"""

import argparse
from collections import deque
import csv
import json
import math
from pathlib import Path
import socket
import struct
import sys
import time

import numpy as np

from focus_eeg import (FocusThresholds, HOP_SECONDS, WINDOW_SECONDS,
                       analyze_window, print_score, raw_result)


SAMPLE_RATE = 256
BOARD_NAMES = ("TP9", "AF7", "AF8", "TP10")
CSV_COLUMNS = ("received_index", "arrival_timestamp", "tp9_uv", "af7_uv",
               "af8_uv", "tp10_uv")
SCHEMA = "commonground.muse2.osc.csv.v1"


def parse_osc_packet(packet):
    """Decode the two OSC messages produced by the local Muse SDK bridge."""
    def read_string(offset):
        end = packet.find(b"\x00", offset)
        if end < 0:
            raise ValueError("OSC string is not terminated")
        value = packet[offset:end].decode("ascii")
        next_offset = (end + 4) & ~3
        if next_offset > len(packet):
            raise ValueError("OSC string padding is truncated")
        return value, next_offset

    address, offset = read_string(0)
    tags, offset = read_string(offset)
    expected = {"/muse/eeg": 4, "/muse/acc": 3}.get(address)
    if expected is None:
        raise ValueError(f"Unexpected OSC address: {address}")
    if tags != "," + "f" * expected or len(packet) != offset + 4 * expected:
        raise ValueError(f"Invalid OSC payload for {address}")
    values = struct.unpack_from(">" + "f" * expected, packet, offset)
    return address, values


def receive_eeg(port, seconds, on_eeg, on_idle=None, forward_port=None):
    """Receive bridge packets on loopback; seconds=None runs until Ctrl+C."""
    if port < 1 or port > 65535 or seconds is not None and seconds <= 0:
        raise ValueError("Port and duration must be positive")
    if forward_port is not None and (forward_port < 1 or forward_port > 65535 or forward_port == port):
        raise ValueError("Forward port must be valid and differ from the listen port")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1_048_576)
    try:
        sock.bind(("127.0.0.1", port))
        print(f"Listening for Muse SDK bridge EEG on 127.0.0.1:{port}...", flush=True)
        start = time.monotonic()
        last_eeg = start
        last_idle = start
        count = 0
        while seconds is None or time.monotonic() - start < seconds:
            remaining = None if seconds is None else seconds - (time.monotonic() - start)
            sock.settimeout(max(0.001, min(0.5, remaining)) if remaining is not None else 0.5)
            try:
                packet, source = sock.recvfrom(512)
            except socket.timeout:
                now = time.monotonic()
                if on_idle is not None and now - last_eeg >= 2 and now - last_idle >= 2:
                    on_idle()
                    last_idle = now
                continue
            if source[0] != "127.0.0.1":
                continue
            try:
                address, values = parse_osc_packet(packet)
            except (UnicodeDecodeError, ValueError):
                continue
            if forward_port is not None:
                sock.sendto(packet, ("127.0.0.1", forward_port))
            if address == "/muse/eeg":
                now = time.monotonic()
                on_eeg(values, time.time(), now, now - last_eeg if count else 0)
                last_eeg = now
                count += 1
        return count
    finally:
        sock.close()


def signal_line(name, samples):
    if len(samples) == 0:
        return f"{name}: NO DATA"
    samples = np.asarray(samples, dtype=float)
    if not np.isfinite(samples).all():
        return f"{name}: INVALID"
    span = float(np.ptp(samples))
    rms = float(np.std(samples))
    label = "LOW AMP" if span < 2.0 else "ARTIFACT" if span > 300.0 else "SIGNAL"
    return f"{name}: {label:8} RMS={rms:8.2f} uV  range={span:8.2f} uV"


def probe(port, seconds, forward_port=None):
    samples = {name: [] for name in BOARD_NAMES}
    last_print = time.monotonic()

    def on_eeg(values, arrival, now, gap):
        nonlocal last_print
        for name, value in zip(BOARD_NAMES, values):
            samples[name].append(value)
        if now - last_print >= 2:
            print(f"Received {len(samples['AF7'])} samples in this interval")
            for name in BOARD_NAMES:
                print(signal_line(name, samples[name]))
                samples[name].clear()
            print(flush=True)
            last_print = now

    count = receive_eeg(port, seconds, on_eeg, forward_port=forward_port)
    if count == 0:
        raise RuntimeError("No /muse/eeg packets arrived; start the Muse SDK bridge and wait for [Status] Connected!")
    print(f"Muse SDK probe complete: {count} EEG packets received")


def record(port, seconds, output, forward_port=None):
    if output.exists() or output.with_suffix(".json").exists():
        raise ValueError(f"Recording already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    file = None
    writer = None
    recent = {name: deque(maxlen=SAMPLE_RATE) for name in ("AF7", "AF8")}

    def on_eeg(values, arrival, now, gap):
        nonlocal count, file, writer
        if file is None:
            file = output.open("w", newline="", encoding="utf-8")
            writer = csv.writer(file)
            writer.writerow(CSV_COLUMNS)
        writer.writerow((count, arrival, *values))
        recent["AF7"].append(values[1])
        recent["AF8"].append(values[2])
        count += 1
        if count % SAMPLE_RATE == 0:
            file.flush()
            print(f"Captured {count} packets; " + signal_line("AF7", recent["AF7"])
                  + "; " + signal_line("AF8", recent["AF8"]), flush=True)

    try:
        receive_eeg(port, seconds, on_eeg, forward_port=forward_port)
    finally:
        if file is not None:
            file.close()
            metadata = {"schema": SCHEMA, "device": "Muse 2 via Muse SDK OSC bridge",
                        "sample_rate_hz": SAMPLE_RATE, "units": "microvolts",
                        "eeg_channels": list(BOARD_NAMES), "columns": list(CSV_COLUMNS),
                        "arrival_timestamp": "Host receipt time; not precise cross-device synchronization"}
            output.with_suffix(".json").write_text(
                json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    if count == 0:
        raise RuntimeError("No /muse/eeg packets arrived; start the Muse SDK bridge")
    print(f"Saved {count} Muse 2 EEG packets to {output}")


class MuseFocusMonitor:
    def __init__(self, thresholds=None, udp=None, avatar_port=None):
        self.thresholds = thresholds
        self.udp = udp
        self.avatar_port = avatar_port
        self.af7 = deque(maxlen=WINDOW_SECONDS * SAMPLE_RATE)
        self.af8 = deque(maxlen=WINDOW_SECONDS * SAMPLE_RATE)
        self.times = deque(maxlen=WINDOW_SECONDS * SAMPLE_RATE)
        self.total = 0
        self.last_evaluated = 0
        self.last_result = None

    def publish(self, scored):
        self.last_result = scored
        print_score(scored)
        if self.udp is not None:
            message = {"source": "eeg_focus", "device": "Muse 2 SDK bridge",
                       "state": scored["state"], "score": None,
                       "quality": scored["quality"],
                       "engagement_index": scored.get("engagement_index")}
            self.udp.sendto(json.dumps(message).encode("utf-8"),
                            ("127.0.0.1", self.avatar_port))

    def ingest(self, values, arrival, now, gap):
        if gap > 0.5:
            self.af7.clear()
            self.af8.clear()
            self.times.clear()
            if self.thresholds is not None:
                self.thresholds.state = "uncertain"
        if not all(math.isfinite(value) for value in values):
            self.af7.clear()
            self.af8.clear()
            self.times.clear()
            if self.thresholds is not None:
                self.thresholds.state = "uncertain"
            self.publish({"quality": "INVALID", "state": "unavailable", "score": None})
            return
        self.af7.append(values[1])
        self.af8.append(values[2])
        self.times.append(now)
        self.total += 1
        if len(self.af7) < WINDOW_SECONDS * SAMPLE_RATE or self.total - self.last_evaluated < HOP_SECONDS * SAMPLE_RATE:
            return
        self.last_evaluated = self.total
        duration = self.times[-1] - self.times[0]
        if not 3.5 <= duration <= 4.5:
            if self.thresholds is not None:
                self.thresholds.state = "uncertain"
            self.publish({"quality": "TIMING", "state": "unavailable", "score": None})
            return
        result = analyze_window(self.af7, self.af8, SAMPLE_RATE, full_scale_uv=None)
        self.publish(raw_result(result, self.thresholds))

    def idle(self):
        self.af7.clear()
        self.af8.clear()
        self.times.clear()
        if self.thresholds is not None:
            self.thresholds.state = "uncertain"
        if self.last_result is None or self.last_result["state"] != "unavailable":
            self.publish({"quality": "NO DATA", "state": "unavailable", "score": None})


def live_focus(port, seconds, thresholds=None, avatar_port=None, forward_port=None):
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) if avatar_port else None
    try:
        if avatar_port is not None:
            print(f"Sending classified focus states to avatar on 127.0.0.1:{avatar_port}", flush=True)
        monitor = MuseFocusMonitor(thresholds, udp, avatar_port)
        count = receive_eeg(port, seconds, monitor.ingest, monitor.idle, forward_port)
        if count == 0:
            raise RuntimeError("No /muse/eeg packets arrived; start the Muse SDK bridge")
    finally:
        if udp is not None:
            udp.close()


def replay(path, speed=1, thresholds=None):
    if speed <= 0:
        raise ValueError("Replay speed must be positive")
    metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    if metadata.get("schema") != SCHEMA:
        raise ValueError("Unsupported Muse 2 SDK recording")
    rate = int(metadata["sample_rate_hz"])
    if rate != SAMPLE_RATE:
        raise ValueError("Recording sample rate differs from the Muse bridge")
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != list(CSV_COLUMNS):
            raise ValueError("Muse SDK recording columns do not match")
        rows = list(reader)
    af7 = np.asarray([float(row["af7_uv"]) for row in rows])
    af8 = np.asarray([float(row["af8_uv"]) for row in rows])
    size, hop = WINDOW_SECONDS * rate, HOP_SECONDS * rate
    for end in range(size, len(rows) + 1, hop):
        result = analyze_window(af7[end-size:end], af8[end-size:end], rate,
                                full_scale_uv=None)
        print_score(raw_result(result, thresholds))
        time.sleep(HOP_SECONDS / speed)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="action", required=True)
    for action in ("probe", "record", "focus"):
        command = subs.add_parser(action)
        command.add_argument("--listen-port", type=int, default=7000,
                             help="Muse SDK bridge OSC port (default: 7000)")
        command.add_argument("--forward-port", type=int,
                             help="forward OSC to another local receiver, such as bci-server on 7001")
        command.add_argument("--seconds", type=float, default=10 if action == "probe" else None)
        if action == "record":
            command.add_argument("--out", required=True, type=Path)
        if action == "focus":
            command.add_argument("--focus-on", type=float)
            command.add_argument("--focus-off", type=float)
            command.add_argument("--avatar-port", type=int,
                                 help="avatar UDP port (default: 5005 when thresholds are set)")
            command.add_argument("--no-avatar", action="store_true",
                                 help="show threshold states without sending them to the avatar")
    playing = subs.add_parser("replay")
    playing.add_argument("path", type=Path)
    playing.add_argument("--speed", type=float, default=1)
    playing.add_argument("--focus-on", type=float)
    playing.add_argument("--focus-off", type=float)
    args = parser.parse_args(argv)
    try:
        thresholds = None
        if args.action in ("focus", "replay"):
            if (args.focus_on is None) != (args.focus_off is None):
                raise ValueError("Set both --focus-on and --focus-off")
            thresholds = (FocusThresholds(args.focus_on, args.focus_off)
                          if args.focus_on is not None else None)
        if args.action == "probe":
            probe(args.listen_port, args.seconds, args.forward_port)
        elif args.action == "record":
            record(args.listen_port, args.seconds, args.out, args.forward_port)
        elif args.action == "focus":
            if args.avatar_port is not None and thresholds is None:
                raise ValueError("Set thresholds before using --avatar-port")
            if args.no_avatar and args.avatar_port is not None:
                raise ValueError("Choose either --no-avatar or --avatar-port")
            avatar_port = (None if args.no_avatar or thresholds is None else
                           args.avatar_port if args.avatar_port is not None else 5005)
            if avatar_port is not None and not 1 <= avatar_port <= 65535:
                raise ValueError("Avatar port must be between 1 and 65535")
            live_focus(args.listen_port, args.seconds, thresholds, avatar_port,
                       args.forward_port)
        else:
            replay(args.path, args.speed, thresholds)
    except KeyboardInterrupt:
        print("\nMuse monitor stopped.")
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Muse error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
