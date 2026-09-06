"""End-to-end coverage for the word-history follow-ups added by issue #46:
recalling a past word ("what was yesterday's word") and the "spell that"
context-gated follow-up. Uses the same offline monkeypatch-the-source
mechanism as the sibling ``test_wod_e2e.py``/``test_golden_utterances.py``
suites, plus a real MiniCroft + adapt/padacioso pipelines so intent routing
and Adapt context matching are exercised for real, not mocked.

The positive "spell that" case seeds the OVOS-CONTEXT-1 shared-scope
"prev_wod_word" context directly onto the session object before sending the
single utterance, instead of chaining two separate
``recognizer_loop:utterance`` messages: this installed ``ovos-bus-client``
version's ``SessionManager.get()`` unconditionally replaces its stored
singleton with whatever session snapshot rides on the *next* message, so a
second utterance built from a snapshot taken before the first turn's context
write (i.e. before that mutation existed) silently reverts the context
injection. That is a pre-existing session-plumbing quirk of the pinned
bus-client, not a defect in this skill, so the test sidesteps it rather than
asserting on it.
"""
import os
from unittest.mock import patch

import pytest

# Four padatious/padacioso pipeline plugins are trained for every test in
# this module (see _PIPELINE below); ovoscope's default 5s trained-timeout
# is tuned for a single pipeline and is too tight here, which leaked
# untorn-down MiniCroft instances between tests. Raise it so teardown
# always runs.
os.environ.setdefault("OVOSCOPE_TRAINED_TIMEOUT", "180")

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

_IGNORE = [
    "mycroft.audio.play_sound",
    "recognizer_loop:audio_output_start",
    "recognizer_loop:audio_output_end",
    "enclosure.mouth.viseme_list",
    "gui.value.set",
    "gui.page.show",
    "gui.page_interaction",
    "mycroft.audio.speech.stop",
]


def _patch_parsers():
    fake = ("testword", "a word used in tests")
    import ovos_skill_word_of_the_day as mod
    return [patch.object(mod, "get_wod", return_value=fake)]


@pytest.fixture()
def minicroft():
    patches = _patch_parsers()
    for p in patches:
        p.start()
    mc = get_minicroft([SKILL_ID])
    yield mc
    mc.stop()
    for p in patches:
        p.stop()


def _send(mc, text, session):
    utterance = Message(
        "recognizer_loop:utterance",
        {"utterances": [text], "lang": LANG},
        {"session": session.serialize(), "source": "A", "destination": "B"},
    )
    capture = CaptureSession(
        mc,
        eof_msgs=["ovos.utterance.handled", "ovos.intent.unmatched"],
        ignore_messages=_IGNORE,
    )
    capture.capture(utterance, timeout=30)
    return capture.finish()


@pytest.mark.timeout(60)
def test_spell_follow_up_speaks_the_remembered_word(minicroft):
    session = Session("history-e2e-spell")
    session.lang = LANG
    session.pipeline = list(_PIPELINE)
    # seed the OVOS-CONTEXT-1 shared-scope context as if a prior "word of
    # the day" turn already ran `session.set_intent_context("prev_wod_word", ...)`
    session.set_intent_context("prev_wod_word", "testword", scope="shared", turns_remaining=3)

    followup = _send(minicroft, "spell that", session)

    types = [m.msg_type for m in followup]
    assert any(t.startswith(f"{SKILL_ID}:") and "SpellWod" in t for t in types), types
    spoken = [m.data.get("utterance") for m in followup
              if m.msg_type in ("speak", "ovos.utterance.speak")]
    assert any("testword is spelled t. e. s. t. w. o. r. d." in (u or "") for u in spoken), spoken


@pytest.mark.timeout(60)
def test_past_word_intent_recalls_a_stored_word(minicroft):
    import datetime as _dt

    skill = minicroft.plugin_skills[SKILL_ID].instance
    yesterday_date = _dt.datetime.now().date() - _dt.timedelta(days=1)
    skill.settings["word_history"] = {yesterday_date.strftime("%Y-%m-%d"): "petrichor"}

    session = Session("history-e2e-past-word")
    session.lang = LANG
    session.pipeline = list(_PIPELINE)

    followup = _send(minicroft, "tell me yesterday's word", session)

    # padatious matches drop the ".intent" file suffix from the bus event
    # name; padacioso keeps it. Accept either since routing (not the exact
    # matched pipeline) is what this assertion cares about.
    types = [m.msg_type for m in followup]
    assert any(t in (f"{SKILL_ID}:past_word", f"{SKILL_ID}:past_word.intent") for t in types), types
    spoken = [m.data.get("utterance") for m in followup
              if m.msg_type in ("speak", "ovos.utterance.speak")]
    assert any("petrichor" in (u or "") for u in spoken), spoken


@pytest.mark.timeout(60)
def test_past_word_intent_speaks_history_dialog_when_nothing_recorded(minicroft):
    skill = minicroft.plugin_skills[SKILL_ID].instance
    skill.settings["word_history"] = {}

    session = Session("history-e2e-past-word-empty")
    session.lang = LANG
    session.pipeline = list(_PIPELINE)

    followup = _send(minicroft, "what was yesterday's word", session)

    spoken = [m.data.get("utterance") for m in followup
              if m.msg_type in ("speak", "ovos.utterance.speak")]
    assert any(
        u in ("I don't have a word recorded for that day",
              "I only know words from days I was asked")
        for u in spoken
    ), spoken


@pytest.mark.timeout(60)
def test_spell_follow_up_without_prior_word_is_not_claimed(minicroft):
    session = Session("history-e2e-spell-no-prior")
    session.lang = LANG
    session.pipeline = list(_PIPELINE)

    messages = _send(minicroft, "spell that", session)

    types = [m.msg_type for m in messages]
    assert not any(t.startswith(f"{SKILL_ID}:") and "SpellWod" in t for t in types), types
