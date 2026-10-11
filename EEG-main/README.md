# You & AI — Signal Room implementation notes

This folder contains the Signal Room EEG visualizer, Bloom browser showcase, opt-in phone capture, and experimental offline TRIBE processing. Media recording is opt-in; no cloud inference is configured. For the makeathon overview and fastest demo, start at the [project README](../README.md).

## Bloom companion preview

The new You & AI / Bubble Kin design is in [design.md](design.md). The main Signal Room now draws Bloom, and `http://127.0.0.1:8765/bloom` shows the full four-state design. For a design-only preview without the EEG dependencies, run this from the CommonGround folder on Windows, then open `http://127.0.0.1:8877/bloom.html`:

```powershell
.\.venv\Scripts\python.exe -m http.server 8877 --directory EEG-main --bind 127.0.0.1
```

Select Happy, Sad, Sleepy, or Focused with the numbered rows or keys 1–4. The eight petals, opaque plum mouth, state-specific motion, keyboard controls, and reduced-motion setting follow the design handoff. These are manual previews and do not claim to infer emotion from the NeuroPawn model. The separate CommonGround `avatar.py` renders Bloom on the Windows desktop and receives camera and Muse focus events.

The NeuroPawn bridge below was built on macOS and currently discovers `/dev/cu.usb*` ports. Its live board connection needs a Windows port-discovery adaptation before using this EEG-main server with a Knight board on Windows. Bloom's design preview itself works without a headset.

