import datetime
import re

import requests
from dateutil.relativedelta import relativedelta
from typing import Optional, Union
from bs4 import BeautifulSoup
from ovos_bus_client.session import SessionManager
from ovos_date_parser import extract_datetime
from ovos_number_parser import extract_number
from ovos_workshop.decorators import intent_handler
from ovos_workshop.skills.auto_translatable import OVOSSkill
from ovos_utils.log import LOG
from ovos_utils.time import now_local

# OVOS-CONTEXT-1 shared-scope key holding the last word of the day spoken
# (today's word or a recalled past word), so a follow-up "spell that" can
# spell it out without repeating it.
PREV_WOD_WORD_CONTEXT = "prev_wod_word"


REQUEST_TIMEOUT = 20
REQUEST_HEADERS = {
    "User-Agent": "OVOS WordOfTheDay Skill/1.0 "
                  "(https://github.com/OpenVoiceOS/ovos-skill-word-of-the-day)"
}
FR_WIKTIONARY_API = "https://fr.wiktionary.org/w/api.php"
FR_WIKTIONARY_PAGE = "Wiktionnaire:Page d’accueil"
DICTIONARY_WOD_URL = "https://www.dictionary.com/e/word-of-the-day"
# how many past words to keep in `self.settings["word_history"]`, keyed by
# ISO date ("YYYY-MM-DD"); oldest entries are dropped once the cap is hit
MAX_WORD_HISTORY = 30
# words on each side of an "ago" marker that may belong to the date phrase
MAX_SPAN_WORDS = 3


def _plain(text: str) -> str:
    """Lower-case words only: engines strip hyphens and apostrophes from a request."""
    return " ".join(re.findall(r"\w+", text.lower()))


def _http_get(url, **kwargs):
    headers = dict(REQUEST_HEADERS)
    headers.update(kwargs.pop("headers", {}) or {})
    timeout = kwargs.pop("timeout", REQUEST_TIMEOUT)
    return requests.get(url, headers=headers, timeout=timeout, **kwargs)


def _http_post(url, **kwargs):
    headers = dict(REQUEST_HEADERS)
    headers.update(kwargs.pop("headers", {}) or {})
    timeout = kwargs.pop("timeout", REQUEST_TIMEOUT)
    return requests.post(url, headers=headers, timeout=timeout, **kwargs)


