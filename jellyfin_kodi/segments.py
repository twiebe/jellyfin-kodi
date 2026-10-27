import threading

import xbmc

from .helper import LazyLogger, settings

LOG = LazyLogger(__name__)

SEGMENT_TYPES_MAP = {
    "Intro": "Introduction",
    "Outro": "Credits",
    "Recap": "Recap",
    "Preview": "Preview",
    "Commercial": "Commercial",
}


# The skip dialog is polled every tick, the segments are checked every second.
TICK_MS = 200
TICKS_PER_CHECK = 5


class SegmentChecker(threading.Thread):
    """Checks the media segments of the playing item and owns the skip dialog.

    The player callbacks only update state. Showing, polling and closing the
    skip dialog happens here: waiting in a callback holds up every callback of
    the service, and the dialog's clicks only arrive while this thread sleeps.
    """

    stop_thread = False
    waiting_logged = False

    def __init__(self, player):
        self.player = player
        self.woken = threading.Event()

        threading.Thread.__init__(self)

    def stop(self):
        self.stop_thread = True

    def wake(self):
        """Check the segments at the next tick, e.g. after a seek."""
        self.woken.set()

    def run(self):
        LOG.info("--->[ segment checker ]")
        monitor = xbmc.Monitor()
        tick = 0

        while not self.stop_thread and not monitor.abortRequested():
            if tick == 0 or self.woken.is_set():
                self.woken.clear()
                tick = 0
                self.check_segments()

            try:
                self.player.update_skip_dialog()
            except Exception as e:
                LOG.exception("Error updating the skip dialog: %s", e)

            tick = (tick + 1) % TICKS_PER_CHECK
            xbmc.sleep(TICK_MS)

        LOG.info("---<[ segment checker ]")

    def check_segments(self):
        if not self.player.isPlaying():
            return

        try:
            self.player.track_position()
        except Exception as e:
            LOG.exception("Error tracking the playback position: %s", e)

        if not settings("mediaSegmentsEnabled.bool"):
            return

        try:
            current_file = self.player.get_playing_file()
            if self.player.is_playing_file(current_file):
                item = self.player.get_file_info(current_file)
                current_pos = int(self.player.getTime())
                self.player.check_skip_segments(item, current_pos)
            elif not self.waiting_logged:
                self.waiting_logged = True
                LOG.info("Current file is not yet playing: %s", current_file)

        except Exception as e:
            LOG.exception("Error in segment checker loop: %s", e)
