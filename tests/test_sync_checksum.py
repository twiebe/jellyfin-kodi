# -*- coding: utf-8 -*-

import copy

from jellyfin_kodi.objects.obj import Objects
from jellyfin_kodi.objects.utils import sync_checksum

MOVIE = {
    "Id": "a",
    "Type": "Movie",
    "Etag": "e1",
    "UserData": {"Played": False, "PlayCount": 0, "IsFavorite": False},
}


def _checksum(item, *settings):
    return sync_checksum(Objects().map(item, "Movie"), *settings)


def test_same_item_same_checksum():
    assert _checksum(MOVIE, "art", False) == _checksum(
        copy.deepcopy(MOVIE), "art", False
    )


def test_short_and_full_item_have_the_same_checksum():
    # The update sync compares the short version of an item (Etag and user
    # data) with the checksum written from the full one
    full = dict(MOVIE, Path="/media/a.mkv", Overview="Plot", People=[])
    assert _checksum(MOVIE, "art") == _checksum(full, "art")


def test_server_changes_change_the_checksum():
    assert _checksum(dict(MOVIE, Etag="e2")) != _checksum(MOVIE)


def test_user_data_changes_change_the_checksum():
    played = copy.deepcopy(MOVIE)
    played["UserData"]["Played"] = True
    assert _checksum(played) != _checksum(MOVIE)


def test_settings_change_the_checksum():
    assert _checksum(MOVIE, "art", False) != _checksum(MOVIE, "art", True)
    assert _checksum(MOVIE, "Movies") != _checksum(MOVIE, "Films")
