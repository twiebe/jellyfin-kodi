# -*- coding: utf-8 -*-

import pytest

from jellyfin_kodi.helper import wrapper


class FakeDialog(object):
    instances = []

    def __init__(self):
        self.closed = False
        FakeDialog.instances.append(self)

    def create(self, *args):
        pass

    def close(self):
        self.closed = True


class Sync(object):
    @wrapper.progress("Testing")
    def run(self, dialog, fail=False):
        if fail:
            raise ValueError("sync failed")
        return "done"


@pytest.fixture(autouse=True)
def fake_dialog(monkeypatch):
    FakeDialog.instances = []
    monkeypatch.setattr(wrapper.xbmcgui, "DialogProgressBG", FakeDialog)
    monkeypatch.setattr(wrapper, "translate", lambda key: key)


def test_dialog_is_closed():
    assert Sync().run() == "done"
    assert FakeDialog.instances[0].closed


def test_dialog_is_closed_when_the_sync_fails():
    with pytest.raises(ValueError):
        Sync().run(fail=True)
    assert FakeDialog.instances[0].closed
