# -*- coding: utf-8 -*-
"""The library thread wakes at once when there is work for its next step.

It used to look every 2 s, and an item passes it three times (download, write, done), so a
change on the server reached Kodi's library 5 to 6 s late.
"""

import queue
from unittest.mock import Mock

from jellyfin_kodi import downloader, library
from jellyfin_kodi.helper import wake


def _library():
    lib = library.Library.__new__(library.Library)
    lib.userdata_queue = queue.Queue()
    lib.updated_queue = queue.Queue()
    lib.removed_queue = queue.Queue()
    lib.total_updates = 0
    lib.userdata_wants_scan = False
    lib.kodi_state = lambda item_id: None
    return lib


def test_queued_work_wakes_the_thread(monkeypatch):
    monkeypatch.setattr(library, "is_own_echo", lambda data, state: True)
    lib = _library()
    for queue_work, data in (
        (lib.userdata, [{"ItemId": "a"}]),
        (lib.updated, ["b"]),
        (lib.removed, ["c"]),
    ):
        wake.LIBRARY.clear()
        queue_work(data)
        assert wake.LIBRARY.is_set(), queue_work.__name__


def test_a_download_wakes_the_thread_for_the_writer(monkeypatch):
    monkeypatch.setattr(downloader, "window", lambda *args, **kwargs: False)
    server = Mock()
    server.http.request.return_value = {"Items": [{"Id": "a", "Type": "Movie"}]}
    work = queue.Queue()
    work.put(["a"])
    output = {"Movie": queue.Queue()}
    wake.LIBRARY.clear()

    worker = downloader.GetItemWorker(server, work, output)
    worker.run()

    assert output["Movie"].get_nowait() == {"Id": "a", "Type": "Movie"}
    assert worker.is_done and wake.LIBRARY.is_set()


def test_workers_end_soon_after_their_last_item():
    assert wake.LINGER <= 0.5
