# -*- coding: utf-8 -*-
from unittest.mock import Mock

import jellyfin_kodi.player as player_module
import jellyfin_kodi.segments as segments_module


def _item():
    return {
        "Id": "item",
        "Path": "movie",
        "PlayOption": "Native",
        "KodiAudioStreamIndexes": [],
        "SubsMapping": {},
        "AudioStreamIndex": None,
        "SubtitleStreamIndex": None,
        "MediaSourceId": "source",
        "PlayMethod": "DirectPlay",
        "Volume": 100,
        "CurrentPosition": 0,
        "Paused": False,
        "Muted": False,
        "PlaySessionId": "session",
        "Server": Mock(),
    }


def _player(monkeypatch, plays, direct_paths=False, waits=None):
    """A Player whose onPlayBackStarted runs without Kodi.

    plays: what window("jellyfin_play.json") returns, one value per call.
    waits: called for every waitForAbort, to run "nested" callbacks.
    """
    player = object.__new__(player_module.Player)
    player.played = {}
    player.stop_playback = Mock()
    player.getPlayingFile = Mock(return_value="movie")
    player.isPlayingAudio = Mock(return_value=False)
    player.getTime = Mock(return_value=0)
    player.set_audio_subs = Mock()
    player.detect_audio_subs = Mock()

    def set_item(file, item):
        player.played[file] = item

    player.set_item = Mock(side_effect=set_item)

    monitor = Mock()

    def wait_for_abort(timeout=None):
        if waits:
            waits(player)
        return False

    monitor.waitForAbort = Mock(side_effect=wait_for_abort)
    monkeypatch.setattr(player_module.xbmc, "Monitor", Mock(return_value=monitor))

    def fake_settings(key, value=None):
        if key == "useDirectPaths":
            return "1" if direct_paths else "0"
        return False

    monkeypatch.setattr(player_module, "settings", fake_settings)

    plays = list(plays)

    def fake_window(name, value=None, **kwargs):
        if name == "jellyfin_play.json" and value is None:
            return plays.pop(0) if len(plays) > 1 else plays[0]
        return None

    monkeypatch.setattr(player_module, "window", fake_window)

    checkers = []

    class Checker:
        def __init__(self, player):
            self.started = False
            self.played_at_start = None
            checkers.append(self)

        def start(self):
            self.started = True
            self.played_at_start = dict(player.played)

        def stop(self):
            self.started = False

        def wake(self):
            pass

    monkeypatch.setattr(player_module, "SegmentChecker", Checker)

    return player, monitor, checkers


def test_started_returns_at_once_for_playback_of_other_addons(monkeypatch):
    # Without the jellyfin_play property, add-on paths cannot be a Jellyfin
    # item. Waiting for it in the callback stalls the service loop 40 seconds.
    player, monitor, checkers = _player(monkeypatch, [None])

    player.onPlayBackStarted()

    monitor.waitForAbort.assert_not_called()
    player.set_item.assert_not_called()
    assert checkers == []


def test_started_stops_waiting_once_on_play_found_no_item(monkeypatch):
    # With direct paths, on_play sets the property from the Player.OnPlay
    # notification, which Kodi runs during the first wait.
    def on_play(player):
        player.on_play_handled += 1

    player, monitor, checkers = _player(
        monkeypatch, [None], direct_paths=True, waits=on_play
    )

    player.onPlayBackStarted()

    assert monitor.waitForAbort.call_count == 1
    player.set_item.assert_not_called()
    assert checkers == []


def test_started_waits_for_the_direct_path_item(monkeypatch):
    item = _item()
    player, monitor, checkers = _player(monkeypatch, [None, [item]], direct_paths=True)

    player.onPlayBackStarted()

    player.set_item.assert_called_once_with("movie", item)


def test_segment_checker_starts_once_the_item_is_set(monkeypatch):
    item = _item()
    player, monitor, checkers = _player(monkeypatch, [[item]])

    player.onPlayBackStarted()

    assert len(checkers) == 1
    assert checkers[0].started
    assert "movie" in checkers[0].played_at_start


def test_segment_checker_logs_not_yet_playing_once(monkeypatch):
    player = Mock()
    player.isPlaying.return_value = True
    player.get_playing_file.return_value = "other"
    player.is_playing_file.return_value = False
    player.skip_dialog = None
    checker = segments_module.SegmentChecker(player)

    sleeps = []

    def sleep(ms):
        sleeps.append(ms)
        if sum(sleeps) >= 5000:
            checker.stop()

    log = Mock()
    monkeypatch.setattr(segments_module, "LOG", log)
    monkeypatch.setattr(segments_module.xbmc, "sleep", sleep)
    monkeypatch.setattr(
        segments_module.xbmc,
        "Monitor",
        Mock(return_value=Mock(abortRequested=Mock(return_value=False))),
    )
    monkeypatch.setattr(segments_module, "settings", lambda key: True)

    checker.run()

    not_playing = [
        call for call in log.info.call_args_list if "not yet playing" in call.args[0]
    ]
    assert len(not_playing) == 1
