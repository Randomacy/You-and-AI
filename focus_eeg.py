"""Experimental Fp1/Fp2 engagement index for the OpenBCI Cyton.

Shows beta/(alpha+theta) directly. Optional user thresholds or personal
calibration can drive the avatar; this is not a direct measure of attention.
"""

import argparse
from collections import deque
import csv
import json
import math
from pathlib import Path
import socket
import sys
import time

import numpy as np

from eeg_cyton import CytonTimebase, FULL_SCALE_UV, configure_max_gain


WINDOW_SECONDS = 4
HOP_SECONDS = 2
MIN_GOOD_WINDOWS = 5
CALIBRATION_SCHEMA = "commonground.focus-calibration.v1"


def analyze_window(fp1, fp2, sample_rate, sample_indices=None, full_scale_uv=FULL_SCALE_UV):
    """Return an engagement index and quality flag, or a rejection reason."""
    channels = np.asarray([fp1, fp2], dtype=float)
    expected = int(WINDOW_SECONDS * sample_rate)
    if channels.ndim != 2 or channels.shape != (2, expected):
        return {"quality": "SHORT WINDOW"}
    if not np.isfinite(channels).all():
        return {"quality": "INVALID"}
    if sample_indices is not None:
        sample_indices = np.asarray(sample_indices, dtype=int)
        gaps = np.diff(sample_indices)
        missing = int(np.sum(gaps - 1))
        if np.any(gaps <= 0) or np.max(gaps) > 5 or missing > 0.01 * expected:
            return {"quality": "PACKET GAP"}
        if missing:
            target = np.arange(sample_indices[-1] - expected + 1, sample_indices[-1] + 1)
            channels = np.asarray([
                np.interp(target, sample_indices, channel) for channel in channels
            ])
    if full_scale_uv is not None and np.max(np.abs(channels)) >= 0.95 * full_scale_uv:
        return {"quality": "RAILED"}
    spans = np.ptp(channels, axis=1)
    # Large frontal deflections are likely blinks or movement. Smaller facial
    # muscle artifacts can remain, so this is only a coarse rejection rule.
    if np.any(spans > 300.0) or np.max(np.abs(np.diff(channels, axis=1))) > 100.0:
        return {"quality": "ARTIFACT"}
    quality = "LOW AMP" if np.any(spans < 2.0) else "GOOD"

    powers = np.asarray([welch_bands(channel, sample_rate) for channel in channels])
    theta, alpha, beta = np.mean(powers, axis=0)
    if theta + alpha <= 0 or beta <= 0:
        return {"quality": "INVALID"}
    ratio = beta / (theta + alpha)
    return {
        "quality": quality,
        "log_engagement": float(math.log(ratio)),
        "engagement_index": float(ratio),
        "theta_power": float(theta),
        "alpha_power": float(alpha),
        "beta_power": float(beta),
    }


def welch_bands(values, sample_rate):
    """Mean 2-second, 50%-overlap Hann PSD; output theta/alpha/beta power."""
    segment_size = int(2 * sample_rate)
    hop = segment_size // 2
    taper = np.hanning(segment_size)
    freqs = np.fft.rfftfreq(segment_size, 1 / sample_rate)
    band_masks = ((freqs >= 4) & (freqs < 8),
                  (freqs >= 8) & (freqs < 13),
                  (freqs >= 13) & (freqs < 30))
    spectra = []
    for start in range(0, len(values) - segment_size + 1, hop):
        segment = np.asarray(values[start:start + segment_size], dtype=float)
        position = np.arange(segment_size, dtype=float)
        centered = position - position.mean()
        slope = np.dot(centered, segment - segment.mean()) / np.dot(centered, centered)
        detrended = segment - segment.mean() - slope * centered
        spectrum = np.abs(np.fft.rfft(detrended * taper)) ** 2
        spectrum *= 2 / (sample_rate * np.sum(taper ** 2))
        spectra.append(spectrum)
    psd = np.mean(spectra, axis=0)
    bin_width = sample_rate / segment_size
    return [float(np.sum(psd[mask]) * bin_width) for mask in band_masks]


