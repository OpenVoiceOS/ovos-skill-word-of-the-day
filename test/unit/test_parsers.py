"""Unit tests for per-language parsers using recorded HTML fixtures.

Real network calls are blocked; each parser receives a small HTML snippet
captured from the upstream site that matches the selectors the parser
uses. If a site changes its markup, the matching fixture must be updated.
"""
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch, MagicMock

import ovos_skill_word_of_the_day as wod

FIXTURES = Path(__file__).parent / "fixtures"


def _fake_response(*, text=None, content=None, json_data=None, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.text = text if text is not None else (content.decode("utf-8") if content else "")
    resp.content = content if content is not None else (text.encode("utf-8") if text else b"")
    resp.json = MagicMock(return_value=json_data if json_data is not None else {})
    resp.raise_for_status = MagicMock()
    return resp


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class TestGetWodEnglish(TestCase):
    def test_parses_dictionary_com(self):
        html = _fixture("dictionary_com.html")
        with patch.object(wod, "_http_get", return_value=_fake_response(text=html)):
            word, definition = wod.get_wod()
        self.assertEqual(word, "serendipity")
        self.assertIn("aptitude for making desirable discoveries", definition)


class TestGetWodPortuguese(TestCase):
    def test_parses_priberam_pt_pt(self):
        html = _fixture("priberam.html")
        with patch.object(wod, "_http_get", return_value=_fake_response(text=html)):
            word, definition = wod.get_wod_pt(pt_br=False)
        self.assertEqual(word, "desígnio")
        self.assertIn("planeia fazer", definition)

    def test_parses_priberam_pt_br(self):
        html = _fixture("priberam.html")
        with patch.object(wod, "_http_get", return_value=_fake_response(text=html)):
            word, _ = wod.get_wod_pt(pt_br=True)
        self.assertEqual(word, "desígnio_br")


class TestGetWodCatalan(TestCase):
    def test_parses_rodamots_two_step(self):
        index = _fixture("rodamots_index.html")
        entry = _fixture("rodamots_entry.html")
        with patch.object(wod, "_http_get", side_effect=[
            _fake_response(text=index),
            _fake_response(text=entry),
        ]):
            word, definition = wod.get_wod_ca()
        self.assertEqual(word, "atzucac")
        self.assertEqual(definition, "Carrer sense sortida.")


class TestGetWodFrench(TestCase):
    def test_parses_wiktionary_api(self):
        html = _fixture("wiktionary_fr_main_etl.html")
        payload = {"parse": {"text": {"*": html}}}
        with patch.object(wod, "_http_get", return_value=_fake_response(json_data=payload)):
            word, definition = wod.get_wod_fr()
        self.assertEqual(word, "aubaine")
        self.assertIn("Avantage inattendu", definition)
        # Nested ul should be stripped
        self.assertNotIn("Exemple ignoré", definition)


class TestGetWodGalician(TestCase):
    def test_parses_portaldaspalabras_two_step(self):
        index = _fixture("portaldaspalabras_index.html")
        word_page = _fixture("portaldaspalabras_word.html")
        with patch.object(wod, "_http_post", side_effect=[
            _fake_response(content=index.encode("utf-8")),
            _fake_response(content=word_page.encode("utf-8")),
        ]):
            word, definition = wod.get_wod_gl()
        self.assertEqual(word, "arrequecer")
        self.assertIn("Mellorar", definition)


class TestNormalizeDefinitionText(TestCase):
    def test_collapses_whitespace_and_punctuation(self):
        out = wod._normalize_definition_text("foo   bar  ,  baz .  qux")
        self.assertEqual(out, "foo bar, baz. qux")
