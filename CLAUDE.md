# CLAUDE.md

Instructions for Claude Code in this repository.

@AGENTS.md

## Start of every session

1. `AGENTS.md` above is the contract. It applies to you in full.
2. Read `SPEC.md` for what the system does. Read the sections for the module you are about to touch before writing anything.
3. Read the last few entries of `DEVLOG.md` to see what changed since you were last here.
4. If you do not know which person (1 to 4) you are working for, ask before doing anything else. You may only edit that person's folders.

## Stack

Python 3.11. OpenCV for capture and drawing. Ultralytics YOLO small (`yolo11s.pt`) with ByteTrack for objects. MediaPipe Hands for fingertips. Grok vision over the Grok API with `httpx` for naming and hazard checks. Tiger Data with `psycopg` 3 for history. `pyttsx3` for speech and `pygame` mixer for the alarm. FastAPI on Uvicorn serving one plain HTML page with MJPEG video and a WebSocket. `python-dotenv`, `pytest`, `ruff`. Git and GitHub.

The full table is in `AGENTS.md` and `SPEC.md` section 2.1. Do not introduce anything outside it.

## Commands

| Command | Use |
|---|---|
| `python -m app` | Run everything on the real camera |
| `python -m app --fake vision` | Run with recorded input, no camera needed |
| `python -m app --only <module> --fake <modules>` | Run one module against fakes |
| `pytest` | Run all smoke tests |

These are defined in `SPEC.md` section 6. If one does not work yet, say so. Do not invent a different command.

## How to work here

- Check the spec before you design. Most behaviour, every message, and every threshold is already decided.
- Keep changes small and inside one module. Four people are committing to this repository at the same time.
- Thresholds come from `config/`. Message shapes come from `contracts/`. Do not redefine either locally.
- Run `pytest` and the relevant `--fake` command before reporting a task as done, and report what you ran.
- If a test fails or you could not verify something, say that plainly.
- End each session by adding a `DEVLOG.md` entry.

## Do not

- Edit `contracts/`, `config/`, `SPEC.md`, `AGENTS.md` or this file without your human confirming all four teammates agreed.
- Edit another person's folder.
- Put network or database calls on the frame path.
- Commit `.env`, keys, model weights, or large video files.
- Describe the hazard feature as a safety device anywhere.
