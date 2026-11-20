# -*- coding: utf-8 -*-

import json

import xbmcvfs

##################################################################################################

from . import settings, LazyLogger

##################################################################################################

LOG = LazyLogger(__name__)

# Artwork is requested no wider than the place it fills, one setting per kind:
# the value is the largest width in pixels, 0 Auto, -1 unlimited. Without mipmaps
# Kodi draws a big image on a small card pixelated (a 1920x1080 still on an
# episode card of 320x180), most on the GPUs of ARM boxes.
ART_KINDS = ("poster", "thumb", "fanart", "logo")
ART_SETTINGS = {
    "poster": "artSizePoster",
    "thumb": "artSizeThumb",
    "fanart": "artSizeFanart",
    "logo": "artSizeLogo",
}
# Auto at a GUI of 1080 lines: poster cards (up to 360 px wide in a library
# view, some room for larger ones), episode and landscape cards (two times their
# width), the full screen, a logo box. It follows the GUI height.
ART_AUTO_1080 = {"poster": 400, "thumb": 640, "fanart": 1920, "logo": 800}
ART_STEPS = (320, 480, 640, 960, 1280, 1920, 3840)
# Items whose artwork keeps its size: square covers drawn large, photos viewed
# full screen, channel logos
ART_UNSIZED_TYPES = {
    "MusicAlbum",
    "MusicArtist",
    "AlbumArtist",
    "Audio",
    "Photo",
    "PhotoAlbum",
    "TvChannel",
    "Program",
    "Recording",
}
# Items whose primary image is a still, not a poster
ART_STILL_TYPES = {"Episode", "MusicVideo", "Video"}
ART_IMAGE_KINDS = {
    "Primary": "poster",
    "BoxRear": "poster",
    "Thumb": "thumb",
    "Backdrop": "fanart",
    "Logo": "logo",
    "Art": "logo",
    "Banner": "logo",
    "Disc": "logo",
}

# The artwork settings once went into the checksum of a synced item, so a new
# setting synced every item again. Now resize_urls rewrites the URLs; the
# checksum keeps the value the settings had by default, earlier checksums hold.
ART_CHECKSUM = ""

# Reading a setting takes about a millisecond, too slow to do for every
# item of a sync. The service resets this when the settings change.
_art_queries = None


def gui_size():
    import xbmcgui

    return xbmcgui.getScreenWidth(), xbmcgui.getScreenHeight()


def art_kind(image, item_type):
    """The size setting of an IMAGE (Primary, Backdrop, ...) of an item of
    ITEM_TYPE: poster, thumb, fanart, logo, or None for one that keeps its size.
    """
    if item_type in ART_UNSIZED_TYPES:
        return None
    if image == "Primary" and item_type in ART_STILL_TYPES:
        return "thumb"
    return ART_IMAGE_KINDS.get(image)


def _art_width(kind, width, height):
    value = int(settings(ART_SETTINGS[kind]) or 0)
    if value < 0:
        return None
    if value == 0:
        auto = int(round(ART_AUTO_1080[kind] * height / 1080.0))
        # a backdrop fills the screen: no wider than it on a 16:10 or 4:3 screen
        return min(auto, width) if kind == "fanart" else auto
    return value


def _queries():
    global _art_queries

    if _art_queries is None:
        # no quality: a resized image is encoded anew anyway, and the width saves
        # far more than a lower quality (the former "compress artwork")
        screen_width, height = gui_size()
        height = height or 1080
        screen_width = screen_width or height * 16 // 9
        _art_queries = {None: ""}
        for kind in ART_KINDS:
            width = _art_width(kind, screen_width, height)
            _art_queries[kind] = "&MaxWidth=%d" % width if width else ""

    return _art_queries


def art_query(kind=None):
    """Image query parameters for artwork of KIND (art_kind)."""
    return _queries()[kind]


def art_key():
    """What the artwork URLs are written with: changes with any artwork setting."""
    queries = _queries()
    return "|".join(queries[kind] for kind in (None,) + ART_KINDS)


def reset_art_query():
    global _art_queries
    _art_queries = None


def _step(width):
    return next((step for step in ART_STEPS if step >= width), ART_STEPS[-1])


