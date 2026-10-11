import tempfile,unittest,json,time
from pathlib import Path
import numpy as np
from capture_session import CaptureSession

class CaptureTests(unittest.TestCase):
 def test_preserves_raw_samples_and_timestamps(self):
  with tempfile.TemporaryDirectory() as root:
   capture=CaptureSession(root);session=capture.start({'channels':['a']*8,'sample_rate_hz':125})
   raw=np.arange(32.).reshape(8,4);ts=np.arange(4.)+100
   capture.append(raw,ts,np.arange(4));raw[:]=0
   with self.assertRaises(ValueError):capture.finish('wrong')
   result=capture.finish(session['id']);self.assertEqual(result['sample_count'],4)
   folder=Path(root)/('capture-'+session['id'])
   with np.load(folder/'eeg.npz',allow_pickle=False) as data:
    self.assertEqual(data['raw_uv'][7,3],31)
    np.testing.assert_array_equal(data['brainflow_timestamp_unix'],ts)
   self.assertIn('Approximate',json.loads((folder/'manifest.json').read_text())['alignment'])
 def test_deadline_limits_samples(self):
  with tempfile.TemporaryDirectory() as root:
   capture=CaptureSession(root);session=capture.start({})
   capture.current['deadline']=time.monotonic()-1
   capture.append(np.ones((8,2)),np.ones(2),np.ones(2))
   self.assertEqual(capture.finish(session['id'])['sample_count'],0)
