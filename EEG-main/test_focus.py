import unittest
import numpy as np
from focus import estimate_focus
class FocusTests(unittest.TestCase):
    def test_quality_and_synthetic_abstain(self):
        x=np.ones((8,375))
        self.assertEqual(estimate_focus(x,125,['noise'])['status'],'unclear')
        self.assertEqual(estimate_focus(x,125,[],True)['status'],'unclear')
    def test_band_ratio_direction(self):
        t=np.arange(375)/125
        low=np.tile(np.sin(2*np.pi*6*t)+np.sin(2*np.pi*10*t)+.2*np.sin(2*np.pi*20*t),(8,1))
        high=np.tile(np.sin(2*np.pi*6*t)+np.sin(2*np.pi*10*t)+2*np.sin(2*np.pi*20*t),(8,1))
        self.assertGreater(estimate_focus(high,125,[])['ratio'],estimate_focus(low,125,[])['ratio'])
