# -*- coding: utf-8 -*-

from types import SimpleNamespace

from jellyfin_kodi import connect
from jellyfin_kodi.jellyfin.configuration import Config


# "Update password" and "Add server" use the running default client: it must
# stay the default one, or the websocket marks its messages as coming from
# another server and the service ignores them (no more library updates)
def test_get_client_keeps_the_default_client(monkeypatch):
    client = SimpleNamespace(config=Config())
    client.config.data["app.default"] = True
    monkeypatch.setattr(connect, "Jellyfin", lambda server_id: client)
    monkeypatch.setattr(connect, "settings", lambda key: True)
    connector = connect.Connect.__new__(connect.Connect)
    connector.info = {"Version": "1", "DeviceName": "dev", "DeviceId": "id"}

    assert connector.get_client() is client
    assert client.config.data["app.default"] is True