def _normalize_definition_text(text: str) -> str:
    text = " ".join(text.split())
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([’'])\s+", r"\1", text)
    return text.strip()


def _dictionary_definition_text(node) -> str:
    if "otd-item-headword__pos-blocks" in (node.get("class") or []):
        lines = [
            line.strip()
            for line in node.get_text("\n", strip=True).splitlines()
            if line.strip()
        ]
        if lines:
            return lines[-1]
    return node.get_text(" ", strip=True)


def _extract_dictionary_wod(html: str, url: str = DICTIONARY_WOD_URL):
    soup = BeautifulSoup(html, "html.parser")

    entry = soup.find(class_="wotd-entry-wrapper")
    word_node = None
    definition_node = None
    if entry is not None:
        word_node = entry.find(class_="wotd-entry-headword")
        definition_node = entry.find(class_="wotd-entry-definition")

    word_node = word_node or soup.find("div", {
        "class": "otd-item-headword__word"
    }) or soup.find(class_="wotd-entry-headword")
    definition_node = definition_node or soup.find("div", {
        "class": "otd-item-headword__pos-blocks"
    }) or soup.find(class_="wotd-entry-definition")

    if word_node is None or definition_node is None:
        raise RuntimeError(f"Failed to parse word of the day from '{url}'")

    wod = _normalize_definition_text(word_node.get_text(" ", strip=True))
    definition = _normalize_definition_text(
        _dictionary_definition_text(definition_node)
    )
    if not wod or not definition:
        raise RuntimeError(f"Failed to parse word of the day from '{url}'")
    return wod, definition


def get_wod_gl(date: Optional[Union[datetime.datetime, datetime.date]] = None):
    """Galician word of the day from portaldaspalabras.gal.

    Two-step: home page links the current word inside an `.entry-title`
    anchor; that link goes to a `palabra-do-dia/<slug>/` page that ships
    the definition under `div.palabra-do-dia-definition`.
    """
    base = "https://portaldaspalabras.gal"
    home = _http_get(f"{base}/").text
    soup = BeautifulSoup(home, "html.parser")
    link = None
    for a in soup.find_all("a", href=re.compile(r"/lexico/palabra-do-dia/[^/]+/?$")):
        anc = a.find_parent(class_=True)
        if anc and "entry-title" in (anc.get("class") or []):
            link = a
            break
    if link is None:
        raise RuntimeError(f"Failed to find current word link on '{base}'")
    word_url = link["href"]
    if word_url.startswith("/"):
        word_url = base + word_url

    word_html = _http_get(word_url).text
    soup = BeautifulSoup(word_html, "html.parser")
    h1 = soup.find("h1", {"class": "entry-title"})
    defi_node = soup.find("div", {"class": "palabra-do-dia-definition"})
    if h1 is None or defi_node is None:
        raise RuntimeError(f"Failed to parse word of the day from '{word_url}'")
    return h1.get_text(strip=True), defi_node.get_text(" ", strip=True)


def get_wod():
    response = _http_get(DICTIONARY_WOD_URL)
    response.raise_for_status()
    return _extract_dictionary_wod(response.text)


def get_wod_pt(pt_br=False):
    """Portuguese (pt-PT / pt-BR) word of the day from Priberam.

    Two-step: home shows the word in a `.dp-widget-palavradodia` widget
    with an `a.dp-palavradodia-card` link to the word page. The word
    page ships the definition under the per-variant `varpt`/`varpb`
    spans inside `.dp-definicao-header`, and the first definition line
    inside any `.dp-definicao-linha` block.
    """
    base = "https://dicionario.priberam.org"
    home = _http_get(f"{base}/").text
    soup = BeautifulSoup(home, "html.parser")
    widget = soup.find("div", {"class": "dp-widget-palavradodia"})
    if widget is None:
        raise RuntimeError(f"Failed to find Priberam WoD widget on '{base}'")
    card = widget.find("a", {"class": "dp-palavradodia-card"})
    if card is None or not card.get("href"):
        raise RuntimeError(f"Failed to find Priberam WoD link on '{base}'")
    href = card["href"]
    word_url = href if href.startswith("http") else f"{base}/{href.lstrip('/')}"

    word_html = _http_get(word_url).text
    soup = BeautifulSoup(word_html, "html.parser")
    header = soup.find("div", {"class": "dp-definicao-header"})
    if header is None:
        raise RuntimeError(f"Failed to parse Priberam WoD page '{word_url}'")
    variant_cls = "varpb" if pt_br else "varpt"
    span = header.find("span", {"class": variant_cls})
    word_link = span.find("a") if span else None
    if word_link is None:
        raise RuntimeError(f"Failed to read '{variant_cls}' variant from '{word_url}'")
    wod = word_link.get_text(strip=True)

    defi_line = soup.find(class_="dp-definicao-linha")
    inner = defi_line.find("span", {"class": "ml-4 p"}) if defi_line else None
    if inner is None:
        raise RuntimeError(f"Failed to parse Priberam definition from '{word_url}'")
    defi = inner.get_text(" ", strip=True).split("\n")[0].strip()
    return wod, defi


def get_wod_ca():
    """Catalan word of the day from rodamots.cat.

    Two-step: home page's first `<article>` link goes to the entry page.
    The entry's `h1.entry-title` wraps the word in `span.midleline` and
    the part-of-speech in `span.tipusgram`; the definition is the first
    `<p>` inside `div.innerdef`.
    """
    home = _http_get("https://rodamots.cat/").text
    soup = BeautifulSoup(home, "html.parser")
    art = soup.find("article")
    link = art.find("a") if art else None
    if link is None or not link.get("href"):
        raise RuntimeError("Failed to find current rodamots entry link")

    entry_html = _http_get(link["href"]).text
    soup = BeautifulSoup(entry_html, "html.parser")
    h1 = soup.find("h1", {"class": "entry-title single-title"})
    word_node = h1.find("span", {"class": "midleline"}) if h1 else None
    innerdef = soup.find("div", {"class": "innerdef"})
    defi_node = innerdef.find("p") if innerdef else None
    if word_node is None or defi_node is None:
        raise RuntimeError(f"Failed to parse rodamots entry '{link['href']}'")
    return word_node.get_text(strip=True), _normalize_definition_text(defi_node.get_text())


def get_wod_fr():
    response = _http_get(FR_WIKTIONARY_API, params={
        "action": "parse",
        "page": FR_WIKTIONARY_PAGE,
        "format": "json",
        "prop": "text"
    })
    response.raise_for_status()

    data = response.json()
    html = data.get("parse", {}).get("text", {}).get("*")
    if not html:
        raise RuntimeError("Failed to retrieve French word of the day")

    soup = BeautifulSoup(html, "html.parser")
    box = soup.find(id="main-etl")
    if box is None:
        raise RuntimeError("Failed to parse French word of the day")

    title = box.find("p", recursive=False)
    word_link = title.find("a") if title else None
    definition_list = box.find("ol", recursive=False)
    first_definition = definition_list.find("li", recursive=False) if definition_list else None

    if word_link is None or first_definition is None:
        raise RuntimeError("Failed to parse French word of the day")

    definition_node = BeautifulSoup(str(first_definition), "html.parser").find("li")
    if definition_node is None:
        raise RuntimeError("Failed to parse French word of the day")
    for nested in definition_node.find_all(["ul", "ol", "dl"]):
        nested.decompose()

    wod = word_link.get_text(strip=True)
    definition = _normalize_definition_text(
        definition_node.get_text(" ", strip=True)
    )
    return wod, definition


class WordOfTheDaySkill(OVOSSkill):

    def _remember_word(self, date: datetime.date, word: str):
        """Persist `word` as the word of the day for `date` in settings.

        Keyed by ISO date so lookups from `_speak_past_word` are a
        plain dict get; capped at `MAX_WORD_HISTORY` entries, dropping the
        oldest dates first (ISO keys sort lexicographically).
        """
        history = dict(self.settings.get("word_history") or {})
        history[date.strftime("%Y-%m-%d")] = word
        if len(history) > MAX_WORD_HISTORY:
            for key in sorted(history)[:len(history) - MAX_WORD_HISTORY]:
                del history[key]
        self.settings["word_history"] = history

    def _recall_word(self, date: datetime.date) -> Optional[str]:
        history = self.settings.get("word_history") or {}
        return history.get(date.strftime("%Y-%m-%d"))

    @intent_handler("word_of_the_day.intent")
    def handle_word_of_the_day_intent(self, message):
        """Speak today's word, or the word of an earlier day when the request
        names one ({date} slot or a ``past.voc`` word such as "yesterday")."""
        try:
            date = self._requested_date(message)
        except ValueError:
            # a {date} slot WAS captured but could not be parsed - say there
            # is no word for it instead of answering about another day
            self.speak_dialog("no_word_history")
            return
        if date is None or date >= now_local().date():
            self._speak_todays_word(message)
        else:
            self._speak_past_word(message, date)

    def _requested_date(self, message) -> Optional[datetime.date]:
        """The earlier day the request names, or None for today.

        The date comes from the {date} slot. Without a slot the matched
        ``before_yesterday.voc``, ``past.voc``, ``weekday.voc`` or ``ago.voc``
        phrase decides, because the m2v engine sends no slot. Only the matched
        phrase is parsed, never the whole utterance: "day" in "word of the
        day" would read as a date. Raises ValueError when the request names a
        day that is not an earlier day this skill can name with certainty.
        """
        today = now_local().date()
        slot = message.data.get("date")
        if slot:
            return self._past_date_of_slot(slot, today)
        utterance = (message.data.get("utterance") or "").lower()
        found = self._past_phrase(utterance, today)
        if found is None:
            return None
        date, start = found
        # "never mind yesterday, what is today's word": the later day word decides
        _, today_start = self._voc_match(utterance, "today", whole_word=True)
        if today_start is not None and today_start > start:
            return None
        return date

    def _past_phrase(self, utterance: str, today: datetime.date):
        """(day, position) of the first past-day phrase of the request, or None."""
        phrase, start = self._voc_match(utterance, "before_yesterday")
        if phrase:
            return today - datetime.timedelta(days=2), start
        phrase, start = self._voc_match(utterance, "past")
        if phrase:
            return self._parse_date(phrase) or today - datetime.timedelta(days=1), start
        phrase, start = self._voc_match(utterance, "weekday")
        if phrase:
            return self._weekday_date(phrase, today), start
        for voc, needs_number in (("ago", False), ("days", True)):
            phrase, start = self._voc_match(utterance, voc, whole_word=True)
            if phrase:
                date = self._date_around_marker(utterance, phrase, today, needs_number)
                return (date, start) if date else None
        return None

    def _weekday_date(self, text: str, today: datetime.date) -> Optional[datetime.date]:
        """The latest day, today included, that falls on the weekday ``text`` names.

        Line N of ``weekday.voc`` lists the spellings of weekday N (Monday is 0),
        so no date parser is involved. Returns None when ``text`` names no weekday.
        """
        text = _plain(text)
        found = [(len(_plain(spelling)), index)
                 for index, spellings in enumerate(self.resources.load_vocabulary_file("weekday"))
                 for spelling in spellings if _plain(spelling) in text]
        if not found:
            return None
        # the longest spelling wins: in fa-IR "شنبه" (Saturday) is inside "یکشنبه" (Sunday)
        index = max(found)[1]
        return today - datetime.timedelta(days=(today.weekday() - index) % 7)

    def _voc_match(self, utterance: str, voc: str, whole_word: bool = False):
        """(longest phrase of ``<voc>.voc`` in the utterance, its position) or (None, None)."""
        text = _plain(utterance)
        for phrase in sorted(self.voc_list(voc), key=len, reverse=True):
            plain = _plain(phrase)
            pattern = rf"(?<!\w){re.escape(plain)}(?!\w)" if whole_word else re.escape(plain)
            found = re.search(pattern, text)
            if found:
                return phrase.lower(), found.start()
        return None, None

    def _voc_phrase(self, utterance: str, voc: str, whole_word: bool = False) -> Optional[str]:
        """The longest phrase of ``<voc>.voc`` that the utterance contains."""
        return self._voc_match(utterance, voc, whole_word)[0]

    def _parse_date(self, text: str, anchor: Optional[datetime.datetime] = None) -> Optional[datetime.date]:
        """The date the parser reads in ``text``, or None. Parser errors count as no date."""
        try:
            parsed = extract_datetime(text, lang=self.lang, anchorDate=anchor)
        except Exception:
            LOG.exception(f"failed to parse a date in {self.lang} from {text!r}")
            return None
        return parsed[0].date() if parsed else None

    def _date_around_marker(self, utterance: str, marker: str, today: datetime.date,
                            needs_number: bool = False) -> Optional[datetime.date]:
        """Parse the smallest span around an "ago" marker that names a past day.

        The marker alone ("days ago") gives no number, and the words next to it
        ("three", "il y a") complete the phrase. A span counts only when it
        gives another day than the marker alone, so the number decides. When no
        span names a day, a marker that always means "ago" raises ValueError.
        A marker that is also an everyday word ("días" in "buenos días") raises
        only when a number stands next to it, and otherwise gives None.
        """
        alone = self._parse_date(marker)
        utterance, marker = _plain(utterance), _plain(marker)
        start = utterance.index(marker)
        before = utterance[:start].split()
        after = utterance[start + len(marker):].split()
        for size in range(1, MAX_SPAN_WORDS * 2 + 1):
            for left in range(min(size, MAX_SPAN_WORDS) + 1):
                right = size - left
                if right > MAX_SPAN_WORDS:
                    continue
                span = " ".join(before[len(before) - left:] + [marker] + after[:right])
                date = self._parse_date(span)
                if date and date < today and date != alone:
                    return date
        around = " ".join(before[-MAX_SPAN_WORDS:] + [marker] + after[:MAX_SPAN_WORDS])
        if needs_number and not self._has_number(around):
            return None
        raise ValueError(utterance)

    def _has_number(self, text: str) -> bool:
        try:
            return extract_number(text, lang=self.lang) is not False
        except Exception:
            return bool(re.search(r"\d", text))

    def _past_date_of_slot(self, slot: str, today: datetime.date) -> datetime.date:
        """The earlier day a {date} slot names with certainty.

        Today's word answers only a slot that says "today". A slot the parser
        reads as today, as a day with no number that the slot spells out, or
        as a day whose number is not in the slot is not certain, and raises
        ValueError. The parser resolves a weekday or a calendar date to its
        next occurrence, so a later result moves back by a month or a year (a slot with digits) when that earlier day parses
        from the same slot. A weekday word names the latest such day without
        the parser, and the weekday of today names today.
        """
        if self._voc_phrase(slot.lower(), "today", whole_word=True):
            return today
        digits = re.findall(r"\d+", slot)
        weekday = None if digits else self._weekday_date(slot, today)
        if weekday:
            return weekday
        date = self._parse_date(slot)
        if date is None:
            raise ValueError(slot)
        # ordinal words ("october twelfth") parse as the 1st of the month
        if (digits and date.day not in map(int, digits)) or (not digits and date.day == 1):
            raise ValueError(slot)
        if date < today:
            return date
        earlier = [date - relativedelta(months=1), date - relativedelta(years=1)] if digits else []
        for candidate in earlier:
            if candidate < today and self._same_date_from_before(slot, candidate):
                return candidate
        raise ValueError(slot)

    def _same_date_from_before(self, slot: str, date: datetime.date) -> bool:
        """True when the slot names ``date`` as the next occurrence after a
        day or three days before it, which is how a weekday or a calendar date
        behaves and how "tomorrow" does not."""
        for days in (1, 3):
            anchor = datetime.datetime.combine(date - datetime.timedelta(days=days), datetime.time(12))
            if self._parse_date(slot, anchor) != date:
                return False
        return True

    def _speak_todays_word(self, message):
        lang = self.lang.lower()
        primary_lang = lang.split("-")[0]
        try:
            if lang == "pt-br":
                wod, definition = get_wod_pt(pt_br=True)
            elif primary_lang == "pt":
                wod, definition = get_wod_pt()
            elif primary_lang == "en":
                wod, definition = get_wod()
            elif primary_lang == "fr":
                wod, definition = get_wod_fr()
            elif primary_lang == "ca":
                wod, definition = get_wod_ca()
            elif primary_lang == "gl":
                wod, definition = get_wod_gl()
            else:
                self.speak_dialog("unknown_wod")
                return
        except Exception:
            LOG.exception("Failed to retrieve word of the day")
            self.speak_dialog("unknown_wod")
            return

        self._remember_word(now_local().date(), wod)
        self.speak_dialog("word_of_day", {"word": wod})
        self.gui.show_text(definition, wod)
        self.speak(definition)
        SessionManager.get(message).set_intent_context(
            PREV_WOD_WORD_CONTEXT, wod, scope="shared", turns_remaining=3)

    def _speak_past_word(self, message, date: datetime.date):
        word = self._recall_word(date)
        if not word:
            self.speak_dialog("no_word_history")
            return
        self.speak_dialog("word_of_day", {"word": word})
        SessionManager.get(message).set_intent_context(
            PREV_WOD_WORD_CONTEXT, word, scope="shared", turns_remaining=3)

    @intent_handler("spell_wod.intent",
                     requires_context=[{"key": PREV_WOD_WORD_CONTEXT, "scope": "shared"}])
    def handle_spell_wod_intent(self, message):
        """Spell out the word from the active "prev_wod_word" conversation
        context. Gated on OVOS-CONTEXT-1 ``requires_context`` rather than a
        keyword vocab: "spell that"/"spell it" carry no word of their own,
        they only make sense as a follow-up to an answer that already set
        the context.
        """
        session = SessionManager.get(message)
        entry = (session.intent_context or {}).get(PREV_WOD_WORD_CONTEXT)
        if not isinstance(entry, dict) or not entry.get("value"):
            self.speak_dialog("no_word_history")
            return
        word = entry["value"]
        letters = " ".join(f"{letter}." for letter in word)
        self.speak_dialog("spell_word", {"word": word, "letters": letters})
