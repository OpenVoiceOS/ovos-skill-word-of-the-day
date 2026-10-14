"""Which day's word the unified ``word_of_the_day`` handler answers.

The history holds one distinct word per day ("word1" is yesterday's word,
"word2" the day before's, and so on), so a test names the word the handler
must speak. The vocabulary comes from the real ``locale/<lang>/*.voc`` files,
so a missing or emptied file fails here.
"""
import contextlib
import datetime
import importlib.util
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from ovos_workshop.resource_files import SkillResources

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("word_of_the_day_skill_dates", ROOT / "__init__.py")
skill = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(skill)

LOCALES = sorted(d.name for d in (ROOT / "locale").iterdir() if d.is_dir())


class FakeSession:
    def __init__(self):
        self.intent_context = {}

    def set_intent_context(self, key, value=None, *, scope="private", turns_remaining=None):
        self.intent_context[key] = {"value": value}


def today():
    return skill.now_local().date()


def history(days=14):
    return {(today() - datetime.timedelta(days=n)).strftime("%Y-%m-%d"): f"word{n}"
            for n in range(1, days + 1)}


def make_instance(lang="en-US"):
    resources = SkillResources(str(ROOT), lang, skill_id="word-of-the-day-test")
    instance = SimpleNamespace(lang=lang, settings={"word_history": history()}, dialogs=[], spoken=[])
    instance.resources = resources
    instance.voc_list = lambda name: [alt for line in resources.load_vocabulary_file(name) for alt in line]
    instance.speak_dialog = lambda dialog, data=None: instance.dialogs.append((dialog, data))
    instance.speak = instance.spoken.append
    instance.gui = SimpleNamespace(show_text=lambda *args: None)
    cls = skill.WordOfTheDaySkill
    for name, function in vars(cls).items():
        if inspect.isfunction(function):
            setattr(instance, name, function.__get__(instance))
    return instance


def ask(lang, data):
    """Run one request; return the dialog the handler spoke."""
    instance = make_instance(lang)
    with patch.object(skill, "SessionManager") as manager, patch_sources():
        manager.get.return_value = FakeSession()
        instance.handle_word_of_the_day_intent(SimpleNamespace(data=data))
    return instance.dialogs[0]


@contextlib.contextmanager
def patch_sources():
    """Every online source answers with the same word, so no test reaches the network."""
    fake = ("todayword", "a definition")
    with contextlib.ExitStack() as stack:
        for name in ("get_wod", "get_wod_fr", "get_wod_ca", "get_wod_gl"):
            stack.enter_context(patch.object(skill, name, return_value=fake))
        stack.enter_context(patch.object(skill, "get_wod_pt", side_effect=lambda pt_br=False: fake))
        yield


def spoken_word(dialog):
    name, data = dialog
    return data["word"] if name == "word_of_day" else name


def test_every_locale_ships_the_past_vocabulary():
    for lang in LOCALES:
        resources = SkillResources(str(ROOT), lang, skill_id="word-of-the-day-test")
        assert resources.load_vocabulary_file("past"), f"{lang} has no past.voc"


def test_every_locale_but_kab_ships_the_before_yesterday_vocabulary():
    for lang in LOCALES:
        if lang != "kab":
            resources = SkillResources(str(ROOT), lang, skill_id="word-of-the-day-test")
            assert resources.load_vocabulary_file("before_yesterday"), f"{lang} has no before_yesterday.voc"


@pytest.mark.parametrize("lang", LOCALES)
def test_every_past_voc_phrase_answers_a_past_word(lang):
    resources = SkillResources(str(ROOT), lang, skill_id="word-of-the-day-test")
    phrases = [alt for line in resources.load_vocabulary_file("past") for alt in line]
    for phrase in phrases:
        word = spoken_word(ask(lang, {"utterance": f"{phrase}"}))
        assert word.startswith("word"), (lang, phrase, word)


@pytest.mark.parametrize("lang", [lang for lang in LOCALES
                                  if (ROOT / "locale" / lang / "before_yesterday.voc").exists()])
def test_every_before_yesterday_phrase_answers_the_word_two_days_back(lang):
    resources = SkillResources(str(ROOT), lang, skill_id="word-of-the-day-test")
    for line in resources.load_vocabulary_file("before_yesterday"):
        for phrase in line:
            assert spoken_word(ask(lang, {"utterance": f"word of the day {phrase}"})) == "word2", (lang, phrase)


