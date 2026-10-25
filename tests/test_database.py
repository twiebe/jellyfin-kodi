# -*- coding: utf-8 -*-

import sqlite3

import pytest

from jellyfin_kodi.database import Database
from jellyfin_kodi.helper.exceptions import LibraryExitException


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = str(tmp_path / "test.db")
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE item(id INTEGER)")
    monkeypatch.setattr(Database, "_sql", lambda self, db_file: db_file)
    return path


def _rows(path):
    with sqlite3.connect(path) as conn:
        return conn.execute("SELECT id FROM item").fetchall()


def test_changes_are_committed(db_path):
    with Database(db_path) as db:
        db.cursor.execute("INSERT INTO item VALUES (1)")
    assert _rows(db_path) == [(1,)]


def test_changes_are_rolled_back_on_error(db_path):
    # A half written item must not end up in the database
    with pytest.raises(ValueError):
        with Database(db_path) as db:
            db.cursor.execute("INSERT INTO item VALUES (1)")
            raise ValueError("failed in the middle of an item")
    assert _rows(db_path) == []


def test_commit_close_false_leaves_commit_to_caller(db_path):
    with Database(db_path, commit_close=False) as db:
        db.cursor.execute("INSERT INTO item VALUES (1)")
    assert _rows(db_path) == []


def test_changes_are_kept_when_stopping(db_path):
    # Raised between items when Kodi exits; finished items stay
    with pytest.raises(LibraryExitException):
        with Database(db_path) as db:
            db.cursor.execute("INSERT INTO item VALUES (1)")
            raise LibraryExitException("Kodi aborted, exiting...")
    assert _rows(db_path) == [(1,)]


def _columns(cursor):
    return [row[1] for row in cursor.execute("PRAGMA table_info(jellyfin)")]


def test_sync_checksum_column_is_added_to_old_databases():
    from jellyfin_kodi.database import jellyfin_tables

    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE jellyfin(
        jellyfin_id TEXT UNIQUE, media_folder TEXT, jellyfin_type TEXT, media_type TEXT,
        kodi_id INTEGER, kodi_fileid INTEGER, kodi_pathid INTEGER, parent_id INTEGER,
        checksum INTEGER)""")

    jellyfin_tables(cursor)
    jellyfin_tables(cursor)

    assert _columns(cursor)[-2:] == ["jellyfin_parent_id", "sync_checksum"]
