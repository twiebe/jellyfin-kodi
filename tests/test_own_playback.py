from unittest.mock import Mock

import jellyfin_kodi.library as library_module
from jellyfin_kodi.helper import own_playback
from jellyfin_kodi.library import Library

OWN = {"ItemId": "own", "Played": False, "PlaybackPositionTicks": 0}
LIBRARY_FOLDER = {"ItemId": "folder", "UnplayedItemCount": 2, "PlayedPercentage": 33.3}
OTHER = {"ItemId": "other", "Played": True, "PlaybackPositionTicks": 0}


def _noted(monkeypatch, age=1):
    monkeypatch.setattr(own_playback.time, "time", lambda: 1000 + age)
    props = {}

    def window(key, value=None, clear=False):
        if value is not None:
            props[key] = value
        return props.get(key)

    monkeypatch.setattr(own_playback, "window", window)
    now = own_playback.time.time
    monkeypatch.setattr(own_playback.time, "time", lambda: 1000)
    own_playback.note_own_playback("own")
    monkeypatch.setattr(own_playback.time, "time", now)


def _echo(data, state=(False, False)):
    return own_playback.is_own_echo(data, lambda item_id: state)


def test_the_echo_with_the_library_folder_is_our_own(monkeypatch):
    _noted(monkeypatch)
    assert _echo([OWN, LIBRARY_FOLDER])


def test_another_item_is_not_an_echo(monkeypatch):
    _noted(monkeypatch)
    assert not _echo([OTHER, LIBRARY_FOLDER])
    assert not _echo([OWN, OTHER])


def test_no_playback_noted_is_not_an_echo(monkeypatch):
    monkeypatch.setattr(own_playback, "window", lambda key: None)
    assert not _echo([OWN])


def test_too_late_is_not_an_echo(monkeypatch):
    _noted(monkeypatch, age=own_playback.ECHO_SECONDS + 1)
    assert not _echo([OWN])


def test_a_server_state_kodi_does_not_have_is_not_an_echo(monkeypatch):
    # The server keeps a resume point where Kodi did not, or the other way round: the lists have
    # not seen what the add-on is about to write
    _noted(monkeypatch)
    assert not _echo([dict(OWN, PlaybackPositionTicks=1200000000)])
    assert not _echo([OWN], state=(False, True))
    assert not _echo([dict(OWN, Played=True)])
    assert not _echo([OWN], state=None)


def _library(monkeypatch, echo):
    monkeypatch.setattr(library_module, "is_own_echo", lambda data, state: echo)
    library = Library.__new__(Library)
    library.userdata_queue = Mock()
    library.total_updates = 0
    library.userdata_wants_scan = False
    return library


def test_a_real_change_asks_for_the_scan(monkeypatch):
    library = _library(monkeypatch, echo=False)
    library.userdata([OTHER])
    assert library.userdata_wants_scan
    assert library.userdata_queue.put.called


def test_the_echo_is_written_without_a_scan(monkeypatch):
    library = _library(monkeypatch, echo=True)
    library.userdata([OWN])
    assert not library.userdata_wants_scan
    assert library.userdata_queue.put.called


def test_the_refresh_keeps_a_scan_once_asked_for():
    library = Library.__new__(Library)
    library.pending_scan = False
    library.enable_pending_refresh(scan=False)
    assert library.pending_refresh and not library.pending_scan
    library.enable_pending_refresh()
    library.enable_pending_refresh(scan=False)
    assert library.pending_scan
