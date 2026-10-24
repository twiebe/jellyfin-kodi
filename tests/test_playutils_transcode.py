# -*- coding: utf-8 -*-

import pytest

from jellyfin_kodi.helper import playutils
from jellyfin_kodi.helper.playutils import PlayUtils, Transcode


class ApiClient:
    class config:
        data = {"auth.token": ""}


SOURCE = {
    "TranscodingUrl": "/videos/1/master.m3u8?AudioStreamIndex=1&SubtitleStreamIndex=2",
    "MediaStreams": [{"Type": "Video"}],
    "Protocol": "File",
}


@pytest.fixture
def transcode(monkeypatch):
    """Run PlayUtils.transcode with skipDialogTranscode set to the given mode."""
    asked = []

    def run(mode):
        values = {"skipDialogTranscode": str(mode), "videoPreferredCodec": "H264/AVC"}
        monkeypatch.setattr(playutils, "settings", lambda key: values[key])

        play = PlayUtils({"MediaType": "Video"}, api_client=ApiClient)
        play.info["ServerAddress"] = "http://server"
        play.get_audio_subs = (
            lambda source, audio, subtitle: asked.append(mode) or "&AudioStreamIndex=3"
        )
        play.get_transcoding_audio_bitrate = lambda: 192
        play.get_max_bitrate = lambda: 10000
        play.get_resolution = lambda: (1920, 1080)
        play.transcode(dict(SOURCE))
        return play.info["Path"], asked

    return run


def test_disabled_keeps_the_servers_tracks(transcode):
    path, asked = transcode(Transcode.Disabled)
    assert "AudioStreamIndex=1" in path
    assert "SubtitleStreamIndex=2" in path
    assert asked == []


@pytest.mark.parametrize(
    "mode",
    [Transcode.Enabled, Transcode.Audio, Transcode.Subtitle, Transcode.MediaDefault],
)
def test_other_modes_choose_tracks(transcode, mode):
    path, asked = transcode(mode)
    assert "AudioStreamIndex=1" not in path
    assert "SubtitleStreamIndex=2" not in path
    assert "AudioStreamIndex=3" in path
    assert asked == [mode]
