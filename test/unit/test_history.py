"""Unit tests for the word-of-the-day history feature (past-word lookup and
the "spell that" follow-up), loaded the same way as ``test_dictionary_wod.py``
-- import the skill module by file path and call the unbound handler methods
against a bare ``SimpleNamespace`` instance, no bus/core required.
"""
import datetime
import importlib.util
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


MODULE_PATH = Path(__file__).resolve().parents[2] / "__init__.py"
SPEC = importlib.util.spec_from_file_location("word_of_the_day_skill_history", MODULE_PATH)
skill = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(skill)


class FakeSession:
    """Minimal stand-in for ``ovos_bus_client.session.Session``, enough to
    exercise ``set_intent_context``'s OVOS-CONTEXT-1 shared-scope shape
    without booting a real bus/session registry."""

    def __init__(self, intent_context=None):
        self.intent_context = intent_context or {}

    def set_intent_context(self, key, value=None, *, scope="private", turns_remaining=None):
        entry = {"value": value}
        if turns_remaining is not None:
            entry["turns_remaining"] = turns_remaining
        self.intent_context[key] = entry


def make_skill_instance(lang="en-US", settings=None):
    instance = SimpleNamespace(
        lang=lang,
        settings=settings if settings is not None else {},
        dialogs=[],
        alphanumeric_skill_id="ovos_skill_word_of_the_day_openvoiceos",
    )
    instance.speak_dialog = (
        lambda dialog, data=None: instance.dialogs.append((dialog, data))
    )
    instance._remember_word = skill.WordOfTheDaySkill._remember_word.__get__(instance)
    instance._recall_word = skill.WordOfTheDaySkill._recall_word.__get__(instance)
    return instance


class DummyMessage:
    def __init__(self, data):
        self.data = data


def test_remember_and_recall_word_round_trip():
    instance = make_skill_instance()
    date = datetime.date(2026, 8, 30)

    instance._remember_word(date, "serendipity")

    assert instance.settings["word_history"] == {"2026-08-30": "serendipity"}
    assert instance._recall_word(date) == "serendipity"
    assert instance._recall_word(datetime.date(2026, 8, 29)) is None


def test_remember_word_caps_history_at_max_entries():
    instance = make_skill_instance()
    base = datetime.date(2026, 1, 1)

    for offset in range(skill.MAX_WORD_HISTORY + 5):
        instance._remember_word(base + datetime.timedelta(days=offset), f"word{offset}")

    history = instance.settings["word_history"]
    assert len(history) == skill.MAX_WORD_HISTORY
    # the oldest 5 dates were evicted, the newest MAX_WORD_HISTORY remain
    newest = base + datetime.timedelta(days=skill.MAX_WORD_HISTORY + 4)
    oldest_kept = base + datetime.timedelta(days=5)
    assert newest.strftime("%Y-%m-%d") in history
    assert oldest_kept.strftime("%Y-%m-%d") in history
    assert base.strftime("%Y-%m-%d") not in history


def bind_word_of_the_day(instance, past_phrases=("yesterday", "yesterday's", "previous")):
    cls = skill.WordOfTheDaySkill
    instance.voc_list = lambda name: list(past_phrases) if name == "past" else []
    instance.spoken = []
    instance.speak = instance.spoken.append
    instance.gui = SimpleNamespace(show_text=lambda *args: None)
    instance.resources = SimpleNamespace(load_vocabulary_file=lambda name: [])
    for name, function in vars(cls).items():
        if inspect.isfunction(function) and name not in instance.__dict__:
            setattr(instance, name, function.__get__(instance))
    return instance


def run_word_of_the_day(instance, data):
    session = FakeSession()
    with patch.object(skill, "SessionManager") as mock_sm:
        mock_sm.get.return_value = session
        instance.handle_word_of_the_day_intent(DummyMessage(data))
    return session


def test_word_of_the_day_without_a_past_word_fetches_todays_word():
    instance = bind_word_of_the_day(make_skill_instance())
    with patch.object(skill, "get_wod", return_value=("serendipity", "a happy accident")):
        session = run_word_of_the_day(instance, {"utterance": "what is the word of the day"})

    assert instance.dialogs == [("word_of_day", {"word": "serendipity"})]
    assert instance.spoken == ["a happy accident"]
    assert instance.settings["word_history"] == {skill.now_local().date().strftime("%Y-%m-%d"): "serendipity"}
    assert session.intent_context["prev_wod_word"]["value"] == "serendipity"


