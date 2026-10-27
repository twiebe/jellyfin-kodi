# -*- coding: utf-8 -*-
from unittest.mock import Mock

import jellyfin_kodi.player as player_module
import jellyfin_kodi.segments as segments_module
from jellyfin_kodi.jellyfin import ws_client

from tests.test_playback_callbacks import _item, _segment_player, _SkipDialog


def _stopping_player(monkeypatch, item):
    player = object.__new__(player_module.Player)
    player.played = {"movie": item}
    player._reset_state = Mock()
    monkeypatch.setattr(player_module, "window", Mock(return_value=None))
    monkeypatch.setattr(player_module, "settings", Mock(return_value=False))
    monkeypatch.setattr(player_module.xbmcvfs, "exists", Mock(return_value=False))
    item["Server"].jellyfin.get_item.return_value = {}
    return player


def _stop_ticks(item):
    return item["Server"].jellyfin.session_stop.call_args.args[0]["PositionTicks"]


# The 10 second progress report lagged behind, stop sent a position up to 10 s old
def test_stop_reports_the_last_tracked_position(monkeypatch):
    item = _item()
    item["CurrentPosition"] = 215
    player = _stopping_player(monkeypatch, item)
    player.getPlayingFile = Mock(return_value="movie")
    player.getTime = Mock(return_value=221.9)

    player.track_position()
    player.stop_playback()

    assert _stop_ticks(item) == 2219000000


def test_stop_reports_the_current_position_without_tracking(monkeypatch):
    item = _item()
    item["CurrentPosition"] = 215
    player = _stopping_player(monkeypatch, item)

    player.stop_playback()

    assert _stop_ticks(item) == 2150000000


def test_a_progress_report_updates_the_tracked_position(monkeypatch):
    # A seek reports at once, a stop right after must not send the old position
    item = _item()
    player = _stopping_player(monkeypatch, item)
    player.getPlayingFile = Mock(return_value="movie")
    player.getTime = Mock(return_value=100.0)
    player.track_position()
    player.getTime = Mock(return_value=600.0)
    player.detect_audio_subs = Mock()
    monkeypatch.setattr(
        player_module, "JSONRPC", Mock(return_value=Mock(execute=Mock(return_value={})))
    )

    player.report_playback()
    player.stop_playback()

    assert _stop_ticks(item) == 6000000000


def test_track_position_ignores_files_of_other_addons(monkeypatch):
    item = _item()
    player = _stopping_player(monkeypatch, item)
    player.getPlayingFile = Mock(return_value="other")
    player.getTime = Mock(return_value=50.0)

    player.track_position()

    assert "LastKnownPosition" not in item


def test_segment_checker_tracks_the_position_without_segments(monkeypatch):
    player = Mock()
    player.isPlaying.return_value = True
    monkeypatch.setattr(segments_module, "settings", lambda key: False)

    segments_module.SegmentChecker(player).check_segments()

    player.track_position.assert_called_once_with()


def test_skip_dialog_closes_after_seeking_before_the_segment(monkeypatch):
    player, monitor = _segment_player(monkeypatch, 5)
    skip_dialog = player.skip_dialog = _SkipDialog()
    player._skip_start_time = 10.0
    player._skip_end_time = 20.0

    player.update_skip_dialog()

    player.seekTime.assert_not_called()
    assert skip_dialog.closed
    assert player.skip_dialog is None


def test_skip_button_remembers_the_segment_start(monkeypatch):
    import jellyfin_kodi.dialogs.skip as skip_module

    monkeypatch.setattr(skip_module, "SkipDialog", _SkipDialog)
    monkeypatch.setattr(player_module, "settings", Mock(return_value=2))
    player, monitor = _segment_player(monkeypatch, 11)
    player.skip_segments = {
        "item": {"aa1": {"Type": "Introduction", "Start": 10, "End": 20}}
    }

    player.check_skip_segments({"Id": "item"}, 11)
    player.getTime = Mock(return_value=12)
    player.update_skip_dialog()

    assert player._skip_start_time == 10
    assert not player.skip_dialog.closed


# Player.OnAVChange arrives after the stop and logged a traceback
def test_playing_file_after_stop_logs_no_traceback(monkeypatch):
    player = object.__new__(player_module.Player)
    player.getPlayingFile = Mock(
        side_effect=RuntimeError("Kodi is not playing any file")
    )
    log = Mock()
    monkeypatch.setattr(player_module, "LOG", log)

    assert player.get_playing_file() is None
    log.exception.assert_not_called()


class _ClosedSocket(object):
    def __init__(self):
        self.sent = 0

    def send(self, message):
        self.sent += 1
        raise ws_client.websocket.WebSocketConnectionClosedException(
            "socket is already closed."
        )


# The connection closed by the server killed the keepalive thread with a traceback
def test_keepalive_ends_quietly_when_the_connection_closed(monkeypatch):
    log = Mock()
    monkeypatch.setattr(ws_client, "LOG", log)
    sock = _ClosedSocket()
    keepalive = ws_client.KeepAlive(None, sock)
    monkeypatch.setattr(keepalive.halt, "wait", lambda timeout: False)

    keepalive.run()

    assert sock.sent == 1
    log.exception.assert_not_called()
