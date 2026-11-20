# -*- coding: utf-8 -*-

import sqlite3

import pytest

from jellyfin_kodi.helper import api
from jellyfin_kodi.objects.kodi import artwork

SERVER = "http://jf:8096"


class _Settings(tuple):
    """values, reads, written, height; and .width of the screen"""

    def __new__(cls, items, width):
        self = super().__new__(cls, items)
        self.width = width
        return self


@pytest.fixture
def settings(monkeypatch):
    values = {
        "artSizePoster": "0",
        "artSizeThumb": "0",
        "artSizeFanart": "0",
        "artSizeLogo": "0",
        "maxArtResolution": "5",
        "artSizeMigrated.bool": True,
    }
    reads = []
    written = {}
    height = [1080]
    width = [1920]

    def fake_settings(key, value=None):
        if value is not None:
            written[key] = value
            values[key] = value
            return None
        reads.append(key)
        return values[key]

    monkeypatch.setattr(api, "settings", fake_settings)
    monkeypatch.setattr(api, "gui_size", lambda: (width[0], height[0]))
    api.reset_art_query()
    yield _Settings((values, reads, written, height), width)
    api.reset_art_query()


def test_auto_fits_the_place_of_each_kind_at_1080(settings):
    assert api.art_query("poster") == "&MaxWidth=400"
    assert api.art_query("thumb") == "&MaxWidth=640"
    assert api.art_query("fanart") == "&MaxWidth=1920"
    assert api.art_query("logo") == "&MaxWidth=800"


def test_auto_keeps_backdrops_to_the_screen_width(settings):
    # 14" MacBook Pro: 3024 x 1964, 16:10
    _, _, _, height = settings
    height[0], settings.width[0] = 1964, 3024
    assert api.art_query("fanart") == "&MaxWidth=3024"
    assert api.art_query("thumb") == "&MaxWidth=1164"
    assert api.art_query("poster") == "&MaxWidth=727"


def test_auto_follows_the_gui_height(settings):
    _, _, _, height = settings
    height[0] = 2160
    assert api.art_query("poster") == "&MaxWidth=800"
    assert api.art_query("thumb") == "&MaxWidth=1280"
    height[0] = 720
    api.reset_art_query()
    assert api.art_query("thumb") == "&MaxWidth=427"


def test_a_width_or_unlimited_per_kind(settings):
    values, _, _, _ = settings
    values.update({"artSizeThumb": "960", "artSizeFanart": "-1"})
    assert api.art_query("thumb") == "&MaxWidth=960"
    assert api.art_query("fanart") == ""
    assert api.art_query("poster") == "&MaxWidth=400"


def test_unsized_artwork_keeps_its_size(settings):
    # music covers, photos and channel logos
    assert api.art_query(None) == ""


def test_settings_are_read_once(settings):
    _, reads, _, _ = settings
    for _ in range(100):
        for kind in api.ART_KINDS + (None,):
            api.art_query(kind)
        api.art_key()
    assert len(reads) == 4


def test_key_changes_with_any_size(settings):
    values, _, _, height = settings
    key = api.art_key()
    values["artSizeLogo"] = "480"
    api.reset_art_query()
    assert api.art_key() != key
    values["artSizeLogo"] = "0"
    height[0] = 2160
    api.reset_art_query()
    assert api.art_key() != key


@pytest.mark.parametrize(
    "image, item_type, kind",
    [
        ("Primary", "Movie", "poster"),
        ("Primary", "Series", "poster"),
        ("Primary", "Season", "poster"),
        ("Primary", "BoxSet", "poster"),
        ("BoxRear", "Movie", "poster"),
        # an episode's or music video's primary image is a still
        ("Primary", "Episode", "thumb"),
        ("Primary", "MusicVideo", "thumb"),
        ("Thumb", "Movie", "thumb"),
        ("Backdrop", "Episode", "fanart"),
        ("Logo", "Series", "logo"),
        ("Art", "Movie", "logo"),
        ("Banner", "Series", "logo"),
        ("Disc", "Movie", "logo"),
        ("Primary", "MusicAlbum", None),
        ("Backdrop", "MusicArtist", None),
        ("Primary", "Audio", None),
        ("Primary", "Photo", None),
        ("Primary", "TvChannel", None),
    ],
)
def test_kind_of_an_image(image, item_type, kind):
    assert api.art_kind(image, item_type) == kind


def _artwork(item_type, **extra):
    obj = {
        "Id": "item",
        "Type": item_type,
        "Tags": {"Primary": "p", "Logo": "l"},
        "BackdropTags": ["b"],
    }
    obj.update(extra)
    return obj


