# Milestone 2 implementation status

Checkpoint before implementation: ba19dc7. Branch: codex/tribe-streaming.

## Implemented, not yet end-to-end validated
- Isolated Python 3.11 runtime in `.tribe/venv`; BrainFlow runtime unchanged.
- Official source checkout pinned at af58661791a351a448a489042a28f6c37e1c14b7.
- Receiver-side complete 60-second MediaRecorder sessions starting every 30 seconds. Individual timeslice blobs are combined per recorder into a complete file. Safari concurrent-recorder behavior requires device testing.
- Owner-authenticated bounded upload endpoints and one-running/one-pending queue. Replaced pending windows counted explicitly.
- Per-window 32 MiB upload cap, session 512 MiB cumulative cap, 15-minute worker timeout. Media deleted after processing; temporary sessions deleted on Stop, disconnect or service shutdown. Abrupt process termination can leave `.tribe/sessions` files; remove these manually before restarting if needed.
- Real official inference adapter; no mock model output. Original arrays and segment metadata retained while session active. Whole-cortex mean/std are diagnostics, not emotion scores.
- Analysis is blocked by a server-side readiness check until a real inference benchmark succeeds.

## Actual feasibility results
Mac: 24 GiB RAM, CUDA unavailable, MPS available. Official package imports in Python 3.11. System certificate trust enabled with truststore; TLS verification remains enabled.
TRIBE config accessible at revision f894e783020944dcd96e5568550afe2aa9743f9f.
Required meta-llama/Llama-3.2-3B access verified with local credentials at revision 13afe5124825b4f3751f836b40dafda64c1ed062.
Official transcription helper uses CPU + float16 and a separate environment that failed TLS certificate verification. Added a project-local adapter with pinned WhisperX 3.8.6, CPU int8 and truststore 0.10.4; original upstream source remains unchanged. Word timestamp contract tests pass in the isolated TRIBE runtime. A synthetic 30-second video passed audio extraction; full inference is still under test. The 708,856,138-byte TRIBE checkpoint downloaded and loaded successfully on CPU. No prediction produced yet.

## Next required work
1. Model access and checkpoint loading completed. Credentials stay local and `.env` files are excluded from Git.
2. Validate CPU transcription (or explicitly choose a GPU worker), feature extraction, and model checkpoint loading on a test clip. Pin model snapshots for reproducibility.
3. Benchmark duration, memory and output timestamps. Do not mark `.tribe/readiness.json` ready before actual successful inference and media-path verification.
4. Verify 60-second overlapping recordings on the user's Safari/iPhone stream. Test stop/reconnect and malformed uploads.
5. Validate segment timing and overlap behavior before exposing a TRIBE painting layer. No predicted-versus-live EEG comparison is currently made.
6. Implement timestamped rendering and multimodal session/EEG persistence. Not yet implemented.

Do not restart the working phone service solely to try model inference yet. Restart it when ready to inspect the disabled analysis UI. Existing phone video, audio and EEG functionality remains independent.

Tests cover pairing access, bounded pending replacement, stop cleanup and missing-runtime errors. They do not certify real-model inference, CPU compatibility or browser media recording.

## Latest benchmark (11 October 2026)
- Speech preprocessing and video/audio event creation completed on the synthetic 30-second diagnostic. The clip has a tone, not real speech; this does not validate spoken-language features. WhisperX generated an unalignable phrase; no Word events were retained.
- The audio feature model loaded. V-JEPA2 loaded and completed its first CPU encoding step in 80.18 seconds, with 60 steps needed for this clip. The CPU run was stopped rather than spending roughly 80 minutes on video extraction alone (linear estimate, not a completed benchmark).
- Official neuralset device validation rejects MPS. A separate direct V-JEPA2 probe loaded onto MPS but did not complete a step within over 90 seconds and was stopped. No upstream package or device-validation bypass was introduced.
- No final TRIBE predictions have been produced; readiness remains false. Live cadence and timing are not validated. Next decision: a supported GPU worker, or explicitly offline processing. No external media upload or GPU rental has been configured.
- Stop/timeout now target the whole inference process group. Extracted WAV/transcript sidecars are removed after jobs. Model feature caches under `.tribe/cache` are separate from session files and may persist.
- Receiver authorization and readiness-gate tests pass. Transcription timestamp tests pass in the isolated runtime.
