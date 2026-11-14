"""One Grok vision call that names one object crop (SPEC.md section 4.5)."""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

import httpx
from dotenv import load_dotenv

from namer import _pending as c

log = logging.getLogger("namer")

# xAI Responses API, image input as a base64 data URL in an "input_image" part.
# Shape checked against docs.x.ai/docs/guides/image-understanding on 2026-11-13.
GROK_RESPONSES_URL = "https://api.x.ai/v1/responses"

INSTRUCTION = (
    "Identify the product in this image. Reply with the brand and product type in at most "
    "5 words. If no brand is readable, reply with the plain object name. No sentences."
)

_env_loaded = False


def _load_env_once() -> None:
    """Load .env into the process environment the first time a call is made."""
    global _env_loaded
    if not _env_loaded:
        load_dotenv()
        _env_loaded = True


def _require_env(name: str) -> str:
    """Return a non-empty environment variable or raise a clear error naming it."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set; add it to .env")
    return value


def build_payload(model: str, jpeg: bytes, class_label: str) -> dict[str, Any]:
    """Build the Responses API request body for one crop."""
    data_url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
    hint = f"Hint: an object detector labelled this as '{class_label}'."
    return {
        "model": model,
        "store": False,
        # No "reasoning" field: set GROK_MODEL to a non-reasoning model, which rejects it.
        # Measured 2026-11-13 on a 320 px crop: grok-4.20-0309-non-reasoning ~0.6 s;
        # grok-4.7 and other reasoning models 3-12 s, often past NAME_TIMEOUT_SECONDS.
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_image", "image_url": data_url, "detail": "high"},
                    {"type": "input_text", "text": f"{INSTRUCTION} {hint}"},
                ],
            }
        ],
    }


def parse_reply(data: Any) -> str:
    """Extract the reply text from a Responses API JSON body, or raise ValueError or TypeError."""
    if not isinstance(data, dict):
        raise TypeError("Grok reply is not a JSON object")
    parts: list[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") == "output_text":
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
    if not parts and isinstance(data.get("output_text"), str):
        parts.append(data["output_text"])
    if not parts:
        raise ValueError("Grok reply has no output text")
    return "".join(parts)


async def name_crop(client: httpx.AsyncClient, jpeg: bytes, class_label: str) -> str:
    """Ask Grok to name the product in one JPEG crop and return its raw reply text."""
    _load_env_once()
    api_key = _require_env("GROK_API_KEY")
    model = _require_env("GROK_MODEL")
    response = await client.post(
        GROK_RESPONSES_URL,
        json=build_payload(model, jpeg, class_label),
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=c.NAME_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return parse_reply(response.json())
