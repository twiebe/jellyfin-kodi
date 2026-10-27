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


class _SkipDialog:
    def __init__(self, *args):
        self.shown = False
        self.closed = False
        self.skip = False
        self.cancel = False

    def set_skip_info(self, segment_type, duration):
        pass

    def show(self):
        self.shown = True

    def close(self):
        self.closed = True

    def is_skip(self):
        return self.skip

    def is_cancel(self):
        return self.cancel


def _segment_player(monkeypatch, position):
    player = player_module.Player()
    player.getTime = Mock(return_value=position)
    player.getTotalTime = Mock(return_value=0)
    player.seekTime = Mock()
    player.skip_dialog = None
    player.skip_prompted = set()
    monitor = Mock()
    monitor.waitForAbort.return_value = False
    monkeypatch.setattr(player_module.xbmc, "Monitor", Mock(return_value=monitor))
    return player, monitor


def test_skip_button_is_shown_without_waiting(monkeypatch):
    # Waiting for the user until the segment ends blocked the segment checker,
    # or a player callback for the whole intro.
    import jellyfin_kodi.dialogs.skip as skip_module

    monkeypatch.setattr(skip_module, "SkipDialog", _SkipDialog)
    monkeypatch.setattr(player_module, "settings", Mock(return_value=2))
    player, monitor = _segment_player(monkeypatch, 11)
    player.skip_segments = {
        "item": {"aa1": {"Type": "Introduction", "Start": 10, "End": 20}}
    }

    player.check_skip_segments({"Id": "item"}, 11)

    monitor.waitForAbort.assert_not_called()
    assert player.skip_dialog.shown
    assert not player.skip_dialog.closed


def test_skip_dialog_seeks_when_skip_is_clicked(monkeypatch):
    player, monitor = _segment_player(monkeypatch, 12)
    skip_dialog = player.skip_dialog = _SkipDialog()
    player._skip_end_time = 20.0
    skip_dialog.skip = True

    player.update_skip_dialog()

    player.seekTime.assert_called_once_with(20.0)
    assert skip_dialog.closed
    assert player.skip_dialog is None


def test_skip_dialog_closes_when_cancelled(monkeypatch):
    player, monitor = _segment_player(monkeypatch, 12)
    skip_dialog = player.skip_dialog = _SkipDialog()
    player._skip_end_time = 20.0
    skip_dialog.cancel = True

    player.update_skip_dialog()

    player.seekTime.assert_not_called()
    assert player.skip_dialog is None


def test_skip_dialog_closes_once_the_segment_ended(monkeypatch):
    player, monitor = _segment_player(monkeypatch, 20.5)
    skip_dialog = player.skip_dialog = _SkipDialog()
    player._skip_end_time = 20.0

    player.update_skip_dialog()

    player.seekTime.assert_not_called()
    assert skip_dialog.closed
    assert player.skip_dialog is None


def test_skip_dialog_stays_open_within_the_segment(monkeypatch):
    player, monitor = _segment_player(monkeypatch, 15)
    skip_dialog = player.skip_dialog = _SkipDialog()
    player._skip_end_time = 20.0

    player.update_skip_dialog()

    assert not skip_dialog.closed
    assert player.skip_dialog is skip_dialog


def test_seek_only_wakes_the_segment_checker(monkeypatch):
    player, monitor = _segment_player(monkeypatch, 15)
    player.played = {"movie": _item()}
    player.getPlayingFile = Mock(return_value="movie")
    player.report_playback = Mock()
    player.check_skip_segments = Mock()
    player.segment_checker = Mock()
    monkeypatch.setattr(player_module, "settings", Mock(return_value=True))

    player.onPlayBackSeek(15000, 5000)

    player.check_skip_segments.assert_not_called()
    player.segment_checker.wake.assert_called_once_with()


def test_started_leaves_the_segments_to_the_checker(monkeypatch):
    item = _item()
    player, monitor, checkers = _player(monkeypatch, [[item]])
    monkeypatch.setattr(player_module, "settings", Mock(return_value=True))
    player._fetch_skip_segments = Mock()
    player.check_skip_segments = Mock()

    player.onPlayBackStarted()

    player._fetch_skip_segments.assert_called_once_with(item)
    player.check_skip_segments.assert_not_called()
    assert checkers[0].started


def _run_checker(monkeypatch, sleeps_until_stop, on_sleep=None):
    player = Mock()
    player.isPlaying.return_value = True
    player.get_playing_file.return_value = "movie"
    player.is_playing_file.return_value = True
    player.getTime.return_value = 5
    checker = segments_module.SegmentChecker(player)
    sleeps = []

    def sleep(ms):
        sleeps.append(ms)
        if on_sleep:
            on_sleep(checker, len(sleeps))
        if len(sleeps) >= sleeps_until_stop:
            checker.stop()

    monkeypatch.setattr(segments_module.xbmc, "sleep", sleep)
    monkeypatch.setattr(
        segments_module.xbmc,
        "Monitor",
        Mock(return_value=Mock(abortRequested=Mock(return_value=False))),
    )
    monkeypatch.setattr(segments_module, "settings", lambda key: True)
    checker.run()
    return player, sleeps


def test_segment_checker_checks_every_second_and_polls_the_dialog(monkeypatch):
    player, sleeps = _run_checker(monkeypatch, 10)

    assert sum(sleeps) == 2000
    assert player.check_skip_segments.call_count == 2
    assert player.update_skip_dialog.call_count == 10


def test_segment_checker_checks_at_once_when_woken(monkeypatch):
    def wake_after_seek(checker, sleeps):
        if sleeps == 2:
            checker.wake()

    player, sleeps = _run_checker(monkeypatch, 5, wake_after_seek)

    assert player.check_skip_segments.call_count == 2


def _stop_on_wait(number):
    """Run onPlayBackStopped nested in the given waitForAbort, as Kodi does."""
    waits = []

    def wait(player):
        waits.append(1)
        if len(waits) == number:
            player.onPlayBackStopped()

    return wait


def test_stop_while_waiting_for_the_item_aborts_started(monkeypatch):
    item = _item()
    player, monitor, checkers = _player(
        monkeypatch, [None, [item]], direct_paths=True, waits=_stop_on_wait(1)
    )

    player.onPlayBackStarted()

    player.set_item.assert_not_called()
    item["Server"].jellyfin.session_playing.assert_not_called()
    assert checkers == []


def test_stop_while_waiting_to_set_the_streams_aborts_started(monkeypatch):
    item = _item()
    item["PlayOption"] = "Addon"
    player, monitor, checkers = _player(monkeypatch, [[item]], waits=_stop_on_wait(1))

    player.onPlayBackStarted()

    player.set_audio_subs.assert_not_called()


def test_next_started_while_waiting_aborts_the_previous_started(monkeypatch):
    first, second = _item(), _item()
    first["PlayOption"] = second["PlayOption"] = "Addon"
    second["AudioStreamIndex"] = 2
    nested = []

    def start_next(player):
        if not nested:
            nested.append(1)
            player.onPlayBackStarted()

    player, monitor, checkers = _player(
        monkeypatch, [[first], [second]], waits=start_next
    )

    player.onPlayBackStarted()

    player.set_audio_subs.assert_called_once_with(2, None)
