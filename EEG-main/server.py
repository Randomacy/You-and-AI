"""Local-only NeuroPawn EEG bridge. No recording or cloud transmission."""
from __future__ import annotations

import argparse
import glob
import json
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
from brainflow.board_shim import BoardIds, BoardShim, BrainFlowInputParams
from scipy.signal import butter, iirnotch, sosfilt, tf2sos
from emotion import EmotionEstimator, unknown
from focus import estimate_focus
from signal_quality import diagnose
from capture_session import CaptureSession

ROOT = Path(__file__).resolve().parent
CHANNELS = ['Fp1', 'Fp2', 'Fz', 'Cz', 'T7', 'T8', 'Pz', 'Oz']


class Bridge:
    def __init__(self):
        self.lock = threading.Lock()
        self.capture = CaptureSession(ROOT / "recordings")
        self.stop_event = threading.Event()
        self.estimator = EmotionEstimator()
        self.thread = None
        self.state = {'status': 'disconnected', 'message': 'Connect your headset to begin.', 'channels': CHANNELS}

    def update(self, **values):
        with self.lock:
            self.state.update(values)

    def snapshot(self):
        with self.lock:
            result = dict(self.state)
        result['model_evaluation'] = {name: {'balanced_accuracy': entry['balanced_accuracy'], 'roc_auc': entry['roc_auc']} for name, entry in (self.estimator.metadata or {}).get('evaluation', {}).items()}
        result['ports'] = sorted(glob.glob('/dev/cu.usb*'))
        if result.get('last_sample_at'):
            result['age_seconds'] = time.time() - result['last_sample_at']
            if result['status'] == 'streaming' and result['age_seconds'] > 2:
                result.update(status='stale', message='No fresh samples. Check the USB connection.')
        if result['status'] != 'streaming':
            result['emotion'] = unknown('Waiting for a fresh EEG stream.')
        return result

    def connect(self, port, synthetic=False):
        with self.lock:
            if self.thread and self.thread.is_alive():
                return False
            self.stop_event.clear()
            self.state = {'status': 'connecting', 'message': 'Opening the board…', 'channels': CHANNELS, 'port': port, 'synthetic': synthetic}
            self.thread = threading.Thread(target=self.run, args=(port, synthetic), daemon=True)
            self.thread.start()
        return True

    def disconnect(self):
        self.stop_event.set()
        self.update(status='disconnecting', message='Releasing the headset…')

    def run(self, port, synthetic):
        board = None
        started = False
        try:
            params = BrainFlowInputParams()
            params.serial_port = port
            params.other_info = json.dumps({'gain': 12})
            board_id = BoardIds.SYNTHETIC_BOARD if synthetic else BoardIds.NEUROPAWN_KNIGHT_BOARD
            board = BoardShim(board_id, params)
            fs = BoardShim.get_sampling_rate(board_id)
            rows = BoardShim.get_eeg_channels(board_id)[:8]
            board.prepare_session()
            board.start_stream(fs * 30)
            started = True
            if not synthetic:
                if self.stop_event.wait(2):
                    return
                # Two-second command spacing passed the hardware channel-isolation check.
                # A successful serial write does not acknowledge applied board settings.
                for ch in range(1, 9):
                    self.update(message=f'Enabling channel {ch}/8 · {CHANNELS[ch - 1]}')
                    board.config_board(f'chon_{ch}_12')
                    if self.stop_event.wait(2):
                        return
                    board.config_board(f'rldadd_{ch}')
                    if self.stop_event.wait(2):
                        return
            board.get_board_data()  # discard configuration interval
            sos = np.vstack([tf2sos(*iirnotch(50, 30, fs)), butter(4, [1, 40], btype='bandpass', fs=fs, output='sos')])
            zi = np.zeros((len(sos), 8, 2))
            history = np.zeros((8, 0))
            raw_history = np.zeros((8, 0))
            next_estimate = 0
            next_diagnostic = 0
            diagnostics = []
            packet_previous = None
            packet_discontinuities = 0
            self.estimator.reset()
            total = 0
            baseline = None
            last_data = time.monotonic()
            began = last_data
            self.update(status='warming', message='Settling filters and collecting a signal window…', sample_rate=fs)
            while not self.stop_event.wait(.1):
                data = board.get_board_data()
                if not data.shape[1]:
                    if time.monotonic() - last_data > 3:
                        self.update(status='stale', message='No packets received. Check the USB connection.')
                    continue
                last_data = time.monotonic()
                sequence = data[BoardShim.get_package_num_channel(board_id)].astype(int)
                if sequence.size:
                    sequence_with_previous = np.r_[packet_previous, sequence] if packet_previous is not None else sequence
                    packet_discontinuities += int(np.sum(np.diff(sequence_with_previous) % 256 != 1))
                    packet_previous = int(sequence[-1])
                raw = data[rows]
                self.capture.append(raw, data[BoardShim.get_timestamp_channel(board_id)], sequence)
                if not np.isfinite(raw).all():
                    raise ValueError('Non-finite samples received; reconnect the board.')
                raw_history = np.concatenate([raw_history, raw], axis=1)[:, -fs * 56:]
                filtered, zi = sosfilt(sos, raw, axis=1, zi=zi)
                history = np.concatenate([history, filtered], axis=1)[:, -fs * 3:]
                total += raw.shape[1]
                # Startup transients are excluded from the live visualization.
                if total < fs * 3:
                    continue
                if time.monotonic() >= next_diagnostic:
                    # Compare raw and filtered spectra over the same displayed window.
                    diagnostics = diagnose(raw_history[:, -history.shape[1]:], fs)
                    filtered_diagnostics = diagnose(history, fs)
                    for entry, clean in zip(diagnostics, filtered_diagnostics):
                        entry['filtered_line_power_uv2'] = clean['line_power_uv2']
                        entry['filtered_line_noise_percent'] = clean['line_noise_percent']
                    self.update(diagnostics=diagnostics,
                                packet_discontinuities=packet_discontinuities, configured_gain=12)
                    next_diagnostic = time.monotonic() + 1
                centered = history - np.median(history, axis=1, keepdims=True)
                rms = np.sqrt(np.mean(centered ** 2, axis=1))
                amplitude = float(np.median(rms))
                baseline = amplitude if baseline is None else .995 * baseline + .005 * amplitude
                relative_energy = float(np.clip(.5 + .4 * np.log2(max(amplitude, .01) / max(baseline, .01)), 0, 1))
                warnings = [f'{CHANNELS[i]} flat' for i, value in enumerate(rms) if value < .05]
                warnings += [f'{CHANNELS[i]} high amplitude' for i, value in enumerate(rms) if value > 150]
                warnings += [f"{entry['name']} raw clipping" for entry in diagnostics if entry['clipping_percent'] > 1]
                warnings += [f"{entry['name']} 50 Hz interference" for entry in diagnostics if entry['line_noise_percent'] > 50]
                if warnings or time.monotonic() >= next_estimate:
                    try:
                        emotion = self.estimator.estimate(raw_history, fs, warnings, synthetic)
                    except (ValueError, RuntimeError) as exc:
                        emotion = unknown(f'Emotion inference unavailable: {exc}', 'error')
                    self.update(emotion=emotion)
                    next_estimate = time.monotonic() + 2
                scale = np.maximum(np.percentile(np.abs(centered), 95, axis=1), 5)
                indices = np.linspace(0, centered.shape[1] - 1, min(240, centered.shape[1])).astype(int)
                traces = np.clip(centered[:, indices] / scale[:, None], -2, 2)
                self.update(focus=estimate_focus(history, fs, warnings, synthetic))
                self.update(status='streaming', message='Receiving EEG · 1–40 Hz display filter · 50 Hz notch',
                            last_sample_at=time.time(), total_samples=total,
                            measured_rate=round(total / (time.monotonic() - began), 1),
                            rms_uv=np.round(rms, 2).tolist(), warnings=warnings,
                            energy=relative_energy,
                            trace_scale_uv=scale.tolist(),
                            trace_times_seconds=((indices - (centered.shape[1] - 1)) / fs).tolist(),
                            traces=np.round(traces, 4).tolist())
        except Exception as exc:
            self.update(status='error', message=f'Connection failed: {exc}. Close other EEG apps and reconnect.')
        finally:
            if board is not None:
                try:
                    if started:
                        board.stop_stream()
                finally:
                    if board.is_prepared():
                        board.release_session()
            if self.stop_event.is_set():
                self.update(status='disconnected', message='Headset released.', traces=[], energy=0)


