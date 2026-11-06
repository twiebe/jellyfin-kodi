# -*- coding: utf-8 -*-

import sys
from unittest.mock import patch

# The module reads Kodi's plugin arguments on import.
with patch.object(sys, "argv", ["plugin://plugin.video.jellyfin/", "1", ""]):
    from jellyfin_kodi.entrypoint import default


class FakeClient(object):
    class jellyfin(object):
        class config(object):
            data = {}  # no app.session: only the service knows the session


class FakeJellyfin(object):
    def __init__(self, server_id=None):
        self.server_id = server_id

    def get_client(self):
        return FakeClient


def run_events(monkeypatch, query):
    events = []
    monkeypatch.setattr(default, "Jellyfin", FakeJellyfin)
    monkeypatch.setattr(default, "QUERY_STRING", query)
    monkeypatch.setattr(
        default, "event", lambda method, data=None: events.append((method, data))
    )
    default.Events()
    return events


def test_playlist_mode_leaves_the_session_to_the_service(monkeypatch):
    assert run_events(monkeypatch, "?mode=playlist&id=abc&server=None") == [
        ("PlayPlaylist", {"Id": "abc", "ServerId": None})
    ]


def test_playlist_mode_names_the_server(monkeypatch):
    assert run_events(monkeypatch, "?mode=playlist&id=abc&server=s1") == [
        ("PlayPlaylist", {"Id": "abc", "ServerId": "s1"})
    ]


def test_play_path_has_no_slash_before_the_query():
    # A synced show makes the add-on's root a tvshows path, and Kodi then ignores
    # the info action on anything below it.
    assert default.play_path("abc", "s1") == (
        "plugin://plugin.video.jellyfin?id=abc&mode=play&server=s1"
    )


class FakeListItem(object):
    def __init__(self):
        self.properties = {"IsPlayable": "true"}

    def setProperty(self, key, value):
        self.properties[key] = value


def listed(monkeypatch, item_type, window):
    monkeypatch.setattr(default.xbmcgui, "getCurrentWindowId", lambda: window)
    li = FakeListItem()
    default.set_click_path({"Id": "abc", "Type": item_type}, li, "s1")
    return li.properties


def test_track_in_the_videos_window_starts_the_plugin(monkeypatch):
    # Kodi has no info page for it there: with "select" set to show information,
    # a click on a playable track did nothing.
    assert listed(monkeypatch, "Audio", 10025) == {
        "IsPlayable": "false",
        "path": "plugin://plugin.video.jellyfin/?mode=playlist&id=abc&server=s1",
    }


def test_track_in_the_music_window_stays_playable(monkeypatch):
    assert listed(monkeypatch, "Audio", 10502) == {
        "IsPlayable": "true",
        "path": "plugin://plugin.video.jellyfin?id=abc&mode=play&server=s1",
    }


def test_video_in_the_videos_window_stays_playable(monkeypatch):
    assert listed(monkeypatch, "Movie", 10025) == {
        "IsPlayable": "true",
        "path": "plugin://plugin.video.jellyfin?id=abc&mode=play&server=s1",
    }
