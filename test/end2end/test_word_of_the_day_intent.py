"""End-to-end tests asserting each locale routes to its own word source.

``expected_messages`` asserts the EXACT canonical message sequence (not "at
least N"), captured once via an isolated probe against this real
skill+MiniCroft before writing this fixture, using ``ovos_spec_tools``'s
``SpecMessage`` constants for every message type that has a canonical OVOS
name. ``End2EndTest`` defaults to ``ignore_gui=True`` regardless of
``ignore_messages``, so the ``gui.value.set``/``gui.page.show`` this
handler's ``self.gui.show_text(...)`` call emits never reach the assertion
-- confirmed by an isolated probe (see this repo's PR description) that
they only show up on a raw ``CaptureSession`` with no ``ignore_gui``.
``mycroft.skill.handler.start/complete``, ``{skill}.activate``, and
``recognizer_loop:*`` have no ``SpecMessage`` entry, so they stay as literal
strings, same as the previous version of this file.
"""
import sys
from unittest import TestCase

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovos_spec_tools import SpecMessage
from ovos_utils.log import LOG
from ovoscope import End2EndTest, get_minicroft


SKILL_ID = "ovos-skill-word-of-the-day.openvoiceos"
INTENT = f"{SKILL_ID}:WordOfTheDayIntent"
SECONDARY_LANGS = ["ca-ES", "fr-FR", "gl-ES", "pt-PT"]
SOURCE_FUNCTIONS = ("get_wod", "get_wod_ca", "get_wod_fr",
                    "get_wod_gl", "get_wod_pt")
IGNORE_MESSAGES = [
    "ovos.common_play.stop.response",
    "common_query.openvoiceos.stop.response",
    "persona.openvoiceos.stop.response",
    "stop.openvoiceos.stop.response",
    # timing-dependent: observed present or absent across otherwise-identical
    # runs (mocked TTS completes near-instantly, racing the capture cutoff).
    # Ignored here for a deterministic exact-count assertion below, same as
    # this suite's sibling test_wod_e2e.py (which never observed it at all).
    "recognizer_loop:audio_output_end",
]


class TestWordOfTheDayIntentRouting(TestCase):
    @classmethod
    def setUpClass(cls):
        LOG.set_level("DEBUG")
        cls.calls = []
        cls.minicroft = get_minicroft(
            [SKILL_ID],
            secondary_langs=SECONDARY_LANGS,
        )
        skill = cls.minicroft.plugin_skills[SKILL_ID].instance
        cls.skill_module = sys.modules[skill.__class__.__module__]
        cls.originals = {
            name: getattr(cls.skill_module, name)
            for name in SOURCE_FUNCTIONS
        }
        for source_name in SOURCE_FUNCTIONS:
            setattr(cls.skill_module, source_name, cls._source(source_name))

    @classmethod
    def tearDownClass(cls):
        for name, source in getattr(cls, "originals", {}).items():
            setattr(cls.skill_module, name, source)
        if getattr(cls, "minicroft", None):
            cls.minicroft.stop()
        LOG.set_level("CRITICAL")

    @classmethod
    def _source(cls, source_name):
        def source(*args, **kwargs):
            cls.calls.append((source_name, args, kwargs))
            return f"{source_name}-word", f"{source_name} definition"
        return source

    def setUp(self):
        self.calls.clear()

    def _assert_routes_to_source(self, utterance, lang, source_name):
        session = Session(f"wod-{lang}-{abs(hash(utterance))}")
        session.lang = lang
        session.pipeline = ["ovos-padacioso-pipeline-plugin-high"]
        message = Message(
            "recognizer_loop:utterance",
            {"utterances": [utterance], "lang": lang},
            {"session": session.serialize()},
        )

        test = End2EndTest(
            minicroft=self.minicroft,
            skill_ids=[SKILL_ID],
            eof_msgs=["ovos.utterance.handled"],
            flip_points=["recognizer_loop:utterance"],
            ignore_messages=IGNORE_MESSAGES,
            source_message=message,
            activation_points=[INTENT],
            # exact sequence, captured via an isolated probe (see module
            # docstring); the handler speaks twice (dialog + definition),
            # with a GUI update in between.
            expected_messages=[
                message,
                Message(f"{SKILL_ID}.activate", {}, {"skill_id": SKILL_ID}),
                Message(SpecMessage.INTENT_MATCHED.value, {}, {"skill_id": SKILL_ID}),
                Message(SpecMessage.INTENT_HANDLER_START.value, {}, {"skill_id": SKILL_ID}),
                Message(INTENT, {}, {"skill_id": SKILL_ID}),
                Message("mycroft.skill.handler.start", {},
                        {"skill_id": SKILL_ID}),
                Message(SpecMessage.SPEAK.value, {}, {"skill_id": SKILL_ID}),
                Message("recognizer_loop:audio_output_start", {}, {"skill_id": SKILL_ID}),
                Message(SpecMessage.SPEAK.value, {}, {"skill_id": SKILL_ID}),
                Message("recognizer_loop:audio_output_start", {}, {"skill_id": SKILL_ID}),
                Message("mycroft.skill.handler.complete", {},
                        {"skill_id": SKILL_ID}),
                Message(SpecMessage.INTENT_HANDLER_COMPLETE.value, {}, {"skill_id": SKILL_ID}),
                Message(SpecMessage.UTTERANCE_HANDLED.value, {}, {"skill_id": SKILL_ID}),
            ],
        )
        test.execute(timeout=15)
        self.assertEqual(self.calls, [(source_name, (), {})])

    def test_english_routes_to_dictionary_source(self):
        self._assert_routes_to_source("word of the day", "en-US", "get_wod")

    def test_french_routes_to_wiktionary_source(self):
        self._assert_routes_to_source("mot du jour", "fr-FR", "get_wod_fr")

    def test_portuguese_routes_to_priberam_source(self):
        self._assert_routes_to_source("palavra do dia", "pt-PT", "get_wod_pt")

    def test_galician_routes_to_portal_das_palabras_source(self):
        self._assert_routes_to_source("palabra do día", "gl-ES", "get_wod_gl")

    def test_catalan_routes_to_rodamots_source(self):
        self._assert_routes_to_source("mot del dia", "ca-ES", "get_wod_ca")
