# -*- coding: utf-8 -*-

import xbmc

from jellyfin_kodi import downloader
from jellyfin_kodi.helper import wrapper


def test_page_size_above_50(monkeypatch):
    # The settings allow up to 100 items per request
    requested = []

    def fake_get(handler, params=None, server_id=None):
        if params.get("EnableTotalRecordCount"):
            return {"TotalRecordCount": 100}
        requested.append((params["StartIndex"], params["Limit"]))
        return {"Items": [{"Id": params["StartIndex"]}]}

    monkeypatch.setattr(downloader, "_get", fake_get)
    monkeypatch.setattr(xbmc.Monitor, "waitForAbort", lambda self, timeout=0: False)
    monkeypatch.setattr(wrapper, "window", lambda key: key == "jellyfin_online.bool")
    monkeypatch.setattr(
        downloader, "settings", {"limitIndex": "80", "limitThreads": "1"}.get
    )

    list(downloader.get_items("lib", "Movie"))

    assert sorted(requested) == [(0, 80), (80, 80)]
