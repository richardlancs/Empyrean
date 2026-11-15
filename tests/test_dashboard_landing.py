"""The one-action landing page and consistent browser asset versions."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

from fastapi.testclient import TestClient

from dashboard.assets import ASSET_PREFIX, asset_revision
from dashboard.server import create_app


class Actions(HTMLParser):
    """Collect interactive elements without mistaking decorative illustrations for controls."""

    def __init__(self) -> None:
        super().__init__()
        self.items: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Collect links, buttons and form inputs."""
        if tag in {"a", "button", "input", "select", "textarea", "summary"}:
            self.items.append((tag, dict(attrs)))


def test_landing_has_one_action_that_opens_the_real_dashboard() -> None:
    """One direct link opens the existing dashboard, with no intermediate choice or form."""
    client = TestClient(create_app())
    page = client.get("/")
    assert page.status_code == 200
    actions = Actions()
    actions.feed(page.text)
    assert len(actions.items) == 1
    tag, attrs = actions.items[0]
    assert tag == "a" and attrs["href"] == "/dashboard"
    assert "Open Empyrean" in page.text
    dashboard = client.get(str(attrs["href"]))
    assert dashboard.status_code == 200 and '<div id="app">' in dashboard.text
    assert page.headers["cache-control"] == dashboard.headers["cache-control"] == "no-store"


def test_dashboard_versions_static_and_dynamic_module_dependencies() -> None:
    """A fresh entry module cannot import an old unversioned feature or helper."""
    client = TestClient(create_app())
    page = client.get("/dashboard").text
    import_map = re.search(r'<script type="importmap">(.*?)</script>', page, re.DOTALL)
    assert import_map is not None
    prefix = json.loads(import_map.group(1))["imports"]["/static/"]
    assert prefix == f"{ASSET_PREFIX}/"
    assert f'src="{prefix}app.js"' in page
    for path in ("app.js", "features/experience/index.js", "features/experience/selectors.js"):
        response = client.get(prefix + path)
        assert response.status_code == 200
        assert "must-revalidate" in response.headers["cache-control"]
    assert "export function languageRequestVoice" in client.get(
        prefix + "features/experience/selectors.js"
    ).text
    legacy = client.get("/static/features/experience/selectors.js")
    assert "must-revalidate" in legacy.headers["cache-control"]
    conditional = client.get(
        "/static/features/experience/selectors.js", headers={"If-None-Match": legacy.headers["etag"]}
    )
    assert conditional.status_code == 304
    assert "must-revalidate" in conditional.headers["cache-control"]


def test_same_size_helper_change_invalidates_the_whole_asset_graph(tmp_path: Path) -> None:
    """Content changes get a fresh module URL even if the entry file and file size stay unchanged."""
    (tmp_path / "app.js").write_text('import "./helper.js";', encoding="utf-8")
    helper = tmp_path / "helper.js"
    helper.write_text("export const value = 1;", encoding="utf-8")
    before = asset_revision(tmp_path)
    helper.write_text("export const value = 2;", encoding="utf-8")
    assert asset_revision(tmp_path) != before


def test_landing_assets_and_walkthrough_return_link_work() -> None:
    """The landing page stays offline-capable and the walkthrough returns to the dashboard."""
    client = TestClient(create_app())
    page = client.get("/").text
    for url in re.findall(r'(?:src|href)="([^"]+)"', page):
        assert url.startswith("/")
        assert client.get(url).status_code == 200, url
    assert 'href="/dashboard"' in client.get("/how-it-works/").text
