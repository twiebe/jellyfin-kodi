# -*- coding: utf-8 -*-

import sqlite3

from jellyfin_kodi.database import jellyfin_tables


def _columns(cursor):
    return [row[1] for row in cursor.execute("PRAGMA table_info(jellyfin)")]


def test_sync_checksum_column_is_added_to_old_databases():
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE jellyfin(
        jellyfin_id TEXT UNIQUE, media_folder TEXT, jellyfin_type TEXT, media_type TEXT,
        kodi_id INTEGER, kodi_fileid INTEGER, kodi_pathid INTEGER, parent_id INTEGER,
        checksum INTEGER)""")

    jellyfin_tables(cursor)
    jellyfin_tables(cursor)

    assert _columns(cursor)[-2:] == ["jellyfin_parent_id", "sync_checksum"]