bridge = Bridge()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def allowed(self):
        host = self.headers.get('Host', '')
        allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        origin = self.headers.get('Origin')
        return host in allowed and (origin is None or origin in {'http://' + h for h in allowed}) and self.headers.get('Sec-Fetch-Site') != 'cross-site'

    def respond(self, payload, status=200):
        body = json.dumps(payload, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.allowed():
            self.respond({'error': 'Local access only'}, 403)
            return
        path = self.path.split('?')[0]
        if path == '/api/phone':
            config = ROOT / '.phone/receiver.json'
            self.respond(json.loads(config.read_text()) if config.exists() else {'url': None})
            return
        if path == '/api/eeg':
            self.respond(bridge.snapshot())
            return
        files = {'/phone_panel.js': ('phone_panel.js', 'text/javascript'), '/signals.js': ('signals.js', 'text/javascript'), '/signals': ('signals.html', 'text/html'), '/signals.html': ('signals.html', 'text/html'), '/': ('index.html', 'text/html'), '/index.html': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/bloom_canvas.js': ('bloom_canvas.js', 'text/javascript'), '/bloom': ('bloom.html', 'text/html'), '/bloom.html': ('bloom.html', 'text/html'), '/bloom.css': ('bloom.css', 'text/css'), '/bloom.js': ('bloom.js', 'text/javascript')}
        if path not in files:
            self.respond({'error': 'Not found'}, 404)
            return
        name, mime = files[path]
        body = (ROOT / name).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mime + '; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-src https:; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self.allowed() or self.headers.get('Content-Type') != 'application/json':
            self.respond({'error': 'Same-origin JSON required'}, 403)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 1024:
                raise ValueError('Invalid body length')
            body = json.loads(self.rfile.read(length))
            if self.path == '/api/record/start':
                state = bridge.snapshot()
                if state['status'] != 'streaming' or state.get('synthetic'):
                    raise ValueError('Connect the real headset and wait for fresh streaming EEG first')
                self.respond(bridge.capture.start({'channels': CHANNELS, 'sample_rate_hz':state['sample_rate'], 'gain':12, 'board':'NeuroPawn Knight', 'quality_at_start':state.get('diagnostics',[])}))
            elif self.path == '/api/record/stop':
                self.respond(bridge.capture.finish(body.get('id')))
            elif self.path == '/api/connect':
                port = body.get('port')
                if port not in glob.glob('/dev/cu.usb*'):
                    raise ValueError('Select an available USB serial port')
                ok = bridge.connect(port)
                self.respond({'ok': ok}, 200 if ok else 409)
            elif self.path == '/api/disconnect':
                bridge.disconnect()
                self.respond({'ok': True})
            else:
                self.respond({'error': 'Not found'}, 404)
        except (ValueError, TypeError, AttributeError) as exc:
            self.respond({'error': str(exc)}, 400)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--serial-port')
    parser.add_argument('--synthetic', action='store_true', help='Explicit SDK test mode; never labelled live EEG')
    args = parser.parse_args()
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    except OSError as exc:
        if exc.errno in (48, 98):
            parser.exit(1, f'Port {args.port} is already in use. Stop the previous server with Ctrl+C, then retry.\n')
        raise
    if args.serial_port or args.synthetic:
        bridge.connect(args.serial_port or '', args.synthetic)
    def shutdown(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, shutdown)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        bridge.disconnect()
        if bridge.thread:
            bridge.thread.join(timeout=10)
        server.server_close()


if __name__ == '__main__':
    main()
