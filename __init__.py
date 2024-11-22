import requests
from bs4 import BeautifulSoup
from ovos_workshop.decorators import intent_handler
from ovos_workshop.intents import IntentBuilder
from ovos_workshop.skills.auto_translatable import UniversalSkill


def get_wod():
    html = requests.get("https://www.dictionary.com/e/word-of-the-day").text

    soup = BeautifulSoup(html, "html.parser")

    h = soup.find("div", {"class": "otd-item-headword__word"})
    wod = h.text.strip()

    h = soup.find("div", {"class": "otd-item-headword__pos-blocks"})
    definition = h.text.strip().split("\n")[-1]

    return wod, definition


class WordOfTheDaySkill(UniversalSkill):
    def __init__(self, *args, **kwargs):
        # website is english only, apply bidirectional translation
        super().__init__(internal_language="en-us", *args, **kwargs)

    @intent_handler(IntentBuilder("WordOfTheDayIntent").require("WordOfTheDayKeyword"))
    def handle_word_of_the_day_intent(self, message):
        self.speak_dialog("word.of.day")
        wod, definition = get_wod()
        self.gui.show_text(definition, wod)
        self.speak(f"The word of the day is {wod}")
        self.speak(definition)
