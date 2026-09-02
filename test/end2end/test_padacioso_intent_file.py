"""Proves ``WordOfTheDayIntent`` is registered from an ``.intent`` file, not
adapt vocabulary.

``WordOfTheDayIntent`` used to be an ``IntentBuilder(...).require(...)``
registration, which only the adapt pipeline can match. This test runs a
MiniCroft with adapt excluded from the session pipeline (only the
padacioso -- keyword-free, regex-based -- pipeline is active) and asserts
"word of the day" (en-US) still routes to the skill's intent handler. This
would fail against the pre-migration adapt-only registration, since adapt
never runs for this session.

``expected_messages`` asserts the EXACT canonical message sequence,
captured via an isolated probe against this real skill+MiniCroft, using
``ovos_spec_tools``'s ``SpecMessage`` constants for every message type
that has a canonical OVOS name -- same shape as the sibling
``test_wod_e2e.py``/``test_word_of_the_day_intent.py`` suites.
"""
from unittest import TestCase
from unittest.mock import patch

import pytest

ovoscope = pytest.importorskip("ovoscope", reason="ovoscope not installed")

from ovos_bus_client.message import Message  # noqa: E402
from ovos_bus_client.session import Session  # noqa: E402
from ovos_spec_tools import SpecMessage  # noqa: E402
from ovos_utils.log import LOG  # noqa: E402
from ovoscope import End2EndTest, get_minicroft  # noqa: E402

SKILL_ID = "ovos-skill-word-of-the-day.openvoiceos"
INTENT = f"{SKILL_ID}:WordOfTheDayIntent"

# no adapt pipeline stage on purpose: only a keyword-free/regex intent
# matcher is active, so a match here can only come from the .intent file.
_PADACIOSO_ONLY_PIPELINE = ["ovos-padacioso-pipeline-plugin-high"]

_IGNORE = [
    "enclosure.mouth.viseme_list",
    "gui.value.set",
    "gui.page.show",
    "gui.page_interaction",
    "mycroft.audio.speech.stop",
    "ovos.common_play.stop.response",
    "recognizer_loop:audio_output_end",
]


class TestWordOfTheDayIntentFileMatchesWithoutAdapt(TestCase):
    @classmethod
    def setUpClass(cls):
        LOG.set_level("DEBUG")
        cls._patch = patch(
            "ovos_skill_word_of_the_day.get_wod",
            return_value=("testword", "a word used in tests"),
        )
        cls._patch.start()
        cls.minicroft = get_minicroft([SKILL_ID])

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "minicroft", None):
            cls.minicroft.stop()
        cls._patch.stop()
        LOG.set_level("CRITICAL")

    def test_en_word_of_the_day_matches_without_adapt(self):
        lang = "en-US"
        utterance = "word of the day"

        session = Session("wod-padacioso-only")
        session.lang = lang
        session.pipeline = _PADACIOSO_ONLY_PIPELINE

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
            ignore_messages=_IGNORE,
            source_message=message,
            activation_points=[INTENT],
            expected_messages=[
                message,
                Message(f"{SKILL_ID}.activate", {}, {"skill_id": SKILL_ID}),
                Message(SpecMessage.INTENT_MATCHED.value, {}, {"skill_id": SKILL_ID}),
                Message(SpecMessage.INTENT_HANDLER_START.value, {}, {"skill_id": SKILL_ID}),
                Message(INTENT, {}, {"skill_id": SKILL_ID}),
                Message("mycroft.skill.handler.start",
                        {"name": "WordOfTheDaySkill.handle_word_of_the_day_intent"},
                        {"skill_id": SKILL_ID}),
                Message(SpecMessage.SPEAK.value, {}, {"skill_id": SKILL_ID}),
                Message("recognizer_loop:audio_output_start", {}, {"skill_id": SKILL_ID}),
                Message(SpecMessage.SPEAK.value, {}, {"skill_id": SKILL_ID}),
                Message("recognizer_loop:audio_output_start", {}, {"skill_id": SKILL_ID}),
                # prev_wod_word session context write (spell-that follow-up)
                Message("add_context", {}, {"skill_id": SKILL_ID}),
                Message("mycroft.skill.handler.complete",
                        {"name": "WordOfTheDaySkill.handle_word_of_the_day_intent"},
                        {"skill_id": SKILL_ID}),
                Message(SpecMessage.INTENT_HANDLER_COMPLETE.value, {}, {"skill_id": SKILL_ID}),
                Message(SpecMessage.UTTERANCE_HANDLED.value, {}, {"skill_id": SKILL_ID}),
            ],
        )
        test.execute(timeout=30)
