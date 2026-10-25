# -*- coding: utf-8 -*-

import threading

import pytest

from jellyfin_kodi import downloader
from jellyfin_kodi.helper import wrapper
from jellyfin_kodi.helper.exceptions import HTTPException, ServerResponseException


@pytest.fixture
def server(monkeypatch):
    """Fake server: maps StartIndex to a page, "count" to the total count."""
    responses = {}
    responses["requested"] = []

    def fake_get(handler, params=None, server_id=None):
        key = "count" if params.get("EnableTotalRecordCount") else params["StartIndex"]
        responses["requested"].append(key)
        response = responses[key]
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(downloader, "_get", fake_get)
    # Let @stop pass: Kodi running, server online
    monkeypatch.setattr(wrapper.monitor, "abortRequested", lambda: False)
    monkeypatch.setattr(wrapper, "window", lambda key: key == "jellyfin_online.bool")
    monkeypatch.setattr(
        downloader, "settings", {"limitIndex": "2", "limitThreads": "1"}.get
    )
    return responses


def _page(*ids):
    return {"Items": [{"Id": i} for i in ids]}


def _fetch(query=None):
    query = query or {"url": "Users/{UserId}/Items", "params": {}}
    return [
        [item["Id"] for item in items["Items"]]
        for items in downloader._get_items(query)
    ]


def test_yields_all_pages(server):
    server["count"] = {"TotalRecordCount": 3}
    server[0] = _page("a", "b")
    server[2] = _page("c")
    assert sorted(_fetch()) == [["a", "b"], ["c"]]


# A failed fetch must not look like an empty library: the full sync removes
# every local item it did not receive.
def test_unreachable_server_raises(server):
    server["count"] = HTTPException("ServerUnreachable", None)
    with pytest.raises(HTTPException):
        _fetch()


# The http client returns None for a 500 response
@pytest.mark.parametrize("count", [None, {}], ids=["http-500", "no-count"])
def test_failed_count_raises(server, count):
    server["count"] = count
    with pytest.raises(ServerResponseException):
        _fetch()


def test_failed_page_raises(server):
    server["count"] = {"TotalRecordCount": 3}
    server[0] = _page("a", "b")
    server[2] = None
    with pytest.raises(ServerResponseException):
        _fetch()


def test_empty_page_is_no_error(server):
    # Items can disappear between the count and the page request
    server["count"] = {"TotalRecordCount": 2}
    server[0] = _page()
    assert _fetch() == [[]]


def _run(func, timeout=5):
    """Run func in a thread, return the exception it raised.

    Fails if func does not return in time.
    """
    errors = []

    def target():
        try:
            func()
        except Exception as error:
            errors.append(error)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout)
    assert not thread.is_alive(), "hangs"
    return errors[0] if errors else None


def test_failed_page_does_not_hang(server):
    # More pages than download threads: later jobs wait on the semaphore
    server["count"] = {"TotalRecordCount": 6}
    server[0] = None
    server[2] = _page("c", "d")
    server[4] = _page("e", "f")

    assert isinstance(_run(_fetch), ServerResponseException)


def test_stopping_early_does_not_hang(server):
    server["count"] = {"TotalRecordCount": 6}
    server[0] = _page("a", "b")
    server[2] = _page("c", "d")
    server[4] = _page("e", "f")

    def fetch_first_page():
        generator = downloader._get_items({"url": "Users/{UserId}/Items", "params": {}})
        next(generator)
        generator.close()

    assert _run(fetch_first_page) is None


def test_no_requests_after_a_failed_page(server, monkeypatch):
    monkeypatch.setattr(
        downloader, "settings", {"limitIndex": "1", "limitThreads": "2"}.get
    )
    server["count"] = {"TotalRecordCount": 4}
    server[0] = None
    server[1] = server[2] = server[3] = _page("x")

    assert isinstance(_run(_fetch), ServerResponseException)
    # Both workers fetch a page, then wait on the semaphore for a free slot
    assert sorted(server["requested"], key=str) == [0, 1, "count"]


def test_items_by_ids_in_pages(server, monkeypatch):
    requested = []

    def fake_get(handler, params=None, server_id=None):
        requested.append(params["Ids"])
        return _page(*params["Ids"].split(","))

    monkeypatch.setattr(downloader, "_get", fake_get)
    pages = list(downloader.get_items_by_ids("lib", "Movie", ["a", "b", "c"]))

    assert requested == ["a,b", "c"]
    assert [(page["StartIndex"], page["TotalRecordCount"]) for page in pages] == [
        (0, 3),
        (2, 3),
    ]


def test_failed_page_by_ids_raises(server, monkeypatch):
    monkeypatch.setattr(downloader, "_get", lambda *args, **kwargs: None)
    with pytest.raises(ServerResponseException):
        list(downloader.get_items_by_ids("lib", "Movie", ["a"]))


def test_basic_items_in_bigger_pages(server):
    # limitIndex 2
    server["count"] = {"TotalRecordCount": 100}
    server[0] = _page("a")
    server[60] = _page("b")
    list(downloader.get_items("lib", "Movie", basic=True))
    assert sorted(server["requested"], key=str) == [0, 60, "count"]


def test_basic_pages_have_at_most_1000_items(server, monkeypatch):
    monkeypatch.setattr(
        downloader, "settings", {"limitIndex": "100", "limitThreads": "1"}.get
    )
    server["count"] = {"TotalRecordCount": 1500}
    server[0] = _page("a")
    server[1000] = _page("b")
    list(downloader.get_items("lib", "Movie", basic=True))
    assert sorted(server["requested"], key=str) == [0, 1000, "count"]


def test_page_size_above_50(server, monkeypatch):
    # The settings allow up to 100 items per request
    monkeypatch.setattr(
        downloader, "settings", {"limitIndex": "80", "limitThreads": "1"}.get
    )
    server["count"] = {"TotalRecordCount": 100}
    server[0] = _page("a")
    server[80] = _page("b")
    list(downloader.get_items("lib", "Movie"))
    assert sorted(server["requested"], key=str) == [0, 80, "count"]