def migrate_art_sizes():
    """Once: a max artwork resolution (a height for all artwork) becomes the
    widths it gave posters and 16:9 images. Logos never reached that height."""
    if settings("artSizeMigrated.bool"):
        return

    heights = [360, 480, 600, 720, 1080]
    old = settings("maxArtResolution")
    if old and old.isdigit() and int(old) < len(heights):
        height = heights[int(old)]
        settings("artSizePoster", str(_step(height * 2 // 3)))
        settings("artSizeThumb", str(_step(height * 16 // 9)))
        settings("artSizeFanart", str(_step(height * 16 // 9)))
        settings("artSizeLogo", "0")
        LOG.info("artwork sizes taken over from a max resolution of %s", height)

    settings("artSizeMigrated.bool", True)
    reset_art_query()


##################################################################################################


class API(object):
    def __init__(self, item, server=None):
        """Get item information in special cases.
        server is the server address, provide if your functions requires it.
        """
        self.item = item
        self.server = server

        addon_data = xbmcvfs.translatePath(
            "special://profile/addon_data/plugin.video.jellyfin/data.json"
        )
        try:
            with open(addon_data, "rb") as infile:
                data = json.load(infile)
            self.path_data = data["Servers"][0].get("paths", {})
        except Exception as e:
            LOG.warning("Addon appears to not be configured yet: {}".format(e))

    def get_playcount(self, played, playcount):
        """Convert Jellyfin played/playcount into
        the Kodi equivalent. The playcount is tied to the watch status.
        """
        return (playcount or 1) if played else None

    def get_naming(self):

        if self.item["Type"] == "Episode" and "SeriesName" in self.item:
            return "%s: %s" % (self.item["SeriesName"], self.item["Name"])

        elif self.item["Type"] == "MusicAlbum" and "AlbumArtist" in self.item:
            return "%s: %s" % (self.item["AlbumArtist"], self.item["Name"])

        elif self.item["Type"] == "Audio" and self.item.get("Artists"):
            return "%s: %s" % (self.item["Artists"][0], self.item["Name"])

        return self.item["Name"]

    def get_actors(self):
        cast = []

        if "People" in self.item:
            self.get_people_artwork(self.item["People"])

            # Define the types of people considered "actors" in a "cast".
            cast_types = ["Actor", "GuestStar"]

            for person in self.item["People"]:

                if person["Type"] in cast_types:
                    cast.append(
                        {
                            "name": person["Name"],
                            "role": person.get("Role", "Unknown"),
                            "order": len(cast) + 1,
                            "thumbnail": person["imageurl"],
                        }
                    )

        return cast

    def media_streams(self, video, audio, subtitles):
        return {"video": video or [], "audio": audio or [], "subtitle": subtitles or []}

    def video_streams(self, tracks, container=None):

        if container:
            container = container.split(",")[0]

        for track in tracks:

            if "DvProfile" in track:
                track["hdrtype"] = "dolbyvision"
            elif track.get("VideoRangeType", "") in ["HDR10", "HDR10Plus"]:
                track["hdrtype"] = "hdr10"
            elif "HLG" in track.get("VideoRangeType", ""):
                track["hdrtype"] = "hlg"

            track.update(
                {
                    "hdrtype": track.get("hdrtype", "").lower(),
                    "codec": track.get("Codec", "").lower(),
                    "profile": track.get("Profile", "").lower(),
                    "height": track.get("Height"),
                    "width": track.get("Width"),
                    "3d": self.item.get("Video3DFormat"),
                    "aspect": 1.85,
                }
            )

            if "msmpeg4" in track["codec"]:
                track["codec"] = "divx"

            elif "mpeg4" in track["codec"] and (
                "simple profile" in track["profile"] or not track["profile"]
            ):
                track["codec"] = "xvid"

            elif "h264" in track["codec"] and container in ("mp4", "mov", "m4v"):
                track["codec"] = "avc1"

            try:
                width, height = self.item.get(
                    "AspectRatio", track.get("AspectRatio", "0")
                ).split(":")
                track["aspect"] = round(float(width) / float(height), 6)
            except (ValueError, ZeroDivisionError):

                if track["width"] and track["height"]:
                    track["aspect"] = round(float(track["width"] / track["height"]), 6)

            track["duration"] = self.get_runtime()

        return tracks

    def audio_streams(self, tracks):

        for track in tracks:

            track.update(
                {
                    "codec": track.get("Codec", "").lower(),
                    "profile": track.get("Profile", "").lower(),
                    "channels": track.get("Channels"),
                    "language": track.get("Language"),
                }
            )

            if "dts-hd ma" in track["profile"]:
                track["codec"] = "dtshd_ma"

            elif "dts-hd hra" in track["profile"]:
                track["codec"] = "dtshd_hra"

        return tracks

    def get_runtime(self):

        try:
            runtime = self.item["RunTimeTicks"] / 10000000.0

        except KeyError:
            runtime = self.item.get("CumulativeRunTimeTicks", 0) / 10000000.0

        return runtime

    @classmethod
    def adjust_resume(cls, resume_seconds):

        resume = 0
        if resume_seconds:
            resume = round(float(resume_seconds), 6)
            jumpback = int(settings("resumeJumpBack"))
            if resume > jumpback:
                # To avoid negative bookmark
                resume = resume - jumpback

        return resume

    def validate_studio(self, studio_name):
        # Convert studio for Kodi to properly detect them
        studios = {
            "abc (us)": "ABC",
            "fox (us)": "FOX",
            "mtv (us)": "MTV",
            "showcase (ca)": "Showcase",
            "wgn america": "WGN",
            "bravo (us)": "Bravo",
            "tnt (us)": "TNT",
            "comedy central": "Comedy Central (US)",
        }
        return studios.get(studio_name.lower(), studio_name)

    def get_overview(self, overview=None):

        overview = overview or self.item.get("Overview")

        if not overview:
            return

        overview = overview.replace('"', "'")
        overview = overview.replace("\n", "[CR]")
        overview = overview.replace("\r", " ")
        overview = overview.replace("<br>", "[CR]")

        return overview

    def get_mpaa(self, rating=None):

        mpaa = rating or self.item.get("OfficialRating", "")

        if mpaa in ("NR", "UR"):
            # Kodi seems to not like NR, but will accept Not Rated
            mpaa = "Not Rated"

        if "FSK-" in mpaa:
            mpaa = mpaa.replace("-", " ")

        return mpaa

    def get_file_path(self, path=None):

        if path is None:
            path = self.item.get("Path")

        if not path:
            return ""

        if path.startswith("\\\\"):
            path = (
                path.replace("\\\\", "smb://", 1)
                .replace("\\\\", "\\")
                .replace("\\", "/")
            )

        if "Container" in self.item:

            if self.item["Container"] == "dvd":
                path = "%s/VIDEO_TS/VIDEO_TS.IFO" % path
            elif self.item["Container"] == "bluray":
                path = "%s/BDMV/index.bdmv" % path

        path = path.replace("\\\\", "\\")

        if "\\" in path:
            path = path.replace("/", "\\")

        if "://" in path:
            protocol = path.split("://")[0]
            path = path.replace(protocol, protocol.lower())

        # Loop through configured path replacements searching for a match
        for local_path in self.path_data.keys():
            if local_path in path:
                path = path.replace(local_path, self.path_data[local_path])

        return path

    def get_user_artwork(self, user_id):
        """Get jellyfin user profile picture."""
        return "%s/Users/%s/Images/Primary?Format=original" % (self.server, user_id)

    def get_people_artwork(self, people):
        """Get people (actor, director, etc) artwork."""
        for person in people:

            if "PrimaryImageTag" in person:

                query = "&MaxWidth=400&MaxHeight=400&Index=0"
                person["imageurl"] = self.get_artwork(
                    person["Id"], "Primary", person["PrimaryImageTag"], query
                )
            else:
                person["imageurl"] = None

        return people

    def get_all_artwork(self, obj, parent_info=False):
        """Get all artwork possible. If parent_info is True,
        it will fill missing artwork with parent artwork.

        obj is from objects.Objects().map(item, 'Artwork')
        """
        item_type = obj.get("Type")

        def query(image):
            return art_query(art_kind(image, item_type))

        all_artwork = {
            "Primary": "",
            "BoxRear": "",
            "Art": "",
            "Banner": "",
            "Logo": "",
            "Thumb": "",
            "Disc": "",
            "Backdrop": [],
        }

        all_artwork["Backdrop"] = self.get_backdrops(
            obj["Id"], obj["BackdropTags"] or [], query("Backdrop")
        )

        for artwork in obj["Tags"] or []:
            all_artwork[artwork] = self.get_artwork(
                obj["Id"], artwork, obj["Tags"][artwork], query(artwork)
            )

        if parent_info:

            if not all_artwork["Backdrop"] and obj["ParentBackdropId"]:
                all_artwork["Backdrop"] = self.get_backdrops(
                    obj["ParentBackdropId"],
                    obj["ParentBackdropTags"],
                    query("Backdrop"),
                )

            for art in ("Logo", "Art", "Thumb"):
                if not all_artwork[art] and obj["Parent%sId" % art]:
                    all_artwork[art] = self.get_artwork(
                        obj["Parent%sId" % art],
                        art,
                        obj["Parent%sTag" % art],
                        query(art),
                    )

            if obj.get("SeriesTag"):
                all_artwork["Series.Primary"] = self.get_artwork(
                    obj["SeriesId"], "Primary", obj["SeriesTag"], art_query("poster")
                )

                if not all_artwork["Primary"]:
                    # sized like the item's own primary image
                    all_artwork["Primary"] = self.get_artwork(
                        obj["SeriesId"], "Primary", obj["SeriesTag"], query("Primary")
                    )

            elif not all_artwork["Primary"] and obj.get("AlbumId"):
                all_artwork["Primary"] = self.get_artwork(
                    obj["AlbumId"], "Primary", obj["AlbumTag"], query("Primary")
                )

        return all_artwork

    def get_backdrops(self, item_id, tags, query=None):
        """Get backdrops based of "BackdropImageTags" in the jellyfin object."""
        backdrops = []

        if item_id is None:
            return backdrops

        for index, tag in enumerate(tags):

            artwork = "%s/Items/%s/Images/Backdrop/%s?Format=original&Tag=%s%s" % (
                self.server,
                item_id,
                index,
                tag,
                (query or ""),
            )
            backdrops.append(artwork)

        return backdrops

    def get_artwork(self, item_id, image, tag=None, query=None):
        """Get any type of artwork: Primary, Art, Banner, Logo, Thumb, Disc"""
        if item_id is None:
            return ""

        url = "%s/Items/%s/Images/%s/0?Format=original" % (self.server, item_id, image)

        if tag is not None:
            url += "&Tag=%s" % tag

        if query is not None:
            url += query or ""

        return url
