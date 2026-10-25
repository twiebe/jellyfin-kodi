# -*- coding: utf-8 -*-

#################################################################################################

import hashlib

from ..helper import JSONRPC
from ..helper import LazyLogger

#################################################################################################

LOG = LazyLogger(__name__)

#################################################################################################


def sync_checksum(obj, *settings):
    """Checksum of what a synced item is written from: the server's item
    and user data, and the add-on settings that change the result.
    """
    values = (obj["Etag"], obj["Checksum"]) + settings
    data = "|".join(str(value) for value in values)

    return hashlib.md5(data.encode("utf-8")).hexdigest()


def get_grouped_set():
    """Get if boxsets should be grouped"""
    result = JSONRPC("Settings.GetSettingValue").execute(
        {"setting": "videolibrary.groupmoviesets"}
    )
    return result.get("result", {}).get("value", False)
