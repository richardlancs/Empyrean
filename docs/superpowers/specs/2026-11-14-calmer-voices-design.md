# Calmer voices: design

Date: 2026-11-14. Status: approved by the user in chat. Plan: `docs/superpowers/plans/2026-11-14-calmer-voices.md`.

## Intent

The spoken voice in `audio/` sounds a little unsettling. The user named three things: it is robotic or synthetic, too fast or rushed, and flat or cold. Today `Pyttsx3Speaker` never picks a voice or a rate. On the macOS demo laptop that means Apple's compact Samantha at pyttsx3's default 200 words per minute. Better voices are already on the machine's operating system, but they are not installed or not chosen.

The goal is five selectable, natural-sounding English voices at a calmer pace. The demo operator or wearer can switch between them live from the dashboard. Languages come later.

## Goals

- Five English voice presets backed by Apple's Premium or Enhanced voices, all offline once downloaded.
- A calmer speaking rate for every voice, read from `config/`.
- The default voice is chosen in `.env` (`AUDIO_VOICE`). A dashboard picker switches it live, and the new voice confirms itself with a short sample line.
- If a preset's voice is not installed, audio still speaks with the best voice it can find and says so on the dashboard.

## Non-goals

- Translation or any non-English speech. Presets carry a locale so a later language plan can filter on it.
- Windows or Linux voice quality. The demo laptop is macOS. Other platforms keep working with their system default voice.
- Pitch or emotion control. pyttsx3's macOS driver does not expose pitch.

## Anti-goals

- A voice switch that delays, cuts off, or queues ahead of a hazard alarm or phrase.
- Any network call on the speech path.
- The dashboard showing a voice as active before audio has confirmed it.

## Constraints

- Approved stack: `pyttsx3` 2.99 offline, `pygame` mixer for the alarm. No new package.
- Shared files (`contracts/`, `config/`, `SPEC.md`) need all four teammates to agree. Record that in `DEVLOG.md`.
- pyttsx3 needs a fresh engine per phrase (see `audio/backends.py`), so the voice and rate are set on every new engine.

## Approaches considered

| Approach | Trade-off | Decision |
|---|---|---|
| 1. pyttsx3 plus Apple Premium/Enhanced voices | No new package; clear quality jump; macOS-only quality; voices are a one-time manual download; pyttsx3 might not see Premium voices | **Chosen** |
| 2. Piper (`piper-tts`, ONNX voices about 60 MB each) | Natural voices on every OS; new dependency needs team agreement; alarm cut-off must be redone, because Piper renders audio files instead of speaking word by word | Fallback only if Task 1's check fails |
| 3. Kokoro-82M | Most natural; heavy runtime (torch or onnxruntime) | Rejected: too much new stack for a hackathon |

## Decided

- **Voices:** `ava` Ava (Premium, en-US, female, default), `zoe` Zoe (Premium, en-US, female), `evan` Evan (Enhanced, en-US, male), `jamie` Jamie (Premium, en-GB, male), `matilda` Matilda (Premium, en-AU, female).
- **Matching:** for each preset, pick the installed voice with that name and locale, preferring premium over enhanced over compact by voice id. If none is found, use compact Samantha (en-US) and report `fallback`. If Samantha is missing too, use the system default voice, also reported as `fallback`.
- **Rate:** `SPEECH_RATE_WPM = 165` in `config/` for every voice, hazard phrases included.
- **Switching:** works like the Regular/Demo detector switch. The dashboard publishes `VoiceChange`. Audio applies it between phrases and answers with `VoiceStatus`. Only `VoiceStatus` changes what the page calls active. A request that is not answered within `VOICE_SWITCH_TIMEOUT_SECONDS = 10` fails on the page.
- **Sample line:** after a switch, audio says "This is Ava." at answer priority (3), so it never displaces a touch or a hazard.
- **Startup:** `AUDIO_VOICE` in `.env` names the preset key. An unknown key logs a warning once and uses `ava`.

## Languages later (recorded, not built)

Grok returns names in English. When languages come, the namer prompt asks Grok to reply in the chosen language (`namer/`, Person 3), because audio must never call the network. Hazard phrases get a per-locale table in `audio/`. Fixed dashboard answers (for example "Touch history is unavailable right now.") need their own table in `dashboard/`.

## Calls made by Claude (user may override)

- The five voice picks and the default.
- The rate of 165 words per minute, and using one rate for every voice.
- The 10-second switch timeout. It is longer than the detector's because a long spoken answer can delay the switch until it ends.
- The sample-line wording.
- A native `<select>` for the picker instead of a five-button segmented control, so it fits at 320 px.
