# -*- coding: utf-8 -*-

from collections import namedtuple

import pytest

from jellyfin_kodi import full_sync

View = namedtuple("View", "view_id view_name media_type")

VIEWS = {
    "shows": View("shows", "Shows", "tvshows"),
    "movies": View("movies", "Movies", "movies"),
    "mixed": View("mixed", "Mixed", "mixed"),
    "sets": View("sets", "Collections", "boxsets"),
}


@pytest.fixture
def sync(monkeypatch):
    """A FullSync that records the libraries it would sync."""
    state = {"sync": {"Libraries": [], "RestorePoint": {}}, "started": []}

    monkeypatch.setattr(full_sync, "get_sync", lambda: state["sync"])
    monkeypatch.setattr(full_sync, "settings", lambda *args: None)
    monkeypatch.setattr(full_sync.xmls, "advanced_settings", lambda: False)

    obj = full_sync.FullSync.__new__(full_sync.FullSync)
    obj.get_library = VIEWS.get
    obj.get_libraries = lambda: list(VIEWS.values())
    obj.start = lambda: state["started"].append(list(obj.sync["Libraries"]))
    state["obj"] = obj
    return state


# An interrupted sync leaves its library and restore point in sync.json
def test_library_of_an_interrupted_sync_is_synced_once(sync):
    sync["sync"]["Libraries"] = ["shows"]
    sync["obj"].libraries("shows")
    assert sync["started"] == [["shows"]]


def test_movies_and_boxsets_are_added_once(sync):
    sync["sync"]["Libraries"] = ["movies", "Boxsets:sets"]
    sync["obj"].libraries("movies")
    assert sync["started"] == [["movies", "Boxsets:sets"]]


def test_mixed_library_is_added_once(sync):
    sync["sync"]["Libraries"] = ["Mixed:mixed", "Boxsets:sets"]
    sync["obj"].libraries("mixed")
    assert sync["started"] == [["Mixed:mixed", "Boxsets:sets"]]


def test_other_libraries_are_added(sync):
    sync["sync"]["Libraries"] = ["shows"]
    sync["obj"].libraries("movies,unknown")
    assert sync["started"] == [["shows", "movies", "Boxsets:sets", "unknown"]]
