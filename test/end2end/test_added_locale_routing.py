"""Proves the intent files for eu-ES, it-IT, nl-NL, pt-BR and sv-SE
route an utterance, not just that they exist.

The skill's intent loader looks up resources by their lowercase,
underscore-separated base name. A locale that ships an intent file under
the wrong name, or is missing the file entirely, loads without error but
never routes any utterance for that intent -- a silent failure that only
shows up when a real user speaks to the skill in that language.

Each case below boots a MiniCroft with the locale under test as the ACTIVE
language (`get_minicroft([SKILL_ID], lang=<locale>)`, not merely
`secondary_langs`), sends a real utterance in that language, and asserts
the skill's `word_of_the_day` intent handles it, so a locale with a
missing or misnamed intent resource fails this test the same way it fails
for a real user.

ca-ES, da-DK, de-DE, es-ES, fr-FR, gl-ES, kab and pt-PT are not covered by
a per-locale active-language routing test in this suite.
"""
from unittest import TestCase
from unittest.mock import patch

import pytest

ovoscope = pytest.importorskip("ovoscope", reason="ovoscope not installed")

from ovos_bus_client.message import Message  # noqa: E402
from ovos_bus_client.session import Session  # noqa: E402
from ovos_utils.log import LOG  # noqa: E402
from ovoscope import get_minicroft  # noqa: E402

SKILL_ID = "ovos-skill-word-of-the-day.openvoiceos"
INTENT = f"{SKILL_ID}:word_of_the_day"

# one representative utterance per added locale, taken from that locale's
# own word_of_the_day.intent template
_LOCALE_UTTERANCES = {
    "eu-ES": "zein da eguneko hitza",
    "it-IT": "qual è la parola del giorno",
    "nl-NL": "wat is het woord van de dag",
    "pt-BR": "qual é a palavra do dia",
    "sv-SE": "vad är dagens ord",
}


def _patch_parsers():
    fake = ("testword", "a word used in tests")
    import ovos_skill_word_of_the_day as mod
    targets = [
        "get_wod", "get_wod_pt", "get_wod_fr",
        "get_wod_ca", "get_wod_gl",
    ]
    return [patch.object(mod, name, return_value=fake) for name in targets if hasattr(mod, name)]


class _AddedLocaleRoutingBase:
    """Mixin: boots a fresh MiniCroft per locale with that locale ACTIVE."""
    lang = None

    @classmethod
    def setUpClass(cls):
        LOG.set_level("CRITICAL")
        cls._patches = _patch_parsers()
        for p in cls._patches:
            p.start()
        cls.minicroft = get_minicroft([SKILL_ID], lang=cls.lang)

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "minicroft", None):
            cls.minicroft.stop()
        for p in getattr(cls, "_patches", []):
            p.stop()
        LOG.set_level("CRITICAL")

    def test_utterance_routes_to_word_of_the_day(self):
        utterance = _LOCALE_UTTERANCES[self.lang]
        session = Session(f"added-locale-{self.lang}")
        session.lang = self.lang
        session.pipeline = ["ovos-padacioso-pipeline-plugin-high"]

        message = Message(
            "recognizer_loop:utterance",
            {"utterances": [utterance], "lang": self.lang},
            {"session": session.serialize()},
        )

        seen = []
        for msg_type in (INTENT, "speak", "complete_intent_failure",
                         "ovos.utterance.handled"):
            self.minicroft.bus.on(msg_type, lambda m: seen.append(m.msg_type))

        response = self.minicroft.bus.wait_for_response(
            message, "ovos.utterance.handled", timeout=15)

        self.assertIsNotNone(
            response, f"no ovos.utterance.handled for {self.lang}: {utterance!r}")
        self.assertIn(
            INTENT, seen,
            f"{self.lang} utterance {utterance!r} did not route to "
            f"{INTENT} (saw: {seen})")
        self.assertNotIn(
            "complete_intent_failure", seen,
            f"{self.lang} utterance {utterance!r} fell through to "
            f"complete_intent_failure (saw: {seen})")


class TestAddedLocaleEuES(_AddedLocaleRoutingBase, TestCase):
    lang = "eu-ES"


class TestAddedLocaleItIT(_AddedLocaleRoutingBase, TestCase):
    lang = "it-IT"


class TestAddedLocaleNlNL(_AddedLocaleRoutingBase, TestCase):
    lang = "nl-NL"


class TestAddedLocalePtBR(_AddedLocaleRoutingBase, TestCase):
    lang = "pt-BR"


class TestAddedLocaleSvSE(_AddedLocaleRoutingBase, TestCase):
    lang = "sv-SE"
