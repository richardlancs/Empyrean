"""Smoke tests for the static How It Works page (howitworks/)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from contracts import messages
from tests.howitworks_server import HOW_DIR, ROOT, build_dev_app

BASE = "/how-it-works/"
MB = 1024 * 1024
OWN_SUFFIXES = {".html", ".js", ".css"}


def _client() -> TestClient:
    """Return a client for the development app."""
    return TestClient(build_dev_app())


def _own_files() -> list[Path]:
    """Return the page's own source files, excluding vendored libraries."""
    return [
        p
        for p in HOW_DIR.rglob("*")
        if p.is_file() and p.suffix in OWN_SUFFIXES and "vendor" not in p.parts
    ]


def _index() -> str:
    """Return the page HTML."""
    return (HOW_DIR / "index.html").read_text(encoding="utf-8")


def _resolve(url: str) -> str:
    """Turn a URL from the page into a path on the server."""
    if url.startswith("/"):
        return url
    return BASE + url.removeprefix("./")


def test_page_is_served() -> None:
    """The page loads and shows its title and the Prototype label."""
    response = _client().get(BASE)
    assert response.status_code == 200
    assert "How it works" in response.text
    assert "Prototype" in response.text


def test_every_local_reference_exists() -> None:
    """Every script, stylesheet, image and import-map target is served."""
    html = _index()
    urls = re.findall(r'(?:src|href)="([^"#]+)"', html)
    urls = [u for u in urls if u != "/" and not u.startswith("data:")]
    import_map = re.search(r'<script type="importmap">(.*?)</script>', html, re.DOTALL)
    assert import_map, "import map missing"
    for target in json.loads(import_map.group(1))["imports"].values():
        urls.append(target + "index.js" if target.endswith("/gsap/") else target)
    client = _client()
    assert urls
    for url in urls:
        if url.endswith("/"):
            continue  # a directory prefix in the import map
        assert client.get(_resolve(url)).status_code == 200, url


def test_no_remote_urls() -> None:
    """Nothing is loaded from the network (XML namespaces excepted)."""
    for path in _own_files():
        text = path.read_text(encoding="utf-8").replace("http://www.w3.org/", "")
        assert "http://" not in text and "https://" not in text, path


def test_no_banned_copy() -> None:
    """The page never calls the prototype a safety device or a cane replacement."""
    for path in _own_files():
        text = path.read_text(encoding="utf-8").lower()
        assert "safety device" not in text, path
        assert not re.search(r"\bcane\b", text), path


def test_no_unsafe_dom_writes() -> None:
    """Page code never writes markup from strings."""
    banned = ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write")
    for path in _own_files():
        text = path.read_text(encoding="utf-8")
        for name in banned:
            assert name not in text, f"{name} in {path}"


def test_file_sizes() -> None:
    """Files stay within the repository's size rules."""
    total = 0
    for path in HOW_DIR.rglob("*"):
        if not path.is_file():
            continue
        size = path.stat().st_size
        total += size
        assert size <= 10 * MB, path
        if path.suffix == ".glb":
            assert size <= 3 * MB, path
    assert total <= 8 * MB


def test_message_names_exist_in_contracts() -> None:
    """Every message named on the page is a real message type."""
    text = (HOW_DIR / "content.js").read_text(encoding="utf-8")
    names = set(re.findall(r'message:\s*"([A-Za-z]+)"', text))
    assert names
    for name in names:
        assert hasattr(messages, name), name


def test_fallback_list_is_in_html() -> None:
    """The five explanations are in the document before any script runs."""
    html = _index()
    block = re.search(r'<ul id="hotspot-list".*?</ul>', html, re.DOTALL)
    assert block
    assert block.group(0).count("<li") == 5


def test_fallback_copy_matches_content() -> None:
    """The static list uses the same labels as content.js."""
    html = _index()
    text = (HOW_DIR / "content.js").read_text(encoding="utf-8")
    labels = re.findall(r'label:\s*"([^"]+)"', text)
    assert len(labels) >= 5
    for label in labels[:5]:
        assert f">{label}<" in html, label


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")
def test_js_unit_tests() -> None:
    """Content, selection and stepper logic (node --test)."""
    files = sorted(str(p) for p in (ROOT / "tests" / "howitworks_js").glob("*.test.mjs"))
    assert files
    result = subprocess.run(
        ["node", "--test", *files], capture_output=True, text=True, timeout=120, check=False
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-2000:]


# ----- the real dashboard serves and links to the page -----

DASHBOARD_STATIC = ROOT / "dashboard" / "static"


def _dashboard_client() -> TestClient:
    """Return a client for the real dashboard app."""
    from dashboard.server import create_app

    return TestClient(create_app())


def test_real_dashboard_serves_page() -> None:
    """The dashboard app serves the page and its files."""
    client = _dashboard_client()
    response = client.get(BASE)
    assert response.status_code == 200
    assert "How it works" in response.text
    assert client.get(BASE + "main.js").status_code == 200


def test_dashboard_still_serves_index_and_static() -> None:
    """Mounting the page leaves the dashboard's own routes alone."""
    client = _dashboard_client()
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200


def test_dashboard_header_links_to_page() -> None:
    """The dashboard's How it works control links to the full page."""
    shell = (DASHBOARD_STATIC / "components" / "app-shell.js").read_text(encoding="utf-8")
    assert 'href: "/how-it-works/"' in shell


def test_both_pages_opt_into_view_transitions() -> None:
    """Both documents enable cross-page transitions and share the brand name."""
    base = (DASHBOARD_STATIC / "styles" / "base.css").read_text(encoding="utf-8")
    how = (HOW_DIR / "how.css").read_text(encoding="utf-8")
    for text in (base, how):
        assert "@view-transition" in text
        assert "view-transition-name: empyrean-brand" in text
