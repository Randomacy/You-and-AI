"""Record and replay OpenBCI Cyton channels 1/2 at Fp1/Fp2.

The Cyton must have Fp1 wired to channel 1, Fp2 to channel 2, and suitable
reference and bias electrodes. This is signal acquisition, not emotion inference.
"""

import argparse
import csv
import json
import math
from pathlib import Path
import re
import sys
import time


GAIN = 24
FULL_SCALE_UV = 4.5 / GAIN * 1_000_000
CHANNELS = {1: "Fp1", 2: "Fp2"}
CSV_COLUMNS = (
    "sample_index", "estimated_timestamp", "arrival_timestamp", "packet_number",
    "fp1_uv", "fp2_uv",
)
# Cyton firmware versions print register bytes both with and without "0x".
REGISTER_RE = re.compile(
    r"\bCH([12])SET\s*,\s*(?:0x)?[0-9a-f]{2}\s*,\s*(?:0x)?([0-9a-f]{2})\b",
    re.I,
)
SPARK_CHARS = " ▁▂▃▄▅▆▇█"


def configure_max_gain(board):
    """Set EEG defaults with x24 gain, then check the ADS1299 register readback.

    Cyton channel command: x, channel, power, gain, input, bias, SRB2, SRB1, X.
    The expected CHnSET gain bits are 110 (x24). We fail closed if the board
    does not return a readable register dump.
    """
    for channel in CHANNELS:
        command = f"x{channel}060110X"
        response = board.config_board(command)
        if f"Success: Channel set for {channel}" not in response:
            raise RuntimeError(
                f"Cyton did not confirm channel {channel} settings: {response!r}"
            )

    readback = board.config_board("?")
    registers = {int(ch): int(value, 16) for ch, value in REGISTER_RE.findall(readback)}
    for channel in CHANNELS:
        value = registers.get(channel)
        if value is None:
            raise RuntimeError(
                f"Could not verify Cyton CH{channel}SET register; board replied: {readback!r}"
            )
        if value & 0x80 or value & 0x70 != 0x60 or value & 0x07:
            raise RuntimeError(
                f"Cyton channel {channel} is not on with normal input and x24 gain "
                f"(CH{channel}SET=0x{value:02X})"
            )
    return registers


def signal_summary(values):
    """Quick acquisition checks; these are not electrode impedance tests."""
    if not values:
        return {"status": "NO DATA", "rms_uv": 0.0, "range_uv": 0.0}
    if any(not math.isfinite(value) for value in values):
        return {"status": "INVALID", "rms_uv": float("nan"), "range_uv": float("nan")}
    average = sum(values) / len(values)
    rms = math.sqrt(sum((value - average) ** 2 for value in values) / len(values))
    span = max(values) - min(values)
    if any(abs(value) >= 0.95 * FULL_SCALE_UV for value in values):
        status = "RAILED"
    elif span < 0.5:
        status = "FLAT"
    elif span < 2.0:
        status = "LOW AMP"
    else:
        status = "SIGNAL"
    return {"status": status, "rms_uv": rms, "range_uv": span}


def sparkline(values, width=32):
    if not values:
        return " " * width
    points = [values[min(len(values) - 1, int(i * len(values) / width))] for i in range(width)]
    low, high = min(points), max(points)
    if high == low:
        return SPARK_CHARS[0] * width
    return "".join(SPARK_CHARS[min(8, int((point - low) / (high - low) * 8))] for point in points)


def display_window(fp1, fp2, sample_rate):
    for name, values in (("Fp1", fp1), ("Fp2", fp2)):
        info = signal_summary(values)
        print(
            f"{name:3} {info['status']:7}  "
            f"RMS {info['rms_uv']:8.2f} µV  range {info['range_uv']:8.2f} µV  "
            f"{sparkline(values)}"
        )
    print(f"{min(len(fp1), len(fp2))} samples in window; nominal rate {sample_rate} Hz\n")


class CytonTimebase:
    """Estimate sample times from the 250 Hz counter, keeping host arrival times.

    FTDI buffering can assign nearly identical host timestamps to many packets.
    Estimated timestamps are suitable for relative replay, but not precise
    synchronization with camera or audio.
    """

    def __init__(self, sample_rate):
        self.sample_rate = sample_rate
        self.sample_index = -1
        self.previous_packet = None
        self.origin = None
        self.missing_packets = 0
        self.duplicate_packets = 0

    def add_batch(self, arrivals, packets):
        if len(arrivals) != len(packets):
            raise ValueError("Cyton timestamp and packet rows have different lengths")
        batch = []
        for arrival, packet in zip(arrivals, packets):
            packet = int(packet) % 256
            if self.previous_packet is None:
                self.sample_index = 0
            else:
                step = (packet - self.previous_packet) % 256
                if step == 0:
                    self.duplicate_packets += 1
                    step = 1
                else:
                    self.missing_packets += step - 1
                self.sample_index += step
            self.previous_packet = packet
            batch.append((self.sample_index, float(arrival), packet))
        if batch and self.origin is None:
            self.origin = batch[-1][1] - batch[-1][0] / self.sample_rate
        return [
            (index, self.origin + index / self.sample_rate, arrival, packet)
            for index, arrival, packet in batch
        ]