@pytest.mark.parametrize("lang,utterance", [
    ("en-US", "what was the word of the day yesterday"),
    ("de-DE", "was war das wort des tages gestern"),
    ("pt-PT", "qual foi a palavra do dia de ontem"),
    ("it-IT", "qual era la parola del giorno ieri"),
    ("nl-NL", "wat was gisteren het woord van de dag"),
])
def test_yesterday_answers_the_word_one_day_back(lang, utterance):
    assert spoken_word(ask(lang, {"utterance": utterance})) == "word1"


@pytest.mark.parametrize("lang,utterance,word", [
    ("en-US", "what was the word of the day the day before yesterday", "word2"),
    ("de-DE", "was war das wort des tages vorgestern", "word2"),
    ("pt-PT", "qual foi a palavra do dia de anteontem", "word2"),
    ("fr-FR", "quel était le mot du jour avant hier", "word2"),
    ("ca-ES", "quina era la paraula del dia d ahir", "word1"),
    ("it-IT", "qual era la parola del giorno l'altro ieri", "word2"),
    ("nl-NL", "wat was het woord van de dag eergisteren", "word2"),
    ("en-US", "what was the word of the day three days ago", "word3"),
    ("de-DE", "was war das wort des tages vor drei tagen", "word3"),
    ("es-ES", "cuál fue la palabra del día hace tres días", "word3"),
    ("fr-FR", "quel était le mot du jour il y a trois jours", "word3"),
    ("da-DK", "hvad var dagens ord for tre dage siden", "word3"),
    ("es-CO", "cuál fue la palabra del día hace tres días", "word3"),
    ("es-CO", "cuál fue la palabra del día antier", "word2"),
    ("fa-IR", "کلمه روز سه روز پیش چه بود", "word3"),
])
def test_relative_past_phrases_answer_the_named_day(lang, utterance, word):
    assert spoken_word(ask(lang, {"utterance": utterance})) == word


def test_a_weekday_slot_answers_the_latest_such_day_not_today():
    day = today() - datetime.timedelta(days=3)
    assert spoken_word(ask("en-US", {"date": day.strftime("%A").lower()})) == "word3"


def test_a_month_day_slot_answers_the_latest_such_day_not_today():
    day = today() - datetime.timedelta(days=10)
    slot = f"{day.strftime('%B').lower()} {day.day}"
    assert spoken_word(ask("en-US", {"date": slot})) == "word10"


TODAYS_WORD = ("word_of_day", {"word": "todayword"})


def is_today(answer):
    """True for the today path: the fetched word, or the unknown-word dialog of a locale with no source."""
    return answer == TODAYS_WORD or answer[0] == "unknown_wod"


def voc_phrases(lang, name):
    resources = SkillResources(str(ROOT), lang, skill_id="word-of-the-day-test")
    return [alt for line in resources.load_vocabulary_file(name) for alt in line]


def locales_with(name):
    return [lang for lang in LOCALES if (ROOT / "locale" / lang / f"{name}.voc").exists()]


@pytest.mark.parametrize("lang", locales_with("ago"))
def test_every_ago_phrase_never_answers_todays_word(lang):
    """A marker that always means "ago" names a past day: the answer is a past word or no_word_history."""
    for phrase in voc_phrases(lang, "ago"):
        assert not is_today(ask(lang, {"utterance": f"word of the day {phrase}"})), (lang, phrase)


@pytest.mark.parametrize("lang", LOCALES)
def test_every_today_phrase_as_a_slot_answers_todays_word(lang):
    assert voc_phrases(lang, "today"), f"{lang} has no today.voc"
    for phrase in voc_phrases(lang, "today"):
        assert is_today(ask(lang, {"date": phrase})), (lang, phrase)


@pytest.mark.parametrize("lang", locales_with("weekday"))
def test_weekday_phrases_answer_a_past_day_except_the_weekday_of_today(lang):
    answers = [ask(lang, {"utterance": f"word of the day {phrase}"}) for phrase in voc_phrases(lang, "weekday")]
    # at most the spellings of today's own weekday (two in pl-PL, ru-RU) name today
    assert sum(is_today(answer) for answer in answers) <= 3, (lang, answers)


@pytest.mark.parametrize("lang,utterance", [
    ("es-ES", "buenos días, cuál es la palabra del día"),
    ("es-CO", "buenos días, cuál es la palabra del día"),
    ("gl-ES", "bos días, cal é a palabra do día"),
    ("pt-PT", "qual é a palavra do dia, já há dias que não pergunto"),
    ("ca-ES", "bon dia, quina és la paraula del dia"),
    ("fr-FR", "quel est le mot du jour, il y a un mot aujourd'hui"),
    ("en-US", "what is the word of the day, it has been days"),
])
def test_a_greeting_with_the_word_days_still_answers_todays_word(lang, utterance):
    assert is_today(ask(lang, {"utterance": utterance}))


