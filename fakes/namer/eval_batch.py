"""Batch naming eval: every image in scratch/eval/manifest.csv through the real Grok call.

Run from the repo root:
    .venv/bin/python -m fakes.namer.eval_batch              # call Grok, write results.csv
    .venv/bin/python -m fakes.namer.eval_batch --summarize  # re-print summary from results.csv

Uses namer.grok_client.name_crop, the exact request the namer sends, and
namer.namer.clean_name, so the scored name is what the app would speak.
Calls respect NAME_MAX_IN_FLIGHT and NAME_MIN_INTERVAL_SECONDS. Each call is
allowed up to SAFETY_CAP_SECONDS so the real latency tail is visible;
"timeout" is yes when a call took longer than NAME_TIMEOUT_SECONDS (the
namer itself would have given up) or the HTTP client timed out.
Needs GROK_API_KEY and GROK_MODEL in .env. Publishes nothing.
"""

from __future__ import annotations

import asyncio
import csv
import os
import re
import statistics
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

from config import NAME_MAX_IN_FLIGHT, NAME_MIN_INTERVAL_SECONDS, NAME_TIMEOUT_SECONDS

EVAL_DIR = Path("scratch/eval")
MANIFEST = EVAL_DIR / "manifest.csv"
RESULTS = EVAL_DIR / "results.csv"
SAFETY_CAP_SECONDS = 15.0

# COCO label the detector would plausibly give, sent as the namer's hint.
# "unknown" marks things COCO has no class for (YOLO would likely not detect them at all).
CATEGORY_HINT = {
    "condiments": "bottle",
    "cereal": "book",
    "snacks": "unknown",
    "drinks": "bottle",
    "candy": "unknown",
    "canned": "cup",
    "toiletries": "bottle",
}
OBJECT_HINT = {
    "mug": "cup",
    "iphone": "cell phone",
    "macbook": "laptop",
    "book": "book",
    "bottle": "bottle",
    "keyboard": "keyboard",
    "mouse": "mouse",
    "controller": "remote",
}

FIELDS = [
    "file", "category", "variant", "class_hint", "expected_brand", "expected_product",
    "reply", "name", "latency_ms", "timeout", "error", "brand_correct", "product_correct",
    "judgement",
]


