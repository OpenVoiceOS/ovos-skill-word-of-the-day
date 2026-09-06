# Locale gaps needing a native speaker

`en-US` ships three intents: `word_of_the_day.intent`, `past_word.intent`
("what was yesterday's word"), and `spell_wod.intent` ("spell that").

Every other locale (`ca-ES`, `da-DK`, `de-DE`, `es-ES`, `fr-FR`, `gl-ES`,
`kab`, `pt-PT`) ships only `word_of_the_day.intent`. Their existing `.voc`
and `.dialog` files contain no phrasing for "yesterday", "on {date}", or
"spell that/it" — there is no shipped content to source a `past_word.intent`
or `spell_wod.intent` from for these locales, so none were added. Inventing
translations would risk shipping a wrong or unnatural sentence, which is
worse than the gap.

A native speaker of each locale needs to contribute the phrasing for:

- `past_word.intent` — asking for the word of the day on a past date
  (e.g. "yesterday's word", "the word of the day on {date}")
- `spell_wod.intent` — a follow-up "spell that" / "spell it" utterance
- `no.word.history.dialog` / `spell.word.dialog` — the dialogs those two
  intents speak (only `en-US` has them)

Until then, `handle_past_word_intent` and `handle_spell_wod_intent` are
reachable only in `en-US`.
