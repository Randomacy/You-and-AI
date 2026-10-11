import queue
import threading
import unittest
from unittest.mock import Mock

from avatar import Avatar


class AvatarFocusTests(unittest.TestCase):
    def make_avatar(self):
        avatar = Avatar.__new__(Avatar)
        avatar.inbox = queue.Queue()
        avatar.camera_worker = None
        avatar.camera_mood = "idle"
        avatar.focus_state = "unavailable"
        avatar.focus_received_at = 0.0
        avatar.manual_override = False
        avatar.auto_selected = False
        avatar.tick = 0
        avatar.root = Mock()
        avatar.set_mood = Mock()
        avatar.spawn_particles = Mock()
        avatar.draw = Mock()
        return avatar

    def test_focus_and_camera_precedence(self):
        avatar = self.make_avatar()
        avatar.inbox.put({"source": "eeg_focus", "state": "focus-like", "score": 90})
        avatar.loop()
        avatar.set_mood.assert_called_with("focused")

        worker = Mock()
        worker.stop_event = threading.Event()
        avatar.camera_worker = worker
        avatar.inbox.put({"source": "camera", "mood": "happy"})
        avatar.loop()
        avatar.set_mood.assert_called_with("happy")

        avatar.inbox.put({"source": "camera", "mood": "idle"})
        avatar.loop()
        avatar.set_mood.assert_called_with("focused")

    def test_manual_override_ignores_focus(self):
        avatar = self.make_avatar()
        avatar.manual_override = True
        avatar.inbox.put({"source": "eeg_focus", "state": "focus-like", "score": 90})
        avatar.loop()
        avatar.set_mood.assert_not_called()


if __name__ == "__main__":
    unittest.main()
