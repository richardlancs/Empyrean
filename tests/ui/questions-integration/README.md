# Questions feature tests

Tests for `dashboard/static/features/questions/` (the "Ask a question" panel).

## Unit tests (no browser, no dependencies)

```sh
node --test tests/ui/questions-integration/
```

- `model.test.mjs`: selectors and record descriptions (correlation rule,
  availability, reconnecting note, unavailable is not "not found", speech wording).
- `controller.test.mjs`: POST/poll/push flow with a manual clock (older answers
  never replace newer ones, looking_up to answered by poll and by push, 15 s
  "still waiting", 503/network/404 errors, dispose).
- `voice.test.mjs`: microphone lifecycle with a fake SpeechRecognition (one
  start per click, no overlap, no restart, transcript not submitted, every error
  code, abort on cancel and on unmount, unsupported browser).

`helpers.mjs` holds the shared fakes; it is not a test file.

## Browser harness (artificial data)

The dashboard server only serves `/static` from `dashboard/static`, so the
harness is served from the repository root with any static server:

```sh
python3 -m http.server 8794 --bind 127.0.0.1    # from the repo root
open http://127.0.0.1:8794/tests/ui/questions-integration/harness.html
```

It mounts the real `dashboard/static/features/questions/index.js` with a fake
context: the real core store (driven by the "Fixture controls"), a fake
`request()` for `POST /api/question` and `GET /api/question/{id}` (latency and
reply are configurable: immediate answer, 202 then poll, 202 then socket push,
unavailable history, stuck lookup, 503, 422, network error) and a scripted fake
SpeechRecognition (or "unsupported", or the real browser API).

URL parameters preset the controls, e.g.
`harness.html?reply=history-poll&latency=300&voice=fake&mic=ok&cap=true&connection=reconnecting&contrast=1`.

## Scripted browser checks

`e2e.mjs` drives the harness with Playwright (not a project dependency; it
loads a local or global install) and writes screenshots to `screenshots/`:

```sh
python3 -m http.server 8794 --bind 127.0.0.1 &   # from the repo root
node tests/ui/questions-integration/e2e.mjs      # HARNESS_URL=..., SHOTS=dir (or SHOTS= to skip)
```
