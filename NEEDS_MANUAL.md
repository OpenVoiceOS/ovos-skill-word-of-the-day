# Locale content needing native review

Every locale ships the same three intents: `word_of_the_day.intent`,
`past_word.intent` ("what was yesterday's word", "what was the word of the
day on {date}"), and `spell_wod.intent` ("spell that").

The `past_word.intent` and `spell_wod.intent` lines for `ca-ES`, `da-DK`,
`de-DE`, `es-ES`, `fr-FR`, `gl-ES`, `kab`, and `pt-PT` were written by a
language model and have not been reviewed by a native speaker. They are
candidates for review, not verified translations. `kab` (Kabyle) is
lower confidence than the others: it uses a less common language for
LLM output and its `word_of_the_day.intent` orthography could not be
cross-checked against an independent source.

`no.word.history.dialog` and `spell.word.dialog` — the dialogs
`past_word.intent` and `spell_wod.intent` speak — still exist only for
`en-US`. A native speaker of each other locale needs to add them; until
then, the two intents will parse and route in every locale, but the
spoken response they produce in a non-`en-US` locale is untested.
