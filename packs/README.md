# Country packs

Everything that changes from one country, city or organisation to the next lives in a pack.
The engine contains no law, no phone number, no hospital and no organisation name, and a test
(`tests/test_multipack.py::test_no_country_specific_strings_in_code`) keeps it that way.

| Pack | Languages | Status |
|---|---|---|
| `ng-lagos` | English, Nigerian Pidgin | Reference pack. Fictional hospitals. Legal text awaiting verification. |
| `ke-nairobi` | English | Built from `docs/research/kenya-pack.md`. Fictional hospitals. Every legal line and contact is unverified. Kiswahili is the next step and needs a fluent reviewer; nothing was machine-translated. |

## Add a country in an afternoon

1. Copy `packs/ng-lagos/` to `packs/<country>-<city>/`.
2. `pack.json`: country, region, language codes (first is the default), currency, what the four
   amount buckets mean locally, local terms the extractor should know, and the organisation's name.
3. `messages.json`: keep every key. Rewrite the country-specific ones: the greeting, the three `A1.*`
   escalation messages, `E.clinical`, `E.handoff`. Add a field per extra language code.
4. `rights.json`, `asks.json`, `contacts.json`: the local law, the asks to management, and contacts.
5. `hospitals.seed.json`: at least five facilities (fictional for a demo).
6. Set every entry that mentions a law, a number or an organisation to `"verified": false`.
   A human who has read the primary source, and test-called the number, flips it to `true`.
   Until then the bot sends a safe fallback instead. `tests/test_multipack.py` fails if legal or
   contact content is marked verified without being on the human-verified list.
7. Add the pack id to the `PACKS` environment variable and run `uv run pytest`. The parity tests
   check that the new pack has every message key, all four asks and the amount buckets.
8. Add a few local stories to `evals/stories.jsonl` with `"pack": "<id>"` and run the evaluation.

Open `/?pack=<id>` for the chat and `/analyst?pack=<id>` for that country's patterns. Reports,
patterns, briefs and follow-ups never mix packs.
