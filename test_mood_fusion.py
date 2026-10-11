import unittest

from mood_fusion import choose_auto_mood


class MoodFusionTests(unittest.TestCase):
    def test_camera_expression_takes_priority(self):
        self.assertEqual(choose_auto_mood("happy", "focus-like"), "happy")
        self.assertEqual(choose_auto_mood("sleepy", "focus-like"), "sleepy")

    def test_focus_fills_idle_camera(self):
        self.assertEqual(choose_auto_mood("idle", "focus-like"), "focused")
        self.assertEqual(choose_auto_mood("idle", "unavailable"), "idle")


if __name__ == "__main__":
    unittest.main()
