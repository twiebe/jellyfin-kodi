# -*- coding: utf-8 -*-

import pytest

from jellyfin_kodi.helper import api


@pytest.fixture
def settings(monkeypatch):
    values = {
        "compressArt.bool": False,
        "maxArtResolution": "3",
    }
    reads = []

    def fake_settings(key):
        reads.append(key)
        return values[key]

    monkeypatch.setattr(api, "settings", fake_settings)
    api.reset_art_query()
    yield values, reads
    api.reset_art_query()


def test_query_follows_settings(settings):
    values, _ = settings
    assert api.art_query() == "&MaxHeight=720"

    values.update({"compressArt.bool": True})
    values["maxArtResolution"] = "5"
    api.reset_art_query()
    assert api.art_query() == "&Quality=90"


def test_settings_are_read_once(settings):
    _, reads = settings
    for _ in range(100):
        api.art_query()
    assert len(reads) == 2
