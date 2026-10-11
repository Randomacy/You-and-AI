"""Set the avatar's mood from another process (e.g. the EEG backend).

CLI:     python send_mood.py happy "you're smiling!"
Import:  from send_mood import send_mood; send_mood("calm")

Moods: idle, happy, calm, focused, sleepy, sad
"""
import json
import socket
import sys

_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def send_mood(mood=None, say=None, port=5005):
    msg = {k: v for k, v in (("mood", mood), ("say", say)) if v}
    _sock.sendto(json.dumps(msg).encode(), ("127.0.0.1", port))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    send_mood(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
