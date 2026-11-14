"""Agent 1 foundation checks: entry document, tokens, contrast, layering, preview harness.

Runs the Node unit tests for dashboard/static/core when Node is installed
(skipped otherwise), and checks the static files and the fixture preview server.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
STATIC = ROOT / "dashboard" / "static"
INDEX = ROOT / "dashboard" / "index.html"
sys.path.insert(0, str(HERE))

from agent1_fixtures import SCENARIOS
from agent1_preview_server import create_preview_app

FOUNDATION_JS = [
    STATIC / "app.js",
    STATIC / "components" / "app-shell.js",
    *sorted((STATIC / "core").glob("*.js")),
]
FOUNDATION_CSS = sorted((STATIC / "styles").glob("*.css"))
MOUNT_IDS = [
    "health-panel",
    "warning-panel",
    "touch-panel",
    "camera-panel",
    "objects-panel",
    "find-panel",
    "events-panel",
    "demo-panel",
]


# ---------- Node unit tests ----------


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")
def test_core_modules_pass_node_unit_tests() -> None:
    """Store, transport, announcer, preferences, loader and app composition (node --test)."""
    result = subprocess.run(
        ["node", "--test", str(HERE / "js")],
        check=False,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-2000:]


# ---------- Entry document ----------


class _Collector(HTMLParser):
    """Collect tags (with attributes) in document order and any inline script/style text."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.inline: list[str] = []
        self._in: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))
        if tag in ("script", "style"):
            self._in = tag

    def handle_endtag(self, tag: str) -> None:
        if tag == self._in:
            self._in = None

    def handle_data(self, data: str) -> None:
        if self._in and data.strip():
            self.inline.append(self._in)


def _parsed_index() -> _Collector:
    parser = _Collector()
    parser.feed(INDEX.read_text(encoding="utf-8"))
    return parser


def test_index_is_a_minimal_entry_document() -> None:
    """No inline style or script; theme boot before the stylesheets; one module entry."""
    page = _parsed_index()
    assert page.inline == [], "index.html must not embed scripts or styles"
    assert not any(tag == "style" for tag, _ in page.tags)
    order = [
        (tag, attrs.get("src") or attrs.get("href"))
        for tag, attrs in page.tags
        if tag in ("script", "link")
    ]
    assert order == [
        ("script", "/static/core/theme-boot.js"),
        ("link", "/static/styles/tokens.css"),
        ("link", "/static/styles/base.css"),
        ("link", "/static/styles/layout.css"),
        ("link", "/static/styles/components.css"),
        ("link", "/static/features/experience/experience.css"),
        ("link", "/static/features/operations/operations.css"),
        ("script", "/static/app.js"),
    ]
    module = [
        a for t, a in page.tags if t == "script" and a.get("src") == "/static/app.js"
    ]
    assert module[0].get("type") == "module"
    html = next(a for t, a in page.tags if t == "html")
    assert html.get("lang") == "en" and html.get("data-theme") == "light"
    assert any(t == "div" and a.get("id") == "app" for t, a in page.tags)


def test_foundation_files_referenced_by_index_exist() -> None:
    """Every foundation asset the page loads is present (feature files are Agents 2 and 3's)."""
    page = _parsed_index()
    for tag, attrs in page.tags:
        url = (
            attrs.get("src") or attrs.get("href") if tag in ("script", "link") else None
        )
        if url and not url.startswith("/static/features/"):
            assert (STATIC / url.removeprefix("/static/")).is_file(), url


def test_copy_never_claims_safety() -> None:
    """No foundation UI text calls this a safety device (AGENTS.md rule 5)."""
    for path in [INDEX, *FOUNDATION_JS, *FOUNDATION_CSS]:
        text = path.read_text(encoding="utf-8").lower()
        assert "safety" not in text, path
        assert "you are safe" not in text and "area is safe" not in text, path


# ---------- Layering ----------


def test_only_the_socket_client_opens_the_websocket() -> None:
    """One WebSocket owner, one HTTP owner; app.js composes them."""
    for path in FOUNDATION_JS:
        text = path.read_text(encoding="utf-8")
        name = path.name
        if name != "socket-client.js":
            assert "new WebSocket" not in text and "WebSocketImpl(" not in text, name
            assert '"/ws"' not in text, name
        if name not in ("api-client.js",):
            assert "fetch(" not in text.replace("fetchImpl", ""), name


