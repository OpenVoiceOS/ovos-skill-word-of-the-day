"""End-to-end coverage for the word-history follow-ups added by issue #46:
recalling a past word ("what was yesterday's word") and the "spell that"
context-gated follow-up. Uses the same offline monkeypatch-the-source
mechanism as the sibling ``test_wod_e2e.py``/``test_golden_utterances.py``
suites, plus a real MiniCroft + adapt/padacioso pipelines so intent routing
and Adapt context matching are exercised for real, not mocked.

The positive "spell that" case seeds the Adapt context directly onto the
session object before sending the single utterance, instead of chaining two
separate ``recognizer_loop:utterance`` messages: this installed
``ovos-bus-client`` version's ``SessionManager.get()`` unconditionally
replaces its stored singleton with whatever session snapshot rides on the
*next* message, so a second utterance built from a snapshot taken before the
first turn's ``self.set_context`` call (i.e. before that mutation existed)
silently reverts the context injection. That is a pre-existing
session-plumbing quirk of the pinned bus-client, not a defect in this skill,
so the test sidesteps it rather than asserting on it.
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
    "ovos-padacioso-pipeline-plugin-high",
    "ovos-adapt-pipeline-plugin-high",
]

_IGNORE = [
    "ovos.utterance.speak",
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


@pytest.mark.timeout(300)
def test_spell_follow_up_speaks_the_remembered_word(minicroft):
    session = Session("history-e2e-spell")
    session.lang = LANG
    session.pipeline = list(_PIPELINE)
    # seed the Adapt context as if a prior "word of the day" turn already
    # ran `self.set_context("prev_wod_word", "testword")`
    session.context.inject_context({
        "confidence": 1.0,
        "data": [("testword", "ovos_skill_word_of_the_day_openvoiceosprev_wod_word")],
        "match": "testword",
        "key": "testword",
        "origin": "",
    })

    followup = _send(minicroft, "spell that", session)

    types = [m.msg_type for m in followup]
    assert any(t == f"{SKILL_ID}:SpellWodIntent" for t in types), types
    spoken = [m.data.get("utterance") for m in followup if m.msg_type == "speak"]
    assert any("testword is spelled t. e. s. t. w. o. r. d." in (u or "") for u in spoken), spoken


@pytest.mark.timeout(300)
def test_past_word_intent_recalls_a_stored_word(minicroft):
    import datetime as _dt

    skill = minicroft.plugin_skills[SKILL_ID].instance
    yesterday_date = _dt.datetime.now().date() - _dt.timedelta(days=1)
    skill.settings["word_history"] = {yesterday_date.strftime("%Y-%m-%d"): "petrichor"}

    session = Session("history-e2e-past-word")
    session.lang = LANG
    session.pipeline = list(_PIPELINE)

    followup = _send(minicroft, "tell me yesterday's word", session)

    types = [m.msg_type for m in followup]
    assert any(t == f"{SKILL_ID}:past_word.intent" for t in types), types
    spoken = [m.data.get("utterance") for m in followup if m.msg_type == "speak"]
    assert any("petrichor" in (u or "") for u in spoken), spoken


@pytest.mark.timeout(300)
def test_past_word_intent_speaks_history_dialog_when_nothing_recorded(minicroft):
    skill = minicroft.plugin_skills[SKILL_ID].instance
    skill.settings["word_history"] = {}

    session = Session("history-e2e-past-word-empty")
    session.lang = LANG
    session.pipeline = list(_PIPELINE)

    followup = _send(minicroft, "what was yesterday's word", session)

    spoken = [m.data.get("utterance") for m in followup if m.msg_type == "speak"]
    assert any(
        u in ("I don't have a word recorded for that day",
              "I only know words from days I was asked")
        for u in spoken
    ), spoken


@pytest.mark.timeout(300)
def test_spell_follow_up_without_prior_word_is_not_claimed(minicroft):
    session = Session("history-e2e-spell-no-prior")
    session.lang = LANG
    session.pipeline = list(_PIPELINE)

    messages = _send(minicroft, "spell that", session)

    types = [m.msg_type for m in messages]
    assert not any(t.startswith(f"{SKILL_ID}:SpellWodIntent") for t in types), types
