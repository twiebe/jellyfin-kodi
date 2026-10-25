# -*- coding: utf-8 -*-

#################################################################################################

import threading
import concurrent.futures
from datetime import date

import queue

import requests

from .helper import settings, stop, window, LazyLogger
from .jellyfin import Jellyfin
from .jellyfin import api
from .helper.exceptions import HTTPException, ServerResponseException

#################################################################################################

LOG = LazyLogger(__name__)

#################################################################################################


def get_jellyfinserver_url(handler):

    if handler.startswith("/"):

        handler = handler[1:]
        LOG.info("handler starts with /: %s", handler)

    return "{server}/%s" % handler


def _http(action, url, request=None, server_id=None):

    if request is None:
        request = {}

    request.update({"url": url, "type": action})
    return Jellyfin(server_id).http.request(request)


def _get(handler, params=None, server_id=None):
    return _http("GET", get_jellyfinserver_url(handler), {"params": params}, server_id)


def _post(handler, json=None, params=None, server_id=None):
    return _http(
        "POST",
        get_jellyfinserver_url(handler),
        {"params": params, "json": json},
        server_id,
    )


def _delete(handler, params=None, server_id=None):
    return _http(
        "DELETE", get_jellyfinserver_url(handler), {"params": params}, server_id
    )


def validate_view(library_id, item_id):
    """This confirms a single item from the library matches the view it belongs to.
    Used to detect grouped libraries.
    """
    try:
        result = _get(
            "Users/{UserId}/Items",
            {"ParentId": library_id, "Recursive": True, "Ids": item_id},
        )
    except Exception as error:
        LOG.exception(error)
        return False

    return bool(len(result["Items"]))


def get_single_item(parent_id, media):
    return _get(
        "Users/{UserId}/Items",
        {
            "ParentId": parent_id,
            "Recursive": True,
            "Limit": 1,
            "IncludeItemTypes": media,
        },
    )


def get_movies_by_boxset(boxset_id):

    for items in get_items(boxset_id, "Movie"):
        yield items


def get_episode_by_show(show_id):

    query = {
        "url": "Shows/%s/Episodes" % show_id,
        "params": {
            "EnableUserData": True,
            "EnableImages": True,
            "UserId": "{UserId}",
            "Fields": api.info(),
        },
    }
    for items in _get_items(query):
        yield items


def get_episode_by_season(show_id, season_id):

    query = {
        "url": "Shows/%s/Episodes" % show_id,
        "params": {
            "SeasonId": season_id,
            "EnableUserData": True,
            "EnableImages": True,
            "UserId": "{UserId}",
            "Fields": api.info(),
        },
    }
    for items in _get_items(query):
        yield items


def get_item_count(parent_id, item_type=None):

    url = "Users/{UserId}/Items"

    query_params = {
        "ParentId": parent_id,
        "IncludeItemTypes": item_type,
        "EnableTotalRecordCount": True,
        "LocationTypes": "FileSystem,Remote,Offline",
        "Recursive": True,
        "Limit": 1,
    }

    result = _get(url, query_params)

    return result.get("TotalRecordCount", 1)


def get_items(parent_id, item_type=None, basic=False, params=None):

    query = {
        "url": "Users/{UserId}/Items",
        "params": {
            "ParentId": parent_id,
            "IncludeItemTypes": item_type,
            "SortBy": "SortName",
            "SortOrder": "Ascending",
            "Fields": api.basic_info() if basic else api.info(),
            "CollapseBoxSetItems": False,
            "IsVirtualUnaired": False,
            "EnableTotalRecordCount": False,
            "LocationTypes": "FileSystem,Remote,Offline",
            "IsMissing": False,
            "Recursive": True,
        },
    }
    if params:
        query["params"].update(params)

    if basic:
        # Without the extra fields the server answers big pages quickly
        query["page_size"] = min(page_size() * 30, 1000)

    for items in _get_items(query):
        yield items


def page_size():
    """Items per request, the range is set in the settings UI."""
    return int(settings("limitIndex") or 15)


def get_items_by_ids(parent_id, item_type, item_ids):
    """Yield the items with the given ids in pages, like get_items."""
    limit = page_size()
    params = {
        "ParentId": parent_id,
        "IncludeItemTypes": item_type,
        "SortBy": "SortName",
        "SortOrder": "Ascending",
        "Fields": api.info(),
        "CollapseBoxSetItems": False,
        "EnableTotalRecordCount": False,
        "Recursive": True,
    }
    starts = range(0, len(item_ids), limit)
    query_params = [
        dict(params, Ids=",".join(item_ids[start : start + limit])) for start in starts
    ]

    for index, result in _get_pages("Users/{UserId}/Items", query_params):
        yield {
            "Items": result["Items"],
            "TotalRecordCount": len(item_ids),
            "StartIndex": starts[index],
        }


def get_artists(parent_id=None):

    query = {
        "url": "Artists",
        "params": {
            "UserId": "{UserId}",
            "ParentId": parent_id,
            "SortBy": "SortName",
            "SortOrder": "Ascending",
            "Fields": api.music_info(),
            "CollapseBoxSetItems": False,
            "IsVirtualUnaired": False,
            "EnableTotalRecordCount": False,
            "LocationTypes": "FileSystem,Remote,Offline",
            "IsMissing": False,
            "Recursive": True,
        },
    }

    for items in _get_items(query):
        yield items


