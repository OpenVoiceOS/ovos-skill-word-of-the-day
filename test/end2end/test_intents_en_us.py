"""E2E intent-routing test for ovos-skill-word-of-the-day (en-US).

``expected_messages`` asserts the EXACT canonical message sequence (not "at
least N" / a subset): captured once via an isolated probe against this real
skill+MiniCroft before writing this fixture, using ``ovos_spec_tools``'s
``SpecMessage`` constants for every message type that has a canonical OVOS
name, same convention as the sibling ``test_wod_e2e.py`` /
``test_word_of_the_day_intent.py`` suites. ``mycroft.skill.handler.
start/complete``, ``{skill}.activate``, and ``recognizer_loop:*`` have no
``SpecMessage`` entry, so they stay as literal strings.

Run: pytest test/end2end/ -v
"""
from unittest import TestCase

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovos_spec_tools import SpecMessage
from ovoscope import End2EndTest, get_minicroft

SKILL_ID = "ovos-skill-word-of-the-day.openvoiceos"
INTENT = f"{SKILL_ID}:WordOfTheDayIntent"
LANG = "en-US"

IGNORE_MESSAGES = [
    "speak",
    "mycroft.audio.play_sound",
    # timing-dependent: mocked TTS completes near-instantly and this event's
    # presence races the capture cutoff -- same fix applied to the sibling
    # test_wod_e2e.py / test_word_of_the_day_intent.py suites.
    "recognizer_loop:audio_output_end",
]


class TestAdapt1_Wordofthedayintent(TestCase):
    """Adapt intent: WordOfTheDayIntent"""

    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_minicroft([SKILL_ID])

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, 'minicroft', None):
            cls.minicroft.stop()

    def test_tell_me_the_word_of_the_day(self):
        utterance = "tell me the word of the day"
        session = Session(f"e2e-en_us-adapt-{hash(utterance)}")
        session.lang = LANG
        session.pipeline = [
            "ovos-adapt-pipeline-plugin-high",
            "ovos-adapt-pipeline-plugin-medium",
            "ovos-adapt-pipeline-plugin-low",
        ]
        message = Message(
            "recognizer_loop:utterance",
            {"utterances": [utterance], "lang": LANG},
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
            # docstring); the handler speaks twice (dialog + definition).
            expected_messages=[
                message,
                Message(f"{SKILL_ID}.activate", {}, {"skill_id": SKILL_ID}),
                Message(SpecMessage.INTENT_MATCHED.value, {}, {"skill_id": SKILL_ID}),
                Message(SpecMessage.INTENT_HANDLER_START.value, {}, {"skill_id": SKILL_ID}),
                Message(INTENT, {}, {"skill_id": SKILL_ID}),
                Message("mycroft.skill.handler.start", {}, {"skill_id": SKILL_ID}),
                Message(SpecMessage.SPEAK.value, {}, {"skill_id": SKILL_ID}),
                Message("recognizer_loop:audio_output_start", {}, {"skill_id": SKILL_ID}),
                Message(SpecMessage.SPEAK.value, {}, {"skill_id": SKILL_ID}),
                Message("recognizer_loop:audio_output_start", {}, {"skill_id": SKILL_ID}),
                Message("mycroft.skill.handler.complete", {}, {"skill_id": SKILL_ID}),
                Message(SpecMessage.INTENT_HANDLER_COMPLETE.value, {}, {"skill_id": SKILL_ID}),
                Message(SpecMessage.UTTERANCE_HANDLED.value, {}, {"skill_id": SKILL_ID}),
            ],
            test_msg_context=False,
        )
        test.execute(timeout=30)
