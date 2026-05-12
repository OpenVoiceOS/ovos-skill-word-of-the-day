"""Unit tests for per-language parsers using real HTML captured from upstream.

Fixtures in test/unit/fixtures/ are real responses trimmed to the relevant
DOM subtree. When a site changes markup, re-capture the fixture and update
the parser. A separate scheduled job (check-parsers.yml) hits the real APIs
periodically to flag drift early.
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
    """dictionary.com — captured 2026-05-12, word 'rigmarole'."""

    def test_parses_dictionary_com(self):
        html = _fixture("dictionary_com.html")
        with patch.object(wod, "_http_get", return_value=_fake_response(text=html)):
            word, definition = wod.get_wod()
        self.assertEqual(word, "rigmarole")
        self.assertEqual(definition, "an elaborate or complicated procedure")


class TestGetWodPortuguese(TestCase):
    """Priberam — captured 2026-05-12, word 'majólica' (two-step: home → word page)."""

    def _run(self, pt_br: bool):
        home = _fixture("priberam_home.html")
        word_page = _fixture("priberam_word.html")
        with patch.object(wod, "_http_get", side_effect=[
            _fake_response(text=home),
            _fake_response(text=word_page),
        ]):
            return wod.get_wod_pt(pt_br=pt_br)

    def test_parses_priberam_pt_pt(self):
        word, definition = self._run(pt_br=False)
        self.assertEqual(word, "majólica")
        self.assertIn("cerâmica", definition)

    def test_parses_priberam_pt_br(self):
        word, definition = self._run(pt_br=True)
        self.assertEqual(word, "majólica")
        self.assertIn("cerâmica", definition)


class TestGetWodCatalan(TestCase):
    """rodamots.cat — captured 2026-05-12, entry 'a ranvespre' (two-step: home → entry)."""

    def test_parses_rodamots_two_step(self):
        index = _fixture("rodamots_index.html")
        entry = _fixture("rodamots_entry.html")
        with patch.object(wod, "_http_get", side_effect=[
            _fake_response(text=index),
            _fake_response(text=entry),
        ]):
            word, definition = wod.get_wod_ca()
        self.assertEqual(word, "a ranvespre")
        self.assertEqual(definition, "A entrada de fosc, a l’horabaixa.")


class TestGetWodFrench(TestCase):
    """fr.wiktionary.org API — captured 2026-05-12, 'sans tambour ni trompette'."""

    def test_parses_wiktionary_api(self):
        payload = json.loads(_fixture("wiktionary_fr.json"))
        with patch.object(wod, "_http_get", return_value=_fake_response(json_data=payload)):
            word, definition = wod.get_wod_fr()
        self.assertEqual(word, "sans tambour ni trompette")
        self.assertEqual(
            definition,
            "Sans avertir quiconque, sans se faire remarquer, sans bruit, en secret.",
        )


class TestGetWodGalician(TestCase):
    """portaldaspalabras.gal — captured 2026-05-12, 'soidade' (two-step: home → word)."""

    def test_parses_portaldaspalabras_two_step(self):
        home = _fixture("portaldaspalabras_home.html")
        word_page = _fixture("portaldaspalabras_word.html")
        with patch.object(wod, "_http_get", side_effect=[
            _fake_response(text=home),
            _fake_response(text=word_page),
        ]):
            word, definition = wod.get_wod_gl()
        self.assertEqual(word, "soidade")
        self.assertTrue(definition, "definition should not be empty")


class TestNormalizeDefinitionText(TestCase):
    def test_collapses_whitespace_and_punctuation(self):
        out = wod._normalize_definition_text("foo   bar  ,  baz .  qux")
        self.assertEqual(out, "foo bar, baz. qux")
