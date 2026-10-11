"""Bloom, an always-on-top desktop companion.

A small flower companion whose mood can be set by:
  - keys 1-6 (click the avatar first), right-click menu
  - the webcam, started from the right-click menu or --camera
  - a UDP message from another process (e.g. the EEG backend), see send_mood.py

Run:  python avatar.py [--scale 16] [--port 5005]
"""
import argparse
import json
import queue
import random
import socket
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox
from PIL import ImageTk

from bloom_art import render_bloom
from camera_mood import (DEFAULT_FROWN_THRESHOLD, DEFAULT_SLEEPY_EYE_THRESHOLD,
                         DEFAULT_SLEEPY_HOLD_SECONDS)
from mood_fusion import choose_auto_mood

KEY = "#ff00fe"  # window colour that Windows renders as fully transparent
CREAM = "#fff8f1"
PLUM = "#2d2250"
BLOOM_LINES = {
    "idle": "What are you noticing?",
    "happy": "Something good is growing.",
    "sad": "We don't have to rush this.",
    "sleepy": "Let's let the day soften.",
    "focused": "I've got the thread. Keep going.",
    "calm": "Take a moment to breathe.",
}

MOODS = set(BLOOM_LINES)
MOOD_KEYS = ["happy", "sad", "sleepy", "focused", "idle", "calm"]


