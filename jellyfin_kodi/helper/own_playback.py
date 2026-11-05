# -*- coding: utf-8 -*-
"""Tell the server's echo of our own playback from a real change.

The server reports a user data change when playback starts and stops. Kodi announced those
already (Player.OnPlay, VideoLibrary.OnUpdate, Player.OnStop) and reloaded its lists, so a library
scan for the echo only reloads them all a second time. It counts as an echo when it holds the item
we played, plus at most its parent folders, soon after, and when it tells Kodi nothing new: the
server has its own rules for resume points and for watched (5 % and 90 %, Kodi 180 s and 92 %).
"""
import time

from .utils import window

# The echo took at most 4 s in 7 stops under a full parallel test run, 0.7 s on an idle box.
# Too short only costs the scan as before.
ECHO_SECONDS = 15


def note_own_playback(item_id):
    window("jellyfin_own_playback.json", {"Id": item_id, "Time": time.time()})


def is_own_echo(data, kodi_state):
    """DATA is the UserDataChanged list. KODI_STATE(item id) returns Kodi's (watched, has a resume
    point) of the item, or None if it does not know."""
    own = window("jellyfin_own_playback.json")
    if not own or time.time() - own["Time"] > ECHO_SECONDS:
        return False

    mine = [x for x in data if x["ItemId"] == own["Id"]]
    others = [x for x in data if x["ItemId"] != own["Id"]]
    # Only folders carry UnplayedItemCount: theirs follows from the item
    if len(mine) != 1 or any("UnplayedItemCount" not in x for x in others):
        return False

    server = (bool(mine[0].get("Played")), mine[0].get("PlaybackPositionTicks", 0) > 0)
    return kodi_state(own["Id"]) == server
