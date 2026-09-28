"""Multilingual golden-utterance end-to-end coverage for
ovos-skill-word-of-the-day.

test_golden_utterances.py only exercises en-US via a single shared
MiniCroft. Every locale under locale/<lang>/intents/ ships real
word_of_the_day.intent, past_word.intent and spell_wod.intent files; this
suite gives each of them a golden row set derived mechanically from that
locale's own template files (see golden_utterances_<lang>.jsonl and the
generator that produced them).

One MiniCroft is booted PER LOCALE in turn (ovos-skill-alerts' shared-
MiniCroft multilang pattern is skipped on dev there for a known ovoscope
harness bug when many secondary_langs are booted at once; the per-locale
boot mirrors ovos-skill-date-time's test_intents_it_it.py instead). One
test item per locale runs every row for that locale and aggregates
failures into one assertion.

spell_wod.intent only fires when the "prev_wod_word" session context is
active (requires_context on the handler). Rows for that intent carry
requires_context: true, and the session seeds that context before firing
(same technique as test_spell_wod_parity.py).
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_minicroft

SKILL_ID = "ovos-skill-word-of-the-day.openvoiceos"
PREV_WOD_WORD_CONTEXT = "prev_wod_word"

_PIPELINE = [
    "ovos-padacioso-pipeline-plugin-high",
    "ovos-padacioso-pipeline-plugin-medium",
    "ovos-padacioso-pipeline-plugin-low",
]

_IGNORE = [
    "speak",
    "ovos.utterance.speak",
    "mycroft.audio.play_sound",
    "recognizer_loop:audio_output_start",
    "recognizer_loop:audio_output_end",
]

END2END_DIR = Path(__file__).parent

LANGS = ["ca-ES", "da-DK", "de-DE", "en-US", "es-ES", "eu-ES", "fr-FR",
         "gl-ES", "it-IT", "kab", "nl-NL", "pt-BR", "pt-PT", "sv-SE"]


def _patch_parsers():
    fake = ("testword", "a word used in tests")
    import ovos_skill_word_of_the_day as mod
    targets = ["get_wod", "get_wod_pt", "get_wod_fr", "get_wod_ca", "get_wod_gl"]
    return [patch.object(mod, name, return_value=fake) for name in targets if hasattr(mod, name)]


def _matches_intent(msg_type: str, skill_id: str, intent_label: str) -> bool:
    prefix = f"{skill_id}:"
    if not msg_type.startswith(prefix):
        return False
    observed = msg_type[len(prefix):]
    observed_base = observed.rsplit(".", 1)[0] if observed.endswith(".intent") else observed
    expected_base = intent_label.rsplit(".", 1)[0] if intent_label.endswith(".intent") else intent_label
    return observed_base == expected_base


def _load_rows(lang):
    path = END2END_DIR / f"golden_utterances_{lang}.jsonl"
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("needs_manual"):
                continue
            rows.append(row)
    return rows


def _types(mc, text, lang, session_id, requires_context=False):
    session = Session(session_id)
    session.lang = lang
    session.pipeline = list(_PIPELINE)
    session.blacklisted_intents = []
    if requires_context:
        session.set_intent_context(PREV_WOD_WORD_CONTEXT, "testword",
                                    scope="shared", turns_remaining=3)
    utterance = Message(
        "recognizer_loop:utterance",
        {"utterances": [text], "lang": lang},
        {"session": session.serialize(), "source": "A", "destination": "B"},
    )
    capture = CaptureSession(
        mc,
        eof_msgs=["ovos.utterance.handled", "ovos.intent.unmatched"],
        ignore_messages=_IGNORE,
    )
    capture.capture(utterance, timeout=30)
    return [m.msg_type for m in capture.finish()]


@pytest.fixture(params=LANGS)
def locale_minicroft(request):
    lang = request.param
    patches = _patch_parsers()
    for p in patches:
        p.start()
    mc = get_minicroft([SKILL_ID], max_wait=150, lang=lang)
    yield lang, mc
    mc.stop()
    for p in patches:
        p.stop()


@pytest.mark.timeout(300)
def test_golden_utterances_per_locale(locale_minicroft):
    lang, mc = locale_minicroft
    rows = _load_rows(lang)
    assert rows, f"no golden rows loaded for {lang}"
    failures = []
    for row in rows:
        types = _types(mc, row["utterance"], lang,
                        f"golden-{lang}-{row['utterance']}",
                        requires_context=row.get("requires_context", False))
        if not any(_matches_intent(t, SKILL_ID, row["intent_label"]) for t in types):
            failures.append(
                f"{row['utterance']!r}: expected {SKILL_ID}:{row['intent_label']}, got {types!r}"
            )
    assert not failures, "\n".join(failures)