class Avatar:
    def __init__(self, scale, port, camera_index=0, camera_model=None,
                 frown_threshold=DEFAULT_FROWN_THRESHOLD,
                 sleepy_eye_threshold=DEFAULT_SLEEPY_EYE_THRESHOLD,
                 sleepy_hold_seconds=DEFAULT_SLEEPY_HOLD_SECONDS,
                 camera_debug=False, reduced_motion=False):
        self.s = scale
        self.w = max(200, 22 * scale)
        self.h = max(220, 24 * scale)
        self.flower_size = max(160, 17 * scale)
        self.reduced_motion = reduced_motion
        self.started = time.monotonic()
        self.photo = None

        self.mood = "idle"
        self.tick = 0
        self.bubble_text, self.bubble_until = "", 0
        self.inbox = queue.Queue()
        self.camera_worker = None
        self.camera_mood = "idle"
        self.focus_state = "unavailable"
        self.focus_received_at = 0.0
        self.manual_override = False
        self.auto_selected = False
        self.camera_index = camera_index
        self.camera_model = camera_model
        self.frown_threshold = frown_threshold
        self.sleepy_eye_threshold = sleepy_eye_threshold
        self.sleepy_hold_seconds = sleepy_hold_seconds
        self.camera_debug = camera_debug

        root = self.root = tk.Tk()
        root.title("Bloom · You & AI")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.config(bg=KEY)
        try:
            root.attributes("-transparentcolor", KEY)
        except tk.TclError:
            pass  # non-Windows: falls back to a coloured square
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{self.w}x{self.h}+{sw - self.w - 40}+{sh - self.h - 80}")

        self.canvas = tk.Canvas(root, width=self.w, height=self.h, bg=KEY,
                                highlightthickness=0, bd=0)
        self.canvas.pack()
        self.font = tkfont.Font(family="Consolas", size=max(9, scale // 3 + 3))
        self.label_font = tkfont.Font(family="Consolas", size=max(8, scale // 3 + 2))

        self.menu = tk.Menu(root, tearoff=0)
        self.menu_mood = tk.StringVar(value=self.mood)
        for i, m in enumerate(MOOD_KEYS, 1):
            self.menu.add_radiobutton(label=f"{i}  {m}", variable=self.menu_mood, value=m,
                                      command=lambda m=m: self.set_manual_mood(m))
        self.menu.add_separator()
        self.camera_menu_index = self.menu.index("end") + 1
        self.menu.add_command(label="Start camera", command=self.toggle_camera)
        self.menu.add_command(label="Resume automatic moods", command=self.resume_auto_mood)
        self.menu.add_separator()
        self.menu.add_command(label="Quit", command=self.quit)

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))
        root.bind("<Escape>", lambda e: self.quit())
        for i, m in enumerate(MOOD_KEYS, 1):
            root.bind(str(i), lambda e, m=m: self.set_manual_mood(m))

        threading.Thread(target=self.listen, args=(port,), daemon=True).start()
        self.say(BLOOM_LINES["idle"], 40)
        self.loop()
        self.keep_on_top()

    # ------------------------------------------------------------ control --
    def set_manual_mood(self, mood):
        if self.camera_worker is not None:
            self.stop_camera()
        self.manual_override = True
        self.auto_selected = False
        self.set_mood(mood)

    def resume_auto_mood(self):
        self.manual_override = False
        self.apply_auto_mood()
        self.say("Automatic mood on")

    def apply_auto_mood(self):
        if self.manual_override:
            return
        current_focus = (
            self.focus_state if time.monotonic() - self.focus_received_at <= 6.0
            else "unavailable"
        )
        camera_mood = self.camera_mood if self.camera_worker is not None else "idle"
        self.set_mood(choose_auto_mood(camera_mood, current_focus))
        self.auto_selected = True

    def start_camera(self):
        if self.camera_worker is not None:
            return
        self.manual_override = False
        self.camera_mood = "idle"
        from camera_mood import CameraMoodWorker
        options = {"emit": self.inbox.put, "camera_index": self.camera_index,
                   "frown_threshold": self.frown_threshold,
                   "sleepy_eye_threshold": self.sleepy_eye_threshold,
                   "sleepy_hold_seconds": self.sleepy_hold_seconds,
                   "debug": self.camera_debug}
        if self.camera_model is not None:
            options["model_path"] = self.camera_model
        self.camera_worker = CameraMoodWorker(**options)
        self.camera_worker.start()
        self.menu.entryconfigure(self.camera_menu_index, label="Stop camera")
        self.apply_auto_mood()
        self.say("Opening camera...")

    def stop_camera(self):
        if self.camera_worker is not None:
            self.camera_worker.stop()
            self.menu.entryconfigure(self.camera_menu_index, label="Stopping camera...")
            self.camera_mood = "idle"
            self.apply_auto_mood()

    def toggle_camera(self):
        if self.camera_worker is None:
            self.start_camera()
        else:
            self.stop_camera()

    def quit(self):
        self.stop_camera()
        self.root.destroy()

    def set_mood(self, mood, say=None):
        if mood not in MOODS:
            return
        changed = mood != self.mood
        self.mood = mood
        self.menu_mood.set(mood)
        if say or changed:
            self.say(say or BLOOM_LINES[mood])

    def say(self, text, ticks=30):
        self.bubble_text, self.bubble_until = text, self.tick + ticks

    def listen(self, port):
        """Accept UDP datagrams: 'happy' or {"mood": "happy", "say": "nice!"}."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError as e:
            print(f"[avatar] UDP port {port} unavailable ({e}); remote control off", file=sys.stderr)
            return
        print(f"[avatar] listening on udp://127.0.0.1:{port}")
        while True:
            data, _ = sock.recvfrom(4096)
            text = data.decode("utf-8", "replace").strip()
            try:
                msg = json.loads(text)
            except json.JSONDecodeError:
                msg = {"mood": text}
            if isinstance(msg, dict):
                self.inbox.put(msg)

    def on_press(self, e):
        self.root.focus_force()
        self.drag_from = (e.x, e.y)
        self.dragged = False

    def on_drag(self, e):
        self.dragged = True
        x, y = self.drag_from
        self.root.geometry(f"+{e.x_root - x}+{e.y_root - y}")

    def on_release(self, e):
        if not self.dragged:
            self.say(random.choice(["Hello there.", "I'm here.", "What are you noticing?"]), 15)

    def keep_on_top(self):
        self.root.attributes("-topmost", True)
        self.root.lift()
        self.root.after(2000, self.keep_on_top)

    # ---------------------------------------------------------- animation --
    def loop(self):
        while not self.inbox.empty():
            msg = self.inbox.get()
            if "camera_status" in msg:
                status = msg["camera_status"]
                if status in ("off", "error"):
                    self.camera_worker = None
                    self.camera_mood = "idle"
                    self.menu.entryconfigure(self.camera_menu_index, label="Start camera")
                    if self.auto_selected:
                        self.apply_auto_mood()
                    if status == "error":
                        print(f"[camera] {msg.get('detail', 'Unknown error')}", file=sys.stderr)
                        self.say("Camera unavailable", 50)
                        messagebox.showerror("Camera unavailable", msg.get("detail", "Unknown error"), parent=self.root)
                    else:
                        self.say("Camera off")
                elif status == "on":
                    self.say("Camera on")
                continue
            if msg.get("source") == "eeg_focus":
                if msg.get("state") in ("focus-like", "rest-like", "uncertain", "unavailable"):
                    self.focus_state = msg["state"]
                    self.focus_received_at = time.monotonic()
                    self.apply_auto_mood()
                continue
            if msg.get("source") == "camera" and (
                self.camera_worker is None or self.camera_worker.stop_event.is_set()
            ):
                continue
            if msg.get("source") == "camera" and msg.get("mood") in MOODS:
                self.camera_mood = msg["mood"]
                self.apply_auto_mood()
                continue
            if msg.get("mood") in MOODS:
                self.auto_selected = False
                self.set_mood(msg["mood"], msg.get("say"))
            elif msg.get("say"):
                self.say(msg["say"])
        if (self.auto_selected and self.focus_state != "unavailable"
                and time.monotonic() - self.focus_received_at > 6.0):
            self.focus_state = "unavailable"
            self.apply_auto_mood()
        self.tick += 1
        self.draw()
        self.root.after(100, self.loop)

    def draw(self):
        c = self.canvas
        c.delete("all")
        frame = render_bloom(self.flower_size, self.mood,
                             time.monotonic() - self.started, self.reduced_motion)
        self.photo = ImageTk.PhotoImage(frame)
        c.create_image(self.w / 2, self.h * .56, image=self.photo)
        c.create_text(self.w / 2, 4, anchor="n", text=f"BLOOM / {self.mood.upper()}",
                      font=self.label_font, fill=PLUM)

        text = self.bubble_text if self.tick < self.bubble_until else BLOOM_LINES[self.mood]
        text = text[:90]
        by = max(24, self.h * .08)
        padding = max(10, self.s // 2)
        text_item = c.create_text(self.w / 2, by + padding, anchor="n", text=text,
                                  font=self.font, fill=PLUM, width=self.w - 64,
                                  justify="center")
        bounds = c.bbox(text_item)
        bh = (bounds[3] - bounds[1]) + 2 * padding
        bw = min(self.w - 16, max(130, bounds[2] - bounds[0] + 2 * padding + 8))
        bx = (self.w - bw) / 2
        c.create_oval(bx, by, bx + bh, by + bh, fill=CREAM, outline=PLUM, width=2)
        c.create_oval(bx + bw - bh, by, bx + bw, by + bh, fill=CREAM, outline=PLUM, width=2)
        c.create_rectangle(bx + bh / 2, by, bx + bw - bh / 2, by + bh,
                           fill=CREAM, outline="")
        c.create_line(bx + bh / 2, by, bx + bw - bh / 2, by, fill=PLUM, width=2)
        c.create_line(bx + bh / 2, by + bh, bx + bw - bh / 2, by + bh, fill=PLUM, width=2)
        c.tag_raise(text_item)
        if self.camera_worker is not None and not self.camera_worker.stop_event.is_set():
            c.create_oval(8, 8, 18, 18, fill="#ff765d", outline=PLUM)
            c.create_text(22, 5, anchor="nw", text="CAM", font=self.label_font, fill=PLUM)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scale", type=int, default=16, help="Bloom size (8–32; default 16)")
    ap.add_argument("--port", type=int, default=5005, help="UDP port for mood messages")
    ap.add_argument("--camera", action="store_true", help="start webcam expression detection")
    ap.add_argument("--camera-index", type=int, default=0, help="webcam device index")
    ap.add_argument("--camera-model", help="path to the MediaPipe Face Landmarker model")
    ap.add_argument("--frown-threshold", type=float, default=DEFAULT_FROWN_THRESHOLD,
                    help=f"minimum average mouth-frown score for sad (default: {DEFAULT_FROWN_THRESHOLD})")
    ap.add_argument("--sleepy-eye-threshold", type=float, default=DEFAULT_SLEEPY_EYE_THRESHOLD,
                    help=f"minimum blink score in both eyes for sleepy (default: {DEFAULT_SLEEPY_EYE_THRESHOLD})")
    ap.add_argument("--sleepy-hold-seconds", type=float, default=DEFAULT_SLEEPY_HOLD_SECONDS,
                    help=f"time both eyes stay lowered before sleepy (default: {DEFAULT_SLEEPY_HOLD_SECONDS})")
    ap.add_argument("--camera-debug", action="store_true",
                    help="print live mouth and eye scores about once a second")
    ap.add_argument("--reduced-motion", action="store_true", help="hold Bloom's pose without continuous movement")
    args = ap.parse_args()
    if not 8 <= args.scale <= 32:
        ap.error("--scale must be between 8 and 32")
    if not 0 <= args.frown_threshold <= 1:
        ap.error("--frown-threshold must be between 0 and 1")
    if not 0 < args.sleepy_eye_threshold <= 1:
        ap.error("--sleepy-eye-threshold must be greater than 0 and at most 1")
    if args.sleepy_hold_seconds <= 0:
        ap.error("--sleepy-hold-seconds must be positive")
    if sys.platform == "win32":
        try:  # crisp pixels on high-DPI screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    avatar = Avatar(args.scale, args.port, args.camera_index, args.camera_model,
                    args.frown_threshold, args.sleepy_eye_threshold,
                    args.sleepy_hold_seconds, args.camera_debug, args.reduced_motion)
    if args.camera:
        avatar.start_camera()
    avatar.root.mainloop()


if __name__ == "__main__":
    main()
