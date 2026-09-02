"""Unit tests for the word-of-the-day history feature (past-word lookup and
the "spell that" follow-up), loaded the same way as ``test_dictionary_wod.py``
-- import the skill module by file path and call the unbound handler methods
against a bare ``SimpleNamespace`` instance, no bus/core required.
"""
import datetime
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


MODULE_PATH = Path(__file__).resolve().parents[2] / "__init__.py"
SPEC = importlib.util.spec_from_file_location("word_of_the_day_skill_history", MODULE_PATH)
skill = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(skill)


def make_skill_instance(lang="en-US", settings=None):
    instance = SimpleNamespace(
        lang=lang,
        settings=settings if settings is not None else {},
        dialogs=[],
        contexts=[],
        alphanumeric_skill_id="ovos_skill_word_of_the_day_openvoiceos",
    )
    instance.speak_dialog = (
        lambda dialog, data=None: instance.dialogs.append((dialog, data))
    )
    instance.set_context = lambda context, word="": instance.contexts.append((context, word))
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


def test_past_word_intent_answers_from_history(monkeypatch):
    yesterday = skill.now_local().date() - datetime.timedelta(days=1)
    instance = make_skill_instance(
        settings={"word_history": {yesterday.strftime("%Y-%m-%d"): "petrichor"}}
    )
    instance.handle_past_word_intent = skill.WordOfTheDaySkill.handle_past_word_intent.__get__(instance)

    message = DummyMessage({"utterance": "what was yesterday's word"})
    instance.handle_past_word_intent(message)

    assert instance.dialogs == [("word.of.day", {"word": "petrichor"})]
    assert instance.contexts == [("prev_wod_word", "petrichor")]


def test_past_word_intent_speaks_history_dialog_when_nothing_recorded():
    instance = make_skill_instance(settings={"word_history": {}})
    instance.handle_past_word_intent = skill.WordOfTheDaySkill.handle_past_word_intent.__get__(instance)

    message = DummyMessage({"utterance": "what was yesterday's word"})
    instance.handle_past_word_intent(message)

    assert instance.dialogs == [("no.word.history", None)]
    assert instance.contexts == []


def test_past_word_intent_with_unparseable_date_slot_speaks_history_dialog():
    """A garbled {date} slot must NOT silently fall back to yesterday's
    word: extract_datetime returns None for it, so the handler must speak
    no.word.history rather than misattributing yesterday's word to the date
    the user actually asked about."""
    yesterday = skill.now_local().date() - datetime.timedelta(days=1)
    instance = make_skill_instance(
        settings={"word_history": {yesterday.strftime("%Y-%m-%d"): "petrichor"}}
    )
    instance.handle_past_word_intent = skill.WordOfTheDaySkill.handle_past_word_intent.__get__(instance)

    message = DummyMessage({
        "date": "flibbertigibbet nonsense",
        "utterance": "what was the word on flibbertigibbet nonsense",
    })
    instance.handle_past_word_intent(message)

    assert instance.dialogs == [("no.word.history", None)]
    assert instance.contexts == []


def test_spell_wod_intent_spells_out_the_context_word():
    instance = make_skill_instance()
    instance.handle_spell_wod_intent = skill.WordOfTheDaySkill.handle_spell_wod_intent.__get__(instance)

    message = DummyMessage({
        "ovos_skill_word_of_the_day_openvoiceosprev_wod_word": "book",
        "utterance": "spell that",
    })
    instance.handle_spell_wod_intent(message)

    assert instance.dialogs == [
        ("spell.word", {"word": "book", "letters": "b. o. o. k."})
    ]
