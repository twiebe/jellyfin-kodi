# -*- coding: utf-8 -*-

import threading

from jellyfin_kodi.jellyfin import ws_client


class FakeJellyfin(object):
    def __init__(self):
        self.capabilities = []

    def post_capabilities(self, data):
        self.capabilities.append(data)


class FakeClient(object):
    def __init__(self):
        self.jellyfin = FakeJellyfin()


def _open_in_thread(client, ws):
    thread = threading.Thread(target=client.on_open, args=(ws,), daemon=True)
    thread.start()
    return thread


# Kodi waits for every thread of the service before it exits
def test_stop_while_opening_starts_no_keepalive(monkeypatch):
    monkeypatch.setattr(ws_client, "settings", lambda key: False)
    client = ws_client.WSClient(FakeClient())

    opening = _open_in_thread(client, object())
    client.stop_client()
    opening.join(1)

    assert not opening.is_alive()
    assert client.keepalive is None
    assert client.client.jellyfin.capabilities == []


def test_stop_ends_running_keepalive(monkeypatch):
    monkeypatch.setattr(ws_client, "settings", lambda key: False)
    client = ws_client.WSClient(FakeClient())
    # Skip the wait before registering the capabilities
    monkeypatch.setattr(client.stopped, "wait", lambda timeout: False)

    client.on_open(object())
    keepalive = client.keepalive
    assert keepalive.is_alive()

    client.stop_client()
    assert not keepalive.is_alive()


class FakeSocket(object):
    def __init__(self):
        self.calls = []

    def abort(self):
        self.calls.append("abort")


class FakeApp(object):
    def __init__(self):
        self.keep_running = True
        self.sock = FakeSocket()
        self.closed = False

    def close(self):
        self.closed = True


def test_stop_wakes_up_the_reading_thread():
    client = ws_client.WSClient(FakeClient())
    client.wsc = app = FakeApp()
    sock = app.sock

    client.stop_client()

    assert sock.calls == ["abort"]
    assert app.keep_running is False
    assert app.closed


class FakeAuth(object):
    def __init__(self, config):
        self.config = config
        self.checked = []

    def check_token(self, token):
        self.checked.append(token)
        self.config.data["auth.token"] = "new"
        return "renewed"


class AuthClient(FakeClient):
    def __init__(self):
        FakeClient.__init__(self)
        self.config = type("Config", (), {})()
        self.config.data = {
            "app.name": "Kodi",
            "app.device_name": "dev",
            "app.device_id": "id",
            "app.version": "1",
            "auth.token": "old",
        }
        self.auth = FakeAuth(self.config)


# The websocket library asks for the header before every connection attempt
def test_reconnect_after_failed_attempt_checks_the_token(monkeypatch):
    monkeypatch.setattr(ws_client, "settings", lambda key: False)
    client = ws_client.WSClient(AuthClient())

    first = client.get_headers()
    assert 'Token="old"' in first["Authorization"]
    assert client.client.auth.checked == []

    # No on_open in between: the attempt failed, e.g. with 403 Forbidden
    second = client.get_headers()
    assert client.client.auth.checked == ["old"]
    assert 'Token="new"' in second["Authorization"]


def test_reconnect_after_open_connection_does_not_check(monkeypatch):
    monkeypatch.setattr(ws_client, "settings", lambda key: False)
    client = ws_client.WSClient(AuthClient())
    monkeypatch.setattr(client.stopped, "wait", lambda timeout: True)

    client.get_headers()
    client.on_open(object())
    client.get_headers()

    assert client.client.auth.checked == []
