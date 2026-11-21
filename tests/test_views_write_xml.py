# -*- coding: utf-8 -*-

import os
import xml.etree.ElementTree as etree

from jellyfin_kodi.views import write_xml


def _node(label):
    xml = etree.Element("node", {"order": "0"})
    etree.SubElement(xml, "label").text = label
    return xml


def test_new_file_is_written_like_elementtree_writes_it(tmp_path):
    file = str(tmp_path / "all.xml")
    expected = str(tmp_path / "expected.xml")
    write_xml(_node("Movies"), file)
    etree.ElementTree(_node("Movies")).write(
        expected, encoding="utf-8", xml_declaration=True
    )
    with open(file, "rb") as a, open(expected, "rb") as b:
        assert a.read() == b.read()


# The nodes are written at every start and sync: flash storage wears out
def test_unchanged_file_is_not_written_again(tmp_path):
    file = str(tmp_path / "all.xml")
    write_xml(_node("Movies"), file)
    os.utime(file, (0, 0))
    write_xml(_node("Movies"), file)
    assert os.stat(file).st_mtime == 0


def test_changed_file_is_written(tmp_path):
    file = str(tmp_path / "all.xml")
    write_xml(_node("Movies"), file)
    write_xml(_node("Films"), file)
    assert etree.parse(file).getroot().find("label").text == "Films"
