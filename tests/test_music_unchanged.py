# -*- coding: utf-8 -*-

import pytest

from jellyfin_kodi.objects.music import Music
from jellyfin_kodi.objects.obj import Objects

SONG = {
    "Id": "s",
    "Type": "Audio",
    "Etag": "e1",
    "UserData": {"Played": False, "PlayCount": 0, "IsFavorite": False},
}


@pytest.fixture
def music():
    music = Music.__new__(Music)
    music.direct_path = False
    music.item_ids = []
    music.skip_unchanged = True
    return music


def _obj(item=SONG):
    return Objects().map(item, "Song")


def _e_item(checksum):
    # kodi_id, kodi_fileid, kodi_pathid, parent_id, media_type, jellyfin_type,
    # media_folder, jellyfin_parent_id, sync_checksum
    return (1, None, 2, 3, "song", "Audio", "lib", None, checksum)


# Kodi's triggers write every update of a song, also with the same values
def test_update_sync_skips_an_unchanged_song(music):
    checksum = music.checksum(_obj())
    assert music.unchanged(_obj(), _e_item(checksum), True)
    assert music.item_ids == ["s"]


def test_changed_song_is_written(music):
    checksum = music.checksum(_obj())
    changed = _obj(dict(SONG, Etag="e2"))
    assert not music.unchanged(changed, _e_item(checksum), True)
    assert changed["SyncChecksum"] != checksum
    assert music.item_ids == []


def test_song_without_checksum_is_written(music):
    assert not music.unchanged(_obj(), _e_item(None), True)


def test_song_missing_in_kodi_is_written(music):
    checksum = music.checksum(_obj())
    assert not music.unchanged(_obj(), _e_item(checksum), False)


def test_only_the_update_sync_skips(music):
    music.skip_unchanged = False
    checksum = music.checksum(_obj())
    assert not music.unchanged(_obj(), _e_item(checksum), True)
