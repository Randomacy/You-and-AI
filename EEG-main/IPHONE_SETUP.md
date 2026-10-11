# iPhone live camera and audio

The EEG server remains localhost-only. A separate HTTPS service relays WebRTC signalling on your Wi-Fi. Live media travels directly between browsers. Explicit session recording uploads the received clip to this Mac and packages it with raw EEG; no external relay is used. Same Wi-Fi with client isolation disabled is required.

## One-time trust setup
1. Get the Mac Wi-Fi IPv4 address from System Settings → Wi-Fi → Details → TCP/IP.
2. In the EEG folder run `.venv/bin/python setup_phone_tls.py --host YOUR_MAC_IP`.
3. Open `.phone/ca.cer` in Keychain Access on the Mac, add it to your login keychain, and explicitly trust this local CA for SSL. Do not share either private-key file.
4. AirDrop **only `.phone/ca.cer`** to the iPhone. Install the downloaded profile in Settings → General → VPN & Device Management. Then enable its trust in Settings → General → About → Certificate Trust Settings. Compare the certificate name/fingerprint with the generator output.
5. Remove this CA trust from both devices when you no longer need the project. The server certificate expires in 90 days; if the Mac address changes, regenerate the server certificate for that address before use (the setup script refuses to overwrite an existing CA).

## Run
Keep the normal `.venv/bin/python server.py` running. Restart it after this feature update.
In a second terminal run `.venv/bin/python phone_server.py --host YOUR_MAC_IP`.
Allow incoming network connections for Python if macOS asks. Only the phone service binds the Wi-Fi address.
Refresh Signal Room, click Pair iPhone, then Create pairing QR. Scan with the iPhone camera, open Safari, and tap Start streaming. Permit camera and microphone. Keep the phone unlocked with Safari foregrounded.
On the Mac, click Enable audio meter. Playback is muted by default to prevent feedback. Press Play if autoplay is blocked. The separate receiver link can be opened in Safari if the embedded browser has media restrictions.

Pair links expire after five minutes and are single-use. Stop/Unpair ends capture; create a fresh QR for reconnection or camera switching. Reopening the receiver while its prior tab is still connected requires closing the old receiver first.

## Limits
Opt-in 15-second audio/video + EEG session recording is available; see README.md. TRIBE processing remains experimental and precise EEG/media alignment is not available. The preview and EEG run concurrently; WebRTC introduces variable delay. Guest Wi-Fi isolation or VPNs can prevent direct WebRTC connections. No cloud relay fallback is configured. Pairing is in-memory and invalidates on server restart. Never expose the receiver link, which carries the controller credential, to other people.