@stop
def _get_items(query, server_id=None):
    """query = {
        'url': string,
        'params': dict -- opt, include StartIndex to resume
        'page_size': int -- opt, items per request instead of limitIndex
    }
    """
    items = {"Items": [], "TotalRecordCount": 0, "RestorePoint": {}}

    limit = query.get("page_size") or page_size()

    url = query["url"]
    query.setdefault("params", {})
    params = query["params"]

    try:
        test_params = dict(params)
        test_params["Limit"] = 1
        test_params["EnableTotalRecordCount"] = True

        result = _get(url, test_params, server_id=server_id) or {}
        if "TotalRecordCount" not in result:
            raise ServerResponseException("No item count in the response")
        items["TotalRecordCount"] = result["TotalRecordCount"]

    except Exception as error:
        LOG.exception(
            "Failed to retrieve the server response %s: %s params:%s",
            url,
            error,
            params,
        )
        # Yielding nothing would look like an empty library, and the full
        # sync removes every local item it did not receive
        raise

    else:
        params.setdefault("StartIndex", 0)

        def get_query_params(params, start, count):
            params_copy = dict(params)
            params_copy["StartIndex"] = start
            params_copy["Limit"] = count
            return params_copy

        query_params = [
            get_query_params(params, offset, limit)
            for offset in range(params["StartIndex"], items["TotalRecordCount"], limit)
        ]

        for index, result in _get_pages(url, query_params, server_id):
            query["params"] = query_params[index]
            items["Items"].extend(result["Items"])
            # Using items to return data and communicate a restore point back to the callee is
            # a violation of the SRP. TODO: Separate responsibilities.
            items["RestorePoint"] = query
            yield items
            del items["Items"][:]


def _get_pages(url, query_params, server_id=None):
    """Request the pages with the given params in parallel. Yields the
    index of the params and the response of each page as it arrives.
    """
    dthreads = int(settings("limitThreads") or 3)

    # multiprocessing.dummy.Pool completes all requests in multiple threads but has to
    # complete all tasks before allowing any results to be processed. ThreadPoolExecutor
    # allows for completed tasks to be processed while other tasks are completed on other
    # threads. Don't be a dummy.Pool, be a ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(dthreads) as p:
        # dictionary for storing the jobs and their results
        jobs = {}

        # semaphore to avoid fetching complete library to memory
        thread_buffer = threading.Semaphore(dthreads)
        stopped = threading.Event()

        # wrapper function for _get that uses a semaphore
        def get_wrapper(params):
            thread_buffer.acquire()
            if stopped.is_set():
                return None
            return _get(url, params, server_id=server_id)

        # create jobs
        for index, param in enumerate(query_params):
            job = p.submit(get_wrapper, param)
            # the index of the query params is later needed again
            jobs[job] = index

        try:
            # process complete jobs
            for job in concurrent.futures.as_completed(jobs):
                # get the result
                result = job.result()
                index = jobs[job]
                if not result or "Items" not in result:
                    raise ServerResponseException(
                        "No items in the response %s params:%s"
                        % (url, query_params[index])
                    )

                # free job memory
                del jobs[job]
                del job

                # Mitigates #216 till the server validates the date provided is valid
                if result["Items"] and result["Items"][0].get("ProductionYear"):
                    try:
                        date(result["Items"][0]["ProductionYear"], 1, 1)
                    except ValueError:
                        LOG.info(
                            "#216 mitigation triggered. Setting ProductionYear to None"
                        )
                        result["Items"][0]["ProductionYear"] = None

                yield index, result

                # release the semaphore again
                thread_buffer.release()
        finally:
            # Unblock the workers, or leaving the pool waits forever for
            # jobs stuck on the semaphore, e.g. after an error or when
            # the caller stops iterating. Woken workers skip their request.
            stopped.set()
            for job in jobs:
                job.cancel()
            for _ in range(dthreads):
                thread_buffer.release()


class GetItemWorker(threading.Thread):

    is_done = False

    def __init__(self, server, queue, output):

        self.server = server
        self.queue = queue
        self.output = output
        threading.Thread.__init__(self)

    def run(self):
        with requests.Session() as s:
            while True:
                try:
                    item_ids = self.queue.get(timeout=1)
                except queue.Empty:

                    self.is_done = True
                    LOG.info("--<[ q:download/%s ]", id(self))

                    return

                request = {
                    "type": "GET",
                    "handler": "Users/{UserId}/Items",
                    "params": {
                        "Ids": ",".join(str(x) for x in item_ids),
                        "Fields": api.info(),
                    },
                }

                try:
                    result = self.server.http.request(request, s)

                    for item in result["Items"]:

                        if item["Type"] in self.output:
                            self.output[item["Type"]].put(item)
                except HTTPException as error:
                    LOG.error("--[ http status: %s ]", error.status)

                    if error.status == "ServerUnreachable":
                        self.is_done = True

                        break

                except Exception as error:
                    LOG.exception(error)

                self.queue.task_done()

                if window("jellyfin_should_stop.bool"):
                    break
