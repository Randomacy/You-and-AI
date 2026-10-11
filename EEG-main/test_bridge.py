"""Run with .venv/bin/python -m unittest -v. Uses BrainFlow synthetic board only."""
import time
import unittest
from server import Bridge, CHANNELS


class BridgeTests(unittest.TestCase):
    def test_map_and_stale_state(self):
        bridge = Bridge()
        self.assertEqual(CHANNELS, ['Fp1', 'Fp2', 'Fz', 'Cz', 'T7', 'T8', 'Pz', 'Oz'])
        bridge.update(status='streaming', last_sample_at=time.time()-4)
        self.assertEqual(bridge.snapshot()['status'], 'stale')

    def test_synthetic_pipeline_and_release(self):
        bridge = Bridge()
        try:
            self.assertTrue(bridge.connect('', synthetic=True))
            self.assertFalse(bridge.connect('', synthetic=True))
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                state = bridge.snapshot()
                if state['status'] in ('streaming', 'error'):
                    break
                time.sleep(.1)
            self.assertEqual(state['status'], 'streaming', state['message'])
            self.assertTrue(state['synthetic'])
            self.assertEqual(len(state['traces']), 8)
            self.assertTrue(all(len(row) == 240 for row in state['traces']))
            self.assertTrue(0 <= state['energy'] <= 1)
        finally:
            bridge.disconnect()
            bridge.thread.join(5)
        self.assertFalse(bridge.thread.is_alive())
        self.assertEqual(bridge.snapshot()['status'], 'disconnected')
        self.assertEqual(bridge.snapshot()['traces'], [])


if __name__ == '__main__':
    unittest.main()
