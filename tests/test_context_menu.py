# -*- coding: utf-8 -*-

import json

import pytest

from jellyfin_kodi.entrypoint import context


def _item(monkeypatch, checksum):
    row = ("id", None, "lib", "Movie", checksum)
    monkeypatch.setattr(context.database, "get_item", lambda kodi_id, media: row)
    obj = context.Context.__new__(context.Context)
    obj.kodi_id = 1
    obj.media = "movie"
    return obj.get_item_id()


# The checksum column holds the user data of the item
def test_user_data_from_the_checksum_column(monkeypatch):
    item = _item(monkeypatch, json.dumps({"IsFavorite": True}))
    assert item == {"Id": "id", "UserData": {"IsFavorite": True}, "Type": "Movie"}


@pytest.mark.parametrize(
    "checksum", [None, "", "0cc175b9c0f1b6a831c399e269772661", "3"]
)
def test_other_values_in_the_checksum_column(monkeypatch, checksum):
    assert _item(monkeypatch, checksum)["UserData"] == {}
