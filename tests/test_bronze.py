"""Persistência Bronze."""

from pathlib import Path

import pytest

from radar_publico.bronze import BronzeStore


def test_write_is_exact_atomic_and_idempotent(tmp_path: Path) -> None:
    store = BronzeStore(tmp_path / "bronze")
    content = b'{"synthetic":true}'

    first = store.write("contratos", 2026, 0, content)
    second = store.write("contratos", 2026, 0, content)

    assert first == second
    assert store.read(first) == content
    assert first.content_hash in first.path.name
    assert not list(first.path.parent.glob(".bronze-*.tmp"))


def test_resource_cannot_escape_root(tmp_path: Path) -> None:
    store = BronzeStore(tmp_path / "bronze")
    obj = store.write("../../outside", 2026, 0, b"{}")

    assert obj.path.is_relative_to(store.root)


def test_corruption_is_detected(tmp_path: Path) -> None:
    store = BronzeStore(tmp_path / "bronze")
    obj = store.write("contratos", 2026, 0, b"{}")
    obj.path.write_bytes(b"broken")

    with pytest.raises(Exception):
        store.read(obj)
