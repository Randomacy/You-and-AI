# CommonGround Bloom avatar prototype

Bloom is the eight-petal desktop companion from [EEG-main/design.md](EEG-main/design.md). Its happy, sad, sleepy, and focused poses follow that design; idle and calm remain available for the existing controls. The avatar reflects visible facial movements through a webcam and can show a thresholded **focus-like** state from Cyton Fp1/Fp2 or Muse 2 AF7/AF8 EEG. These prototype mappings do not directly measure feelings. Camera processing runs on this computer; the app does not save or transmit video. EEG recordings stay local.

Open the matching four-state showcase at `http://127.0.0.1:8765/bloom` when the separate `EEG-main/server.py` is running. The showcase is a manual design preview; the desktop Bloom receives the live camera and Muse events. On the desktop avatar, keys **1–4** preview Happy, Sad, Sleepy, and Focused; **5–6** select Idle and Calm. Right-click to resume automatic moods. Pass `--reduced-motion` to hold Bloom's pose without continuous animation.

## Run on Windows

Use Python 3.14 and install the camera dependencies in a virtual environment:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe avatar.py
```

Right-click the avatar and choose **Start camera**, or start directly with:

```powershell
.\.venv\Scripts\python.exe avatar.py --camera
```

Use `--camera-index 1` if the desired webcam is not camera 0. The Face Landmarker model is expected at `models/face_landmarker.task`; use `--camera-model PATH` to select another copy. The model comes from [Google's Face Landmarker model bundle](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker#models).

The camera currently maps a clear smile to **happy**, a frown to **sad**, and both eyelids held partly lowered to **sleepy**. A neutral expression or no detected face returns to **idle**. **Focused** comes from thresholded Cyton or Muse EEG when the camera is neutral; **calm** remains a manual or UDP state. These mappings are simple prototype heuristics, not emotion diagnoses.

The frown trigger now starts at an average mouth-frown score of `0.01`, based on observed scores from the camera. Launch with `--camera --camera-debug` to see live scores, the recent vote count, and the active avatar state in PowerShell. You can raise the trigger, for example with `--frown-threshold 0.02`, if neutral expressions trigger **sad**. The frown score must also exceed the smile score, and the expression must remain consistent across several frames. The `browDown` score in debug output helps show whether an eyebrow frown is being detected separately from the mouth movement.

For **sleepy**, both eyes' `eyeBlink` scores must reach at least `0.35` across most recent frames and stay there for `1.5` seconds; they do not have to be fully closed. Debug output shows `eyeL`, `eyeR`, `eyeVotes`, and `eyeHold`. If your half-closed eyes score lower, try `--sleepy-eye-threshold 0.25`. Raise the threshold if ordinary relaxed eyes trigger sleepy.

The coral **CAM** indicator appears while camera control is active. Keys 1–6 select a mood manually and turn off camera control. Right-click **Stop camera** to release the webcam. Escape or **Quit** closes the avatar.

To control the avatar from another process, run `.\.venv\Scripts\python.exe send_mood.py happy` in another terminal while the avatar is open.

## Record OpenBCI Cyton Fp1/Fp2

Connect Fp1 to Cyton channel 1 and Fp2 to channel 2, with reference and bias electrodes as in the [OpenBCI Mark IV guide](https://docs.openbci.com/AddOns/Headwear/MarkIV/). Plug in the Cyton dongle, turn on the board, and close other software using its COM port. Find the port in Windows Device Manager or with `[System.IO.Ports.SerialPort]::GetPortNames()` in PowerShell.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe eeg_cyton.py record --port COM5 --out recordings\first-session.csv --seconds 30
```

