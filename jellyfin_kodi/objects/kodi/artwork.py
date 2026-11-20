# -*- coding: utf-8 -*-

#################################################################################################

import re

from ...helper import LazyLogger, api

from . import queries as QU

##################################################################################################

LOG = LazyLogger(__name__)

##################################################################################################


class Artwork(object):

    def __init__(self, cursor):

        self.cursor = cursor

    def update(self, image_url, kodi_id, media, image):
        """Update artwork in the video database.
        Delete current entry before updating with the new one.
        """
        if not image_url or image == "poster" and media in ("song", "artist", "album"):
            return

        try:
            self.cursor.execute(
                QU.get_art,
                (
                    kodi_id,
                    media,
                    image,
                ),
            )
            url = self.cursor.fetchone()[0]
        except TypeError:

            LOG.debug("ADD to kodi_id %s art: %s", kodi_id, image_url)
            self.cursor.execute(QU.add_art, (kodi_id, media, image, image_url))
        else:
            if url != image_url:
                LOG.info("UPDATE to kodi_id %s art: %s", kodi_id, image_url)
                self.cursor.execute(QU.update_art, (image_url, kodi_id, media, image))

    def add(self, artwork, *args):
        """Add all artworks."""
        KODI = {
            "Primary": ["thumb", "poster"],
            "Banner": "banner",
            "Logo": "clearlogo",
            "Art": "clearart",
            "Thumb": "landscape",
            "Disc": "discart",
            "Backdrop": "fanart",
        }

        for art in KODI:

            if art == "Backdrop":
                self.cursor.execute(QU.get_backdrops, args + ("fanart%",))

                if len(self.cursor.fetchall()) > len(artwork["Backdrop"]):
                    self.cursor.execute(QU.delete_backdrops, args + ("fanart_",))

                for index, backdrop in enumerate(artwork["Backdrop"]):

                    if index:
                        self.update(*(backdrop,) + args + ("%s%s" % ("fanart", index),))
                    else:
                        self.update(*(backdrop,) + args + ("fanart",))

            elif art == "Primary":
                for kodi_image in KODI["Primary"]:
                    self.update(*(artwork["Primary"],) + args + (kodi_image,))

            elif artwork.get(art):
                self.update(*(artwork[art],) + args + (KODI[art],))

    def delete(self, *args):
        """Delete artwork from kodi database"""
        self.cursor.execute(QU.delete_art, args)


# Kodi's media types of the library and the Jellyfin items they are written from
MEDIA_ITEM_TYPES = {
    "movie": "Movie",
    "set": "BoxSet",
    "tvshow": "Series",
    "season": "Season",
    "episode": "Episode",
    "musicvideo": "MusicVideo",
}
# An image URL of the server as API.get_artwork and API.get_backdrops write it
SERVER_IMAGE = re.compile(
    r"/Items/[^/?]+/Images/(\w+)(?:/\d+)?\?Format=original(?:&|$)"
)
SIZE_PARAMS = ("Quality", "MaxHeight", "MaxWidth")


def resize_urls(cursor):
    """Write the artwork URLs of the video library with the size and quality the
    artwork settings give them now (api.art_query); the number of URLs changed.
    Cast images keep their own size.
    """
    cursor.execute("SELECT art_id, media_type, url FROM art")
    changes = []

    for art_id, media_type, url in cursor.fetchall():
        item_type = MEDIA_ITEM_TYPES.get(media_type)
        match = SERVER_IMAGE.search(url or "")
        if item_type is None or match is None:
            continue

        base, _, query = url.partition("?")
        params = [p for p in query.split("&") if p.split("=", 1)[0] not in SIZE_PARAMS]
        new = "%s?%s%s" % (
            base,
            "&".join(params),
            api.art_query(api.art_kind(match.group(1), item_type)),
        )
        if new != url:
            changes.append((new, art_id))

    cursor.executemany("UPDATE art SET url = ? WHERE art_id = ?", changes)
    if changes:
        LOG.info("artwork sizes: %s URLs rewritten", len(changes))

    return len(changes)
