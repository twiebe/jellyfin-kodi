# -*- coding: utf-8 -*-

import pytest

from jellyfin_kodi.entrypoint import context
from jellyfin_kodi.helper.exceptions import HTTPException


class FakeApi(object):
    def __init__(self, playlists, contains=(), refuse=()):
        self.playlists = playlists
        self.contains = contains
        self.refuse = refuse
        self.added = []

    def get_playlists(self):
        return {"Items": self.playlists}

    def is_in_playlist(self, playlist_id, item_id):
        return playlist_id in self.contains

    def add_to_playlist(self, playlist_id, item_id):
        if playlist_id in self.refuse:
            raise HTTPException(403, "Forbidden")
        self.added.append((playlist_id, item_id))


@pytest.fixture
def menu(monkeypatch):
    calls = []
    answers = {}

    def fake_dialog(dialog_type, *args, **kwargs):
        calls.append((dialog_type, args, kwargs))
        return answers.get(dialog_type)

    monkeypatch.setattr(context, "dialog", fake_dialog)
    monkeypatch.setattr(context, "translate", lambda string_id: "%s {0}" % string_id)

    def make(item_type, api):
        obj = context.Context.__new__(context.Context)
        obj.item = {"Id": "item", "Type": item_type, "UserData": {}}
        obj.api_client = api
        return obj

    return make, calls, answers


PLAYLISTS = [
    {"Id": "p1", "Name": "Evening", "MediaType": "Video"},
    {"Id": "p2", "Name": "Songs", "MediaType": "Audio"},
    {"Id": "p3", "Name": "New", "MediaType": "Unknown"},
    {"Id": "p4", "Name": "Old server"},
]


def test_offers_only_playlists_of_the_same_media(menu):
    make, calls, _ = menu
    make("Movie", FakeApi(PLAYLISTS)).add_to_playlists()

    dialog_type, args, _ = calls[0]
    assert dialog_type == "multi"
    assert args[1] == ["Evening", "New", "Old server"]


def test_adds_to_every_chosen_playlist(menu):
    make, calls, answers = menu
    api = FakeApi(PLAYLISTS)
    answers["multi"] = [0, 2]

    make("Movie", api).add_to_playlists()

    assert api.added == [("p1", "item"), ("p4", "item")]
    assert calls[-1][2]["message"] == "30416 Evening, Old server"


def test_skips_playlists_that_hold_the_item_and_reports_failures(menu):
    make, calls, answers = menu
    api = FakeApi(PLAYLISTS, contains=("p1",), refuse=("p4",))
    answers["multi"] = [0, 1, 2]

    make("Episode", api).add_to_playlists()

    assert api.added == [("p3", "item")]
    assert calls[-1][2]["message"] == "30416 New\n30417 Evening\n30418 Old server"


def test_cancelled_selection_adds_nothing(menu):
    make, calls, answers = menu
    api = FakeApi(PLAYLISTS)
    answers["multi"] = None

    make("Movie", api).add_to_playlists()

    assert api.added == []
    assert [call[0] for call in calls] == ["multi"]


def test_without_matching_playlist_says_so(menu):
    make, calls, _ = menu
    make("Audio", FakeApi(PLAYLISTS[:1])).add_to_playlists()

    assert [call[0] for call in calls] == ["ok"]
