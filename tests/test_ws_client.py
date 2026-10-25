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
