"""Parity coverage for every "spell that" phrasing accepted by
``spell_wod.intent`` (the file-intent migration of the Adapt-era
``SpellWodIntent``, gated on the ``spell_wod.voc`` wording plus the
"prev_wod_word" context). Each phrasing must resolve to
``handle_spell_wod_intent`` when the session already carries an active
"prev_wod_word" context (seeded directly via
``session.set_intent_context``, same approach as the sibling
``test_history_e2e.py`` suite), and must NOT be claimed by the skill in a
fresh session that never asked for the word of the day.
"""
from unittest.mock import patch

import pytest

ovoscope = pytest.importorskip("ovoscope", reason="ovoscope not installed")

from ovos_bus_client.message import Message  # noqa: E402
from ovos_bus_client.session import Session  # noqa: E402
from ovoscope import CaptureSession, get_minicroft  # noqa: E402

SKILL_ID = "ovos-skill-word-of-the-day.openvoiceos"
LANG = "en-US"

_PIPELINE = [
    "ovos-padatious-pipeline-plugin-high",
    "ovos-padacioso-pipeline-plugin-high",
    "ovos-padatious-pipeline-plugin-medium",
    "ovos-padacioso-pipeline-plugin-medium",
]

_IGNORE = ["mycroft.audio.play_sound"]

# every spell_wod.intent template line, verbatim
SPELL_PHRASINGS = [
    "spell that",
    "spell that word",
    "how do you spell that",
    "how do you spell it",
    "spell it",
    "spell it for me",
    "spell it out",
    "spell it out for me",
    "can you spell that",
    "can you spell it",
]


@pytest.fixture(scope="module")
def minicroft():
    mc = get_minicroft([SKILL_ID])
    yield mc
    mc.stop()


def _session(session_id, prev_word=None):
    session = Session(session_id)
    session.lang = LANG
    session.pipeline = list(_PIPELINE)
    if prev_word is not None:
        session.set_intent_context("prev_wod_word", prev_word, scope="shared", turns_remaining=3)
    return session


def _fire(mc, session, text):
    utterance = Message(
        "recognizer_loop:utterance",
        {"utterances": [text], "lang": LANG},
        {"session": session.serialize(), "source": "A", "destination": "B"},
    )
    capture = CaptureSession(
        mc,
        eof_msgs=["mycroft.skill.handler.complete", "ovos.intent.unmatched"],
        ignore_messages=_IGNORE,
    )
    capture.capture(utterance, timeout=30)
    messages = capture.finish()
    spoken = [m.data.get("utterance", "") for m in messages
              if m.msg_type in ("speak", "ovos.utterance.speak")]
    types = [m.msg_type for m in messages]
    return spoken, types


@pytest.mark.timeout(60)
@pytest.mark.parametrize("phrasing", SPELL_PHRASINGS, ids=SPELL_PHRASINGS)
def test_spell_phrasing_speaks_word_with_active_context(minicroft, phrasing):
    session = _session(f"parity-positive-{phrasing}", prev_word="serendipity")
    spoken, types = _fire(minicroft, session, phrasing)
    assert any(t.startswith(f"{SKILL_ID}:") for t in types), (phrasing, types)
    assert any("serendipity" in u.lower() for u in spoken), (phrasing, spoken)


@pytest.mark.timeout(60)
@pytest.mark.parametrize("phrasing", SPELL_PHRASINGS, ids=SPELL_PHRASINGS)
def test_spell_phrasing_does_not_fire_without_prior_context(minicroft, phrasing):
    session = _session(f"parity-negative-{phrasing}")
    _, types = _fire(minicroft, session, phrasing)
    claimed = any(t.startswith(f"{SKILL_ID}:") for t in types)
    assert not claimed, f"{phrasing!r} with no prior word was claimed by {SKILL_ID}: {types!r}"
