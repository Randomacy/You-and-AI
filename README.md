# You & AI

**A makeathon prototype that turns live signals into a gentle, expressive companion.**

![Bloom, the eight-petal You & AI companion](bloom-preview.png)

You & AI explores what a more human-centered brain-computer experience could feel like. **Bloom** gives camera and EEG signals a visual language through movement, color, and short reflective prompts. It invites the wearer to notice a state without claiming to know how they feel.

## Try the demo in one minute

The browser showcase needs only Python 3. It does **not** need a camera or headset.

```powershell
python -m http.server 8877 --directory EEG-main --bind 127.0.0.1
```

Open [http://127.0.0.1:8877/bloom.html](http://127.0.0.1:8877/bloom.html). Click **Happy**, **Sad**, **Sleepy**, and **Focused**, or use keys **1–4**. These are manual design previews, not detected emotions.

## What is working

| Part | What it does | What you need |
| --- | --- | --- |
| **Bloom showcase** | Animates four distinct poses in a browser, with reduced-motion support. | Python 3 for the local file server. |
| **Desktop Bloom** | Shows a small Windows companion. Keys **1–6** select a state; right-click opens its controls. | Windows, Python 3.14, project dependencies. |
| **Optional webcam input** | MediaPipe facial movement scores drive simple happy, sad, and sleepy *display states*. Frames are processed in memory. | Webcam and a separately downloaded Face Landmarker model. |
| **Optional EEG focus input** | Cyton Fp1/Fp2 or Muse 2 AF7/AF8 data produce a beta/(alpha + theta) focus-like proxy. A threshold can switch Bloom to focused. | Headset, working signal, and device-specific setup. |
| **Signal Room** | Visualizes a NeuroPawn Knight EEG stream and offers manual interaction experiments. | Its separate Python server; real board access was developed on macOS. |

Camera expressions take priority over the EEG focus state. A neutral camera state lets the EEG focus proxy show through. Manual selection pauses automatic changes until **Resume automatic moods** is chosen.

## Run the Windows desktop companion

From the repository root in PowerShell:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe avatar.py
```

The manual controls work without a headset or camera model. To use the webcam, download the [MediaPipe Face Landmarker model bundle](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker) to `models/face_landmarker.task`, then run:

```powershell
.\.venv\Scripts\python.exe avatar.py --camera
```

Camera use is opt-in. The app does not save or transmit webcam frames. The model file and personal recordings are excluded from Git.

For EEG, start Bloom in one terminal and a monitor in another. First inspect signal quality and choose thresholds for **your own device and session**:

```powershell
# OpenBCI Cyton, with the correct serial port
.\.venv\Scripts\python.exe focus_eeg.py live --port COM5

# Muse 2, after starting an external Muse SDK-to-OSC bridge
.\.venv\Scripts\python.exe eeg_muse.py probe --seconds 10
.\.venv\Scripts\python.exe eeg_muse.py focus --seconds 30
```

Both monitors can send a focus-like state to Bloom after thresholds are set. Run `python focus_eeg.py --help` or `python eeg_muse.py --help` for the live options. The Muse bridge is a separate local service and is **not** included in this repository.

## How it works

```text
Manual controls ─────────────────────────────────────────────┐
Webcam → facial movement rules → happy / sad / sleepy ──────┼→ Bloom
EEG → signal checks → beta/(alpha + theta) → focus-like ────┘
```

The EEG ratio is calculated over four-second windows, updated every two seconds. Signal checks flag weak or artifact-heavy windows. Thresholds and camera rules are prototype heuristics, not measures of emotion, attention, or mental health.

## Research track and current limits

The [Signal Room](EEG-main/README.md) also explores opt-in iPhone audio/video capture and an experimental [TRIBE v2](https://github.com/facebookresearch/tribev2) workflow. TRIBE v2 is **third-party research code** that predicts population-level fMRI responses to media. It does not read the wearer's EEG, and no complete end-to-end TRIBE prediction has been validated in this project. Its downloaded source and weights are not part of this repository. See the [implementation status](EEG-main/MILESTONE_2.md).

An experimental EEG emotion model in Signal Room did not generalize reliably to held-out participants; the live interface reports **Unsure**. The browser action buttons are manual simulations, not thought-controlled commands. Phone media capture is opt-in, and EEG/media timestamps are only approximately aligned.

This is a makeathon prototype for exploration and self-reflection, not a diagnostic or clinical tool.

## Repository map

- [`avatar.py`](avatar.py), [`bloom_art.py`](bloom_art.py), and [`camera_mood.py`](camera_mood.py): desktop companion and webcam input.
- [`focus_eeg.py`](focus_eeg.py), [`eeg_cyton.py`](eeg_cyton.py), and [`eeg_muse.py`](eeg_muse.py): EEG capture, checks, and focus proxy.
- [`EEG-main/`](EEG-main/README.md): browser showcase, Signal Room, phone capture, and detailed implementation notes.
- [`EEG-main/design.md`](EEG-main/design.md): product and visual design direction.

## Privacy and credits

Processing runs locally. Webcam frames are not stored; EEG and optional media recordings stay in local, Git-ignored folders. No cloud inference is configured by this repository.

Bloom and the integration code in this repository are the makeathon work. We use or investigate [MediaPipe Face Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker), [BrainFlow](https://brainflow.readthedocs.io/), the [INTERFACES EEG dataset](https://github.com/IoBT-VISTEC/EEG-Emotion-Recognition-INTERFACES-datasets), and [Meta's TRIBE v2](https://github.com/facebookresearch/tribev2). Those external projects and their models are credited to their respective authors and retain their own license terms.