@pytest.mark.parametrize("lang", locales_with("weekday"))
def test_every_weekday_phrase_names_its_latest_day(lang):
    """Line N of weekday.voc is weekday N: each spelling answers the word of the latest such day."""
    resources = SkillResources(str(ROOT), lang, skill_id="word-of-the-day-test")
    lines = resources.load_vocabulary_file("weekday")
    assert len(lines) == 7, lang
    for index, spellings in enumerate(lines):
        back = (today().weekday() - index) % 7
        for spelling in spellings:
            answer = ask(lang, {"utterance": f"word of the day {spelling}"})
            if back == 0:
                assert is_today(answer), (lang, spelling)
            else:
                assert answer == ("word_of_day", {"word": f"word{back}"}), (lang, spelling, answer)


def test_the_weekday_of_today_answers_todays_word_in_en_us():
    name = today().strftime("%A").lower()
    assert is_today(ask("en-US", {"utterance": f"happy {name}, what's the word of the day"}))
    assert is_today(ask("en-US", {"date": name}))


@pytest.mark.parametrize("utterance,expected", [
    ("never mind yesterday, what is today's word", TODAYS_WORD),
    ("never mind yesterday's word, what is today's word of the day", TODAYS_WORD),
    ("never mind today's word, what was yesterday's", ("word_of_day", {"word": "word1"})),
    ("what was the word of the day yesterday", ("word_of_day", {"word": "word1"})),
])
def test_the_later_day_word_decides(utterance, expected):
    answer = ask("en-US", {"utterance": utterance})
    assert is_today(answer) if expected == TODAYS_WORD else answer == expected


def test_the_later_day_word_decides_in_de_de():
    assert is_today(ask("de-DE", {"utterance": "vergiss das gestrige wort, wie lautet das heutige wort"}))
    assert ask("de-DE", {"utterance": "vergiss das heutige wort, wie lautete das gestrige wort"}) == ("word_of_day", {"word": "word1"})


def first_of_a_past_month():
    day = today().replace(day=1)
    return day if day < today() else (day - datetime.timedelta(days=1)).replace(day=1)


def ask_with_parser(lang, data, parsed_date, history_extra=None):
    """Run a request whose slot the parser reads as ``parsed_date``."""
    instance = make_instance(lang)
    instance.settings["word_history"][parsed_date.strftime("%Y-%m-%d")] = "parsedword"
    result = (datetime.datetime.combine(parsed_date, datetime.time(12)), "")
    with patch.object(skill, "SessionManager") as manager, \
            patch.object(skill, "extract_datetime", return_value=result), patch_sources():
        manager.get.return_value = FakeSession()
        instance.handle_word_of_the_day_intent(SimpleNamespace(data=data))
    return instance.dialogs[0]


def test_a_slot_whose_number_the_parser_dropped_speaks_no_word_history():
    """"the 12th" read as another day of the month names no day with certainty."""
    day = today() - datetime.timedelta(days=5)
    assert day.day != 12
    assert ask_with_parser("en-US", {"date": "the 12th"}, day) == ("no_word_history", None)


def test_a_spelled_out_date_the_parser_reads_as_the_first_speaks_no_word_history():
    assert ask_with_parser("en-US", {"date": "october twelfth"}, first_of_a_past_month()) == ("no_word_history", None)


def test_a_slot_whose_number_the_parser_kept_answers_that_day():
    day = today() - datetime.timedelta(days=5)
    assert ask_with_parser("en-US", {"date": f"the {day.day}th"}, day) == ("word_of_day", {"word": "parsedword"})


EU_MONTHS = ["urtarrilaren", "otsailaren", "martxoaren", "apirilaren", "maiatzaren", "ekainaren",
             "uztailaren", "abuztuaren", "irailaren", "urriaren", "azaroaren", "abenduaren"]


def test_a_basque_month_day_slot_moves_back_to_the_latest_such_day():
    """The eu-ES parser rejects a timezone-aware anchor, which would drop the rollback."""
    day = today() - datetime.timedelta(days=10)
    assert spoken_word(ask("eu-ES", {"date": f"{EU_MONTHS[day.month - 1]} {day.day}"})) == "word10"


