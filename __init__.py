import requests
from bs4 import BeautifulSoup
from ovos_workshop.decorators import intent_handler
from ovos_workshop.intents import IntentBuilder
from ovos_workshop.skills.auto_translatable import OVOSSkill


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
        else:
            self.speak_dialog("unknown.wod")
            return

        self.speak_dialog("word.of.day", {"word": wod})
        self.gui.show_text(definition, wod)
        self.speak(definition)


