"""INTERFACES-based experimental estimates, with explicit abstention."""
import json
from pathlib import Path

import joblib
import numpy as np
from scipy.signal import butter, iirnotch, lfilter, resample_poly, welch

CHANNELS = ['Fp1', 'Fp2', 'Fz', 'Cz', 'T7', 'T8', 'Pz', 'Oz']
BANDS = [(3, 7), (8, 13), (14, 29), (30, 47)]
WINDOW_SECONDS = 56


def unknown(reason, status='unsure', **kwargs):
    return {'face': 'unsure', 'status': status, 'reason': reason, **kwargs}


def extract_features(raw_uv, sample_rate):
    """Reproduce authors' no-ICA CAR, order-2 bands, log peak Welch PSD.

    Upsampling matches the 250-Hz reference feature grid, not extra information.
    An input 50-Hz notch approximates the dataset's acquisition notch.
    """
    raw_uv = np.asarray(raw_uv, dtype=float)
    if sample_rate not in (125, 250):
        raise ValueError('Supported acquisition rates: 125 or 250 Hz')
    if raw_uv.shape != (8, sample_rate * WINDOW_SECONDS) or not np.isfinite(raw_uv).all():
        raise ValueError('Expected a finite 56-second, eight-channel microvolt window')
    x = resample_poly(raw_uv, 2, 1, axis=1) if sample_rate == 125 else raw_uv.copy()
    x = lfilter(*iirnotch(50, 30, 250), x, axis=1)
    x -= x.mean(axis=0, keepdims=True)
    features = np.empty((8, 4))
    for band, (low, high) in enumerate(BANDS):
        filtered = lfilter(*butter(2, [low, high], btype='bandpass', fs=250), x, axis=1)
        _, psd = welch(filtered, fs=250, nperseg=256, noverlap=128, axis=1)
        features[:, band] = np.log(np.maximum(psd.max(axis=1), 1e-20))
    return features.ravel()


class EmotionEstimator:
    def __init__(self, directory=None):
        directory = directory or Path(__file__).resolve().parent / 'models'
        self.metadata = None
        self.models = {}
        self.previous = None
        self.load_error = None
        try:
            self.metadata = json.loads((directory / 'emotion.json').read_text())
            if self.metadata['channels'] != CHANNELS or self.metadata['feature_recipe'] != 'interfaces-no-ica-log-peak-welch-v1':
                raise ValueError('Model montage/feature recipe does not match this demo')
            # Only locally trained files at fixed project paths are loaded.
            self.models = {name: joblib.load(directory / f'{name}.joblib') for name in ('valence', 'arousal')}
        except (OSError, ValueError, KeyError) as exc:
            self.load_error = str(exc)

    def reset(self):
        self.previous = None

    def estimate(self, raw_uv, sample_rate, warnings=(), synthetic=False):
        if synthetic:
            self.reset()
            return unknown('Synthetic test stream; emotion inference is disabled.', 'synthetic')
        if not self.models:
            return unknown('Model unavailable. Run train_emotion.py.', 'missing_model')
        if warnings:
            self.reset()
            return unknown('Signal quality is too poor for an emotion estimate. Check electrode contact.', 'poor_signal')
        required = sample_rate * WINDOW_SECONDS
        if raw_uv.shape[1] < required:
            return unknown(f'Collecting EEG: {raw_uv.shape[1] / sample_rate:.0f} / 56 seconds.', 'collecting')
        # This is a modest engineering gate, not a scientific certification.
        metrics = self.metadata['evaluation']
        if any(metrics[name]['balanced_accuracy'] < .55 for name in self.models):
            self.reset()
            return unknown('Held-out-person accuracy is near chance. Personal calibration is needed before interpreting emotion.', 'validation_insufficient')
        x = extract_features(raw_uv[:, -required:], sample_rate)
        for name in self.models:
            spec = self.metadata['models'][name]
            z = (x - np.asarray(spec['mean'])) / np.asarray(spec['scale'])
            if np.sqrt(np.mean(z*z)) > spec['ood_rms_limit'] or np.max(np.abs(z)) > 8:
                self.reset()
                return unknown('These EEG features differ too much from the training dataset.', 'out_of_distribution')
        p = np.array([self.models[name].predict_proba(x[None, :])[0, 1] for name in ('valence', 'arousal')])
        p = p if self.previous is None else .7 * self.previous + .3 * p
        self.previous = p
        if np.any(np.maximum(p, 1-p) < .65):
            return unknown('The model cannot distinguish the emotion dimensions confidently.', 'uncertain')
        face = ('excited' if p[1] >= .5 else 'calm') if p[0] >= .5 else ('tense' if p[1] >= .5 else 'subdued')
        return {'status': 'estimated', 'face': face, 'reason': 'Experimental estimate; not calibrated to you.',
                'valence_high': round(float(p[0]), 3), 'arousal_high': round(float(p[1]), 3)}
