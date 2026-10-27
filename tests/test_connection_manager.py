# -*- coding: utf-8 -*-

from types import SimpleNamespace

import pytest

from jellyfin_kodi.jellyfin.credentials import Credentials
from jellyfin_kodi.jellyfin.connection_manager import (
    CONNECTION_STATE,
    ConnectionManager,
)


def _connect(status_code):
    """Validate a saved login while system/info answers with status_code."""
    manager = ConnectionManager.__new__(ConnectionManager)
    manager.config = SimpleNamespace(data={})
    manager.API = SimpleNamespace(
        validate_authentication_token=lambda server: {"Status_Code": status_code}
    )
    server = {"Id": "server", "UserId": "user", "AccessToken": "token"}
    public_info = {"Id": "server", "ServerName": "Jellyfin"}
    state = manager._after_connect_validated(
        server, {"Servers": [server]}, public_info, True, {}
    )
    return state, server


def test_rejected_token_is_dropped():
    state, server = _connect(401)
    assert state["State"] == CONNECTION_STATE["Unavailable"]
    assert state["Status_Code"] == 401
    assert server["AccessToken"] is None
    assert server["UserId"] is None


# Server errors and an access schedule (403) say nothing about the token;
# dropping it forces the user to sign in again.
@pytest.mark.parametrize("status_code", [403, 500, 502, 503])
def test_token_survives_other_errors(status_code):
    state, server = _connect(status_code)
    assert state["State"] == CONNECTION_STATE["Unavailable"]
    assert state["Status_Code"] == status_code
    assert server["AccessToken"] == "token"
    assert server["UserId"] == "user"


class RenewingManager(ConnectionManager):
    def __init__(self, renewal):
        self.config = SimpleNamespace(data={"auth.ssl": False})
        self.credentials = Credentials()
        self.renewal = renewal
        self.renewed = []
        self.tokens = []

        def validate(server):
            self.tokens.append(server["AccessToken"])
            if server["AccessToken"] == "new":
                return {"Id": "server", "ServerName": "Jellyfin"}
            return {"Status_Code": 401}

        self.API = SimpleNamespace(validate_authentication_token=validate)

    def renew_token(self, rejected_token, server=None):
        self.renewed.append(rejected_token)
        if self.renewal == "renewed":
            server["AccessToken"] = "new"
        return self.renewal


def _connect_saved_password(renewal):
    manager = RenewingManager(renewal)
    server = {
        "Id": "server",
        "UserId": "user",
        "AccessToken": "old",
        "address": "http://server",
        "Username": "tester",
        "Password": "secret",
    }
    credentials = {"Servers": [server]}
    manager.credentials.set_credentials(credentials)
    public_info = {"Id": "server", "ServerName": "Jellyfin"}
    state = manager._after_connect_validated(server, credentials, public_info, True, {})
    return manager, state, server


def test_rejected_token_at_start_is_renewed_with_saved_password():
    manager, state, server = _connect_saved_password("renewed")
    assert manager.renewed == ["old"]
    assert manager.tokens == ["old", "new"]
    assert state["State"] == CONNECTION_STATE["SignedIn"]
    assert manager.config.data["auth.token"] == "new"


# The service tries again later, without asking the user to sign in
def test_disabled_user_at_start_keeps_the_login():
    manager, state, server = _connect_saved_password("disabled")
    assert state["State"] == CONNECTION_STATE["Unavailable"]
    assert state["TokenRenewal"] == "disabled"
    assert server["AccessToken"] == "old"


@pytest.mark.parametrize("renewal", ["failed", None])
def test_failed_renewal_at_start_asks_to_sign_in(renewal):
    manager, state, server = _connect_saved_password(renewal)
    assert state["State"] == CONNECTION_STATE["Unavailable"]
    assert state["Status_Code"] == 401
    assert server["AccessToken"] is None
