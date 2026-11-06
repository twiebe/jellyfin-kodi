# -*- coding: utf-8 -*-

from unittest.mock import Mock

import pytest

from jellyfin_kodi.objects.actions import Actions

MOVIE = {
    "Id": "abc",
    "Type": "Movie",
    "MediaType": "Video",
    "Name": "A movie",
    "DateCreated": "2026-01-01T00:00:00.000Z",
    "UserData": {},
}


def video_info(db_id):
    """The video info a list item gets for this database id."""
    client = Mock()
    client.config.data = {"auth.server": "http://server", "auth.token": "token"}
    listitem = Mock()
    Actions("server", client).set_listitem(dict(MOVIE), listitem, db_id)
    return listitem.setInfo.call_args[0][1]


def test_no_database_id_for_an_item_outside_the_library():
    # Kodi would store 0 for None, which reads as a library item: the Play button of
    # Nightcity's info page then asks JSON-RPC for movie 0 and nothing plays.
    assert "dbid" not in video_info(None)


@pytest.mark.parametrize("db_id", (0, 7))
def test_database_id_of_a_library_item(db_id):
    assert video_info(db_id)["dbid"] == db_id
