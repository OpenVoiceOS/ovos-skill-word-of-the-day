# Locale gaps needing a native speaker

`en-US`, `eu-ES`, `it-IT`, `nl-NL`, `pt-BR`, and `sv-SE` ship the full intent
set: `word_of_the_day.intent`, `past_word.intent` ("what was yesterday's
word"), and `spell_wod.intent` ("spell that"), plus all four dialogs
(`word.of.day.dialog`, `unknown.wod.dialog`, `no.word.history.dialog`,
`spell.word.dialog`).

`ca-ES`, `da-DK`, `de-DE`, `es-ES`, `fr-FR`, `gl-ES`, `kab`, and `pt-PT` ship
only `word_of_the_day.intent` with `word.of.day.dialog` and
`unknown.wod.dialog`. Their `.voc` and `.dialog` files contain no phrasing
for "yesterday", "on {date}", or "spell that/it".

There is no shipped content to source a `past_word.intent` or
`spell_wod.intent` from for those locales, so none were added. Inventing
translations would risk shipping a wrong or unnatural sentence. That risk
is worse than the gap.

`da-DK` is a partial exception. It carries `no.word.history.dialog` and
`spell.word.dialog` translations with no `past_word.intent` or
`spell_wod.intent` to trigger them. Those two dialogs stay unreachable
there until the matching intents exist.

A native speaker of each locale without the full set needs to contribute
the phrasing for:

- `past_word.intent`: asking for the word of the day on a past date
  (e.g. "yesterday's word", "the word of the day on {date}")
- `spell_wod.intent`: a follow-up "spell that" / "spell it" utterance
- `no.word.history.dialog` / `spell.word.dialog`: the dialogs those two
  intents speak

Until a locale gets that phrasing, `handle_past_word_intent` and
`handle_spell_wod_intent` stay reachable only in the six locales with the
full set.
