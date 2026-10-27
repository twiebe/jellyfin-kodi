# -*- coding: utf-8 -*-

from unittest.mock import Mock

from jellyfin_kodi import monitor as monitor_module
from jellyfin_kodi.monitor import Monitor


class _Timer:
    started = []

    def __init__(self, interval, function):
        self.interval, self.function, self.daemon = interval, function, False

    def start(self):
        _Timer.started.append(self)


def test_stop_does_not_block_the_callback(monkeypatch):
    # Sleeping in onNotification holds up the callbacks of every other add-on
    # (a skin script waiting for the stop) until the sleep is over.
    sleeps = []
    monkeypatch.setattr(monitor_module.xbmc, "sleep", sleeps.append)
    monkeypatch.setattr(monitor_module.threading, "Timer", _Timer)
    _Timer.started = []
    Monitor.__new__(Monitor).onNotification("xbmc", "Player.OnStop", "{}")
    assert sleeps == []
    assert [t.interval for t in _Timer.started] == [3.0]
    assert _Timer.started[0].daemon


def test_stopped_playlist_is_cleared_when_nothing_plays(monkeypatch):
    builtins = []
    monkeypatch.setattr(
        monitor_module.xbmc, "getCondVisibility", lambda condition: True
    )
    monkeypatch.setattr(monitor_module.xbmc, "executebuiltin", builtins.append)
    Monitor.__new__(Monitor)._clear_stopped_playlist()
    assert builtins == ["Playlist.Clear"]


def test_stopped_playlist_is_kept_when_the_next_item_plays(monkeypatch):
    builtins = []
    monkeypatch.setattr(
        monitor_module.xbmc, "getCondVisibility", lambda condition: False
    )
    monkeypatch.setattr(monitor_module.xbmc, "executebuiltin", builtins.append)
    Monitor.__new__(Monitor)._clear_stopped_playlist()
    assert builtins == []


def test_on_play_tells_the_player_it_was_handled(monkeypatch):
    # onPlayBackStarted waits for the playback info of direct paths only until
    # on_play has run, even when on_play fails.
    def on_play(data, server):
        raise ValueError("no item")

    monkeypatch.setattr(monitor_module, "on_play", on_play)
    monkeypatch.setattr(monitor_module, "Jellyfin", lambda *args: Mock())
    monitor = Monitor.__new__(Monitor)
    monitor.player = Mock(on_play_handled=0)
    try:
        monitor.onNotification("xbmc", "Player.OnPlay", "{}")
    except ValueError:
        pass
    assert monitor.player.on_play_handled == 1
