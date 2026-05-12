"""End-to-end tests for WordOfTheDaySkill via ovoscope.

Verifies that the adapt intent `WordOfTheDayIntent` matches for each supported
language and that the handler runs to completion. Parser functions that fetch
the word from external sites are monkey-patched so tests run offline.
"""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch

import pytest

ovoscope = pytest.importorskip("ovoscope", reason="ovoscope not installed")

from ovos_bus_client.message import Message  # noqa: E402
from ovos_bus_client.session import Session  # noqa: E402
from ovos_utils.log import LOG  # noqa: E402
from ovoscope import End2EndTest, get_minicroft  # noqa: E402

SKILL_ID = "ovos-skill-word-of-the-day.openvoiceos"

_IGNORE = [
    "speak",
    "enclosure.mouth.viseme_list",
    "gui.value.set",
    "gui.page.show",
    "gui.page_interaction",
    "mycroft.audio.speech.stop",
    "ovos.common_play.stop.response",
]


def _patch_parsers():
    """Patch every per-language parser to return a fixed (word, definition)."""
    fake = ("testword", "a word used in tests")
    import ovos_skill_word_of_the_day as mod
    targets = [
        "get_wod", "get_wod_pt", "get_wod_fr",
        "get_wod_ca", "get_wod_gl",
    ]
    return [patch.object(mod, name, return_value=fake) for name in targets if hasattr(mod, name)]


class _WODBase(TestCase):
    lang = "en-US"
    utterance = "tell me the word of the day"

    @classmethod
    def setUpClass(cls):
        LOG.set_level("DEBUG")
        cls._patches = _patch_parsers()
        for p in cls._patches:
            p.start()
        cls.minicroft = get_minicroft(
            [SKILL_ID],
            secondary_langs=["pt-PT", "pt-BR", "fr-FR", "ca-ES", "gl-ES", "de-DE", "es-ES"],
        )

    @classmethod
    def tearDownClass(cls):
        if cls.minicroft:
            cls.minicroft.stop()
        for p in cls._patches:
            p.stop()
        LOG.set_level("CRITICAL")

    def _run(self, utterance: str, lang: str):
        session = Session(f"wod-{lang}")
        session.lang = lang
        session.pipeline = ["ovos-adapt-pipeline-plugin-high"]

        message = Message(
            "recognizer_loop:utterance",
            {"utterances": [utterance], "lang": lang},
            {"session": session.serialize()},
        )

        final_session = deepcopy(session)
        final_session.active_skills = [(SKILL_ID, 0.0)]

        test = End2EndTest(
            minicroft=self.minicroft,
            skill_ids=[SKILL_ID],
            eof_msgs=["ovos.utterance.handled"],
            flip_points=["recognizer_loop:utterance"],
            ignore_messages=_IGNORE,
            source_message=message,
            final_session=final_session,
            activation_points=[f"{SKILL_ID}:WordOfTheDayIntent"],
            expected_messages=[
                message,
                Message(f"{SKILL_ID}.activate", {}, {"skill_id": SKILL_ID}),
                Message(f"{SKILL_ID}:WordOfTheDayIntent",
                        {"utterance": utterance, "lang": lang},
                        {"skill_id": SKILL_ID}),
                Message("mycroft.skill.handler.start",
                        {"name": "WordOfTheDaySkill.handle_word_of_the_day_intent"},
                        {"skill_id": SKILL_ID}),
                Message("mycroft.skill.handler.complete",
                        {"name": "WordOfTheDaySkill.handle_word_of_the_day_intent"},
                        {"skill_id": SKILL_ID}),
                Message("ovos.utterance.handled", {}, {"skill_id": SKILL_ID}),
            ],
        )
        test.execute(timeout=30)


class TestWODEnglish(_WODBase):
    def test_en_word_of_the_day(self):
        self._run("tell me the word of the day", "en-US")

    def test_en_short(self):
        self._run("word of the day", "en-US")


class TestWODPortuguese(_WODBase):
    def test_pt_word_of_the_day(self):
        # Use the literal pt-PT vocab entry; falls back gracefully if not registered
        self._run("palavra do dia", "pt-PT")


class TestWODFrench(_WODBase):
    def test_fr_word_of_the_day(self):
        self._run("mot du jour", "fr-FR")


