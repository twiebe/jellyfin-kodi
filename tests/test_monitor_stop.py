# -*- coding: utf-8 -*-

import json
from unittest.mock import Mock

from jellyfin_kodi import monitor as monitor_module
from jellyfin_kodi.monitor import Monitor


class _Thread:
    """Stands in for threading.Thread and threading.Timer: records what the
    monitor defers, so a test runs it at the moment it chooses."""

    started = []

    def __init__(self, *timer, target=None, args=(), daemon=False):
        self.interval = None
        if timer:  # threading.Timer(interval, function)
            self.interval, target = timer
        self.target, self.args, self.daemon = target, args, daemon

    def start(self):
        _Thread.started.append(self)

    def run(self):
        self.target(*self.args)


class _Kodi:
    """The playlists and the player of a fake Kodi. Builtins and JSON-RPC
    playlist calls run on Kodi's main thread: a builtin is queued there and
    the caller goes on, a JSON-RPC call waits until the main thread has run
    everything queued before it and then the call itself."""

    def __init__(self, music=(), video=()):
        self.playlists = {0: list(music), 1: list(video)}
        self.has_media = False
        self.cleared = []
        self.main_thread = []
        self.on_check = None

    def run_main_thread(self):
        while self.main_thread:
            self.main_thread.pop(0)()

    def clear(self, playlist_id):
        self.playlists[playlist_id] = []
        self.cleared.append(playlist_id)

    def execute_builtin(self, builtin):
        assert builtin == "Playlist.Clear"
        self.main_thread.append(lambda: [self.clear(0), self.clear(1)])

    def execute_jsonrpc(self, query):
        self.run_main_thread()
        query = json.loads(query)
        playlist_id = query["params"]["playlistid"]

        if query["method"] == "Playlist.GetItems":
            items = [{"file": path} for path in self.playlists[playlist_id]]
            return json.dumps({"result": {"items": items}})

        assert query["method"] == "Playlist.Clear"
        self.clear(playlist_id)
        return json.dumps({"result": "OK"})

    def get_cond_visibility(self, condition):
        has_media = self.has_media
        if self.on_check:
            self.on_check()
        return not has_media


def _stop(monkeypatch, kodi, during_wait=None):
    """Stop playback and run the clear that the stop schedules, then let
    Kodi's main thread catch up. during_wait runs while the clear waits for
    the player, as a skin setting up its next queue would."""
    monkeypatch.setattr(monitor_module.xbmc, "executeJSONRPC", kodi.execute_jsonrpc)
    monkeypatch.setattr(
        monitor_module.xbmc, "getCondVisibility", kodi.get_cond_visibility
    )
    monkeypatch.setattr(monitor_module.xbmc, "executebuiltin", kodi.execute_builtin)
    monkeypatch.setattr(monitor_module.threading, "Thread", _Thread)
    monkeypatch.setattr(monitor_module.threading, "Timer", _Thread)
    _Thread.started = []
    monitor = Monitor.__new__(Monitor)

    def wait_for_abort(timeout):
        assert timeout == 3.0
        if during_wait:
            during_wait(monitor)
        return False

    monitor.waitForAbort = wait_for_abort
    monitor.onNotification("xbmc", "Player.OnStop", '{"end": false}')
    (thread,) = _Thread.started
    assert thread.daemon
    if thread.interval and during_wait:
        during_wait(monitor)  # a timer waits before it runs
    thread.run()
    kodi.run_main_thread()


def test_stop_does_not_block_the_callback(monkeypatch):
    # Sleeping in onNotification holds up the callbacks of every other add-on
    # (a skin script waiting for the stop) until the sleep is over.
    sleeps = []
    monkeypatch.setattr(monitor_module.xbmc, "sleep", sleeps.append)
    monkeypatch.setattr(monitor_module.threading, "Thread", _Thread)
    monkeypatch.setattr(monitor_module.threading, "Timer", _Thread)
    _Thread.started = []
    Monitor.__new__(Monitor).onNotification("xbmc", "Player.OnStop", "{}")
    assert sleeps == []
    assert len(_Thread.started) == 1
    assert _Thread.started[0].daemon


