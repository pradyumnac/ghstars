from pathlib import Path

import pytest
from conftest import StarFactory
from filelock import Timeout

from ghstars.core.models import List
from ghstars.core.state_store import StateStore


def test_save_and_load_stars_roundtrip(tmp_path: Path, make_star: StarFactory) -> None:
    store = StateStore(tmp_path)
    star = make_star()
    store.save_stars([star])
    assert store.load_stars() == [star]


def test_load_stars_empty_when_never_saved(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    assert store.load_stars() == []


def test_save_and_load_lists_roundtrip(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    lst = List(id="L_1", name="Explore: General", slug="explore-general")
    store.save_lists([lst])
    assert store.load_lists() == [lst]


def test_creates_base_dir_if_missing(tmp_path: Path, make_star: StarFactory) -> None:
    base = tmp_path / "nested" / "state"
    store = StateStore(base)
    store.save_stars([make_star()])
    assert base.exists()


def test_concurrent_write_is_locked_out(tmp_path: Path, make_star: StarFactory) -> None:
    store = StateStore(tmp_path)
    with store.lock():
        other = StateStore(tmp_path)
        with pytest.raises(Timeout):
            other.save_stars([make_star()], lock_timeout=0.05)


def test_concurrent_read_is_locked_out_during_write(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    with store.lock():
        other = StateStore(tmp_path)
        with pytest.raises(Timeout):
            other.load_stars(lock_timeout=0.05)