Replace `COM5` with the Cyton dongle's port. The recorder explicitly configures channels 1 and 2 to the Cyton's **maximum ×24 gain**, then reads back their registers. If either channel does not confirm normal input, powered on, and ×24 gain, recording stops with an error. It will **not** reduce gain automatically. OpenBCI documents the [channel settings command and register query](https://docs.openbci.com/Cyton/CytonSDK/).

The terminal displays a short trace, RMS, range, and basic flags each interval. `RAILED` means the signal approaches the input limit; `FLAT` means less than 0.5 µV range; `LOW AMP` means less than 2 µV range. These are rough display flags, not electrode contact tests. OpenBCI notes that ×24 gain can rail on some wearers; check electrode placement and contact if that happens. [OpenBCI troubleshooting](https://docs.openbci.com/Troubleshooting/GUI_Troubleshooting/)

Recording writes microvolt samples to `first-session.csv` and device metadata to `first-session.json`. New recordings include the Cyton packet counter, an approximate sample time based on its nominal 250 Hz rate, and BrainFlow's raw host arrival time. The estimated time is useful for replay but is not precise enough yet to synchronize EEG with camera or audio. The older three-column recordings still replay; replay now groups samples by count because their host timestamps can arrive in USB batches. These files are local and are not sent anywhere. To inspect a saved recording without the headset:

```powershell
.\.venv\Scripts\python.exe eeg_cyton.py replay recordings\first-session.csv
```

The recorder itself only captures EEG. The focus monitor below can combine a thresholded EEG engagement index with the camera's avatar states. This does not infer a full emotional state.

## Personal focus proxy from Fp1/Fp2

`focus_eeg.py` computes the classic experimental engagement index, **beta power / (alpha power + theta power)**, over four-second Fp1/Fp2 windows, updated every two seconds. Beta is 13–30 Hz, alpha is 8–13 Hz, and theta is 4–8 Hz. It averages the two channels' band powers before forming the ratio. The ratio is an EEG feature, not a definitive measure of attention or emotion. A study found engagement indices can respond to task demands, but results vary across tasks and people. [EEG engagement study](https://pmc.ncbi.nlm.nih.gov/articles/PMC11506387/)

First check the signal and view the raw ratio in your recording:

```powershell
.\.venv\Scripts\python.exe focus_eeg.py inspect recordings\first-session.csv
.\.venv\Scripts\python.exe focus_eeg.py replay recordings\first-session.csv --speed 10
```

`replay` prints the ratio and theta, alpha, and beta band powers for each window. `LOW AMP` appears beside a ratio when a channel spans less than 2 µV; the number is still shown, but may be dominated by noise. Railed, artifact-heavy, invalid, and severely gapped windows remain unavailable. Your existing `first-session.csv` has `LOW AMP` windows, so use its ratios only to test the display, not to choose reliable thresholds.

Run live without thresholds to observe your own ratio during neutral and concentrated periods:

```powershell
.\.venv\Scripts\python.exe focus_eeg.py live --port COM8
```

After observing the values, choose an upper threshold to turn focus on and a lower one to turn it off. For example, these numbers are **examples only**, not validated values for your EEG:

```powershell
.\.venv\Scripts\python.exe avatar.py --camera
.\.venv\Scripts\python.exe focus_eeg.py live --port COM8 --focus-on 1.5 --focus-off 1.0 --avatar-port 5005
```

Run those commands in separate terminals. The ratio must reach `--focus-on` to enter **focused** and fall to `--focus-off` to leave it; values in between keep the previous state. Both thresholds act on the raw ratio and must satisfy `focus-on > focus-off >= 0`. Close the EEG recorder and OpenBCI GUI first because they cannot share the Cyton COM port. The avatar shows **focused** when the camera is neutral. A camera-detected smile, frown, or sleepy eyes takes priority. A manually chosen avatar mood pauses automatic control; right-click **Resume automatic moods** to resume it. The focus monitor sends only state, quality, and ratio metadata through local UDP, never raw EEG samples.

Personal calibration remains available as an optional alternative. It maps separate rest and focused-task recordings to a 0–100 proxy and requires at least five clean four-second windows in each. To use it, record about one minute resting quietly with eyes open and one minute doing a concentration task such as sustained reading or mental arithmetic. Keep headset placement the same, sit still, and relax your jaw in both sessions:

```powershell
.\.venv\Scripts\python.exe eeg_cyton.py record --port COM8 --out recordings\rest.csv --seconds 60
.\.venv\Scripts\python.exe eeg_cyton.py record --port COM8 --out recordings\focus.csv --seconds 60
.\.venv\Scripts\python.exe focus_eeg.py calibrate --rest recordings\rest.csv --focus recordings\focus.csv --out recordings\focus-calibration.json
```

Calibration fails with an explanation if the signal is too weak or the sessions do not separate. To inspect a saved focus recording:

```powershell
.\.venv\Scripts\python.exe focus_eeg.py replay recordings\focus.csv --calibration recordings\focus-calibration.json --speed 10
```

For calibrated live feedback, start the avatar in one terminal and the focus monitor in another:

```powershell
.\.venv\Scripts\python.exe avatar.py --camera
.\.venv\Scripts\python.exe focus_eeg.py live --port COM8 --calibration recordings\focus-calibration.json --avatar-port 5005
```

The optional calibrated score requires clean EEG windows; the manual threshold mode still reports and classifies `LOW AMP` windows so you can experiment while seeing the warning.

If both channels show `LOW AMP` while all four electrodes are on the skin, first check that Fp1/Fp2 reach the bottom channel 1/2 inputs and that the reference and bias ear clips reach the bottom SRB2 and BIAS pins. Confirm contact and try a few deliberate blinks while watching for clear Fp1/Fp2 changes. The [OpenBCI headband guide](https://docs.openbci.com/AddOns/Headwear/HeadBand/) shows this wiring, and the [OpenBCI GUI guide](https://docs.openbci.com/Software/OpenBCISoftware/GUIWidgets/) shows frontal blink responses. If the stream still looks almost flat, compare it in the OpenBCI GUI before interpreting it as EEG.

If live samples arrive in uneven bursts on Windows, OpenBCI documents changing the dongle's FTDI **Latency Timer** from 16 ms to 1 ms in Device Manager. This is a driver setting, separate from Cyton's 250 Hz sample rate. [OpenBCI FTDI guide](https://docs.openbci.com/Troubleshooting/FTDI_Fix_Windows/)

## Muse 2 EEG via the Muse SDK bridge

The existing Muse SDK bridge in `C:\Users\User\Desktop\Jack\Play\ReapHackathon\bci-server` owns the Bluetooth connection. It sends four EEG channels (`TP9, AF7, AF8, TP10`) as OSC packets to `127.0.0.1:7000`. CommonGround receives that stream; it does not connect to Muse through BrainFlow. It calculates focus from **AF7 and AF8**, which are different positions from the Cyton Fp1/Fp2 electrodes. Choose separate thresholds for each headset. [Muse 2 specifications](https://eu.choosemuse.com/pages/muse-s-muse-2-holiday-offers)

In terminal 1, turn on the headband, start the bridge, and wait for `[Status] Connected!`:

```powershell
Set-Location 'C:\Users\User\Desktop\Jack\Play\ReapHackathon\bci-server'
.\scripts\Start-Bridge.ps1
```

In terminal 2, run a short EEG check from CommonGround:

```powershell
Set-Location 'C:\Users\User\Desktop\Jack\Play\CommonGround'
.\.venv\Scripts\python.exe eeg_muse.py probe --seconds 10
```

The probe prints packet counts and each channel's RMS and range. `LOW AMP` and `ARTIFACT` are rough signal checks, not contact measurements. If the bridge stays at `[Scan]`, check that Muse-272A remains on and that no other app is connected to it. If the bridge reports `[Status] Connected!` but the probe receives no packets, ensure another process is not already listening on UDP port 7000.

To save all four channels and inspect the raw engagement ratio:

```powershell
.\.venv\Scripts\python.exe eeg_muse.py record --seconds 30 --out recordings\muse-first.csv
.\.venv\Scripts\python.exe eeg_muse.py replay recordings\muse-first.csv --speed 10
.\.venv\Scripts\python.exe eeg_muse.py focus --seconds 30
```

Once you know your own Muse ratio, run the avatar and focus monitor in separate terminals. Setting thresholds automatically sends focus states to the avatar's default UDP port 5005. These thresholds are examples only:

```powershell
.\.venv\Scripts\python.exe avatar.py --camera
.\.venv\Scripts\python.exe eeg_muse.py focus --focus-on 1.5 --focus-off 1.0
```

Use `--avatar-port` if the avatar uses a different port, or `--no-avatar` to view threshold states without controlling it. The camera's happy, sad, and sleepy states take priority over EEG focus; use the avatar's **Resume automatic moods** menu item after a manual mood selection.

The Muse monitor uses four-second beta/(alpha+theta) windows and updates every two seconds. It displays `LOW AMP` beside a calculated ratio; strong artifacts and invalid windows do not produce a focus state. The CSV saves received EEG values and host arrival times; the bridge does not provide a packet counter, so lost OSC packets cannot always be identified. These timestamps are not precise cross-device synchronization. Muse gain is controlled by the headset and is unrelated to the Cyton ×24 setting.

Only one process can receive the bridge's OSC port 7000. To feed the separate `bci-server` service at the same time as CommonGround, set `$env:BCI_OSC_PORT = '7001'` before starting that service in live mode, and add `--forward-port 7001` to the CommonGround `focus` command. CommonGround will forward both EEG and accelerometer OSC packets unchanged to the service.

## Troubleshooting

- If the camera does not open, close other apps using it and check Windows camera permissions. Try `--camera-index 1` if multiple cameras are attached.
- If the face model or camera packages are missing, the app reports an error and the avatar remains usable manually.
- No camera preview is shown. The camera is only activated when you explicitly select **Start camera** or pass `--camera`.