def test_core_does_not_depend_on_features_or_components() -> None:
    """Dependency direction: core imports only core."""
    for path in sorted((STATIC / "core").glob("*.js")):
        for target in re.findall(r'from\s+"([^"]+)"', path.read_text(encoding="utf-8")):
            assert target.startswith("./"), f"{path.name} imports {target}"


def test_foundation_never_renders_html_strings() -> None:
    """External names are rendered as text, never parsed as HTML."""
    for path in FOUNDATION_JS:
        text = path.read_text(encoding="utf-8")
        for unsafe in (
            "innerHTML",
            "outerHTML",
            "insertAdjacentHTML",
            "document.write",
        ):
            assert unsafe not in text, f"{path.name} uses {unsafe}"


def test_shell_supplies_every_contract_mount() -> None:
    """The shared contract's eight mount ids are created by the shell."""
    shell = (STATIC / "components" / "app-shell.js").read_text(encoding="utf-8")
    for mount_id in MOUNT_IDS:
        assert f'id: "{mount_id}"' in shell, mount_id


# ---------- Tokens and contrast ----------


def _token_block(css: str, selector_pattern: str) -> dict[str, str]:
    match = re.search(selector_pattern + r"\s*\{(.*?)\n\}", css, re.DOTALL)
    assert match, selector_pattern
    return dict(re.findall(r"--([\w-]+):\s*([^;]+);", match.group(1)))


def _themes() -> dict[str, dict[str, str]]:
    css = (STATIC / "styles" / "tokens.css").read_text(encoding="utf-8")
    light = _token_block(css, r':root,\s*:root\[data-theme="light"\]')
    contrast = {**light, **_token_block(css, r':root\[data-theme="high-contrast"\]')}
    return {"light": light, "high-contrast": contrast}


