# -*- coding: utf-8 -*-

import threading
from unittest.mock import Mock

from jellyfin_kodi import monitor as monitor_module
from jellyfin_kodi.monitor import Monitor

Thread = threading.Thread  # the tests replace threading.Thread


class _Thread:
    """Stands in for threading.Thread and threading.Timer: records what the
    monitor defers, so a test runs it when it chooses."""

    started = []

    def __init__(self, *timer, target=None, args=(), daemon=False):
        self.interval = 0.0
        if timer:  # threading.Timer(interval, function)
            self.interval, target = timer
        self.target, self.args, self.daemon = target, args, daemon

    def start(self):
        _Thread.started.append(self)


class _Kodi:
    """The player and playlists of a fake Kodi, on a clock that counts the
    seconds since the stop. A user action is due at its time; it runs on
    Kodi's main thread before any playlist change the main thread applies
    from then on. That is the order in the logs: the clear looked, found
    nothing playing, and its Playlist.Clear came after the album the user
    started at that moment."""

    def __init__(self, music=(), video=()):
        self.playlists = {0: list(music), 1: list(video)}
        self.position = ""  # Kodi forgets it on a stop from the user
        self.has_media = False
        self.busy = False
        self.clock = 0.0
        self.actions = []  # (time, action) of the user
        self.queued = []  # builtins queued on the main thread
        self.cleared = 0

    def user_action(self, time, action):
        self.actions.append((time, action))

    def run_due(self, clock):
        for due in [due for due in self.actions if due[0] <= clock]:
            self.actions.remove(due)
            due[1]()

    def clear(self):
        self.run_due(self.clock)
        self.playlists = {0: [], 1: []}
        self.cleared += 1

    def execute_builtin(self, builtin, wait=False):
        assert builtin == "Playlist.Clear"
        if wait:
            self.clear()
        else:
            self.queued.append(self.clear)

    def finish(self):
        """The main thread catches up, then the rest of the user's actions."""
        while self.queued:
            self.queued.pop(0)()
        self.run_due(float("inf"))

    def get_cond_visibility(self, condition):
        for name, value in (
            ("Player.HasMedia", self.has_media),
            ("Window.IsVisible(busydialognocancel)", self.busy),
            ("Window.IsVisible(busydialog)", self.busy),
        ):
            condition = condition.replace(name, str(value))
        condition = condition.replace("+", " and ").replace("|", " or ")
        return eval(condition.replace("!", " not "))

    def get_info_label(self, label):
        assert label == "Playlist.Position"
        return self.position

    def start_album(self):
        """What the skin does to play an album: clear, add the songs, open."""
        self.playlists[0] = ["1.mp3", "2.mp3", "3.mp3"]
        self.position = "1"
        self.has_media = True


def _patch(monkeypatch, kodi):
    for name, fake in (
        ("getCondVisibility", kodi.get_cond_visibility),
        ("getInfoLabel", kodi.get_info_label),
        ("executebuiltin", kodi.execute_builtin),
    ):
        monkeypatch.setattr(monitor_module.xbmc, name, fake)
    monkeypatch.setattr(monitor_module.threading, "Thread", _Thread)
    monkeypatch.setattr(monitor_module.threading, "Timer", _Thread)
    _Thread.started = []


def _stop(monkeypatch, kodi, after_stop=()):
    """Stop the playback, deliver the notifications in AFTER_STOP and run
    what the monitor deferred at the time it asked for."""
    _patch(monkeypatch, kodi)
    monitor = Monitor.__new__(Monitor)
    monitor.onNotification("xbmc", "Player.OnStop", '{"end": false}')
    for method in after_stop:
        monitor.onNotification("xbmc", method, '{"playlistid": 0}')
    (thread,) = _Thread.started
    assert thread.daemon
    kodi.clock += thread.interval
    thread.target(*thread.args)
    kodi.finish()


def test_stop_does_not_block_the_callback(monkeypatch):
    # Sleeping in onNotification holds up the callbacks of every other add-on
    # (a skin script waiting for the stop) until the sleep is over.
    sleeps = []
    monkeypatch.setattr(monitor_module.xbmc, "sleep", sleeps.append)
    _patch(monkeypatch, _Kodi())
    Monitor.__new__(Monitor).onNotification("xbmc", "Player.OnStop", "{}")
    assert sleeps == []
    assert len(_Thread.started) == 1
    assert _Thread.started[0].daemon


def test_stopped_playlist_is_cleared(monkeypatch):
    kodi = _Kodi(music=["a.mp3", "b.mp3"], video=["queued.mkv"])
    _stop(monkeypatch, kodi)
    assert kodi.playlists == {0: [], 1: []}


def test_queue_started_after_the_stop_is_kept(monkeypatch):
    # Stop the music, then start an album about 3 s later: only the current
    # song played, the clear of the stopped playlist had emptied the queue.
    kodi = _Kodi(music=["a.mp3", "b.mp3"])
    kodi.user_action(3.0, kodi.start_album)
    _stop(monkeypatch, kodi)
    assert kodi.playlists[0] == ["1.mp3", "2.mp3", "3.mp3"]


def test_playlist_is_kept_when_kodi_plays_another_item_of_it(monkeypatch):
    # Choosing another song of the queue stops the playing one first; Kodi
    # keeps the playlist position then.
    kodi = _Kodi(music=["a.mp3", "b.mp3"])
    kodi.position = "2"
    _stop(monkeypatch, kodi)
    assert kodi.cleared == 0


def test_playlist_is_kept_when_something_plays(monkeypatch):
    kodi = _Kodi(music=["a.mp3", "b.mp3"])
    kodi.has_media = True
    _stop(monkeypatch, kodi)
    assert kodi.cleared == 0


def test_playlist_is_kept_while_kodi_is_busy(monkeypatch):
    # The busy dialog: something resolves the next item to play.
    kodi = _Kodi(music=["a.mp3", "b.mp3"])
    kodi.busy = True
    _stop(monkeypatch, kodi)
    assert kodi.cleared == 0


def test_playlist_is_kept_when_it_changed_after_the_stop(monkeypatch):
    kodi = _Kodi(music=["a.mp3", "b.mp3"])
    _stop(monkeypatch, kodi, ["Playlist.OnClear", "Playlist.OnAdd"])
    assert kodi.cleared == 0


def test_clear_waits_for_a_remote_play_command(monkeypatch):
    # PlayNow stops the playback, then builds its queue item by item: the
    # stop must not clear what it built.
    kodi = _Kodi(music=["a.mp3"])
    _patch(monkeypatch, kodi)
    monitor = Monitor.__new__(Monitor)

    with monitor_module.playlist_lock:
        monitor.onNotification("xbmc", "Player.OnStop", '{"end": false}')
        (deferred,) = _Thread.started
        clear = Thread(target=deferred.target, args=deferred.args)
        clear.start()
        clear.join(0.2)
        assert clear.is_alive()  # waits for the queue
        kodi.start_album()

    clear.join(5)
    assert kodi.playlists[0] == ["1.mp3", "2.mp3", "3.mp3"]


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