def read_recording(path):
    metadata_path = path.with_suffix(".json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    schema = metadata.get("schema")
    if schema not in ("commonground.eeg.csv.v1", "commonground.eeg.csv.v2"):
        raise ValueError(f"Unsupported EEG recording: {path}")
    sample_rate = int(metadata["sample_rate_hz"])
    if sample_rate <= 0:
        raise ValueError("Recording has an invalid sample rate")
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        required = {"fp1_uv", "fp2_uv"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"Missing Fp1/Fp2 columns in {path}")
        rows = list(reader)
    fp1 = np.asarray([float(row["fp1_uv"]) for row in rows])
    fp2 = np.asarray([float(row["fp2_uv"]) for row in rows])
    indices = np.asarray(
        [int(row["sample_index"]) for row in rows] if schema.endswith("v2")
        else list(range(len(rows))), dtype=int,
    )
    return sample_rate, fp1, fp2, indices


def recording_features(path, hop_seconds=WINDOW_SECONDS):
    sample_rate, fp1, fp2, indices = read_recording(path)
    size = int(WINDOW_SECONDS * sample_rate)
    hop = int(hop_seconds * sample_rate)
    features, rejected = [], {}
    for start in range(0, len(fp1) - size + 1, hop):
        result = analyze_window(
            fp1[start:start + size], fp2[start:start + size], sample_rate,
            indices[start:start + size],
        )
        if result["quality"] == "GOOD":
            features.append(result["log_engagement"])
        else:
            reason = result["quality"]
            rejected[reason] = rejected.get(reason, 0) + 1
    return sample_rate, features, rejected


def build_calibration(rest_path, focus_path):
    rest_rate, rest, rest_rejected = recording_features(rest_path)
    focus_rate, focus, focus_rejected = recording_features(focus_path)
    if rest_rate != focus_rate:
        raise ValueError("Rest and focus recordings use different sample rates")
    if len(rest) < MIN_GOOD_WINDOWS or len(focus) < MIN_GOOD_WINDOWS:
        raise ValueError(
            f"Need at least {MIN_GOOD_WINDOWS} clean 4-second windows in each recording; "
            f"got rest={len(rest)} {rest_rejected}, focus={len(focus)} {focus_rejected}. "
            "Resolve the reported signal issues; record longer sessions if too few windows remain."
        )
    rest_center = float(np.median(rest))
    focus_center = float(np.median(focus))
    difference = focus_center - rest_center
    variation = max(
        float(np.median(np.abs(np.asarray(rest) - rest_center))),
        float(np.median(np.abs(np.asarray(focus) - focus_center))),
    )
    if abs(difference) < max(0.25, 1.5 * variation):
        raise ValueError(
            "The two recordings do not separate reliably with this EEG feature. "
            "Repeat with good contact and clearly different tasks."
        )
    return {
        "schema": CALIBRATION_SCHEMA,
        "feature": "log(beta_13_30/(alpha_8_13+theta_4_8))",
        "channels": ["Fp1", "Fp2"],
        "sample_rate_hz": rest_rate,
        "window_seconds": WINDOW_SECONDS,
        "rest_median": rest_center,
        "focus_median": focus_center,
        "rest_clean_windows": len(rest),
        "focus_clean_windows": len(focus),
    }


def score_window(result, calibration):
    if result["quality"] != "GOOD":
        return {"quality": result["quality"], "score": None, "state": "unavailable"}
    denominator = calibration["focus_median"] - calibration["rest_median"]
    if abs(denominator) < 1e-9:
        raise ValueError("Calibration has no separation")
    position = (result["log_engagement"] - calibration["rest_median"]) / denominator
    score = float(np.clip(100 * position, 0, 100))
    state = "focus-like" if score >= 65 else "rest-like" if score <= 35 else "uncertain"
    return {"quality": "GOOD", "score": score, "state": state,
            "engagement_index": result["engagement_index"]}


class FocusThresholds:
    """User-selected hysteresis thresholds on the raw engagement index."""

    def __init__(self, on, off):
        if not all(math.isfinite(value) for value in (on, off)) or off < 0 or on <= off:
            raise ValueError("Thresholds must be finite and satisfy focus-on > focus-off >= 0")
        self.on = on
        self.off = off
        self.state = "uncertain"

    def classify(self, result):
        ratio = result.get("engagement_index")
        if ratio is None:
            self.state = "uncertain"
            return {"quality": result["quality"], "engagement_index": None,
                    "score": None, "state": "unavailable"}
        if ratio >= self.on:
            self.state = "focus-like"
        elif ratio <= self.off:
            self.state = "rest-like"
        return {"quality": result["quality"], "engagement_index": ratio,
                "score": None, "state": self.state,
                "theta_power": result["theta_power"],
                "alpha_power": result["alpha_power"],
                "beta_power": result["beta_power"]}


def raw_result(result, thresholds=None):
    if thresholds is not None:
        return thresholds.classify(result)
    return {**result, "score": None,
            "state": "unclassified" if "engagement_index" in result else "unavailable"}


def load_calibration(path):
    calibration = json.loads(path.read_text(encoding="utf-8"))
    if calibration.get("schema") != CALIBRATION_SCHEMA:
        raise ValueError("Unsupported focus calibration")
    return calibration


def print_score(result):
    if result.get("engagement_index") is not None and result["score"] is None:
        print(f"Engagement index {result['engagement_index']:.3f}  "
              f"{result['state']:12}  [{result['quality']}]  "
              f"theta={result['theta_power']:.3f} alpha={result['alpha_power']:.3f} "
              f"beta={result['beta_power']:.3f} uV^2")
    elif result["score"] is None:
        print(f"Focus unavailable: {result['quality']}")
    else:
        print(f"Focus proxy {result['score']:5.1f}/100  {result['state']:10}  "
              f"engagement index {result['engagement_index']:.3f}")


def replay_focus(path, calibration=None, speed=1, thresholds=None):
    if speed <= 0:
        raise ValueError("Replay speed must be positive")
    rate, fp1, fp2, indices = read_recording(path)
    if calibration is not None and rate != calibration["sample_rate_hz"]:
        raise ValueError("Recording sample rate differs from calibration")
    size = int(WINDOW_SECONDS * rate)
    hop = int(HOP_SECONDS * rate)
    for end in range(size, len(fp1) + 1, hop):
        result = analyze_window(fp1[end - size:end], fp2[end - size:end],
                                rate, indices[end - size:end])
        print_score(score_window(result, calibration) if calibration is not None
                    else raw_result(result, thresholds))
        time.sleep(HOP_SECONDS / speed)


def live_focus(serial_port, calibration=None, avatar_port=None, thresholds=None):
    from brainflow.board_shim import BoardIds, BoardShim, BrainFlowInputParams
    from brainflow.exit_codes import BrainFlowError
    params = BrainFlowInputParams()
    params.serial_port = serial_port
    board_id = BoardIds.CYTON_BOARD.value
    board = BoardShim(board_id, params)
    eeg_rows = BoardShim.get_eeg_channels(board_id)
    packet_row = BoardShim.get_package_num_channel(board_id)
    timestamp_row = BoardShim.get_timestamp_channel(board_id)
    rate = BoardShim.get_sampling_rate(board_id)
    if calibration is not None and rate != calibration["sample_rate_hz"]:
        raise ValueError("Cyton sample rate differs from calibration")
    size, hop = int(WINDOW_SECONDS * rate), int(HOP_SECONDS * rate)
    left, right, indices = deque(maxlen=size), deque(maxlen=size), deque(maxlen=size)
    timebase = CytonTimebase(rate)
    current_count = 0
    last_evaluated = 0
    prepared = streaming = False
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) if avatar_port else None
    try:
        board.prepare_session()
        prepared = True
        registers = configure_max_gain(board)
        print("Cyton gain verified: " + ", ".join(
            f"CH{ch}SET=0x{registers[ch]:02X}" for ch in (1, 2)))
        board.start_stream()
        streaming = True
        print("Waiting for 4 seconds of Fp1/Fp2 data. Press Ctrl+C to stop.")
        while True:
            time.sleep(0.5)
            data = board.get_board_data()
            if data.shape[1] == 0:
                continue
            left.extend(data[eeg_rows[0], :].tolist())
            right.extend(data[eeg_rows[1], :].tolist())
            timings = timebase.add_batch(
                data[timestamp_row, :].tolist(), data[packet_row, :].tolist()
            )
            indices.extend(timing[0] for timing in timings)
            current_count += data.shape[1]
            if len(left) < size or current_count - last_evaluated < hop:
                continue
            last_evaluated = current_count
            result = analyze_window(list(left), list(right), rate, list(indices))
            scored = (score_window(result, calibration) if calibration is not None
                      else raw_result(result, thresholds))
            print_score(scored)
            if udp is not None:
                message = {"source": "eeg_focus", "state": scored["state"],
                           "score": scored["score"], "quality": scored["quality"],
                           "engagement_index": scored.get("engagement_index")}
                udp.sendto(json.dumps(message).encode("utf-8"), ("127.0.0.1", avatar_port))
    except BrainFlowError as exc:
        raise RuntimeError(f"Cyton error on {serial_port}: {exc}") from exc
    finally:
        if udp is not None:
            udp.close()
        try:
            if streaming:
                board.stop_stream()
        finally:
            if prepared:
                board.release_session()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="action", required=True)
    inspect = subs.add_parser("inspect", help="check clean windows in a recording")
    inspect.add_argument("path", type=Path)
    calibrate = subs.add_parser("calibrate", help="fit rest and focused-task recordings")
    calibrate.add_argument("--rest", required=True, type=Path)
    calibrate.add_argument("--focus", required=True, type=Path)
    calibrate.add_argument("--out", required=True, type=Path)
    replay = subs.add_parser("replay", help="show engagement index from saved EEG")
    replay.add_argument("path", type=Path)
    replay.add_argument("--calibration", type=Path)
    replay.add_argument("--focus-on", type=float, help="raw ratio at or above which focus turns on")
    replay.add_argument("--focus-off", type=float, help="raw ratio at or below which focus turns off")
    replay.add_argument("--speed", type=float, default=1)
    live = subs.add_parser("live", help="show engagement index from Cyton")
    live.add_argument("--port", required=True)
    live.add_argument("--calibration", type=Path)
    live.add_argument("--focus-on", type=float, help="raw ratio at or above which focus turns on")
    live.add_argument("--focus-off", type=float, help="raw ratio at or below which focus turns off")
    live.add_argument("--avatar-port", type=int, help="send focus events to an open avatar")
    args = parser.parse_args(argv)
    try:
        thresholds = None
        if args.action in ("replay", "live"):
            if (args.focus_on is None) != (args.focus_off is None):
                raise ValueError("Set both --focus-on and --focus-off")
            if args.calibration is not None and args.focus_on is not None:
                raise ValueError("Choose either --calibration or raw ratio thresholds")
            if args.focus_on is not None:
                thresholds = FocusThresholds(args.focus_on, args.focus_off)
            if args.action == "live" and args.avatar_port is not None and thresholds is None and args.calibration is None:
                raise ValueError("Set focus thresholds or --calibration before using --avatar-port")
        if args.action == "inspect":
            rate, features, rejected = recording_features(args.path)
            print(f"{args.path}: {len(features)} clean 4-second windows at {rate} Hz; rejected {rejected}")
        elif args.action == "calibrate":
            result = build_calibration(args.rest, args.focus)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print(f"Saved personal focus calibration to {args.out}")
            print(f"Clean windows: rest {result['rest_clean_windows']}, focus {result['focus_clean_windows']}")
        elif args.action == "replay":
            calibration = load_calibration(args.calibration) if args.calibration else None
            replay_focus(args.path, calibration, args.speed, thresholds)
        else:
            calibration = load_calibration(args.calibration) if args.calibration else None
            live_focus(args.port, calibration, args.avatar_port, thresholds)
    except KeyboardInterrupt:
        print("\nFocus monitor stopped.")
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        print(f"Focus error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
