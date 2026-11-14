"""Person 3 code uses the shared contracts/ and config/ definitions, not local copies.

A copied dataclass with the same name and fields is a different class, so on a
bus that routes by message type it silently misses its subscribers. A copied
threshold silently stops following config/. These checks look at class identity
and at the source of every Person 3 module, so neither copy can come back.

Bus wiring (register(bus) subscribing and publishing the contracts classes) is
tested in tests/test_register.py. The real Namer's published class is checked in
tests/test_namer.py.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
from pathlib import Path

import pytest

import config
import contracts

ROOT = Path(__file__).resolve().parents[1]
P3_DIRS = ("namer", "storage", "fakes/namer", "fakes/storage")
P3_FILES = sorted(p for d in P3_DIRS for p in (ROOT / d).glob("*.py"))
MESSAGE_NAMES = set(contracts.__all__)
THRESHOLD_NAMES = {name for name in vars(config) if name.isupper()}


def _module_level_definitions(path: Path) -> tuple[set[str], set[str]]:
    """Return the class names and assigned names defined at the top level of path."""
    classes: set[str] = set()
    assigned: set[str] = set()
    for node in ast.parse(path.read_text(), filename=str(path)).body:
        if isinstance(node, ast.ClassDef):
            classes.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                assigned.update(
                    n.id for n in ast.walk(target) if isinstance(n, ast.Name)
                )
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and isinstance(
            node.target, ast.Name
        ):
            assigned.add(node.target.id)
    return classes, assigned


def test_p3_files_found() -> None:
    """The source scan below actually sees the Person 3 modules."""
    names = {p.relative_to(ROOT).as_posix() for p in P3_FILES}
    assert {
        "namer/namer.py",
        "storage/_deps.py",
        "fakes/namer/fake_namer.py",
        "fakes/storage/fake_store.py",
    } <= names


@pytest.mark.parametrize(
    "module",
    [
        "namer._pending",
        "storage._pending",
        "fakes.namer._pending",
        "fakes.storage._pending",
    ],
)
def test_pending_shims_are_gone(module: str) -> None:
    """None of the four temporary _pending shims can be imported."""
    assert importlib.util.find_spec(module) is None


@pytest.mark.parametrize("path", P3_FILES, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_no_local_copy_of_a_message_or_threshold(path: Path) -> None:
    """No Person 3 module defines its own message class, Box/Point, or config threshold."""
    classes, assigned = _module_level_definitions(path)
    assert not classes & MESSAGE_NAMES, (
        f"message class redefined: {sorted(classes & MESSAGE_NAMES)}"
    )
    copied = assigned & (MESSAGE_NAMES | THRESHOLD_NAMES)
    assert not copied, (
        f"shared name assigned locally instead of imported: {sorted(copied)}"
    )


@pytest.mark.parametrize(
    ("module", "names"),
    [
        ("namer", ["NameRequest"]),
        ("namer.namer", ["NameRequest", "NameResult"]),
        (
            "storage._deps",
            ["TouchEvent", "HazardEvent", "LastSeenQuery", "SpeakRequest"],
        ),
        (
            "storage.writer",
            ["TouchEvent", "HazardEvent", "LastSeenQuery", "SpeakRequest"],
        ),
        ("fakes.namer.fake_namer", ["NameRequest", "NameResult"]),
        (
            "fakes.storage.fake_store",
            ["TouchEvent", "HazardEvent", "LastSeenQuery", "SpeakRequest"],
        ),
    ],
)
def test_module_message_names_are_the_shared_classes(
    module: str, names: list[str]
) -> None:
    """Each message name a Person 3 module uses is the contracts class itself."""
    mod = importlib.import_module(module)
    for name in names:
        assert getattr(mod, name) is getattr(contracts, name), f"{module}.{name}"
