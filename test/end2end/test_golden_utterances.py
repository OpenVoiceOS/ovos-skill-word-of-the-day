"""Golden-utterance end-to-end coverage for ovos-skill-word-of-the-day (en-US).

The golden corpus (``golden_utterances.jsonl``) is a vendored slice of the
shared ovoscope golden-utterance dataset, keyed by
``skill_id == "ovos-skill-word-of-the-day.openvoiceos"`` (matches this
skill's real OPM entry point too). The corpus only has one row for this
skill; it is still run through a real MiniCroft like the other repos in
this campaign, asserting intent routing.

The word/definition sources are monkeypatched (same mechanism as the
sibling ``test_wod_e2e.py``/``test_word_of_the_day_intent.py`` suites) so
routing is exercised offline and deterministically.
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_minicroft

SKILL_ID = "ovos-skill-word-of-the-day.openvoiceos"
LANG = "en-US"

_PIPELINE = ["ovos-padacioso-pipeline-plugin-high"]

_IGNORE = [
    "speak",
    "ovos.utterance.speak",
    "mycroft.audio.play_sound",
    "recognizer_loop:audio_output_start",
    "recognizer_loop:audio_output_end",
]

GOLDEN_PATH = Path(__file__).parent / "golden_utterances.jsonl"


def _patch_parsers():
    fake = ("testword", "a word used in tests")
    import ovos_skill_word_of_the_day as mod
    targets = ["get_wod", "get_wod_pt", "get_wod_fr", "get_wod_ca", "get_wod_gl"]
    return [patch.object(mod, name, return_value=fake) for name in targets if hasattr(mod, name)]


# utterances lifted verbatim from OTHER skills' golden-utterance slices in
# the shared ovoscope corpus, picked for lexical overlap with word-of-the-
# day's "word"/"tell me" vocabulary -- includes the wolfie/wikipedia/wordnet
# trio since single-word lookups are conceptually adjacent.
NEGATIVE_UTTERANCES = [
    ("can you tell me the weather", "ovos-skill-weather.openvoiceos"),
    ("can you find something on wikipedia", "ovos-skill-wikipedia.openvoiceos"),
    ("ask the wolf something", "ovos-skill-wolfie.openvoiceos"),
    ("ask wordnet about word", "ovos-skill-wordnet.openvoiceos"),
    ("search wikihow for something", "ovos-skill-wikihow.openvoiceos"),
    ("can you spell word", "ovos-skill-spelling.openvoiceos"),
    ("set an alarm", "ovos-skill-alerts.openvoiceos"),
]


def _matches_intent(msg_type: str, skill_id: str, intent_label: str) -> bool:
    """Tolerant matcher, same shape as the sibling repos' suites."""
    prefix = f"{skill_id}:"
    if not msg_type.startswith(prefix):
        return False
    observed = msg_type[len(prefix):]
    observed_base = observed.rsplit(".", 1)[0] if observed.endswith(".intent") else observed
    expected_base = intent_label.rsplit(".", 1)[0] if intent_label.endswith(".intent") else intent_label
    return observed_base == expected_base


_XFAIL_REASONS = {}


def _load_golden_rows():
    rows = []
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("needs_manual"):
                continue
            rows.append(row)
    return rows


def _as_param(row):
    reason = _XFAIL_REASONS.get(row["utterance"])
    if reason is None:
        return pytest.param(row, id=row["utterance"])
    return pytest.param(row, id=row["utterance"], marks=pytest.mark.xfail(reason=reason, strict=True))


GOLDEN_ROWS = [_as_param(r) for r in _load_golden_rows()]


@pytest.fixture(scope="module")
def minicroft():
    patches = _patch_parsers()
    for p in patches:
        p.start()
    mc = get_minicroft([SKILL_ID])
    yield mc
    mc.stop()
    for p in patches:
        p.stop()


def _types(mc, text, session_id):
    session = Session(session_id)
    session.lang = LANG
    session.pipeline = list(_PIPELINE)
    session.blacklisted_intents = []
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
    return [m.msg_type for m in capture.finish()]


def _golden_id(row):
    return row["utterance"]


@pytest.mark.timeout(60)
@pytest.mark.parametrize("row", GOLDEN_ROWS, ids=_golden_id)
def test_golden_utterance(minicroft, row):
    types = _types(minicroft, row["utterance"], f"golden-{_golden_id(row)}")
    assert any(_matches_intent(t, SKILL_ID, row["intent_label"]) for t in types), (
        f"{row['utterance']!r}: expected {SKILL_ID}:{row['intent_label']}, got {types!r}"
    )


@pytest.mark.timeout(60)
@pytest.mark.parametrize("negative", NEGATIVE_UTTERANCES, ids=lambda n: n[0])
def test_negative_confusable_not_claimed(minicroft, negative):
    text, source_skill = negative
    types = _types(minicroft, text, f"negative-{text}")
    claimed = any(t.startswith(f"{SKILL_ID}:") for t in types)
    assert not claimed, f"{text!r} (from {source_skill}) was incorrectly claimed by {SKILL_ID}"
