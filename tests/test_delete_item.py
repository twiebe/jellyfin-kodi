# -*- coding: utf-8 -*-
"""A deleted item leaves the Kodi library at once.

The server reports the removal only after its LibraryUpdateDuration (30 s by
default), so the add-on hands the id to the service itself, in the shape of
the server's LibraryChanged message.
"""

import json
from unittest.mock import Mock

import jellyfin_kodi.entrypoint.service as service_module
import jellyfin_kodi.player as player_module
from jellyfin_kodi.entrypoint import context
from jellyfin_kodi.entrypoint.service import Service
from jellyfin_kodi.helper import deletion
from jellyfin_kodi.helper.exceptions import HTTPException

from tests.test_playback_reporting import _stopping_player
from tests.test_playback_callbacks import _item


def _events(monkeypatch):
    sent = []
    monkeypatch.setattr(
        deletion, "event", lambda method, data=None: sent.append((method, data))
    )
    return sent


def test_a_deleted_item_is_handed_to_the_service(monkeypatch):
    sent = _events(monkeypatch)
    api_client = Mock()

    assert deletion.delete_item(api_client, "abc")

    api_client.delete_item.assert_called_once_with("abc")
    assert sent == [
        (
            "LibraryChanged",
            {"ItemsAdded": [], "ItemsUpdated": [], "ItemsRemoved": ["abc"]},
        )
    ]


def test_a_refused_delete_removes_nothing(monkeypatch):
    sent = _events(monkeypatch)
    api_client = Mock()
    api_client.delete_item.side_effect = HTTPException(500, "read-only")

    assert not deletion.delete_item(api_client, "abc")
    assert sent == []


# Only the default server is synced into the Kodi library
def test_an_item_of_another_server_is_not_in_the_library(monkeypatch):
    sent = _events(monkeypatch)
    api_client = Mock()

    assert deletion.delete_item(api_client, "abc", server_id="other")

    api_client.delete_item.assert_called_once_with("abc")
    assert sent == []


def test_the_service_removes_what_was_handed_over(monkeypatch):
    sent = _events(monkeypatch)
    deletion.delete_item(Mock(), "abc")
    method, data = sent[0]

    service = Service.__new__(Service)
    service.library_thread = Mock()
    monkeypatch.setattr(service_module, "window", lambda key: True)
    # What NotifyAll delivers: the event's list, the method behind the sender
    service.onNotification(
        "plugin.video.jellyfin", "Other.%s" % method, json.dumps([data])
    )

    service.library_thread.removed.assert_called_once_with(["abc"])


def _context(monkeypatch, server_id=None):
    obj = context.Context.__new__(context.Context)
    obj.item = {"Id": "abc"}
    obj.server_id = server_id
    obj.api_client = Mock()
    monkeypatch.setattr(context, "settings", lambda key: True)
    calls = []
    monkeypatch.setattr(
        context, "delete_item", lambda *args, **kwargs: calls.append((args, kwargs))
    )
    return obj, calls


def test_the_context_menu_deletes_through_the_handover(monkeypatch):
    obj, calls = _context(monkeypatch)
    obj.delete_item()
    assert calls == [((obj.api_client, "abc"), {"server_id": None})]


def test_the_context_menu_passes_on_the_server(monkeypatch):
    obj, calls = _context(monkeypatch, server_id="other")
    obj.delete_item()
    assert calls == [((obj.api_client, "abc"), {"server_id": "other"})]


def test_delete_after_watching_uses_the_handover(monkeypatch):
    item = _item()
    item["ServerId"] = None
    player = _stopping_player(monkeypatch, item)
    item["Server"].jellyfin.get_item.return_value = {
        "UserData": {"Played": True},
        "Type": "Movie",
    }
    monkeypatch.setattr(player_module, "settings", Mock(return_value=True))
    monkeypatch.setattr(player_module, "dialog", Mock(return_value=True))
    calls = []
    monkeypatch.setattr(
        player_module,
        "delete_item",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    player.stop_playback()

    assert calls == [((item["Server"].jellyfin, "item"), {"server_id": None})]
    assert player.played == {}
