"""Train only on the public INTERFACES no-ICA features; split by person."""
import hashlib
import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, roc_auc_score, confusion_matrix
from sklearn.model_selection import GroupKFold, GridSearchCV
from sklearn.svm import SVC
import joblib
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data/interfaces'
CHANNELS = ['Fp1', 'Fp2', 'Fz', 'Cz', 'T7', 'T8', 'Pz', 'Oz']


def train():
    x = np.load(DATA / 'EEG_no_ICA.npy', allow_pickle=False)
    if x.shape != (645, 32) or not np.isfinite(x).all():
        raise ValueError('Expected finite INTERFACES no-ICA features shaped (645, 32).')
    groups = np.repeat(np.arange(43), 15)  # subject-major order verified in authors' preprocessing notebook
    artifact = {'schema': 1, 'channels': CHANNELS, 'window_seconds': 56,
                'feature_recipe': 'interfaces-no-ica-log-peak-welch-v1',
                'source': 'https://github.com/IoBT-VISTEC/EEG-Emotion-Recognition-INTERFACES-datasets',
                'models': {}, 'evaluation': {}, 'files_sha256': {}}
    for path in DATA.glob('*.npy'):
        artifact['files_sha256'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    for label in ['valence', 'arousal']:
        y = np.load(DATA / f'{label}.npy', allow_pickle=False)
        if y.shape != (645,) or set(np.unique(y)) != {0, 1}:
            raise ValueError(f'Unexpected {label} labels')
        probability = np.zeros(len(y))
        folds = []
        for train_idx, test_idx in GroupKFold(5).split(x, y, groups):
            assert not set(groups[train_idx]) & set(groups[test_idx])
            search = GridSearchCV(make_pipeline(StandardScaler(), SVC(class_weight='balanced', probability=True, random_state=42)), {'svc__C': [.1, 1, 10], 'svc__gamma': ['scale', .01, .1]}, scoring='balanced_accuracy', cv=GroupKFold(3), n_jobs=2)
            search.fit(x[train_idx], y[train_idx], groups=groups[train_idx])
            probability[test_idx] = search.predict_proba(x[test_idx])[:, 1]
            print(label, 'outer fold complete', flush=True)
            folds.append({'train_subjects': groups[train_idx].astype(int).tolist()[::15], 'test_subjects': sorted(set(groups[test_idx].astype(int).tolist()))})
        evaluation = {'balanced_accuracy': float(balanced_accuracy_score(y, probability >= .5)),
                      'roc_auc': float(roc_auc_score(y, probability)),
                      'confusion_matrix': confusion_matrix(y, probability >= .5).tolist(),
                      'method': 'Nested 5-fold held-out-subject evaluation; 3-fold grouped inner tuning; preprocessing fit only on training folds',
                      'folds': folds}
        artifact['evaluation'][label] = evaluation
        search.fit(x, y, groups=groups)
        model = search.best_estimator_
        scaler = model.steps[0][1]
        z = scaler.transform(x)
        joblib.dump(model, ROOT / f'models/{label}.joblib')
        artifact['models'][label] = {'mean': scaler.mean_.tolist(), 'scale': scaler.scale_.tolist(),
            'pipeline': f'{label}.joblib', 'parameters': search.best_params_,
            'ood_rms_limit': float(np.quantile(np.sqrt(np.mean(z*z, axis=1)), .99) * 1.5)}
        print(label, {k:v for k,v in evaluation.items() if k != 'folds'})
    (ROOT / 'models').mkdir(exist_ok=True)
    (ROOT / 'models/emotion.json').write_text(json.dumps(artifact, indent=2))


if __name__ == '__main__':
    train()
