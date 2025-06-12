import datetime

import requests
from typing import Optional, Union
from bs4 import BeautifulSoup
from ovos_workshop.decorators import intent_handler
from ovos_workshop.intents import IntentBuilder
from ovos_workshop.skills.auto_translatable import OVOSSkill
from ovos_utils.time import now_local


def get_wod_gl(date: Optional[Union[datetime.datetime, datetime.date]] = None):
    url = 'https://portaldaspalabras.gal/lexico/palabra-do-dia'
    now = date or now_local()
    data = {
        'orde': 'data',
        'comeza': '',
        'palabra': '',
        'data-do': f'{now.year}-{now.month}-{now.day}',
        'data-ao': f'{now.year}-{now.month}-{now.day}',
        'paged': ''
    }

    def post_retry(u, data=None):
        for _ in range(3):
            try:
                response = requests.post(u, data=data)
                if response.status_code == 200:
                    return response
            except:
                continue
        raise RuntimeError(f"Failed to retrieve data from '{url}'")

    response = post_retry(url, data)
    soup = BeautifulSoup(response.content, "html.parser")
    h = soup.find("div", {"class":"archive-palabra-do-dia"})
    if h is None:
        if date is None:
            return get_wod_gl(now - datetime.timedelta(days=1))
        raise RuntimeError(f"Failed to parse word of the day from '{url}'")
    wod = h.text.strip().split("\n")[-1]

    response = post_retry(f"{url}/{wod}")
    soup = BeautifulSoup(response.content, "html.parser")
    h = soup.find("div", {"class": "palabra-do-dia-definition"})
    if h is None:
        raise RuntimeError(f"Failed to parse word of the day from '{url}'")
    return wod, h.text


def get_wod():
    html = requests.get("https://www.dictionary.com/e/word-of-the-day").text

    soup = BeautifulSoup(html, "html.parser")

    h = soup.find("div", {"class": "otd-item-headword__word"})
    wod = h.text.strip()

    h = soup.find("div", {"class": "otd-item-headword__pos-blocks"})
    definition = h.text.strip().split("\n")[-1]

    return wod, definition


def get_wod_pt(pt_br=False):
    url = "https://dicionario.priberam.org/"
    html = requests.get(url).text
    soup = BeautifulSoup(html, "html.parser")

    h = soup.find("div", {"class": "dp-definicao-header"})
    if pt_br:
        wod = h.find("span", {"class": "varpb"}).text.strip()  # pt-br
    else:
        wod = h.find("span", {"class": "varpt"}).text.strip()  # pt-pt

    h = soup.find("p", {"class": "ml-12 py-4 dp-definicao-linha"})
    defi = h.find("span", {"class": "ml-4 p"}).text.split("\n")[0].strip()
    return wod, defi


def get_wod_ca():
    url = "https://rodamots.cat/"
    html = requests.get(url).text
    soup = BeautifulSoup(html, "html.parser")
    h = soup.find("article").find("a")
    url2 = h["href"]
    html = requests.get(url2).text
    soup = BeautifulSoup(html, "html.parser")
    w = soup.find("h1", {"class": "entry-title single-title"}).text.strip()[:-1].split("[")[0].strip()
    d = soup.find("div", {"class": "innerdef"}).find("p").text
    return w, d


class WordOfTheDaySkill(OVOSSkill):

    @intent_handler(IntentBuilder("WordOfTheDayIntent").require("WordOfTheDayKeyword"))
    def handle_word_of_the_day_intent(self, message):
        l = self.lang.lower()
        if l.lower() == "pt-br":
            wod, definition = get_wod_pt(pt_br=True)
        elif l.lower().split("-")[0] == "pt":
            wod, definition = get_wod_pt()
        elif l.lower().split("-")[0] == "en":
            wod, definition = get_wod()
        elif l.lower().split("-")[0] == "ca":
            wod, definition = get_wod_ca()
        elif l.lower().split("-")[0] == "gl":
            wod, definition = get_wod_gl()
        else:
            self.speak_dialog("unknown.wod")
            return

        self.speak_dialog("word.of.day", {"word": wod})
        self.gui.show_text(definition, wod)
        self.speak(definition)