def test_stopped_playlist_is_cleared_when_nothing_plays(monkeypatch):
    kodi = _Kodi(music=["a.mp3", "b.mp3"], video=["queued.mkv"])
    _stop(monkeypatch, kodi)
    assert kodi.cleared == [0, 1]
    assert kodi.playlists == {0: [], 1: []}


def test_stopped_playlist_is_kept_when_the_next_item_plays(monkeypatch):
    kodi = _Kodi(music=["a.mp3", "b.mp3"])

    def next_item_plays(monitor):
        kodi.has_media = True

    _stop(monkeypatch, kodi, next_item_plays)
    assert kodi.cleared == []


def test_queue_set_up_after_the_stop_is_kept(monkeypatch):
    # Stop the music, then start an album about 3 s later: the skin clears the
    # playlist, adds the songs and opens the player in one go, on Kodi's main
    # thread. If that lands while the clear waits, nothing plays yet when the
    # clear looks, but the queue is new and must stay.
    kodi = _Kodi(music=["a.mp3", "b.mp3"])

    def album_queued(monitor):
        kodi.playlists[0] = ["1.mp3", "2.mp3", "3.mp3"]

    _stop(monkeypatch, kodi, album_queued)
    assert kodi.playlists[0] == ["1.mp3", "2.mp3", "3.mp3"]
    assert kodi.cleared == []


def test_queue_set_up_while_the_clear_looks_is_kept(monkeypatch):
    # The order in the logs: the clear finds nothing playing, the skin's album
    # (clear, add the songs, open the player) runs on Kodi's main thread right
    # then, and the clear lands after it and empties the new queue.
    kodi = _Kodi(music=["a.mp3", "b.mp3"])

    def album_started():
        def on_main_thread():
            kodi.playlists[0] = ["1.mp3", "2.mp3", "3.mp3"]
            kodi.has_media = True

        kodi.on_check = None
        kodi.main_thread.append(on_main_thread)

    kodi.on_check = album_started
    _stop(monkeypatch, kodi)
    assert kodi.playlists[0] == ["1.mp3", "2.mp3", "3.mp3"]
    assert kodi.cleared == []


def test_queue_rebuilt_with_the_same_items_after_the_stop_is_kept(monkeypatch):
    # The same album again: the items match the stopped ones, but Kodi
    # announced the new queue after the stop.
    kodi = _Kodi(music=["a.mp3", "b.mp3"])

    def album_queued_again(monitor):
        monitor.onNotification("xbmc", "Playlist.OnClear", '{"playlistid": 0}')
        for position in range(2):
            monitor.onNotification(
                "xbmc",
                "Playlist.OnAdd",
                json.dumps({"playlistid": 0, "position": position}),
            )

    _stop(monkeypatch, kodi, album_queued_again)
    assert kodi.cleared == []


def test_only_the_playlist_left_by_the_stop_is_cleared(monkeypatch):
    # A video queue set up after the music stopped stays; the stopped music
    # playlist goes.
    kodi = _Kodi(music=["a.mp3"])

    def videos_queued(monitor):
        kodi.playlists[1] = ["one.mkv", "two.mkv"]

    _stop(monkeypatch, kodi, videos_queued)
    assert kodi.playlists == {0: [], 1: ["one.mkv", "two.mkv"]}


def test_clear_is_dropped_when_kodi_shuts_down(monkeypatch):
    kodi = _Kodi(music=["a.mp3"])
    monkeypatch.setattr(Monitor, "waitForAbort", lambda self, timeout: True)
    monkeypatch.setattr(monitor_module.threading, "Thread", _Thread)
    monkeypatch.setattr(monitor_module.threading, "Timer", _Thread)
    monkeypatch.setattr(monitor_module.xbmc, "executeJSONRPC", kodi.execute_jsonrpc)
    _Thread.started = []
    Monitor.__new__(Monitor).onNotification("xbmc", "Player.OnStop", "{}")
    _Thread.started[0].run()
    assert kodi.cleared == []


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
