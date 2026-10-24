# -*- coding: utf-8 -*-

import sqlite3

from jellyfin_kodi.jellyfin.utils import sqlite_namedtuple_factory


def _cursor():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite_namedtuple_factory
    return conn.cursor()


def test_rows_have_named_fields():
    row = _cursor().execute("SELECT 1 AS a, 'x' AS b").fetchone()
    assert (row.a, row.b) == (1, "x")
    assert row == (1, "x")


def test_queries_with_other_columns_get_other_rows():
    cursor = _cursor()
    first = cursor.execute("SELECT 1 AS a").fetchone()
    second = cursor.execute("SELECT 2 AS b, 3 AS c").fetchone()
    assert first._fields == ("a",)
    assert second._fields == ("b", "c")
    assert cursor.execute("SELECT 4 AS a").fetchone().a == 4
