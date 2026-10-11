import unittest

from bloom_art import PLUM, render_bloom


class BloomArtTests(unittest.TestCase):
    def test_four_states_are_distinct_and_keep_opaque_plum_mouth(self):
        frames = [render_bloom(320, mood, 1.5) for mood in
                  ("happy", "sad", "sleepy", "focused")]
        self.assertEqual(len({frame.tobytes() for frame in frames}), 4)
        for mood, frame in zip(("happy", "sad", "sleepy", "focused"), frames):
            self.assertEqual(frame.getpixel((0, 0))[3], 0)
            mouth_y = round(320 * (.53 + (.025 if mood == "sad" else 0) + .187 * .32))
            self.assertEqual(frame.getpixel((160, mouth_y)), PLUM)

    def test_reduced_motion_holds_the_pose(self):
        for mood in ("happy", "sad", "sleepy", "focused"):
            self.assertEqual(render_bloom(160, mood, 0, True).tobytes(),
                             render_bloom(160, mood, 100, True).tobytes())


if __name__ == "__main__":
    unittest.main()