@pytest.mark.parametrize("lang,utterance", [
    ("pl-PL", "jakie było słowo dnia trzy dni temu"),
    ("it-IT", "qual era la parola del giorno tre giorni fa"),
    ("ca-ES", "quina era la paraula del dia fa tres dies"),
    ("pt-PT", "qual foi a palavra do dia há três dias"),
    ("ru-RU", "какое было слово дня три дня назад"),
    ("sv-SE", "vad var ordet för dagen för tre dagar sedan"),
])
def test_an_ago_request_with_a_count_never_answers_todays_word(lang, utterance):
    assert not is_today(ask(lang, {"utterance": utterance}))


@pytest.mark.parametrize("lang,utterance", [
    ("it-IT", "qual era la parola del giorno lunedì"),
    ("ru-RU", "какое было слово дня в понедельник"),
    ("pl-PL", "jakie było słowo dnia w poniedziałek"),
])
def test_a_weekday_request_never_answers_todays_word(lang, utterance):
    if today().weekday() == 0:
        pytest.skip("the request names the weekday of today")
    assert not is_today(ask(lang, {"utterance": utterance}))


@pytest.mark.parametrize("lang,utterance", [
    ("en-US", "what was the word of the day on monday"),
    ("fr-FR", "quel était le mot du jour lundi"),
    ("pt-PT", "qual foi a palavra do dia na segunda-feira"),
    ("pt-BR", "qual foi a palavra do dia na segunda-feira"),
    ("de-DE", "was war das wort des tages am montag"),
    ("pt-PT", "qual foi a palavra do dia na segunda feira"),
    ("sv-SE", "vad var ordet för dagen i måndags"),
    ("da-DK", "hvad var dagens ord i mandags"),
])
def test_a_weekday_without_a_slot_never_answers_todays_word(lang, utterance):
    name, data = ask(lang, {"utterance": utterance})
    assert data != {"word": "todayword"}
    assert name == "no_word_history" or data["word"].startswith("word"), (name, data)


@pytest.mark.parametrize("lang,utterance", [
    ("ca-ES", "quina era la paraula del dia fa tres dies"),
    ("it-IT", "qual era la parola del giorno tre giorni fa"),
    ("nl-NL", "wat was het woord van de dag drie dagen geleden"),
])
def test_an_ago_request_the_parser_cannot_read_speaks_no_word_history(lang, utterance):
    assert ask(lang, {"utterance": utterance}) == ("no_word_history", None)


@pytest.mark.parametrize("slot", ["october twelfth", "march third", "august fifth"])
def test_an_ordinal_word_date_speaks_no_word_history(slot):
    """The parser reads these as the 1st of the month."""
    assert ask("en-US", {"date": slot}) == ("no_word_history", None)


def test_a_slot_that_the_parser_reads_as_today_without_saying_so_speaks_no_word_history():
    today_slot = f"the {today().day}th"
    assert ask("en-US", {"date": today_slot}) == ("no_word_history", None)


def test_the_parser_failing_on_a_slot_speaks_no_word_history():
    instance_dialog = None
    with patch.object(skill, "extract_datetime", side_effect=TypeError("naive and aware")):
        instance_dialog = ask("en-US", {"date": "march 3"})
    assert instance_dialog == ("no_word_history", None)


def test_every_date_entity_value_of_every_locale_answers_without_error():
    """No slot m2v can send from a date.entity file crashes the handler, and
    none gets today's word or a word from a day it does not name."""
    checked = 0
    for lang in LOCALES:
        entity = ROOT / "locale" / lang / "intents" / "date.entity"
        if not entity.exists():
            continue
        for value in entity.read_text(encoding="utf-8").splitlines():
            if value.strip():
                name, data = ask(lang, {"date": value.strip(), "utterance": f"word of the day {value.strip()}"})
                assert name == "no_word_history" or data["word"].startswith("word"), (lang, value, name, data)
                checked += 1
    assert checked >= 150


def test_a_future_slot_speaks_no_word_history():
    assert ask("en-US", {"date": "tomorrow"}) == ("no_word_history", None)


def test_a_slot_that_is_today_answers_todays_word():
    name, data = ask("en-US", {"date": "today"})
    assert (name, data) == ("word_of_day", {"word": "todayword"})


def test_the_day_in_the_skill_name_is_not_a_date():
    assert ask("en-US", {"utterance": "tell me the word of the day"}) == ("word_of_day", {"word": "todayword"})
