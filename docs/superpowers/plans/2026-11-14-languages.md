# Five Languages Implementation Plan

> **For agentic workers:** each stream below is one subagent. Use TDD (failing test, run, implement, run). Do not commit; the lead commits. Steps use checkbox (`- [ ]`) syntax.

**Goal:** The glasses speak English, Mandarin, Spanish, French or Hindi. The demo operator picks the language on the dashboard. Every spoken phrase follows the chosen language and stays offline.

**Architecture:** Each Piper voice preset belongs to one language. The active language is the language of audio's *confirmed* voice, `VoiceStatus.language`. Picking a language on the dashboard sends the existing `VoiceChange` for that language's voice. Namer, storage and the dashboard subscribe to `VoiceStatus` and word their spoken text in that language.

- **Names:** Grok returns each name in English (`NameResult.name`, unchanged for storage, search and the dashboard) and in the active language (`NameResult.spoken_name`, spoken by audio).
- **Fixed phrases:** hazard phrases, the sample line, class labels and template answers come from fixed offline tables.

**Builds on:** `docs/superpowers/plans/2026-11-14-calmer-voices.md`, PR #34 and branch `p4-calmer-voices`.

**Shared contract (committed, read-only for streams):**
- `contracts/languages.py`: `LANGUAGES` (code → native name, menu order `en zh es fr hi`), `DEFAULT_LANGUAGE = "en"`, `LANGUAGE_NAMES_EN` (for Grok prompts), `CLASS_LABELS`, `known_language(code)` and `translate_label(label, language)`.
- `NameResult` gains `spoken_name: str = ""` and `language: str = ""`.
- `VoiceStatus` gains `language: str = "en"` and `voice_languages: dict[str, str]`.
- The rules are in SPEC §4.8 ("Languages").

## Global Constraints

- No new package. No network call on any speech path; translations are fixed tables. Only namer's existing Grok calls produce translated names and answers.
- The hazard path is unchanged: hazard phrases are pre-rendered per voice as today. Nothing may delay them.
- **Fallback rule:** if the chosen preset is not installed, pyttsx3's English voice speaks. `VoiceStatus.language` is then `"en"`, so every module stays in English. It never sends Hindi text to an English voice.
- A `spoken_name` whose `language` differs from the active language is never spoken.
- Language codes come only from `contracts/languages.py`. Never import across module folders.
- Type hints, one-line docstrings, the module-folder logger, and no bare `print` outside `fakes/` and tests.
- Python: `/Users/richardlan/Empyrean/.venv/bin/python`. Ruff: `/Users/richardlan/Empyrean/.venv/bin/ruff`. Worktree: `/Users/richardlan/Empyrean/.claude/worktrees/p4-calmer-voices`.

## Review Focus

1. **Switching language while an object is pointed at.** Its old-language `spoken_name` is not spoken. The translated class label is spoken instead.
2. **Hindi model missing.** The fallback is English and everything stays English, with no Devanagari sent to Samantha.
3. **A hazard during a language switch.** The beeps and the hazard phrase come first, in the voice already loaded.
4. **Grok answers with only one line in naming.** `spoken_name` is empty, and audio speaks the translated class label.
5. **Namer or storage starts before audio's first `VoiceStatus`.** They default to English until the first status arrives.

---

### Stream A (audio): presets, phrases, spoken names

**Owns:** `audio/`, `fakes/audio/`, `tests/test_audio*.py`, `tests/test_speak_test.py`.

- `VoicePreset` gains `language: str` (the English presets use `"en"`). Add these four presets after the English ones:

| key | label | voice_name | locale | model | language |
|---|---|---|---|---|---|
| `huayan` | Huayan | Huayan | zh-CN | zh_CN-huayan-medium | zh |
| `claude` | Claude | Claude | es-MX | es_MX-claude-high | es |
| `siwis` | Siwis | Siwis | fr-FR | fr_FR-siwis-medium | fr |
| `priyamvada` | Priyamvada | Priyamvada | hi-IN | hi_IN-priyamvada-medium | hi |

  All four models are already downloaded in `audio/voice_models/`. `fetch_voices` must fetch them too, and its URL builder already handles their folders.
- Add `language_of(key) -> str` and `default_voice_for(language) -> str`, which returns the first preset of that language in menu order.
- `HAZARD_PHRASES` becomes `dict[language, dict[type, str]]`, and the fallback phrase becomes a dict per language:

| type | en | zh | es | fr | hi |
|---|---|---|---|---|---|
| stairs_down | Stop. Stairs. | 停。楼梯。 | Alto. Escaleras. | Stop. Escalier. | रुकिए। सीढ़ियाँ। |
| drop_off | Stop. Drop ahead. | 停。前方有落差。 | Alto. Desnivel adelante. | Stop. Dénivelé devant. | रुकिए। आगे गड्ढा। |
| vehicle | Stop. Vehicle. | 停。车辆。 | Alto. Vehículo. | Stop. Véhicule. | रुकिए। वाहन। |
| obstacle | Stop. Obstacle. | 停。障碍物。 | Alto. Obstáculo. | Stop. Obstacle. | रुकिए। रुकावट। |
| (fallback) | Stop. | 停。 | Alto. | Stop. | रुकिए। |

- **Sample line:** en `This is {label}.`, zh `我是{label}。`, es `Soy {label}.`, fr `Je suis {label}.`, hi `मैं {label} हूँ।`
- **Active language:** the preset's language when quality is not `fallback`, otherwise `"en"`. Publish it in `VoiceStatus.language`, and send `voice_languages` for every preset.
- **Pre-rendering:** `prepare()` gets the active language's hazard phrases and fallback phrase.
- **Touch speech:** keep `spoken_names[object_id] = (spoken_name, language)` from `NameResult`. What to speak:
  - In English: `name`, then the class label, exactly as today.
  - In another language: the `spoken_name` when its language matches. Otherwise `translate_label(class_label, language)`.
  - The late-name rule (speak once if it arrives within the window after a label) also applies to a matching `spoken_name`.
