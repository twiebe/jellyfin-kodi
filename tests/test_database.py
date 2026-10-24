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
