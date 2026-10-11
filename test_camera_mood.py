import unittest

from camera_mood import both_eyes_lowered, expression_from_scores


class ExpressionMappingTests(unittest.TestCase):
    def test_neutral_is_idle(self):
        self.assertEqual(expression_from_scores({}), "idle")

    def test_clear_smile_is_happy(self):
        self.assertEqual(expression_from_scores({"mouthSmileLeft": 0.8, "mouthSmileRight": 0.7}), "happy")

    def test_clear_frown_is_sad(self):
        self.assertEqual(expression_from_scores({"mouthFrownLeft": 0.8, "mouthFrownRight": 0.7}), "sad")

    def test_moderate_frown_is_sad(self):
        scores = {"mouthFrownLeft": 0.28, "mouthFrownRight": 0.24,
                  "mouthSmileLeft": 0.03, "mouthSmileRight": 0.03}
        self.assertEqual(expression_from_scores(scores), "sad")
        self.assertEqual(expression_from_scores(scores, frown_threshold=0.4), "idle")

    def test_low_frown_score_can_trigger(self):
        scores = {"mouthFrownLeft": 0.013, "mouthFrownRight": 0.013,
                  "mouthSmileLeft": 0.0, "mouthSmileRight": 0.0}
        self.assertEqual(expression_from_scores(scores), "sad")

    def test_weak_frown_does_not_trigger(self):
        self.assertEqual(expression_from_scores({"mouthFrownLeft": 0.002,
                                                  "mouthFrownRight": 0.005}), "idle")

    def test_mixed_expression_is_idle(self):
        self.assertEqual(expression_from_scores({"mouthSmileLeft": 0.7, "mouthSmileRight": 0.7,
                                                  "mouthFrownLeft": 0.7, "mouthFrownRight": 0.7}), "idle")

    def test_partly_lowered_eyes_can_trigger_sleepy(self):
        scores = {"eyeBlinkLeft": 0.42, "eyeBlinkRight": 0.38}
        self.assertTrue(both_eyes_lowered(scores))
        self.assertEqual(expression_from_scores(scores, eyes_lowered_for=0.2), "idle")
        self.assertEqual(expression_from_scores(scores, eyes_lowered_for=1.5), "sleepy")

    def test_one_open_eye_does_not_count_as_sleepy(self):
        self.assertFalse(both_eyes_lowered({"eyeBlinkLeft": 0.8, "eyeBlinkRight": 0.1}))


if __name__ == "__main__":
    unittest.main()
