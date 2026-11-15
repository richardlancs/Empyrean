"""Voice download CLI selection, without fetching models over the network."""

import pytest

from audio import fetch_voices
from audio.voices import PRESETS


@pytest.mark.parametrize("keys", [[], ["cori"], ["alba", "huayan"]])
def test_download_selection(monkeypatch: pytest.MonkeyPatch, keys: list[str]) -> None:
    """No arguments selects all voices; explicit keys select only those presets."""
    fetched: list[str] = []
    monkeypatch.setattr(fetch_voices, "fetch", fetched.append)
    assert fetch_voices.main(keys) == 0
    assert fetched == [p.model for p in PRESETS if not keys or p.key in keys]


def test_invalid_key_downloads_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject the whole request before downloading if any preset is unknown."""
    fetched: list[str] = []
    monkeypatch.setattr(fetch_voices, "fetch", fetched.append)
    with pytest.raises(SystemExit) as exc:
        fetch_voices.main(["alba", "unknown"])
    assert exc.value.code == 2
    assert fetched == []
