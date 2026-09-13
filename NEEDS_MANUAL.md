# Locale gaps needing a native speaker

`en-US`, `eu-ES`, `it-IT`, `nl-NL`, `pt-BR`, and `sv-SE` ship the full intent
set: `word_of_the_day.intent`, `past_word.intent` ("what was yesterday's
word"), and `spell_wod.intent` ("spell that"), plus all four dialogs
(`word_of_day.dialog`, `unknown_wod.dialog`, `no_word_history.dialog`,
`spell_word.dialog`).

`ca-ES`, `da-DK`, `de-DE`, `es-ES`, `fr-FR`, `gl-ES`, and `pt-PT` now also
ship `past_word.intent` and `spell_wod.intent`, machine-translated from the
en-US phrasing (`.intent` lines, `google.com/translate`-grade output — a
candidate for review, not a verified translation). `kab` still has neither:
linguonnx has no permissive route into Kabyle, and inventing the phrasing by
hand risks a wrong or unnatural sentence, worse than the gap.

`ca-ES`, `de-DE`, `es-ES`, `fr-FR`, `gl-ES`, and `pt-PT` also gained
`no_word_history.dialog` (machine-translated). `da-DK` already had it.
`ca-ES`, `de-DE`, `es-ES`, `fr-FR`, and `pt-PT` gained `spell_word.dialog`
too; `gl-ES` did not — every attempt translating "{word} is spelled
{letters}" through `nos-coda_iacobus-en-gl-int8` either dropped a `{slot}`
or produced unrelated text, so the line was dropped rather than shipped
broken. `gl-ES/spell_word.dialog` still needs a native speaker (or a better
Galician route) to write directly.

`kab` still ships only `word_of_the_day.intent` with `word_of_day.dialog`
and `unknown_wod.dialog`.

A native speaker of each locale below needs to review or contribute:

- `kab`: `past_word.intent`, `spell_wod.intent`, `no_word_history.dialog`,
  `spell_word.dialog` — all four, from scratch.
- `ca-ES`, `da-DK`, `de-DE`, `es-ES`, `fr-FR`, `pt-PT`: review the
  machine-translated `past_word.intent` and `spell_wod.intent` phrasing.
- `ca-ES`, `de-DE`, `es-ES`, `fr-FR`, `pt-PT`: review the machine-translated
  `no_word_history.dialog` and `spell_word.dialog` text.
- `gl-ES`: review `past_word.intent`, `spell_wod.intent`, and
  `no_word_history.dialog`; write `spell_word.dialog` directly.

Until `kab` gets that phrasing, `handle_past_word_intent` and
`handle_spell_wod_intent` stay unreachable there.
