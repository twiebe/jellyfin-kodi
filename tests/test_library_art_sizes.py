# -*- coding: utf-8 -*-
"""The library thread rewrites the artwork URLs of the library when the artwork
settings changed, at start and while it runs, once per change."""

import contextlib
import threading

from jellyfin_kodi import library
from jellyfin_kodi.objects.kodi import artwork


def _library(monkeypatch, key, applied):
    lib = library.Library.__new__(library.Library)
    lib.database_lock = threading.Lock()
    stored = {"artSizeApplied": applied}
    resized = []

    @contextlib.contextmanager
    def database(name):
        assert name == "video" and lib.database_lock.locked()
        yield type("Db", (), {"cursor": "cursor"})()

    monkeypatch.setattr(library, "Database", database)
    monkeypatch.setattr(library.api, "art_key", lambda: key[0])
    monkeypatch.setattr(
        artwork, "resize_urls", lambda cursor: resized.append(cursor) or 3
    )
    monkeypatch.setattr(
        library,
        "settings",
        lambda name, value=None: (
            stored.update({name: value}) if value is not None else stored[name]
        ),
    )
    return lib, stored, resized


def test_new_sizes_are_written_once(monkeypatch):
    key = ["auto"]
    lib, stored, resized = _library(monkeypatch, key, "old")
    lib.art_key = stored["artSizeApplied"]
    lib.apply_art_sizes()
    lib.apply_art_sizes()
    assert resized == ["cursor"] and stored["artSizeApplied"] == "auto"
    key[0] = "960"
    lib.apply_art_sizes()
    assert resized == ["cursor", "cursor"] and stored["artSizeApplied"] == "960"


def test_sizes_already_written_are_left(monkeypatch):
    lib, stored, resized = _library(monkeypatch, ["auto"], "auto")
    lib.art_key = stored["artSizeApplied"]
    lib.apply_art_sizes()
    assert resized == []


def test_startup_takes_over_the_old_setting_first(monkeypatch):
    calls = []
    lib, stored, resized = _library(monkeypatch, ["auto"], "")
    monkeypatch.setattr(
        library.api, "migrate_art_sizes", lambda: calls.append("migrate")
    )
    lib.start_art_sizes()
    assert calls == ["migrate"] and resized == ["cursor"]


def test_a_failed_rewrite_keeps_the_library_thread_and_is_tried_at_the_next_start(
    monkeypatch,
):
    lib, stored, _ = _library(monkeypatch, ["auto"], "old")
    lib.art_key = "old"

    def locked(cursor):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(artwork, "resize_urls", locked)
    lib.apply_art_sizes()
    lib.apply_art_sizes()
    assert stored["artSizeApplied"] == "old"
