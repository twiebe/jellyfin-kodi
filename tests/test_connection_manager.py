# -*- coding: utf-8 -*-

from types import SimpleNamespace

import pytest

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
