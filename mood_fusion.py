"""Small, explicit precedence rule for camera expressions and EEG focus."""


CAMERA_EXPRESSIONS = {"happy", "sad", "sleepy"}


def choose_auto_mood(camera_mood, focus_state):
    if camera_mood in CAMERA_EXPRESSIONS:
        return camera_mood
    if focus_state == "focus-like":
        return "focused"
    return "idle"