- **Fakes:** `PrintSpeaker` lists all nine presets. The `speak_test --all` sample uses each preset's own-language sample line plus that language's stairs phrase.
- **Tests:**
  - presets and `default_voice_for`;
  - the hazard phrase in each language after a switch;
  - the fallback preset reports `language == "en"` and speaks English;
  - a spoken name in the wrong language is not spoken;
  - a translated label is used when no `spoken_name` exists;
  - `prepare()` receives the target language's phrases.

### Stream B (namer): bilingual names and answers

**Owns:** `namer/`, `fakes/namer/`, `tests/test_namer*.py`, `tests/test_naming.py`.

- `register()` also subscribes `VoiceStatus`. Track `language = known_language(msg.language)`. Start with `"en"`. The handler only sets a field under a lock.
- **Naming, when the language is not `en`:** append to the existing prompt: `f"Then, on a second line, write the same name in {LANGUAGE_NAMES_EN[lang]}."`
  - The first line goes through today's cleaning into `name`.
  - The second line is trimmed, cut to `NAME_MAX_CHARS` and goes into `spoken_name`. `language` is the language captured *when the request started*.
  - A missing second line means `spoken_name=""`.
  - In English the prompt and result are unchanged, with `spoken_name=""` and `language=""`.
- **Scene questions:** when the language is not `en`, add `f"Answer in {LANGUAGE_NAMES_EN[lang]}."` to the instructions.
- **Fixed answers:** namer's own spoken answers (busy, no or stale frame, unavailable, error) use a fixed table for all five languages. Keep the English wording exactly.
- **Fake namer:** its `NameResult`s carry `spoken_name = translate_label(<its scripted label>, lang)` when the language is not English, so the fake demo speaks the language.
- **Tests:**
  - the prompt includes the second-line request only for non-English;
  - two-line parsing, one-line parsing, and capture of the request-time language;
  - the scene-question instruction;
  - the fixed answers in Hindi and English;
  - the `VoiceStatus` handler does not block.

### Stream C (storage): translated history answers

**Owns:** `storage/`, `fakes/storage/`, `tests/test_storage.py`, `tests/test_p3_shared_classes.py` (only if needed).

- `register()` also subscribes `VoiceStatus` and tracks the language the same way as Stream B.
- `format_answer`, `NOT_SEEN` and `UNAVAILABLE` get templates for all five languages. Keep the English output byte-identical. Word the object as `translate_label(label, lang)` when it is a known class label, else as stored.
- `LastSeenResult.answer` stays "exactly what was spoken", now translated.
- Do not change the SQL or the stored values.
- **Tests:**
  - every template in every language;
  - English unchanged;
  - the language is captured when the query is received, not when it is answered.

### Stream D1 (dashboard server): language view and spoken messages

**Owns:** `dashboard/services/`, `dashboard/api/`, `dashboard/state.py`, `dashboard/server.py`, `dashboard/bus_adapter.py`, `dashboard/questions.py`, `tests/test_voice_dashboard.py`, `tests/test_dashboard_questions.py`, `tests/test_dashboard*.py`.

- `VoiceService.view()` keeps every key and adds:
  - `language`: the active code from the last `VoiceStatus`, or `"en"`;
  - `languages`: `[{"code", "label"}]` in `LANGUAGES` order, only languages with at least one option;
  - `"language"` on each option.
- `POST /api/voice` is unchanged. The page picks a language by requesting that language's first voice.
- **Spoken messages:** every `SpeakRequest` the dashboard itself publishes (for example "Touch history is unavailable right now." and "Please wait for the current question to finish.") comes from a five-language table keyed by `voice.view()["language"]`. English stays byte-identical.
- Question routing stays as it is (English wording); note it in the report.
- **Tests:**
  - the view fields;
  - an unknown language code shows as `"en"`;
  - each spoken message in French and English.

### Stream D2 (dashboard page): Language picker

**Owns:** `dashboard/static/`, `tests/ui/`.

- **Pinned server view additions:** `state.voice.language`, `state.voice.languages: [{code, label}]`, and `options[i].language`. `core/normalize.js` already passes `voice` through.
- Add a labelled native `<select>` "Language" directly above the Voice select.
  - The Voice select lists only the options whose `language` equals the confirmed `language`.
  - Choosing a language POSTs `/api/voice` with the first option of that language, through the same request flow, lock and handoff as the Voice select. Choosing the current language sends nothing.
  - Both selects lock while a switch is pending.
  - Status text, for example "Voice: Siwis (Français)", stays an English UI string. The page chrome is not translated.
- Add `selectLanguage(snapshot, local)` in `features/experience/selectors.js`, returning `{options:[{code,label}], value, locked, statusText}`.
- `selectVoice` gains filtering by the confirmed language.
- Fits at 320 px.
- **Tests:** `node --test` for:
  - the language options;
  - the voice filtering;
  - the locked states;
  - a request for a new language using that language's first voice;
  - the current language sending nothing.

### Integration (lead)

- Full `pytest`, `node --test` over `tests/ui`, `ruff check .`
- `python -m app --fake vision audio namer storage`: switch to Español in the browser and confirm `VoiceChange claude`, "Soy Claude.", the pointed bottle spoken as "botella", and a hazard phrase in Spanish via the hazard fake.
- One real by-ear phrase per language through `speak_test`.
- DEVLOG, then push to PR #34.