def write_metadata(path, sample_rate):
    metadata = {
        "schema": "commonground.eeg.csv.v2",
        "device": "OpenBCI Cyton",
        "montage": {"channel_1": "Fp1", "channel_2": "Fp2"},
        "gain": {"channel_1": GAIN, "channel_2": GAIN},
        "sample_rate_hz": sample_rate,
        "units": "microvolts",
        "estimated_timestamp": "Approximate Unix seconds from packet counter and nominal sample rate; not precise cross-device sync",
        "arrival_timestamp": "BrainFlow host arrival Unix seconds; may be batched by USB driver",
        "columns": list(CSV_COLUMNS),
    }
    path.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def record(serial_port, output, seconds, interval):
    try:
        from brainflow.board_shim import BoardIds, BoardShim, BrainFlowInputParams
        from brainflow.exit_codes import BrainFlowError
    except ImportError as exc:
        raise RuntimeError("BrainFlow is missing. Install requirements.txt into .venv.") from exc

    params = BrainFlowInputParams()
    params.serial_port = serial_port
    board_id = BoardIds.CYTON_BOARD.value
    board = BoardShim(board_id, params)
    prepared = False
    streaming = False
    try:
        board.prepare_session()
        prepared = True
        registers = configure_max_gain(board)
        print(
            "Verified Cyton x24 gain: "
            + ", ".join(f"CH{ch}SET=0x{registers[ch]:02X}" for ch in CHANNELS)
        )
        eeg_rows = BoardShim.get_eeg_channels(board_id)
        timestamp_row = BoardShim.get_timestamp_channel(board_id)
        packet_row = BoardShim.get_package_num_channel(board_id)
        sample_rate = BoardShim.get_sampling_rate(board_id)
        if len(eeg_rows) < 2:
            raise RuntimeError("BrainFlow did not expose Cyton channels 1 and 2")

        output.parent.mkdir(parents=True, exist_ok=True)
        timebase = CytonTimebase(sample_rate)
        with output.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(CSV_COLUMNS)
            board.start_stream()
            streaming = True
            write_metadata(output, sample_rate)
            print(f"Recording {sample_rate} Hz Fp1/Fp2 from {serial_port} to {output}")
            print("Press Ctrl+C to stop. LOW AMP flags a very small range; no display flag proves good electrode contact.\n")
            start = time.monotonic()
            count = 0
            try:
                while seconds is None or time.monotonic() - start < seconds:
                    time.sleep(interval)
                    data = board.get_board_data()
                    if data.shape[1] == 0:
                        print("No EEG samples received in this interval.\n")
                        continue
                    fp1 = data[eeg_rows[0], :].tolist()
                    fp2 = data[eeg_rows[1], :].tolist()
                    arrivals = data[timestamp_row, :].tolist()
                    packets = data[packet_row, :].tolist()
                    sample_times = timebase.add_batch(arrivals, packets)
                    writer.writerows(
                        (*timing, left, right)
                        for timing, left, right in zip(sample_times, fp1, fp2)
                    )
                    file.flush()
                    count += len(arrivals)
                    display_window(fp1, fp2, sample_rate)
            except KeyboardInterrupt:
                print("\nStopping recording...")
        if count == 0:
            raise RuntimeError("No EEG samples were captured; check the Cyton connection and COM port")
        print(
            f"Saved {count} samples to {output}; counter gaps: "
            f"{timebase.missing_packets} missing, {timebase.duplicate_packets} duplicate"
        )
    except BrainFlowError as exc:
        raise RuntimeError(
            f"Cyton error on {serial_port}: {exc}. Check the dongle and close other apps using this COM port."
        ) from exc
    finally:
        try:
            if streaming:
                board.stop_stream()
        finally:
            if prepared:
                board.release_session()


def replay(path, speed):
    if speed <= 0:
        raise ValueError("Replay speed must be positive")
    metadata_path = path.with_suffix(".json")
    if not metadata_path.exists():
        raise FileNotFoundError(f"Missing recording metadata: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    schema = metadata.get("schema")
    if schema not in ("commonground.eeg.csv.v1", "commonground.eeg.csv.v2"):
        raise ValueError("Unsupported EEG recording format")
    sample_rate = int(metadata["sample_rate_hz"])
    expected_columns = (
        ["timestamp", "fp1_uv", "fp2_uv"] if schema.endswith("v1") else list(CSV_COLUMNS)
    )
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != expected_columns:
            raise ValueError("Recording columns do not match Fp1/Fp2 format")
        fp1, fp2 = [], []
        for row in reader:
            fp1.append(float(row["fp1_uv"]))
            fp2.append(float(row["fp2_uv"]))
            if len(fp1) >= sample_rate:
                display_window(fp1, fp2, sample_rate)
                time.sleep(len(fp1) / sample_rate / speed)
                fp1, fp2 = [], []
        if fp1:
            display_window(fp1, fp2, sample_rate)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    recording = subparsers.add_parser("record", help="record live Cyton Fp1/Fp2")
    recording.add_argument("--port", required=True, help="Cyton dongle serial port, e.g. COM5")
    recording.add_argument("--out", required=True, type=Path, help="CSV recording path")
    recording.add_argument("--seconds", type=float, help="stop after this many seconds")
    recording.add_argument("--interval", type=float, default=1.0, help="live display interval, seconds")
    playing = subparsers.add_parser("replay", help="replay a saved CSV recording")
    playing.add_argument("path", type=Path)
    playing.add_argument("--speed", type=float, default=1.0)
    args = parser.parse_args(argv)
    try:
        if args.action == "record":
            if args.seconds is not None and args.seconds <= 0:
                parser.error("--seconds must be positive")
            if args.interval <= 0:
                parser.error("--interval must be positive")
            record(args.port, args.out, args.seconds, args.interval)
        else:
            replay(args.path, args.speed)
    except KeyboardInterrupt:
        print("\nRecording stopped.")
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"EEG error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