def norm(text: str) -> str:
    """Casefold, strip accents, and drop punctuation and spaces for contains checks."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9&]+", "", text.lower())


def contains(reply: str, expected: str) -> bool:
    """Case-insensitive contains, ignoring punctuation and spacing (Kellogg's == Kelloggs)."""
    return bool(expected) and norm(expected) in norm(reply)


def class_hint(row: dict[str, str]) -> str:
    """Return the COCO hint for one manifest row; a class_label column wins if present."""
    if row.get("class_label", "").strip():
        return row["class_label"].strip()  # the detector's real label, for camera crops
    if row["category"] != "objects":
        return CATEGORY_HINT.get(row["category"], "unknown")
    stem = Path(row["file"]).stem.split("--")[0]
    return next((v for k, v in OBJECT_HINT.items() if k in stem), "unknown")


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile; 0.0 for an empty list."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, round(pct / 100 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


async def run_all(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Name every row with the real client, rate limited like the namer."""
    import httpx

    from namer.grok_client import name_crop
    from namer.namer import clean_name

    slots = asyncio.Semaphore(NAME_MAX_IN_FLIGHT)
    loop = asyncio.get_running_loop()
    results: list[dict[str, Any]] = []

    async def one(client: httpx.AsyncClient, row: dict[str, str]) -> None:
        hint = class_hint(row)
        out: dict[str, Any] = {k: row.get(k, "") for k in FIELDS}
        out.update(class_hint=hint, reply="", name="", error="", judgement="")
        start = time.monotonic()
        try:
            raw = await asyncio.wait_for(
                name_crop(client, Path(row["file"]).read_bytes(), hint), SAFETY_CAP_SECONDS
            )
            out["reply"], out["name"] = raw, clean_name(raw)
        except Exception as exc:  # noqa: BLE001 - eval records every failure and keeps going
            out["error"] = type(exc).__name__
        finally:
            slots.release()
        seconds = time.monotonic() - start
        timed_out = seconds > NAME_TIMEOUT_SECONDS or "Timeout" in out["error"]
        out["latency_ms"] = round(seconds * 1000)
        out["timeout"] = "yes" if timed_out else "no"
        out["brand_correct"] = "yes" if contains(out["name"], row["expected_brand"]) else "no"
        out["product_correct"] = "yes" if contains(out["name"], row["expected_product"]) else "no"
        results.append(out)
        print(f"  {out['latency_ms']:5d} ms  {Path(row['file']).name:40} {out['name'] or out['error']}")

    async with httpx.AsyncClient(timeout=NAME_TIMEOUT_SECONDS) as client:
        tasks = []
        last_start: float | None = None
        for row in rows:
            await slots.acquire()
            if last_start is not None:
                delay = last_start + NAME_MIN_INTERVAL_SECONDS - loop.time()
                if delay > 0:
                    await asyncio.sleep(delay)
            last_start = loop.time()
            tasks.append(asyncio.create_task(one(client, row)))
        await asyncio.gather(*tasks)
    order = {r["file"]: i for i, r in enumerate(rows)}
    return sorted(results, key=lambda r: order[r["file"]])


def summarize(results: list[dict[str, Any]]) -> None:
    """Print accuracy overall, per category and per variant, plus latency stats."""

    def acc(group: list[dict[str, Any]]) -> str:
        n = len(group)
        brand = sum(r["brand_correct"] == "yes" for r in group)
        product = sum(r["product_correct"] == "yes" for r in group)
        both = sum(r["brand_correct"] == r["product_correct"] == "yes" for r in group)
        judged = [r for r in group if r.get("judgement")]
        good = sum(r["judgement"] == "correct" for r in judged)
        judge = f"{good:>2}/{len(judged):<2}" if judged else "  -  "
        return f"{n:>3}  {brand:>2}/{n:<2}  {product:>2}/{n:<2}  {both:>2}/{n:<2}  {judge}"

    header = f"{'':16}{'n':>3}  {'brand':5}  {'prod.':5}  {'both':5}  {'judged ok'}"
    print("\nAccuracy (contains checks are case and punctuation insensitive)")
    print(header)
    print(f"{'overall':16}{acc(results)}")
    for key in ("category", "variant"):
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in results:
            groups[r[key]].append(r)
        print(f"-- by {key}")
        for name in sorted(groups):
            print(f"{name:16}{acc(groups[name])}")

    ok = [float(r["latency_ms"]) for r in results if not r["error"]]
    every = [float(r["latency_ms"]) for r in results]
    over = sum(float(r["latency_ms"]) > NAME_TIMEOUT_SECONDS * 1000 for r in results)
    errors = [r["error"] for r in results if r["error"]]
    print(f"\nLatency, successful calls: p50 {percentile(ok, 50):.0f} ms, p95 {percentile(ok, 95):.0f} ms,"
          f" max {max(ok, default=0):.0f} ms (n={len(ok)})")
    print(f"Latency, all calls: p50 {percentile(every, 50):.0f} ms, p95 {percentile(every, 95):.0f} ms")
    print(f"Calls over NAME_TIMEOUT_SECONDS ({NAME_TIMEOUT_SECONDS:.0f} s): {over} of {len(results)}")
    print(f"Errors: {len(errors)} {sorted(set(errors)) if errors else ''}")
    if ok:
        print(f"Mean successful latency {statistics.mean(ok):.0f} ms")


def _path_arg(argv: list[str], flag: str, default: Path) -> Path:
    """Value after flag in argv, else default."""
    if flag in argv and argv.index(flag) + 1 < len(argv):
        return Path(argv[argv.index(flag) + 1])
    return default


def main(argv: list[str]) -> int:
    """Run the batch (or just the summary) and return an exit code.

    --manifest PATH and --results PATH point at another set, such as camera
    crops, so the web-photo results are not overwritten.
    """
    manifest = _path_arg(argv, "--manifest", MANIFEST)
    results_path = _path_arg(argv, "--results", RESULTS)
    if "--summarize" in argv:
        with results_path.open(newline="", encoding="utf-8") as f:
            summarize(list(csv.DictReader(f)))
        return 0
    if not manifest.exists():
        print(f"No {manifest}. Build the eval set first.")
        return 1
    from dotenv import load_dotenv

    load_dotenv()
    missing = [v for v in ("GROK_API_KEY", "GROK_MODEL") if not os.environ.get(v)]
    if missing:
        print(f"Missing {', '.join(missing)} in the environment. Add them to .env and retry.")
        return 1
    with manifest.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"Naming {len(rows)} images, {NAME_MAX_IN_FLIGHT} in flight, "
          f"{NAME_MIN_INTERVAL_SECONDS:.1f} s between starts")
    results = asyncio.run(run_all(rows))
    with results_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(results)
    print(f"Wrote {results_path}")
    summarize(results)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