## Run

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python server.py
```

Open http://127.0.0.1:8765 and click Connect headset. Close/disconnect the NeuroPawn visualizer first; only one app can own the serial port. Disconnect releases the device. Ctrl+C stops the server and releases BrainFlow.

Channel order: Fp1, Fp2, Fz, Cz, T7, T8, Pz, Oz.
Knight board ID comes from BrainFlow; gain 12, eight enabled channels and RLD, with documented command delays. Initialization takes about 20 seconds. Display uses a continuous 1–40 Hz filter and 50 Hz notch, excludes startup transients, and shows independently scaled waveforms with filtered RMS in microvolts. Amplitude relative to a slowly adapting baseline drives movement; artifacts can drive movement too. This is not thought decoding or a signal-quality certification.

A cycles actions; D executes. These remain manual simulation commands. No Playwright integration yet. Pause freezes Bloom, while EEG monitoring continues. No synthetic fallback on disconnection.

For explicit software-only verification: `.venv/bin/python server.py --port 8766 --synthetic`. The UI labels this SYNTHETIC SDK TEST, never LIVE EEG.

Sources: https://docs.neuropawn.tech/software/brainflow/board-setup/ and https://docs.neuropawn.tech/knight-board/command-set/

## Experimental INTERFACES emotion model

Public EEG no-ICA features and valence/arousal labels are in `data/interfaces/`.
The authors' reference code is in `interfaces-reference/`. Models are trained locally; never replace the joblib files with untrusted downloaded models.

Run `.venv/bin/python train_emotion.py` to reproduce training. We use 645 clips from 43 people (15 per person), subject-major order from the authors' preprocessing code. Standard scaling and RBF SVM hyperparameters are fit inside nested grouped cross-validation: 5 outer folds by subject, 3 inner folds by subject. Final models use all public training rows. No personal EEG is recorded by this demo.

Observed held-out-person balanced accuracy: valence 48.1%, arousal 52.2%; chance baseline 50%. ROC AUC: valence 0.488, arousal 0.458. The initial logistic baseline was 50.0% and 47.0%. Neither tested approach demonstrates reliable generalization to a new person. These are our results, not a replication of the paper's reported evaluation.

Consequently, the live face abstains: **Unsure**. It does not pretend to read your feelings. The inference path is implemented, but both dimensions must pass a modest 55% validation gate, signal checks, feature-domain checks and model score checks before showing an estimate. Passing those gates would still not validate it on NeuroPawn or on you. Personal labelled calibration and independent session validation are the next step.

Feature extraction uses an independent raw 56-second buffer, upsampling 125 → 250 Hz to match the reference Welch grid, 50-Hz notch, common-average reference, order-2 band filters (3–7, 8–13, 14–29, 30–47 Hz), and natural log of peak Welch PSD (`nperseg=256`, `noverlap=128`), channel-major ordering. Upsampling adds no information. Hardware/acquisition-notch differences remain. This path is separate from the 1–40 Hz visualization filter. Precomputed public features limit our ability to verify or rerun the authors' original preprocessing.

Expressions: calm (high valence/low arousal), excited (high/high), subdued (low/low), tense (low/high). These are artistic mappings, not clinical or literal emotion labels. The manual expression preview is explicitly labelled and does not use EEG. “Return to EEG” exits preview.

Restart the server after code/model changes, refresh the page, connect the headset and allow 56 seconds for a full window. Poor signals return Unsure immediately. Tests: `.venv/bin/python -m unittest -v`.

Dataset: https://github.com/IoBT-VISTEC/EEG-Emotion-Recognition-INTERFACES-datasets
Citation: P. Lakhan et al., “Consumer Grade Brain Sensing for Emotion Recognition,” IEEE Sensors Journal 19(21), 9896–9907 (2019). DOI: 10.1109/JSEN.2019.2928781.

## Signal-quality diagnosis

The Headset signal check table reports raw range, samples within 1% of the gain-12 ADC limit, 49–51 Hz power as a fraction of 1–60 Hz power, and packet-counter discontinuities. These are engineering checks, not electrode impedance measurements. The scale and rail calculation are specific to the Knight gain-12 parser. Keep gain at 12 unless the acquisition and scaling implementation are changed together.

For dominant 50-Hz noise: test the laptop on battery without powered docks/monitors, connect the headset directly, secure the COMM/RLD reference, verify common-reference switches, and improve scalp contact. Clipped input cannot be repaired by stronger filtering. Stop streaming before moving cables or electrodes. Change one factor at a time. Source: https://docs.neuropawn.tech/troubleshooting/#strong-50-or-60-hz-interference


## Testing on another laptop

The repository excludes virtual environments, recordings, downloaded models, local certificates,
and credentials. Transfer a test clip separately if needed. The current Mac's running inference
is independent of this commit; committing does not stop it.

For phone setup follow [IPHONE_SETUP.md](IPHONE_SETUP.md), using the **new laptop's LAN IP**.
Create certificates on that laptop and trust its CA on the phone. Existing pairing links and
certificates are machine-specific. Do not copy private keys or `.env` files into Git.
The receiver includes **Record 15-second clip**, which saves audio/video locally; it does not
record synchronized EEG. Refresh the receiver and reconnect the phone after installing changes.

### Offline TRIBE environment

The commands below use macOS/Linux shell paths and require Git and `uv` on PATH.
Keep TRIBE separate from the app environment. Python 3.11 was used for TRIBE;
`requirements-tribe.lock` is the tested Mac environment snapshot, not a universal GPU lockfile.

```sh
uv venv --python 3.11 .tribe/venv
git clone https://github.com/facebookresearch/tribev2.git .tribe/source
git -C .tribe/source checkout af58661791a351a448a489042a28f6c37e1c14b7
uv pip install --python .tribe/venv/bin/python -r requirements-tribe.lock
uv pip install --python .tribe/venv/bin/python --no-deps -e .tribe/source
.tribe/venv/bin/hf auth login
```

Your Hugging Face account must have access to `meta-llama/Llama-3.2-3B` and
`facebook/tribev2`. Authenticate on the new machine; never commit an access token.
Model downloads require internet and substantial disk space. Inference uses local media.
The CPU transcription adapter invokes an isolated, pinned WhisperX environment via `uv`.
It uses system certificate trust and the bundled FFmpeg binary.

Place your clip at `recordings/test/clip.mp4`, then run:

```sh
.tribe/venv/bin/python -u tribe_worker.py recordings/test/clip.mp4 recordings/test/prediction.json > recordings/test/worker.log 2>&1
```

In another terminal:

```sh
tail -f recordings/test/worker.log
```

Successful completion writes `prediction.json` and `prediction.npz`. Until then, logs alone
are not a successful prediction. `timing_verified` remains false pending validation.
Official chunking preserves a 15-second clip; this has been checked with actual short media.
TRIBE predicts population-level fMRI responses to media, not the wearer's measured EEG or emotion.

CPU is the current test path. `--device cuda` is exposed but has not been validated in this
project; a GPU machine needs compatible NVIDIA drivers/PyTorch and transcription dependencies.
Apple MPS is rejected by upstream feature configuration. Do not bypass the live readiness gate:
no complete end-to-end prediction has yet been validated. See [MILESTONE_2.md](MILESTONE_2.md).

Tests:

```sh
.venv/bin/python -m unittest discover -p 'test_*.py'
.tribe/venv/bin/python -m unittest test_tribe_transcription
```

The transcription tests require the isolated TRIBE environment and skip in the EEG environment.
The upstream TRIBE license is CC BY-NC 4.0; review its terms before reuse.


## Share a 15-second EEG + audio/video session

Start both servers, connect the real headset in Signal Room, and wait for live EEG.
Pair the iPhone with the separate Mac Safari receiver. Under **15-second EEG + audio/video
session**, click **Record 15-second session** and keep both browsers visible. Recording
stops automatically; wait for saving, then use **Download EEG + audio/video ZIP**.

The package is also saved at `recordings/capture-<id>/session.zip`. Send that ZIP and
this code repository to your collaborator separately. `recordings/` remains Git-ignored.
It contains `clip.mp4` (or WebM), `eeg.npz`, `manifest.json`, and `README.txt`.
Read NPZ with `numpy.load(path, allow_pickle=False)`: `raw_uv` has shape 8 × samples;
`brainflow_timestamp_unix`, `packet_counter`, and `host_received_unix` describe each sample.
The manifest records channel order, sample rate, gain, packet discontinuities and the
browser/server capture timing. EEG is unfiltered microvolts and may contain artifacts.
Check sample counts and discontinuities before analysis.

EEG capture starts before MediaRecorder and is bounded to 20 seconds, allowing pre/post-roll
around the 15-second media clip. WebRTC delay and browser/server clock differences remain:
this is approximate alignment, not hardware synchronization. A zero-sample capture is
explicitly flagged. Cancel may leave an EEG-only folder for diagnosis; it is not a complete
multimodal package. Captures are not automatically deleted. Nothing is sent to your friend
automatically, and no model runs during capture.

The friend can pass the media file to `tribe_worker.py` using the offline instructions above.
EEG is supplied separately for analysis; TRIBE does not accept it as input.
