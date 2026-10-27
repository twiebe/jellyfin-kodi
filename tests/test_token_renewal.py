# -*- coding: utf-8 -*-

from types import SimpleNamespace

import pytest

from jellyfin_kodi import connect
from jellyfin_kodi.jellyfin import connection_manager
from jellyfin_kodi.jellyfin.connection_manager import ConnectionManager
from jellyfin_kodi.jellyfin.credentials import Credentials

AUTH = {"AccessToken": "new", "User": {"Id": "user"}, "ServerId": "server"}


class FakeAPI(object):
    """Answers the logins with the given results, a status code or a dict."""

    def __init__(self, *results):
        self.results = list(results)
        self.logins = []
        self.validations = []
        self.validate_status = 401
        self.last_login_status = None

    def login(self, server_url, username, password=""):
        self.logins.append((server_url, username, password))
        result = self.results.pop(0)
        if isinstance(result, dict):
            self.last_login_status = 200
            return result
        self.last_login_status = result
        return {}

    def validate_authentication_token(self, server):
        self.validations.append(server["AccessToken"])
        if isinstance(self.validate_status, Exception):
            raise self.validate_status
        if self.validate_status == 200:
            return {"Id": "server", "ServerName": "Jellyfin"}
        return {"Status_Code": self.validate_status}


@pytest.fixture
def env(monkeypatch):
    properties = {}

    def window(key, value=None, clear=False):
        if clear:
            properties.pop(key, None)
        elif value is not None:
            properties[key] = value
        else:
            return properties.get(key, "")

    notifications = []
    now = [1000.0]
    monkeypatch.setattr(connection_manager, "window", window)
    monkeypatch.setattr(connection_manager, "notify", notifications.append)
    monkeypatch.setattr(connection_manager.time, "time", lambda: now[0])

    server = {
        "Id": "server",
        "address": "http://server",
        "UserId": "user",
        "AccessToken": "old",
        "Username": "tester",
        "Password": "secret",
    }
    manager = ConnectionManager.__new__(ConnectionManager)
    manager.config = SimpleNamespace(data={"auth.token": "old", "auth.user_id": "user"})
    manager.credentials = Credentials()
    manager.credentials.set_credentials({"Servers": [server]})
    manager.server_id = "server"
    manager.API = FakeAPI()
    manager.saved = []
    manager._save_token = manager.saved.append
    return SimpleNamespace(
        manager=manager,
        server=server,
        properties=properties,
        notifications=notifications,
        now=now,
    )


def test_rejected_token_is_renewed_with_saved_password(env):
    env.manager.API = FakeAPI(AUTH)

    assert env.manager.renew_token("old") == "renewed"
    assert env.manager.API.logins == [("http://server", "tester", "secret")]
    assert env.server["AccessToken"] == "new"
    assert env.manager.config.data["auth.token"] == "new"
    assert env.manager.saved == [env.server]
    assert env.notifications == []


def test_no_renewal_without_saved_password(env):
    del env.server["Password"]

    assert env.manager.renew_token("old") is None
    assert env.manager.API.logins == []


def test_token_renewed_elsewhere_is_used_without_signing_in(env):
    env.manager.config.data["auth.token"] = "renewed-by-another-thread"

    assert env.manager.renew_token("old") == "renewed"
    assert env.manager.API.logins == []


def test_changed_password_fails_without_notification(env):
    env.manager.API = FakeAPI(401)

    assert env.manager.renew_token("old") == "failed"
    assert env.notifications == []
    assert env.server["AccessToken"] == "old"


def test_disabled_user_is_announced_once_and_retried_once_a_minute(env):
    env.manager.API = FakeAPI(403, 403, AUTH)

    # Disabled: the server refuses the login with 403
    assert env.manager.renew_token("old") == "disabled"
    assert env.notifications == [34077]

    # No login until the delay passed
    env.now[0] += connection_manager.RENEW_RETRY_DELAY - 1
    assert env.manager.renew_token("old") == "disabled"
    assert len(env.manager.API.logins) == 1

    # Still disabled: tried again, but not announced again
    env.now[0] += 1
    assert env.manager.renew_token("old") == "disabled"
    assert len(env.manager.API.logins) == 2
    assert env.notifications == [34077]

    # Enabled again: signs in and says so
    env.now[0] += connection_manager.RENEW_RETRY_DELAY
    assert env.manager.renew_token("old") == "renewed"
    assert env.notifications == [34077, 34078]
    assert env.properties == {}


def test_websocket_check_renews_a_rejected_token(env):
    env.manager.API = FakeAPI(AUTH)

    assert env.manager.check_token("old") == "renewed"
    assert env.manager.API.validations == ["old"]
    assert env.manager.config.data["auth.token"] == "new"


@pytest.mark.parametrize("status", [200, 500, IOError("unreachable")])
def test_websocket_check_keeps_a_token_the_server_does_not_reject(env, status):
    env.manager.API.validate_status = status

    assert env.manager.check_token("old") is None
    assert env.manager.API.logins == []


def test_websocket_check_runs_once_a_minute(env):
    env.manager.API.validate_status = 200
    env.manager.check_token("old")
    env.manager.check_token("old")
    assert env.manager.API.validations == ["old"]

    env.now[0] += connection_manager.RENEW_RETRY_DELAY
    env.manager.check_token("old")
    assert env.manager.API.validations == ["old", "old"]


def test_websocket_check_needs_a_saved_password(env):
    del env.server["Password"]

    assert env.manager.check_token("old") is None
    assert env.manager.API.validations == []


def test_websocket_check_skips_a_token_renewed_elsewhere(env):
    env.manager.config.data["auth.token"] = "new"

    assert env.manager.check_token("old") == "renewed"
    assert env.manager.API.validations == []


def test_save_password_is_kept_next_to_the_token(env):
    del env.server["Password"]
    env.manager.save_password("tester", "")

    assert env.server["Username"] == "tester"
    assert env.server["Password"] == ""


def test_new_sign_in_forgets_the_saved_password(env):
    env.manager.config.data = {}
    env.manager._save_auth_credentials(AUTH)

    assert "Password" not in env.server
    assert "Username" not in env.server
    assert env.server["AccessToken"] == "new"


@pytest.fixture
def offer(monkeypatch):
    calls = SimpleNamespace(saved=[], questions=[], answer=True, setting=True)
    monkeypatch.setattr(connect, "settings", lambda key: calls.setting)

    def dialog(dialog_type, *args, **kwargs):
        calls.questions.append(args)
        return calls.answer

    monkeypatch.setattr(connect, "dialog", dialog)
    manager = SimpleNamespace(
        save_password=lambda *args: calls.saved.append(args),
    )
    return manager, calls


def test_password_is_saved_when_the_user_agrees(offer):
    manager, calls = offer

    connect.offer_save_password(manager, "tester", "secret")

    assert len(calls.questions) == 1
    assert calls.saved == [("tester", "secret")]


def test_password_is_not_saved_when_the_user_declines(offer):
    manager, calls = offer
    calls.answer = False

    connect.offer_save_password(manager, "tester", "secret")

    assert calls.saved == []


def test_user_without_password_is_not_asked(offer):
    manager, calls = offer

    connect.offer_save_password(manager, "nopass", "")

    assert calls.questions == []
    assert calls.saved == [("nopass", "")]


def test_setting_turns_saving_off(offer):
    manager, calls = offer
    calls.setting = False

    connect.offer_save_password(manager, "tester", "secret")
    connect.offer_save_password(manager, "nopass", "")

    assert calls.questions == []
    assert calls.saved == []
