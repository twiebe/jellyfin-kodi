# -*- coding: utf-8 -*-

import sqlite3

import pytest

from jellyfin_kodi.database import jellyfin_db, jellyfin_tables


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    jellyfin_tables(conn.cursor())
    db = jellyfin_db.JellyfinDatabase(conn.cursor())
    db.add_view("a", "Movies", "movies")
    conn.commit()
    yield conn, db
    conn.close()


def _rows(conn):
    return conn.execute("SELECT rowid, * FROM view").fetchall()


# The views are added again at every start: an unchanged one is not written
def test_unchanged_view_is_not_written(db):
    conn, views = db
    before, changes = _rows(conn), conn.total_changes
    views.add_view("a", "Movies", "movies")
    assert conn.total_changes == changes
    assert _rows(conn) == before


def test_renamed_view_is_updated(db):
    conn, views = db
    views.add_view("a", "Films", "movies")
    assert _rows(conn) == [(1, "a", "Films", "movies")]


def test_new_view_is_added(db):
    conn, views = db
    views.add_view("b", "Shows", "tvshows")
    assert [row[1:] for row in _rows(conn)] == [
        ("a", "Movies", "movies"),
        ("b", "Shows", "tvshows"),
    ]
