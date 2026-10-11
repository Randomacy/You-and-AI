"""Bounded opt-in raw EEG recording; shared by the acquisition thread and API."""
import json
import secrets
import threading
import time
from pathlib import Path
import numpy as np

class CaptureSession:
    def __init__(self, root):
        self.root = Path(root)
        self.lock = threading.Lock()
        self.current = None

    def start(self, metadata):
        with self.lock:
            expired = self.current['id'] if self.current and time.monotonic() > self.current['deadline'] else None
        if expired:
            self.finish(expired)
        with self.lock:
            if self.current is not None:
                raise ValueError('Finish the existing recording first')
            sid = secrets.token_hex(12)
            self.current = {'id': sid, 'started_at_unix': time.time(),
                            'deadline': time.monotonic() + 20, 'chunks': [],
                            'metadata': metadata}
            return {'id': sid, 'started_at_unix': self.current['started_at_unix'],
                    'maximum_eeg_seconds': 20}

    def append(self, raw, timestamps, packets):
        with self.lock:
            s = self.current
            if s is None or time.monotonic() > s['deadline']:
                return
            s['chunks'].append((raw.copy(), timestamps.copy(), packets.copy(),
                                np.full(raw.shape[1], time.time())))

    def finish(self, sid):
        with self.lock:
            s = self.current
            if s is None or sid != s['id']:
                raise ValueError('Recording session expired')
            self.current = None
        folder = self.root / ('capture-' + sid)
        folder.mkdir(parents=True, exist_ok=False)
        chunks = s.pop('chunks')
        metadata = s.pop('metadata')
        s.pop('deadline')
        if chunks:
            raw = np.concatenate([c[0] for c in chunks], axis=1)
            timestamps, packets, received = [np.concatenate([c[i] for c in chunks]) for i in (1,2,3)]
        else:
            raw = np.empty((8,0));timestamps=packets=received=np.empty(0)
        np.savez_compressed(folder/'eeg.npz', raw_uv=raw,
                            brainflow_timestamp_unix=timestamps,
                            packet_counter=packets, host_received_unix=received)
        s.update(metadata, packet_discontinuities=int(np.sum(np.diff(packets) % 256 != 1)), ended_at_unix=time.time(), sample_count=raw.shape[1],
                 eeg_complete=bool(raw.shape[1]),
                 alignment='Approximate host timing. BrainFlow timestamps and WebRTC arrival are not hardware synchronized. EEG includes pre/post-roll up to 20 seconds.',
                 filters='Raw BrainFlow microvolts; no notch or bandpass applied to saved EEG.')
        (folder/'manifest.json').write_text(json.dumps(s, indent=2)+'\n')
        return {'id':sid,'sample_count':raw.shape[1]}
