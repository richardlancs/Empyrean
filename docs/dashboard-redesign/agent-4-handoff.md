# Agent 4 handoff: runtime data, API, integration

**Status: IN_PROGRESS**

| | |
|---|---|
| Base commit | `a5ea3afb5871ea636829e34b4a9b45e6f735a26a` (verified against `origin`, `richardlancs/Empyrean`) |
| Branch | `design/light-dashboard-integration` |
| Worktree | `../empyrean-design-4` |
| Agent | Claude Code (Claude Opus 5.5) |

The implemented API is in [api.md](api.md). Read it instead of the brief where they differ.

## Answers to integration requests so far

- **Agent 2**: every field and endpoint you listed is implemented. Differences:
  `current_touch` is `null` once nothing is in a hand (state is only `touching`
  or `held`); the released object is in the additive `last_touch`.
  `request_id` is a 32-char hex string. `/video` ignores unknown params such as
  `r=`. `thumbnail_url` changes at most every 5 s. Server-side search timeout is
  8 s (shorter than your 10 s), so the page normally sees `unavailable` first.
- **Agent 1**: the server mounts `dashboard/static/` at `/static` with
  `text/javascript` for `.js`; `/` serves `dashboard/index.html`. Error bodies are
  `{"detail": "..."}`; please give `ctx.request` errors a numeric `.status` and
  the `detail` as the message.
- **Agent 3**: requests 1–5 are done: `latest_real_warning` and
  `latest_simulated_warning` (each with `active`), `source` and `confidence` as
  fields on every hazard entry, `event_log_size`, `diagnostics` with
  `camera.stale_after_seconds`, and simulate still returns the full snapshot and
  publishes nothing. One difference: idle naming is `starting` for the first
  10 s and then `unknown` ("Idle: no naming requests yet"), not `active`, because
  the namer reports no health of its own; it is never `failed` while idle.
  Request 5 for Agent 1 (static "Simulate alert" text): I will update
  `tests/test_dashboard.py` to check the served page plus its modules instead.
