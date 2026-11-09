# -*- coding: utf-8 -*-

#################################################################################################

from .exceptions import HTTPException
from .lazylogger import LazyLogger
from .utils import event

#################################################################################################

LOG = LazyLogger(__name__)

#################################################################################################


def delete_item(api_client, item_id, server_id=None):
    """Delete the item on the server, then from the Kodi library at once.

    The server reports the removal only after its LibraryUpdateDuration
    (30 s by default), the title stayed in the lists until then. The id goes
    to the service the way that message does, so the service removes it and
    refreshes the lists. The server's message later finds nothing to remove.
    Only the default server (server_id None) is synced into the library.

    Returns False and removes nothing if the server did not delete the item.
    """
    try:
        api_client.delete_item(item_id)
    except HTTPException as error:
        LOG.warning("The server did not delete %s: %s", item_id, error.status)
        return False

    if server_id is None:
        event(
            "LibraryChanged",
            {"ItemsAdded": [], "ItemsUpdated": [], "ItemsRemoved": [item_id]},
        )

    return True
