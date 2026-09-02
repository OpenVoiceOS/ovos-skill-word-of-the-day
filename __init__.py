import datetime
import re

import requests
from typing import Optional, Union
from bs4 import BeautifulSoup
from ovos_workshop.decorators import intent_handler
from ovos_workshop.skills.auto_translatable import OVOSSkill
from ovos_utils.log import LOG
from ovos_utils.time import now_local


REQUEST_TIMEOUT = 20
REQUEST_HEADERS = {
    "User-Agent": "OVOS WordOfTheDay Skill/1.0 "
                  "(https://github.com/OpenVoiceOS/ovos-skill-word-of-the-day)"
}
FR_WIKTIONARY_API = "https://fr.wiktionary.org/w/api.php"
FR_WIKTIONARY_PAGE = "Wiktionnaire:Page d’accueil"
DICTIONARY_WOD_URL = "https://www.dictionary.com/e/word-of-the-day"


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

    @intent_handler("WordOfTheDayIntent.intent")
    def handle_word_of_the_day_intent(self, message):
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
                self.speak_dialog("unknown.wod")
                return
        except Exception:
            LOG.exception("Failed to retrieve word of the day")
            self.speak_dialog("unknown.wod")
            return

        self.speak_dialog("word.of.day", {"word": wod})
        self.gui.show_text(definition, wod)
        self.speak(definition)
