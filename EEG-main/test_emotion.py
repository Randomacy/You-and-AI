import json
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from emotion import EmotionEstimator, extract_features


class ConstantModel:
    def __init__(self, probability):
        self.probability = probability
    def predict_proba(self, x):
        return np.array([[1-self.probability, self.probability]])


class EmotionTests(unittest.TestCase):
    def test_features_units_bands_and_rate(self):
        t = np.arange(56*250)/250
        x = np.arange(1,9)[:,None] * np.sin(2*np.pi*10*t)
        features = extract_features(x, 250).reshape(8,4)
        self.assertTrue(np.all(features.argmax(axis=1) == 1))
        np.testing.assert_allclose(extract_features(x*2,250)-features.ravel(), np.log(4), atol=1e-8)
        np.testing.assert_allclose(extract_features(x[:,::2],125), features.ravel(), atol=.08)
        with self.assertRaises(ValueError):
            extract_features(x[:7],250)

    def test_real_artifact_and_subject_separation(self):
        model = EmotionEstimator()
        self.assertIsNone(model.load_error)
        for entry in model.metadata['evaluation'].values():
            seen=[]
            for fold in entry['folds']:
                self.assertFalse(set(fold['train_subjects']) & set(fold['test_subjects']))
                seen.extend(fold['test_subjects'])
            self.assertEqual(sorted(seen), list(range(43)))
        self.assertEqual(model.estimate(np.zeros((8,7000)),125)['status'], 'validation_insufficient')
        self.assertEqual(model.estimate(np.zeros((8,7000)),125,['noise'])['status'], 'poor_signal')
        self.assertEqual(model.estimate(np.zeros((8,7000)),125,synthetic=True)['status'], 'synthetic')

    def test_faces_and_uncertainty_with_controlled_model(self):
        model=EmotionEstimator()
        for entry in model.metadata['evaluation'].values():
            entry['balanced_accuracy']=.8
        for entry in model.metadata['models'].values():
            entry.update(mean=[0]*32,scale=[1]*32,ood_rms_limit=3)
        for valence,arousal,expected in [(.9,.9,'excited'),(.9,.1,'calm'),(.1,.9,'tense'),(.1,.1,'subdued'),(.51,.9,'unsure')]:
            model.reset()
            model.models={'valence':ConstantModel(valence),'arousal':ConstantModel(arousal)}
            with patch('emotion.extract_features',return_value=np.zeros(32)):
                self.assertEqual(model.estimate(np.zeros((8,7000)),125)['face'], expected)
        with patch('emotion.extract_features',return_value=np.ones(32)*20):
            self.assertEqual(model.estimate(np.zeros((8,7000)),125)['status'],'out_of_distribution')