def test_word_of_the_day_with_yesterday_voc_answers_from_history():
    yesterday = skill.now_local().date() - datetime.timedelta(days=1)
    instance = bind_word_of_the_day(make_skill_instance(
        settings={"word_history": {yesterday.strftime("%Y-%m-%d"): "petrichor"}}))
    with patch.object(skill, "get_wod", side_effect=AssertionError("must not fetch today's word")):
        session = run_word_of_the_day(instance, {"utterance": "what was yesterday's word of the day"})

    assert instance.dialogs == [("word_of_day", {"word": "petrichor"})]
    assert session.intent_context["prev_wod_word"]["value"] == "petrichor"


def test_word_of_the_day_with_an_explicit_date_slot_answers_from_history():
    day = skill.now_local().date() - datetime.timedelta(days=3)
    instance = bind_word_of_the_day(make_skill_instance(
        settings={"word_history": {day.strftime("%Y-%m-%d"): "ephemeral"}}))
    session = run_word_of_the_day(instance, {
        "date": day.strftime("%B %d %Y"),
        "utterance": f"what was the word of the day on {day.strftime('%B %d %Y')}"})

    assert instance.dialogs == [("word_of_day", {"word": "ephemeral"})]
    assert session.intent_context["prev_wod_word"]["value"] == "ephemeral"


def test_word_of_the_day_never_reads_the_day_in_its_own_name_as_a_date():
    """"day" in "word of the day" must not make a past request."""
    instance = bind_word_of_the_day(make_skill_instance())
    with patch.object(skill, "get_wod", return_value=("serendipity", "a happy accident")):
        run_word_of_the_day(instance, {"utterance": "tell me the word of the day"})

    assert instance.dialogs == [("word_of_day", {"word": "serendipity"})]


def test_word_of_the_day_speaks_history_dialog_when_nothing_recorded():
    instance = bind_word_of_the_day(make_skill_instance(settings={"word_history": {}}))
    session = run_word_of_the_day(instance, {"utterance": "what was yesterday's word"})

    assert instance.dialogs == [("no_word_history", None)]
    assert session.intent_context == {}


def test_word_of_the_day_with_unparseable_date_slot_speaks_history_dialog():
    """A garbled {date} slot must NOT silently fall back to yesterday's or
    today's word: the handler speaks no_word_history rather than answering
    about a date the user never asked about."""
    yesterday = skill.now_local().date() - datetime.timedelta(days=1)
    instance = bind_word_of_the_day(make_skill_instance(
        settings={"word_history": {yesterday.strftime("%Y-%m-%d"): "petrichor"}}))
    session = run_word_of_the_day(instance, {
        "date": "flibbertigibbet nonsense",
        "utterance": "what was the word on flibbertigibbet nonsense"})

    assert instance.dialogs == [("no_word_history", None)]
    assert session.intent_context == {}


def test_spell_wod_intent_spells_out_the_context_word():
    instance = make_skill_instance()
    instance.handle_spell_wod_intent = skill.WordOfTheDaySkill.handle_spell_wod_intent.__get__(instance)

    session = FakeSession(intent_context={"prev_wod_word": {"value": "book"}})
    message = DummyMessage({"utterance": "spell that"})
    with patch.object(skill, "SessionManager") as mock_sm:
        mock_sm.get.return_value = session
        instance.handle_spell_wod_intent(message)

    assert instance.dialogs == [
        ("spell_word", {"word": "book", "letters": "b. o. o. k."})
    ]


def test_spell_wod_intent_without_context_speaks_history_dialog():
    instance = make_skill_instance()
    instance.handle_spell_wod_intent = skill.WordOfTheDaySkill.handle_spell_wod_intent.__get__(instance)

    session = FakeSession()
    message = DummyMessage({"utterance": "spell that"})
    with patch.object(skill, "SessionManager") as mock_sm:
        mock_sm.get.return_value = session
        instance.handle_spell_wod_intent(message)

    assert instance.dialogs == [("no_word_history", None)]
