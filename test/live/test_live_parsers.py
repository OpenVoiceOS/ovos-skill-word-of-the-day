"""Live parser tests — hit the real APIs and assert each parser returns
a non-empty `(word, definition)` pair.

These are intentionally network-bound so we catch upstream markup changes
early. Skipped if the network is unavailable. Run by the `check-parsers`
scheduled workflow every 48h; when something breaks, a GitHub issue is
opened automatically.

Run locally:
    pytest test/end2end/test_live_parsers.py -v --no-header
"""
import socket
import pytest

import ovos_skill_word_of_the_day as wod


def _net_up() -> bool:
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=3).close()
        return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _net_up(), reason="no network")


def _assert_pair(pair, lang: str):
    assert isinstance(pair, tuple) and len(pair) == 2, f"{lang}: expected (word, defn)"
    word, definition = pair
    assert isinstance(word, str) and word.strip(), f"{lang}: empty word"
    assert isinstance(definition, str) and definition.strip(), f"{lang}: empty definition"
    assert len(definition) > 5, f"{lang}: definition suspiciously short: {definition!r}"


def test_live_get_wod_en():
    _assert_pair(wod.get_wod(), "en")


def test_live_get_wod_pt_pt():
    _assert_pair(wod.get_wod_pt(pt_br=False), "pt-PT")


def test_live_get_wod_pt_br():
    _assert_pair(wod.get_wod_pt(pt_br=True), "pt-BR")


def test_live_get_wod_ca():
    _assert_pair(wod.get_wod_ca(), "ca")


def test_live_get_wod_fr():
    _assert_pair(wod.get_wod_fr(), "fr")


def test_live_get_wod_gl():
    _assert_pair(wod.get_wod_gl(), "gl")
