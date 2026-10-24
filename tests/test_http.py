# -*- coding: utf-8 -*-

from datetime import timedelta
from types import SimpleNamespace

import pytest
import requests

from jellyfin_kodi.jellyfin import http as http_module
from jellyfin_kodi.jellyfin.http import HTTP


class FakeResponse(object):
    status_code = 204
    content = b""
    headers = {}
    elapsed = timedelta(0)

    def raise_for_status(self):
        pass

    def json(self):
        raise ValueError("no body")


class FakeSession(object):
    """Fails the first `failures` requests with a connection error."""

    def __init__(self, failures):
        self.failures = failures
        self.methods = []

    def _request(self, method):
        self.methods.append(method)
        if len(self.methods) <= self.failures:
            raise requests.exceptions.ConnectionError("connection reset")
        return FakeResponse()

    def get(self, **kwargs):
        return self._request("GET")

    def post(self, **kwargs):
        return self._request("POST")

    def delete(self, **kwargs):
        return self._request("DELETE")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(http_module.time, "sleep", lambda seconds: None)
    config = SimpleNamespace(
        data={
            "auth.server": "http://server",
            "auth.server-id": "server",
            "http.timeout": 5,
            "http.user_agent": None,
        }
    )
    return HTTP(SimpleNamespace(config=config, callback=lambda *args: None))


@pytest.mark.parametrize("method", ["POST", "DELETE"])
def test_retry_keeps_the_method(client, method):
    session = FakeSession(failures=2)
    client.request({"type": method, "handler": "Users/u/PlayedItems/1"}, session)
    assert session.methods == [method] * 3