def _luminance(hex_color: str) -> float:
    value = hex_color.strip().lstrip("#")
    channels = [int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [
        c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _ratio(fg: str, bg: str) -> float:
    a, b = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


SOFT_BACKGROUNDS = [
    "accent-soft",
    "caution-soft",
    "danger-soft",
    "sim-soft",
    "neutral-soft",
]
TEXT_PAIRS = [
    *[
        (fg, bg)
        for fg in ("text", "text-secondary")
        for bg in ("page", "surface", "surface-sunken", *SOFT_BACKGROUNDS)
    ],
    ("on-accent", "accent"),
    ("on-accent", "accent-hover"),
    ("on-danger", "danger"),
    ("on-danger", "danger-hover"),
    ("accent-text", "surface"),
    ("accent-text", "page"),
    ("accent-text", "accent-soft"),
    ("caution", "caution-soft"),
    ("caution", "surface"),
    ("danger", "danger-soft"),
    ("danger", "surface"),
    ("sim", "sim-soft"),
    ("sim", "surface"),
    ("neutral", "neutral-soft"),
]
NON_TEXT_PAIRS = [
    ("border-control", "surface"),
    ("border-control", "page"),
    ("focus", "surface"),
    ("focus", "page"),
    ("focus", "danger-soft"),
    ("accent", "surface"),
    ("caution", "surface"),
    ("danger", "surface"),
    ("danger", "danger-soft"),
    ("sim", "surface"),
]


@pytest.mark.parametrize("theme", ["light", "high-contrast"])
def test_token_contrast_meets_wcag(theme: str) -> None:
    """Text pairs: 4.5:1 (light) or 7:1 (high contrast). Boundaries and focus: 3:1."""
    tokens = _themes()[theme]
    text_min = 7.0 if theme == "high-contrast" else 4.5
    failures = []
    for fg, bg in TEXT_PAIRS:
        ratio = _ratio(tokens[f"color-{fg}"], tokens[f"color-{bg}"])
        if ratio < text_min:
            failures.append(f"{fg} on {bg}: {ratio:.2f}")
    for fg, bg in NON_TEXT_PAIRS:
        ratio = _ratio(tokens[f"color-{fg}"], tokens[f"color-{bg}"])
        if ratio < 3.0:
            failures.append(f"{fg} on {bg}: {ratio:.2f} (non-text)")
    assert not failures, failures


def test_light_palette_matches_the_shared_design_language() -> None:
    """The current brief's light tokens are used as given (design/friendly-clarity).

    Softened Bauhaus: warm off-white paper, clear dark text, light dividers, one
    deep blue for action and touch, red only for hazards, pastel accents only for
    illustration and subtle backgrounds. Contrast: test_token_contrast_meets_wcag.
    """
    light = _themes()["light"]
    expected = {
        "color-page": "#F8F5EF",
        "color-surface": "#FFFFFF",
        "color-text": "#1F1F1F",
        "color-text-secondary": "#57524A",
        "color-border-control": "#7A7367",
        "color-accent": "#1947B8",
        "color-accent-soft": "#E8EEFB",
        "color-caution": "#1F1F1F",
        "color-caution-soft": "#FBEFC4",
        "color-danger": "#B42318",
        "color-danger-soft": "#FDECEA",
        "color-sim": "#6D28D9",
        "color-sim-soft": "#F3EEFF",
        "color-focus": "#1947B8",
    }
    assert {k: light[k] for k in expected} == expected


def test_no_dark_theme_and_readable_minimum_sizes() -> None:
    """Light is the default (no dark media query); no text below 13px; 44px targets."""
    tokens = _themes()["light"]
    assert _luminance(tokens["color-page"]) > 0.8
    assert tokens["target-min"] == "44px"
    assert tokens["text-badge"].startswith("0.8125rem")
    assert tokens["text-body"].startswith("1.0625rem")
    for path in FOUNDATION_CSS:
        css = path.read_text(encoding="utf-8")
        assert "prefers-color-scheme: dark" not in css, path.name
        for size in re.findall(r"font-size:\s*([\d.]+)(px|rem)", css):
            px = float(size[0]) * (16 if size[1] == "rem" else 1)
            assert px >= 13, f"{path.name}: font-size {size}"


def test_reduced_motion_is_honoured() -> None:
    """base.css switches animation and transitions off for reduced motion."""
    base = (STATIC / "styles" / "base.css").read_text(encoding="utf-8")
    assert "prefers-reduced-motion: reduce" in base
    assert (
        "animation-duration: 0.01ms" in base and "transition-duration: 0.01ms" in base
    )


# ---------- Preview harness ----------


def test_preview_serves_real_foundation_and_fixture_state() -> None:
    """The preview uses the real index.html and static files, plus fixture /ws data."""
    client = TestClient(create_preview_app())
    page = client.get("/")
    assert page.status_code == 200 and "/static/app.js" in page.text
    app_js = client.get("/static/app.js")
    assert app_js.status_code == 200 and "startDashboard" in app_js.text
    assert "javascript" in app_js.headers["content-type"]
    assert client.get("/static/features/experience/index.js").status_code == 200
    with client.websocket_connect("/ws") as ws:
        state = ws.receive_json()
    assert state["current_touch"]["text"] == "Heinz ketchup"
    assert client.post("/preview/scenario/legacy").status_code == 200
    assert "current_touch" not in client.get("/api/state").json()


def test_preview_can_simulate_missing_feature_modules() -> None:
    """--missing-features makes both feature modules 404, to show the load-error state."""
    client = TestClient(create_preview_app(missing_features=True))
    assert client.get("/static/features/experience/index.js").status_code == 404
    assert client.get("/static/features/operations/index.js").status_code == 404
    assert client.get("/static/app.js").status_code == 200


def test_preview_last_seen_flow_and_validation() -> None:
    """202 + request_id, pending then found; empty query is a 422 with a message."""
    client = TestClient(create_preview_app())
    accepted = client.post("/api/last-seen", json={"query": "ketchup"})
    assert accepted.status_code == 202
    request_id = accepted.json()["request_id"]
    assert client.get(f"/api/last-seen/{request_id}").json()["status"] == "pending"
    found = client.get(f"/api/last-seen/{request_id}").json()
    assert found["status"] == "found" and isinstance(found["matched_at"], float)
    assert client.post("/api/last-seen", json={"query": " "}).status_code == 422


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_every_scenario_has_the_base_state_fields(name: str) -> None:
    """Fixtures keep today's snapshot fields so the legacy path stays covered."""
    state = SCENARIOS[name](1_800_000_000.0)
    for field in (
        "now",
        "hazard_active_seconds",
        "latest_warning",
        "events",
        "objects",
    ):
        assert field in state, field
