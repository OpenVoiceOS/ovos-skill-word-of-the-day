import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "__init__.py"
SPEC = importlib.util.spec_from_file_location("word_of_the_day_skill", MODULE_PATH)
skill = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(skill)


class DummyGui:
    def __init__(self):
        self.text = []

    def show_text(self, definition, word):
        self.text.append((definition, word))


class DummyLog:
    def __init__(self):
        self.exceptions = []

    def exception(self, message):
        self.exceptions.append(message)


def make_skill_instance(lang="en-US"):
    instance = SimpleNamespace(
        lang=lang,
        gui=DummyGui(),
        dialogs=[],
        speech=[]
    )
    instance.speak_dialog = (
        lambda dialog, data=None: instance.dialogs.append((dialog, data))
    )
    instance.speak = lambda text: instance.speech.append(text)
    return instance


def test_extract_dictionary_wod_from_current_markup():
    html = """
    <div class="wotd-entry-wrapper">
        <div class="wotd-entry-date">May 12, 2026</div>
        <a class="wotd-entry-headword">rigmarole</a>
        <p class="wotd-entry-definition">
            an elaborate or complicated procedure
        </p>
    </div>
    <div class="wotd-entry-wrapper">
        <a class="wotd-entry-headword">scupper</a>
        <p class="wotd-entry-definition">
            to prevent from happening or succeeding
        </p>
    </div>
    """

    assert skill._extract_dictionary_wod(html) == (
        "rigmarole",
        "an elaborate or complicated procedure"
    )


def test_extract_dictionary_wod_from_legacy_markup():
    html = """
    <div class="otd-item-headword__word">halcyon</div>
    <div class="otd-item-headword__pos-blocks">
        <span>adjective</span>
        <p>happy; blissful; carefree</p>
    </div>
    """

    assert skill._extract_dictionary_wod(html) == (
        "halcyon",
        "happy; blissful; carefree"
    )


def test_extract_dictionary_wod_raises_clear_error_for_unknown_markup():
    with pytest.raises(RuntimeError, match="Failed to parse word of the day"):
        skill._extract_dictionary_wod("<html></html>")


def test_handler_speaks_unknown_when_source_fails(monkeypatch):
    log = DummyLog()

    def fail():
        raise RuntimeError("source changed")

    monkeypatch.setattr(skill, "LOG", log)
    monkeypatch.setattr(skill, "get_wod", fail)

    instance = make_skill_instance()
    skill.WordOfTheDaySkill.handle_word_of_the_day_intent(instance, None)

    assert instance.dialogs == [("unknown.wod", None)]
    assert instance.gui.text == []
    assert instance.speech == []
    assert log.exceptions == ["Failed to retrieve word of the day"]
