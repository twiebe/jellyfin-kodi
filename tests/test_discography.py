# -*- coding: utf-8 -*-

import sqlite3

import pytest

from jellyfin_kodi.objects.kodi import queries_music as QU
from jellyfin_kodi.objects.kodi.music import Music


@pytest.fixture
def music():
    conn = sqlite3.connect(":memory:")
    # As in Kodi's MyMusic database: no unique index
    conn.execute(
        "CREATE TABLE discography (idArtist integer, strAlbum text, strYear text,"
        " strReleaseGroupMBID TEXT)"
    )
    music = Music.__new__(Music)
    music.cursor = conn.cursor()
    yield conn, music
    conn.close()


def _rows(conn):
    return conn.execute(
        "SELECT idArtist, strAlbum, strYear FROM discography ORDER BY rowid"
    ).fetchall()


# Each sync adds the albums of an artist again
def test_album_is_added_once(music):
    conn, db = music
    for _ in range(3):
        db.add_discography(2, "Rust and Glory", 2016)
        db.add_discography(2, "Rust and Glory", 0)
        db.add_discography(2, "Untitled", None)
    assert _rows(conn) == [
        (2, "Rust and Glory", "2016"),
        (2, "Rust and Glory", "0"),
        (2, "Untitled", None),
    ]


def test_duplicates_of_former_syncs_are_deleted(music):
    conn, db = music
    for _ in range(3):
        for row in ((2, "Signal Lost", "2021"), (3, "Tidal Code", "0")):
            conn.execute(
                "INSERT INTO discography(idArtist, strAlbum, strYear) VALUES (?, ?, ?)",
                row,
            )
    db.delete_duplicate_discography()
    assert _rows(conn) == [(2, "Signal Lost", "2021"), (3, "Tidal Code", "0")]


def test_query_takes_the_discography_values():
    assert QU.update_discography.count("?") == len(QU.update_discography_obj)