def test_all_artwork_is_sized_by_kind(settings):
    art = api.API({}, SERVER).get_all_artwork(_artwork("Episode"))
    assert art["Primary"].endswith(
        "/Items/item/Images/Primary/0?Format=original&Tag=p&MaxWidth=640"
    )
    assert art["Logo"].endswith("&Tag=l&MaxWidth=800")
    assert art["Backdrop"] == [
        SERVER + "/Items/item/Images/Backdrop/0?Format=original&Tag=b&MaxWidth=1920"
    ]
    art = api.API({}, SERVER).get_all_artwork(_artwork("Movie"))
    assert art["Primary"].endswith("&Tag=p&MaxWidth=400")


def test_an_episode_without_a_still_shows_the_series_poster_at_the_size_of_a_still(
    settings,
):
    # sized like the slot it fills, as resize_urls sizes it later
    obj = _artwork(
        "Episode",
        Tags={},
        BackdropTags=[],
        ParentBackdropId=None,
        ParentLogoId=None,
        ParentArtId=None,
        ParentThumbId=None,
        SeriesId="show",
        SeriesTag="s",
    )
    art = api.API({}, SERVER).get_all_artwork(obj, parent_info=True)
    assert art["Series.Primary"].endswith(
        "/Items/show/Images/Primary/0?Format=original&Tag=s&MaxWidth=400"
    )
    assert art["Primary"].endswith(
        "/Items/show/Images/Primary/0?Format=original&Tag=s&MaxWidth=640"
    )


def test_music_artwork_keeps_its_size(settings):
    art = api.API({}, SERVER).get_all_artwork(_artwork("MusicAlbum"))
    assert art["Primary"].endswith("&Tag=p")


@pytest.mark.parametrize(
    "old, widths",
    [
        # MaxHeight 720: posters 480 wide, 16:9 images 1280; logos never reached that height
        (
            "3",
            {
                "artSizePoster": "480",
                "artSizeThumb": "1280",
                "artSizeFanart": "1280",
                "artSizeLogo": "0",
            },
        ),
        (
            "0",
            {
                "artSizePoster": "320",
                "artSizeThumb": "640",
                "artSizeFanart": "640",
                "artSizeLogo": "0",
            },
        ),
        (
            "4",
            {
                "artSizePoster": "960",
                "artSizeThumb": "1920",
                "artSizeFanart": "1920",
                "artSizeLogo": "0",
            },
        ),
        # unlimited, the old default: Auto
        ("5", {}),
        ("", {}),
    ],
)
def test_max_art_resolution_is_taken_over_once(settings, old, widths):
    values, _, written, _ = settings
    values.update({"maxArtResolution": old, "artSizeMigrated.bool": False})
    api.migrate_art_sizes()
    assert written == dict(widths, **{"artSizeMigrated.bool": True})
    written.clear()
    api.migrate_art_sizes()
    assert written == {}


def _db(rows):
    con = sqlite3.connect(":memory:")
    con.execute(
        "CREATE TABLE art (art_id INTEGER PRIMARY KEY, media_id INTEGER, media_type TEXT, type TEXT, url TEXT)"
    )
    con.executemany(
        "INSERT INTO art (media_id, media_type, type, url) VALUES (1, ?, ?, ?)", rows
    )
    return con


def test_resize_urls_rewrites_the_library_to_the_sizes(settings):
    # the quality of the former "compress artwork" goes too
    old = "&Quality=90&MaxHeight=720"
    con = _db(
        [
            (
                "episode",
                "thumb",
                SERVER + "/Items/e/Images/Primary/0?Format=original&Tag=p" + old,
            ),
            (
                "movie",
                "poster",
                SERVER + "/Items/m/Images/Primary/0?Format=original&Tag=p",
            ),
            (
                "movie",
                "fanart1",
                SERVER + "/Items/m/Images/Backdrop/1?Format=original&Tag=b" + old,
            ),
            (
                "tvshow",
                "clearlogo",
                SERVER + "/Items/s/Images/Logo/0?Format=original&Tag=l&MaxWidth=960",
            ),
            ("movie", "thumb", "image://video@/media/m.mkv/"),
            (
                "actor",
                "thumb",
                SERVER
                + "/Items/a/Images/Primary/0?Format=original&Tag=a&MaxWidth=400&MaxHeight=400&Index=0",
            ),
        ]
    )
    assert artwork.resize_urls(con.cursor()) == 4
    urls = [row[0] for row in con.execute("SELECT url FROM art ORDER BY art_id")]
    assert urls == [
        SERVER + "/Items/e/Images/Primary/0?Format=original&Tag=p&MaxWidth=640",
        SERVER + "/Items/m/Images/Primary/0?Format=original&Tag=p&MaxWidth=400",
        SERVER + "/Items/m/Images/Backdrop/1?Format=original&Tag=b&MaxWidth=1920",
        SERVER + "/Items/s/Images/Logo/0?Format=original&Tag=l&MaxWidth=800",
        "image://video@/media/m.mkv/",
        SERVER
        + "/Items/a/Images/Primary/0?Format=original&Tag=a&MaxWidth=400&MaxHeight=400&Index=0",
    ]
    assert artwork.resize_urls(con.cursor()) == 0
