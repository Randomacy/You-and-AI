"""Read facial movements from a webcam and send cautious mood changes to the avatar.

Only the live frames in memory are used. No images or scores are saved or sent.
"""

from collections import Counter, deque
from pathlib import Path
import threading
import time


DEFAULT_MODEL = Path(__file__).resolve().parent / "models" / "face_landmarker.task"
DEFAULT_FROWN_THRESHOLD = 0.01
DEFAULT_SLEEPY_EYE_THRESHOLD = 0.35
DEFAULT_SLEEPY_HOLD_SECONDS = 1.5


def both_eyes_lowered(scores, threshold=DEFAULT_SLEEPY_EYE_THRESHOLD):
    """Require both eyelids to be at least partly lowered."""
    return min(scores.get("eyeBlinkLeft", 0.0), scores.get("eyeBlinkRight", 0.0)) >= threshold


def expression_from_scores(scores, eyes_lowered_for=0.0,
                           frown_threshold=DEFAULT_FROWN_THRESHOLD,
                           sleepy_hold_seconds=DEFAULT_SLEEPY_HOLD_SECONDS):
    """Map visible movements to avatar moods, not to a claim about inner feelings."""
    mean = lambda left, right: (scores.get(left, 0.0) + scores.get(right, 0.0)) / 2
    smile = mean("mouthSmileLeft", "mouthSmileRight")
    frown = mean("mouthFrownLeft", "mouthFrownRight")
    if eyes_lowered_for >= sleepy_hold_seconds:
        return "sleepy"
    if smile >= 0.50 and smile > frown + 0.15:
        return "happy"
    if frown >= frown_threshold and frown > smile:
        return "sad"
    return "idle"


class CameraMoodWorker:
    def __init__(self, emit, camera_index=0, model_path=DEFAULT_MODEL,
                 frown_threshold=DEFAULT_FROWN_THRESHOLD,
                 sleepy_eye_threshold=DEFAULT_SLEEPY_EYE_THRESHOLD,
                 sleepy_hold_seconds=DEFAULT_SLEEPY_HOLD_SECONDS, debug=False):
        self.emit = emit
        self.camera_index = camera_index
        self.model_path = Path(model_path)
        self.frown_threshold = frown_threshold
        self.sleepy_eye_threshold = sleepy_eye_threshold
        self.sleepy_hold_seconds = sleepy_hold_seconds
        self.debug = debug
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, name="camera-mood", daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def run(self):
        capture = None
        failed = False
        try:
            if not self.model_path.is_file():
                raise RuntimeError(f"Face model missing: {self.model_path}")
            try:
                import cv2
                import mediapipe as mp
            except ImportError as exc:
                raise RuntimeError("Install camera dependencies: pip install -r requirements.txt") from exc

            options = mp.tasks.vision.FaceLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(self.model_path)),
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_faces=1,
                output_face_blendshapes=True,
            )
            capture = cv2.VideoCapture(self.camera_index)
            if not capture.isOpened():
                raise RuntimeError(f"Camera {self.camera_index} could not be opened")
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.emit({"camera_status": "on"})

            recent = deque(maxlen=6)
            eye_recent = deque(maxlen=5)
            current_mood = "idle"
            eyes_lowered_since = None
            no_face_since = None
            read_failures = 0
            last_timestamp = 0
            last_debug_at = 0.0
            with mp.tasks.vision.FaceLandmarker.create_from_options(options) as detector:
                while not self.stop_event.is_set():
                    ok, frame = capture.read()
                    if not ok:
                        read_failures += 1
                        if read_failures >= 10:
                            raise RuntimeError("Camera stopped providing frames")
                        self.stop_event.wait(0.1)
                        continue
                    read_failures = 0
                    height, width = frame.shape[:2]
                    if width > 640:
                        frame = cv2.resize(frame, (640, round(height * 640 / width)))
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                    timestamp = max(last_timestamp + 1, int(time.monotonic() * 1000))
                    last_timestamp = timestamp
                    result = detector.detect_for_video(image, timestamp)
                    now = time.monotonic()

                    if result.face_blendshapes:
                        no_face_since = None
                        scores = {item.category_name: item.score for item in result.face_blendshapes[0]}
                        eye_recent.append(both_eyes_lowered(scores, self.sleepy_eye_threshold))
                        eyes_lowered = len(eye_recent) >= 3 and sum(eye_recent) >= 3
                        eyes_lowered_since = (eyes_lowered_since or now) if eyes_lowered else None
                        lowered_for = now - eyes_lowered_since if eyes_lowered_since is not None else 0.0
                        candidate = expression_from_scores(
                            scores, lowered_for, self.frown_threshold, self.sleepy_hold_seconds
                        )
                        recent.append(candidate)
                        vote_mood, vote_count = Counter(recent).most_common(1)[0]
                        if len(recent) == recent.maxlen and vote_count >= 4 and vote_mood != current_mood:
                            current_mood = vote_mood
                            self.emit({"mood": vote_mood, "source": "camera"})
                        if self.debug and now - last_debug_at >= 1.0:
                            smile = (scores.get("mouthSmileLeft", 0) + scores.get("mouthSmileRight", 0)) / 2
                            frown = (scores.get("mouthFrownLeft", 0) + scores.get("mouthFrownRight", 0)) / 2
                            brow_down = (scores.get("browDownLeft", 0) + scores.get("browDownRight", 0)) / 2
                            eye_left = scores.get("eyeBlinkLeft", 0)
                            eye_right = scores.get("eyeBlinkRight", 0)
                            print(f"[camera] smile={smile:.3f} frown={frown:.3f} "
                                  f"browDown={brow_down:.3f} eyeL={eye_left:.3f} eyeR={eye_right:.3f} "
                                  f"eyeVotes={sum(eye_recent)}/{len(eye_recent)} "
                                  f"eyeHold={lowered_for:.1f}s threshold={self.frown_threshold:.3f} "
                                  f"candidate={candidate} votes={vote_mood}:{vote_count}/{len(recent)} "
                                  f"active={current_mood}", flush=True)
                            last_debug_at = now
                    else:
                        eyes_lowered_since = None
                        eye_recent.clear()
                        recent.clear()
                        no_face_since = no_face_since or now
                        if self.debug and now - last_debug_at >= 1.0:
                            print("[camera] no face detected", flush=True)
                            last_debug_at = now
                        if current_mood != "idle" and now - no_face_since >= 1.0:
                            current_mood = "idle"
                            self.emit({"mood": "idle", "source": "camera"})

                    self.stop_event.wait(0.08)
        except Exception as exc:
            failed = True
            self.emit({"camera_status": "error", "detail": str(exc)})
        finally:
            if capture is not None:
                capture.release()
            if not failed:
                self.emit({"camera_status": "off"})
