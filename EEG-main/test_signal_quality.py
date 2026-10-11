import unittest
import numpy as np
from signal_quality import diagnose, ADC_LIMIT_UV


class SignalQualityTests(unittest.TestCase):
    def test_line_noise_and_rails(self):
        t=np.arange(500)/125
        x=np.tile(100*np.sin(2*np.pi*50*t),(8,1))
        result=diagnose(x,125)
        self.assertGreater(result[0]['line_noise_percent'],99)
        self.assertEqual(result[0]['dominant_hz'],50)
        self.assertAlmostEqual(result[0]['line_power_uv2'],5000,delta=10)
        self.assertLess(result[0]['other_power_uv2'],10)
        self.assertEqual(result[0]['clipping_percent'],0)
        x[0,:100]=ADC_LIMIT_UV
        self.assertGreaterEqual(diagnose(x,125)[0]['clipping_percent'],20)

    def test_flat_and_non_mains(self):
        result=diagnose(np.zeros((8,250)),125)
        self.assertTrue(result[0]['notes'][0].startswith('Flat'))
        t=np.arange(500)/125
        result=diagnose(np.tile(30*np.sin(2*np.pi*10*t),(8,1)),125)
        self.assertLess(result[0]['line_noise_percent'],1)
        self.assertEqual(result[0]['dominant_hz'],10)
