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


class UnauthorizedResponse(FakeResponse):
    status_code = 401

    def raise_for_status(self):
        raise requests.exceptions.HTTPError("401 Client Error: Unauthorized")


class TokenSession(object):
    """Refuses every request whose token is not in `accepted`."""

    def __init__(self, accepted=()):
        self.accepted = accepted
        self.tokens = []

    def get(self, **kwargs):
        token = kwargs["headers"]["Authorization"].split("Token=")[-1]
        self.tokens.append(token)
        if token in self.accepted:
            return FakeResponse()
        return UnauthorizedResponse()


@pytest.fixture
def auth_client(client):
    """A client with a token, whose renewal answers with `renewal.result`."""
    client.config.data.update({"auth.token": "old", "auth.user_id": "user"})
    events = []
    renewal = SimpleNamespace(result=None, calls=[], revoked=0)

    def renew_token(rejected_token):
        renewal.calls.append(rejected_token)
        if renewal.result == "renewed":
            client.config.data["auth.token"] = "new"
        return renewal.result

    def revoke_token():
        renewal.revoked += 1
        client.config.data["auth.token"] = None

    client.client.callback = lambda message, data: events.append(message)
    client.client.auth = SimpleNamespace(
        renew_token=renew_token, revoke_token=revoke_token
    )
    return client, renewal, events


def test_rejected_token_is_renewed_and_the_request_repeated(auth_client):
    client, renewal, events = auth_client
    renewal.result = "renewed"
    session = TokenSession(accepted=["new"])

    client.request({"type": "GET", "handler": "Items"}, session)

    assert session.tokens == ["old", "new"]
    assert renewal.calls == ["old"]
    assert events == []
    assert renewal.revoked == 0


def test_rejected_token_without_saved_password_is_reported(auth_client):
    client, renewal, events = auth_client
    session = TokenSession()

    with pytest.raises(http_module.HTTPException) as error:
        client.request({"type": "GET", "handler": "Items"}, session)

    assert error.value.status == "Unauthorized"
    assert session.tokens == ["old"]
    assert events == ["Unauthorized"]
    assert renewal.revoked == 1


# Nothing for the user to resolve, the saved password signs in again later
def test_disabled_user_is_not_reported_as_unauthorized(auth_client):
    client, renewal, events = auth_client
    renewal.result = "disabled"
    session = TokenSession()

    with pytest.raises(http_module.HTTPException) as error:
        client.request({"type": "GET", "handler": "Items"}, session)

    assert error.value.status == "Unauthorized"
    assert events == []
    assert renewal.revoked == 0
    assert client.config.data["auth.token"] == "old"


def test_renewed_token_is_tried_only_once(auth_client):
    client, renewal, events = auth_client
    renewal.result = "renewed"
    session = TokenSession()

    with pytest.raises(http_module.HTTPException):
        client.request({"type": "GET", "handler": "Items"}, session)

    assert session.tokens == ["old", "new"]
    assert renewal.calls == ["old"]
    assert events == ["Unauthorized"]
