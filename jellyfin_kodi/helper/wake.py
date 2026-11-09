# -*- coding: utf-8 -*-
"""Wakes the library thread at once when there is work for its next step.

The library thread used to look every 2 s, and an item passes it three times (download, write,
done), so a change on the server reached Kodi's library 5 to 6 s late. Whoever queues work or
finishes a step sets LIBRARY; the thread still looks every 2 s without it.
"""
from __future__ import division, absolute_import, print_function, unicode_literals

import threading

LIBRARY = threading.Event()

# How long a worker thread waits for more items before it ends: the library thread counts it as
# busy until then, and only marks the sync done once every worker ended
LINGER = 0.25
