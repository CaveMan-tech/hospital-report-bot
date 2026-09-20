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
   Optional `references.json`: documents a reporter can open to read the source for themselves
   (title, whether it is law or policy, size, https link). A right lists the ones behind it in
   `"references": [...]`. Prefer official hosts, state the size honestly, and sign one off only
   after opening the link on a phone.
5. `hospitals.seed.json`: at least five facilities (fictional for a demo).
6. Mark every message that mentions a law, a number or an organisation `"gated": true`, leave
   it `"verified": false`, and list what it must be checked against in `check_against`. Rights,
   asks and contacts are always gated. Until a human signs an entry off, the bot sends a safe
   fallback instead. A bare `"verified": true` does not count: the sign-off must say who, when and
   against what, and a test enforces it. See "Verifying content" below.
7. Add the pack id to the `PACKS` environment variable and run `uv run pytest`. The parity tests
   check that the new pack has every message key, all four asks and the amount buckets.
8. Add a few local stories to `evals/stories.jsonl` with `"pack": "<id>"` and run the evaluation.

## Verifying content

```bash
uv run python -m app.verify list <pack>
uv run python -m app.verify mark <pack> <messages|rights|contacts|asks> <id> --by "Your Name" --source "citation and URL"
uv run python -m app.verify unmark <pack> <file> <id>
```

`/analyst/content?pack=<id>` shows every gated entry beside the source to check it against, and
who has signed it off. Sign-off is stored in the pack files, so `git log -p packs/` is the audit
trail. For phone numbers, "verified" means someone test-called it.

Open `/?pack=<id>` for the chat and `/analyst?pack=<id>` for that country's patterns. Reports,
patterns, briefs and follow-ups never mix packs.
