# -*- coding: utf-8 -*-

import json
import os

import pytest

from jellyfin_kodi import database


@pytest.fixture
def addon_data(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "ADDON_DATA", str(tmp_path))
    monkeypatch.setattr(database.xbmcvfs, "exists", os.path.exists)
    return tmp_path


def _saved(addon_data):
    with open(str(addon_data / "sync.json")) as infile:
        return json.load(infile)


# sync.json is saved at every start and sync
def test_unchanged_sync_state_is_not_written_again(addon_data):
    sync = database.get_sync()
    sync["Whitelist"] = ["a", "b"]
    database.save_sync(sync)
    os.utime(str(addon_data / "sync.json"), (0, 0))

    sync = database.get_sync()
    database.save_sync(sync)

    assert os.stat(str(addon_data / "sync.json")).st_mtime == 0


def test_changed_sync_state_is_written(addon_data):
    database.save_sync({"Libraries": [], "Whitelist": ["a"]})

    sync = database.get_sync()
    sync["Whitelist"].append("b")
    database.save_sync(sync)

    assert _saved(addon_data)["Whitelist"] == ["a", "b"]
    assert _saved(addon_data)["Date"]


def test_whitelist_keeps_its_order_without_duplicates(addon_data):
    database.save_sync({"Whitelist": ["c", "a", "c", "b"]})
    assert database.get_sync()["Whitelist"] == ["c", "a", "b"]
