# Build Spec: Hospital Pattern Reporting (working title: [BOT_NAME])

Andela x OSF Hackathon. Deadline **Mon 21 Sept 2026, 23:59 UTC**. Target submit time: Mon 18:00 UTC.
Tracks: Safety, Reporting & Protection + Transparency & Accountability.

**One line:** people with no audience report privately and get immediate help; an advocacy organisation gets clean, anonymised, aggregated patterns per hospital that it can turn into public pressure.

**Deployment model:** the bot is one cog in a larger organisation (health-accountability NGO or investigative newsroom). The bot collects, protects, structures and aggregates. The organisation verifies, publishes and campaigns (X, print media, direct submissions to governing bodies). The build covers the bot plus a thin analyst view that proves the loop closes.

**Pitch spine (Ikechi's reasoning, quote in deck):**
1. Official complaint channels route reports to the institution, where they die one by one.
2. The only thing that works in Nigeria is public pressure, and X is where that pressure lands.
3. Today a call-out only works if you have followers or someone dies. A poor patient with 40 followers gets nothing, and a lone story is easy to dismiss.
4. So: collect privately, aggregate, and hand the *pattern* to an organisation with the reach, editorial checks and standing to campaign on it, with a specific ask addressed to the body that can fix it.

Markers: `[VERIFY]` = check against primary source before shipping. `[TBD]` = open decision. Pidgin is a first draft for Ikechi to correct.

Judging criteria (25% each): uniqueness, scalability across geographies, AI coding tool usage, presentation/track alignment. Sections 9 to 11 exist to score the last three.

---

## 1. Design rules

1. **Assume the user is angry, tired, stressed, or all three.** Acknowledge first. One free-text story. Never a form.
2. **Maximum three follow-up questions.** The AI extracts the rest. Every closed question (danger check, opt-in, follow-up status, when, which department) comes with tap-to-answer options, so nobody has to type YES. Options are part of the engine's reply (`quick_replies`), so WhatsApp and Telegram adapters can render them natively; tapped `when` and `department` answers map directly to field values with no AI call.
3. **Safety check before anything else.**
4. **The AI writes nothing a reporter reads.** It classifies and extracts. Every message, including the acknowledgement, is pre-written in the pack; legal claims and phone numbers additionally need a human `verified` flag; numbers in briefs are template-filled. Deterministic nets run on top of the model for handoff phrases, Pidgin detection and scrubbing identifiers from summaries.
5. **No clinical judgement.** Rights and conduct only.
6. **No identity collected.** No name, phone, or login. A reference code is the only link.
7. **Honest about limits.** The bot cannot send help, reports are unverified, and the story is processed by a third-party AI provider. It says all three.
8. **Reply in the user's language** (English, Pidgin in PoC; Yoruba, Hausa, Igbo, voice notes on roadmap).
9. **The tool publishes nothing itself.** No public counts, no public page. Patterns go to the partner organisation's analysts, and a human there decides what is used.
10. **Patterns are signals, not rates.** Wording in every brief is always "N unverified reports, warrants investigation". No percentages, no hospital rankings, no staff names.
11. **Frame patterns as system failure, not staff villainy.** Deposit demands often reflect unfunded emergency care. The ask targets policy and management.
12. **Demo uses fictional hospitals and a fictional partner organisation.** Seeded data against real names is fabricated allegation, label or not.

---

## 2. Categories

| Code | Meaning | Default branch |
|---|---|---|
| `emergency_refused` | Emergency care refused or delayed until a deposit or other condition is met | Severe if ongoing |
| `detention` | Patient (or body) held over an unpaid bill | Severe if ongoing |
| `abuse` | Verbal or physical abuse by staff | Non-severe |
| `neglect` | Left unattended, staff absent | Non-severe, unless patient is critical now |
| `other` | Anything else, including clinical complaints | Non-severe |

These four were chosen as the problems most recognisable to anyone who has used a Lagos public hospital.

**Categories stay few; detail lives in facets.** Splitting categories (child neglect vs adult neglect) would fragment counts below the pattern threshold. Instead every report carries facets the analyst can slice by:

| Facet | Values |
|---|---|
| `patient_group` | `newborn`, `child`, `adult`, `pregnant`, `elderly`, `unknown`. Coarse on purpose: never an exact age. |
| `subtype` | `emergency_refused`: `deposit_demanded`, `no_bed_space`, `no_staff`, `other`. `detention`: `patient_held`, `body_held`. `abuse`: `verbal`, `physical`, `humiliation`, `other`. `neglect`: `left_unattended`, `staff_absent`, `calls_ignored`, `other`. |
| `harm_outcome` | `none`, `condition_worsened`, `death`, `unknown` |
| `time_bucket` | `day`, `night`, `weekend`, `unknown` |
| `money_demanded` | true / false / null, with `amount_bucket`: `small`, `medium`, `large`, `very_large`, `unknown`. Each pack defines the thresholds in its own currency. |

**Slice privacy rule:** the threshold of 5 applies to every cell of every slice, not only the top-level pattern. A slice with fewer than 5 reports shows as "fewer than 5". Enough facets combined can describe one family.

---

## 3. Conversation flow

```
S0 GREETING (includes privacy line)
   |
S1 STORY (free text) --> AI extraction (section 5)
   |
S2 DANGER CHECK (skipped only if story is clearly in the past)
   |
   |-- severe --> A1 escalation message (by category)
   |              A2 capture hospital if missing (1 question)
   |              A3 reference code + follow-up opt-in
   |
   |-- not severe --> B1 fill missing fields (max 3 questions)
                      B2 rights check
                      B3 self-help steps
                      B4 reference code + counted line
                      B5 follow-up opt-in

F  FOLLOW-UP (next day, opt-in only)
   F1 status question --> F2 reply by status ("worse" re-enters S2)
```

### Severity rules (deterministic, applied to AI output)

- User answers YES to danger check: **severe. Always wins.**
- `category` in (`emergency_refused`, `detention`) and `is_ongoing` is not `false`: **severe**.
- `category` = `neglect`, `is_ongoing` true, `critical_condition` true: **severe**.
- AI returns `severity: "uncertain"`: ask the danger check. Never guess.
- Skip the danger check only when the event is clearly in the past.

---

## 4. Bot messages

`{braces}` are system-filled. `{ack}` is the pre-written `S1.ack` message. No AI-written text is shown to a reporter.

### S0 Greeting

**EN:** Hello. This is a safe place to report what happened to you, or to someone you know, at a government hospital. You do not need to give your name. Tell me what happened, in your own words. You can write in English or Pidgin.
_(small print under the input)_ Your words are read by an AI service to understand your report. We do not keep your original message, only a short summary with names removed.

**PCM:** Hello. For here, you fit report wetin happen to you or your person for government hospital. You no need give your name. Just tell me wetin happen, as e take happen. You fit write am for English or Pidgin.
_(small print)_ Na AI dey read wetin you write make e understand your report. We no dey keep your original message, na only short summary wey no get name.

### S2 Danger check

**EN:** {ack} One quick question first. Is anyone in danger right now? For example, someone who needs urgent treatment and is not getting it, or someone being held at the hospital. Reply YES or NO.

**PCM:** {ack} One quick question first. Anybody dey for danger as we dey talk so? Like person wey need treatment sharp sharp but dem never treat am, or person wey dem hold for hospital. Reply YES or NO.

### A1 Severe: emergency care refused

**EN:**
What you describe is against the law. Section 20 of the National Health Act says no hospital or health worker may refuse a person emergency treatment for any reason.

Do this now:
1. If the person is getting worse, getting care comes first. Call 112 or 767 (free in Lagos), or go to the nearest other hospital. Do not stay to argue.
2. If you can, ask calmly for the most senior doctor or officer on duty and say: "Section 20 of the National Health Act says you cannot refuse emergency treatment."
3. Note the time, the department, and who you spoke to.

I cannot send anyone to you. I will record this so it is counted.

**PCM:**
Wetin you talk so, law no gree am. Section 20 of National Health Act talk say no hospital or health worker fit refuse to treat person wey get emergency, for any reason.

Do this one now:
1. If the person condition dey worse, make e get treatment first. Call 112 or 767 (e free for Lagos), or carry am go another hospital wey near. No stay dey argue.
2. If you fit, ask gently for the most senior doctor or officer wey dey duty, tell am: "Section 20 of National Health Act talk say una no fit refuse emergency treatment."
3. Write the time, the department, and who you follow talk.

I no fit send anybody come meet you. But I go record am make e count.

Sources: National Health Act 2014 s.20(1),(2) (fine N100,000, up to six months, or both). Lagos lines 112 and 767. `[VERIFY both again against primary sources before marking verified]`. The Act forbids refusal; it does not say treatment is free. The bot never claims that.
`[TBD Ikechi: does step 2 help or inflame in a real Lagos emergency ward? Drop it if it inflames.]`

### A1 Severe: detention over unpaid bill

This message deliberately states no legal conclusion, so it does not depend on a lawyer's sign-off.

**EN:**
Many people in Nigeria have faced this, and you have options. A hospital bill is a debt, and there are proper ways to settle a debt.

What you can do:
1. Ask to speak to the hospital's medical social services (social welfare) unit about a payment plan or waiver. `[VERIFY unit name]`
2. Ask for the itemised bill in writing.
3. Free legal help: {contact:legal_aid} `[VERIFY: Lagos Office of the Public Defender, Legal Aid Council, NHRC, with numbers]`

I cannot send anyone to you. I will record this so it is counted.

**PCM:**
Plenty people for Nigeria don face this kind thing, and you get options. Hospital bill na debt, and correct way dey to settle debt.

Wetin you fit do:
1. Ask make you see the hospital medical social services (social welfare) people, make una talk about how you go pay small small or whether dem fit waive am.
2. Ask make dem give you the bill for paper, with everything wey dem charge written.
3. Free lawyer help: {contact:legal_aid}

I no fit send anybody come meet you. But I go record am make e count.

### A2 / B1 Missing-field questions (only what is missing, this order, max three)

| Field | EN | PCM |
|---|---|---|
| Hospital | Which hospital is this? | Which hospital be this? |
| Department | Which part of the hospital? For example emergency, maternity, children's ward. | Which side for the hospital? Like emergency, maternity, children ward. |
| When | When did this happen? Today, this week, or earlier? | When e happen? Today, this week, or e don tey? |
| Category confirm (low confidence only) | Just to be sure I understand: is this mainly about {category_plain}? | Make I sure say I understand: na {category_plain} be the main matter? |

Hospital is the one required field. A report with no hospital is stored but cannot join a pattern.

### B2 Rights check

From the country pack's `rights.json`, by category.

| Category | Right shown | Source |
|---|---|---|
| `abuse` | You have the right to be treated with respect and dignity. | Patients' Bill of Rights (2018) `[VERIFY wording]` |
| `neglect` | You have the right to quality care, and to urgent attention when you need it. | Patients' Bill of Rights `[VERIFY]` |
| any | You have the right to complain and to be heard. | Patients' Bill of Rights `[VERIFY]` |

**EN template:** What happened to you is not acceptable, and it is not just your opinion. {right_text} ({source})
**PCM template:** Wetin dem do you no correct, and no be only you talk am. {right_text} ({source})

### B3 Self-help steps

**Abuse (EN):**
1. If you feel safe doing so, ask for the nurse in charge or matron of the ward and tell them what happened.
2. Note the time, the ward, and what was said or done. If someone saw it, remember who.
3. You do not have to confront anyone. Reporting here already counts.

**Neglect (EN):**
1. Ask at the nurses' station who the nurse in charge is and which doctor is on call.
2. If the patient is getting worse, tell me now and I will show you what to do.
3. Note the time you asked for help and how long you waited.

`[Pidgin versions after English is approved.]`

### B4 Receipt

**EN:** Your report is recorded. Your code is **{ref_code}**. Keep it. It is the only way to check or update your report. I did not store your name or number.

**Counted line (no numbers, ever):** Your report has been counted. When enough reports about the same problem build up at a hospital, the pattern (numbers only, never stories) goes to {org_name}, who use it to push publicly for change at that hospital.

**PCM:** We don record your report. Your code na **{ref_code}**. Keep am well. Na only that code you fit use check or update your report. I no keep your name or number.
We don count your report. When plenty report about the same wahala gather for one hospital, the pattern (na only numbers, no be story) go reach {org_name}, wey go use am push for change for that hospital for public.

The receipt never shows a report number or count: that would leak counts below the pattern threshold to anyone who submits, and would tell the first reporter they are alone.

### B5 / A3 Follow-up opt-in

**EN:** May I check in tomorrow to ask if anything changed? It helps show whether hospitals fix problems. Reply YES or NO.
**PCM:** I fit check on you tomorrow to ask whether anything change? E go help show whether hospital dey fix matter. Reply YES or NO.

Web PoC: user returns with their code; a demo-only "simulate next day" control triggers F1. Production: WhatsApp template message.

### F1 Follow-up

**EN:** Hello again. Yesterday you reported {category_plain} at {hospital}. How are things now?
1. It was sorted out
2. Nothing has changed
3. It got worse
4. We have left the hospital

**F2:** (1) `resolved`, thank. (2) `unchanged`, repeat self-help. (3) `worse`, go to danger check. (4) `left`, thank.

Follow-up data is only ever reported as "of the N people who answered a follow-up, M said nothing had changed". Never as a percentage or a resolution rate.

### Edge cases

| Situation | Behaviour |
|---|---|
| Clinical complaint | Say plainly the bot cannot judge medical decisions. Record as `other`. Point to regulator `[VERIFY: MDCN route]`. |
| Sexual assault, violence, user in crisis | Out of scope for patterns. Hand off immediately `[VERIFY: Lagos DSVA line etc.]`. Skip normal flow. |
| User names a staff member | Accept, strip from stored summary, tell user names are never published. |
| Private hospital | Store with `facility_type`. Excluded from patterns in PoC. |
| Reporter is hospital staff | Store `reporter_role = staff`. Always ask the danger question rather than assume (a staff member describing a practice is not necessarily beside a patient in danger). If not in danger, skip the patient-oriented rights and self-help text and send `B3.staff`: no need to confront anyone, note dates and instructions but never copy patient records, do not use work devices or hospital Wi-Fi. Counts as one report like any other. Dedicated whistleblower channel on roadmap. |
| Page reloads or the network drops mid-report | The visible chat is kept in the tab's `sessionStorage` only (never `localStorage`, never the server), so a reload resumes where they were, with the tap options restored. A message that failed to send is not lost: "Try again" resends it. If the server session has expired, the bot says so and starts again. |
| Someone walks up behind the reporter | **Hide this chat**: wipes the chat from the device, deletes the unfinished conversation on the server immediately (`POST /api/chat/forget`) rather than at expiry, and leaves with `location.replace`, so the Back button does not return to it. A finished report is never affected. |
| Nonsense or abusive input | One polite retry, then end session. Nothing stored. |
| Prompt injection in story ("ignore your instructions...") | Extraction prompt treats the story as data only. Output is schema-validated; invalid JSON or out-of-enum values fall back to `other` + danger check. |

---

## 5. AI extraction contract

One LLM call after the story, and again after each answer with running context. Model: OpenAI `gpt-5-mini` (id pinned in `OPENAI_MODEL` env) using structured outputs (JSON schema), returned as a validated Pydantic model via Pydantic AI (invalid output is rejected and retried). All calls go through one `extract()` wrapper so the provider can be swapped. `EXTRACT_MODE=mock` runs a keyword-based stub for local development and tests without a key.

```json
{
  "language": "a language code from the pack, e.g. en | pcm",
  "category": "emergency_refused | detention | abuse | neglect | other",
  "category_confidence": 0.0,
  "secondary_categories": [],
  "hospital_name_raw": "string or null",
  "department": "emergency | maternity | paediatrics | outpatient | ward | pharmacy | lab | records | other | unknown",
  "incident_timing": "ongoing | today | this_week | this_month | older | unknown",
  "is_ongoing": true,
  "critical_condition": false,
  "severity": "severe | not_severe | uncertain",
  "reporter_role": "patient | relative | witness | staff | unknown",
  "patient_group": "newborn | child | adult | pregnant | elderly | unknown",
  "subtype": "per-category enum, see section 2",
  "harm_outcome": "none | condition_worsened | death | unknown",
  "time_bucket": "day | night | weekend | unknown",
  "money_demanded": null,
  "amount_bucket": "small | medium | large | very_large | unknown",
  "clinical_complaint": false,
  "safety_handoff": "none | sexual_violence | self_harm | other_violence",
  "implausible": false,
  "summary_redacted": "One or two neutral sentences. No names, ages, phone numbers, bed numbers, or exact dates.",
  "missing_fields": ["hospital", "department", "when"]
}
```

**Raw story handling:** the raw story lives in `sessions.context` only while the chat is active. It is deleted from the context the moment the report row is written, and sessions expire after 2 hours. The honest public claim is "we do not retain your original message", plus the third-party AI disclosure in S0.

Hospital matching: case-insensitive fuzzy match on `hospitals.name` and `aliases`. No match: store raw name with `hospital_id = null`, flag for review.

---

## 6. Data model (Postgres)

The full schema is `db/schema.sql`. Three tables:

- **`reports`**: one row per report. Structured fields and facets (section 2), `summary_redacted`, `ref_code_hmac`, `credibility` (`ok`, `review`, `excluded`), `dedupe_key`, `extraction_version`, `extra jsonb` for future facets, `is_sample`. Never the raw story, never the code, never an identifier.
- **`followups`**: next-day answers, linked to a report.
- **`sessions`**: short-lived conversation state. The raw story lives in `context` only while the chat is active, is removed the moment the report row is written, and unfinished sessions are purged after 2 hours.

Hospitals are part of the country pack (`hospitals.seed.json`), not a table, so a deployment is fully described by its pack. Reports reference them by pack id; an unmatched name is kept in `hospital_name_raw` and held for review.

Only the server talks to the database. On Railway it is reachable solely over the private network from the app service, so there is no public database endpoint at all. The schema is applied automatically at startup (every statement is idempotent).

Patterns are computed in `app/analyst.py` from the store, so the same logic runs on Postgres and on the in-memory store. Both stores are held to one contract test suite: group by hospital and category over 90 days, count only `credibility = 'ok'`, require at least 5, exclude private facilities.

Why a threshold of 5 even for analysts (deck talking point): a count of 1 on a quiet ward can identify the reporter, and the partner organisation should never be in a position to identify anyone. Analysts only ever see redacted summaries. In breakdowns, cells under 5 are masked, and when any cell is masked the visible cells are rounded down ("10+") so the masked value cannot be found by subtraction.

Reference codes: 12 chars, Crockford base32 (about 60 bits), shown as `XXXX-XXXX-XXXX`. Stored as HMAC with a server secret, so a leaked table cannot be brute-forced. Lookup endpoint is rate-limited.

### Abuse and credibility controls (PoC level, stated honestly)

- Rate-limit `/api/chat` and `/api/report/lookup` per IP, in memory, IP never stored.
- `dedupe_key = HMAC(daily rotating salt, IP)`. Same key + same hospital + same category within 24h: second report gets `credibility = 'review'`. Salt is discarded daily, so the key cannot be linked to a person afterwards.
- AI `implausible = true`: `credibility = 'review'`.
- Threshold counts only `ok` reports. Analyst sees the flagged count beside every pattern and can exclude reports.
- The analyst view and every exported brief say "unverified reports".
- Roadmap: optional evidence (photo of bill/receipt, EXIF stripped), partner-verified reports, reporter reputation via ref code.

---

## 7. Analyst view: where the loop closes

The bot's job ends at clean data. This thin slice proves the data is usable for advocacy. It must be in the demo video: report goes in on a phone, pattern appears on the organisation's screen, brief comes out.

**Page `/analyst`** (guarded by `ANALYST_PASSWORD` env). Header shows the fictional partner organisation's name from the pack.

- **Patterns table:** one row per hospital + category from the `patterns` view: reports in 90 days, followed up, unchanged or worse, flagged count. Banner "SAMPLE DATA, fictional hospitals" whenever `includes_sample_data`.
- **Pattern detail:** the redacted summaries behind the pattern, breakdowns by department, `patient_group`, `subtype`, `harm_outcome` and `time_bucket` (cells under 5 shown as "fewer than 5"), and an "Exclude report" action (sets `credibility = 'excluded'`).
- **Export pattern brief:** one button, one page of markdown (download or copy). Pure template fill; numbers, law and ask come from the view and the pack, never from the LLM:
  - Headline: "{report_count} unverified reports of {category_plain} at {hospital}, {period}"
  - What was reported, in one template sentence, plus "of the N who answered a follow-up, M said nothing had changed" when `followed_up >= 5`
  - The rule: {law_line}
  - Suggested ask: {ask}
  - Method and caveats: anonymous, unverified, self-selected, signals that warrant investigation, not rates
- **Trend:** reports per week for the last 13 weeks as a small chart, with a rising / steady / falling label. Weekly numbers are small, so they stay on the analyst's screen and never go into a brief, a thread or a card.
- **Ready to post:** a five-post X thread (each within 280 characters) and a 1200x675 share card, filled from the same pattern numbers as the brief, addressed to the pack's target body. Template fill only, nothing written by AI. Plain-words facts such as "mostly at night" appear only when the top value covers at least half of the credible reports and at least 5 of them. Copy buttons, an "Open in X" link and PNG download; no X API integration. The organisation reviews and publishes under its own name.
- **Review queue (`/analyst/review`):** every report held back and not counted, with the reason (hospital name not recognised, possible duplicate, flagged as implausible, AI unreachable). An analyst can count it, exclude it, or for an unrecognised name choose which hospital it is; a report cannot be counted without a hospital, or with a hospital from another pack. Without this screen a held report would be in no pattern and nobody would ever see it.
- **Decision log:** every count / exclude / hold is recorded (who, when, from, to, detail) in `analyst_actions` and shown under the queue. A tool for accountability has to be accountable: excluding reports until a pattern disappears leaves a trace. The password is shared in the proof of concept, so the name is whatever was typed at sign-in; individual accounts are next.
- **CSV export** of the patterns table and of report-level facets (no summaries) for patterns above threshold. Cheap, and it is what a real data team would ask for first.

**Asks (`asks.json`, per category):** e.g. `emergency_refused`: "Publish your emergency admission policy and confirm in writing that no patient is turned away for a deposit, as section 20 of the National Health Act requires." `[TBD Ikechi to sharpen]`

**What the partner does with the data (one deck slide, not code):** X threads tagging the responsible body, with a public "Day N, no response" clock; press briefs to health desks; open letters and direct submissions to governing bodies and legislators; share cards for WhatsApp. `[TBD: name 1 or 2 real organisation types that would plausibly run this, and the real body responsible for Lagos general hospitals. VERIFY which body actually runs them.]`

---

## 8. Country packs (the scalability story)

Everything jurisdiction-specific lives in `packs/<id>/`, nothing in code:

```
packs/ng-lagos/
  pack.json        { id, country, languages[], emergency_numbers[], org_name }
  rights.json      { id, category[], text_en, text_pcm, source, verified }
  contacts.json    { id, label, number, applies_to[], verified, verified_on }
  messages.json    every bot message in section 4, keyed by state + language
  asks.json        { category, ask_text, law_line, verified }
  hospitals.seed.json  (fictional in PoC)
```

The bot refuses to send gated content (anything with a law, a number, a contact or a regulator; all rights, asks and contacts) unless it carries a recorded sign-off: `verified_by`, `verified_on`, `verified_source`. A bare `verified: true` does not count. Sign-off is made with `python -m app.verify mark`, shown at `/analyst/content`, and lives in the pack files so the repository history is the audit trail. Enforced in code and covered by tests.

**Fail-safe.** If the AI call fails or exceeds its timeout, the engine degrades instead of failing: keyword fallback for facets, the danger question is always asked, the pre-written escalation still goes out, deterministic handoff checks still run, and the report is held for review rather than counted. If the whole request fails, the reply is pack-worded safety text, which is also baked into the page for when the network drops.

**Second pack: `packs/ke-nairobi/`** (English only). Kenyan emergency-treatment law (Constitution Art 43(2), Health Act 2017 s.7), High Court case law on detention of patients and bodies, the Patients' Rights Charter, Kenyan contacts and terminology ("casualty", "county referral hospital", "cash deposit", "waiver"), fictional Nairobi hospitals and a fictional organisation. Sourced in `docs/research/kenya-pack.md` with a confidence label per claim; every legal line and contact ships `verified: false` `[VERIFY with a Kenyan lawyer; test-call every number]`. Kiswahili is the next step and needs a fluent reviewer; nothing is machine-translated.

How packs work at runtime: a deployment lists its packs in `PACKS`; each conversation picks one when it starts (`/?pack=<id>`, or a field on the first `POST /api/chat`) and keeps it. Reports carry their pack, and patterns, briefs, follow-ups and the analyst view (`/analyst?pack=<id>`) never mix packs. Languages and money buckets are defined by the pack, not by the code: the extractor receives a deployment context (country, language codes, what small/medium/large/very large mean in local currency, local terms). A test fails if any country-specific string appears in the engine. `packs/README.md` is the add-a-country guide.

Deck framing: any advocacy organisation in any country deploys this with a country pack and its own name. No code changes.

---

## 9. API surface

| Route | Purpose |
|---|---|
| `POST /api/chat` | `{ session_id?, channel, pack?, text }` returns `{ session_id, replies[], state, ref_code? }`. All bot logic behind this one endpoint; other channels are thin adapters. |
| `POST /api/report/lookup` | `{ ref_code }` returns redacted summary and status. Rate-limited. |
| `GET /analyst` | Analyst (password). Patterns table. |
| `GET /analyst/pattern/{hospital}/{category}` | Analyst. Breakdowns, brief, redacted summaries, exclude / count-it actions. |
| `GET /analyst/brief/{hospital}/{category}.md` | Analyst. Template-filled markdown brief. |
| `GET /analyst/patterns.csv`, `GET /analyst/facets.csv` | Analyst. Exports. Facets are week-level, no summaries. |
| `POST /analyst/reports/{id}/{exclude,accept,hold}` | Analyst. Sets credibility; `accept` can also assign a hospital. Always logged. |
| `GET /analyst/review`, `GET /analyst/content` | Analyst. Review queue with decision log; content sign-off status. |
| `POST /api/chat/forget` | Deletes an unfinished conversation now. Used by quick exit and "start again". |
| `POST /api/demo/next-day` | Demo only. Triggers F1. |

Stack: Python, FastAPI + Pydantic AI, deployed as one always-on service on Railway. Railway Postgres (asyncpg). OpenAI `gpt-5-mini` behind a small `extract()` wrapper. Pages are server-rendered plain HTML with a few lines of vanilla JS.

**The engine is framework-independent:** `engine.handle_message(session_id, channel, text)` returns replies and the new state, and knows nothing about HTTP or any chat platform. `POST /api/chat` is a thin wrapper; WhatsApp and Telegram become webhook adapters that call the same function; next-day follow-ups run as a background job in the same process. Storage sits behind a `Store` interface with Postgres and in-memory implementations, so the app runs locally and in tests with no external services. Chat page: no images, no framework, a few kilobytes, works on a weak connection.

---

## 10. Evaluation (scores "AI usage" and "trust")

`evals/stories.jsonl`: 30 hand-written stories with expected `category`, `severity`, `language`, `safety_handoff`, `patient_group`, `subtype`. Mix: English and Pidgin, past-tense, ambiguous, clinical, out-of-scope, prompt-injection, sexual-violence handoff, and at least 8 true emergencies.

`uv run python -m evals.run` prints a table and writes `evals/RESULTS.md`. **Headline metric: missed emergencies (severe classified as not_severe without a danger check). Target: zero.** Report category accuracy honestly whatever it is. Results table goes in the README and one deck slide.

Unit tests (few, high value): severity rules, verified-only content gate, threshold excludes `review` reports, ref code HMAC round trip, brief contains only numbers present in the view.

---

## 11. AI-tool usage evidence (25% of the score)

- `CLAUDE.md` in repo root: project rules the coding agent followed (design rules 4, 9, 10 especially).
- This `SPEC.md` committed first; spec-driven build visible in commit history. Small commits, one per build step.
- `docs/ai-workflow.md`: what the AI tools did (spec critique, scaffolding, evals, copy drafts), what the human decided (problem, pressure-through-patterns mechanism, the NGO deployment model, X as the pressure channel, categories, Pidgin, tone of emergency messages), and where AI output was rejected.
- Honest idea-provenance paragraph for the written summary, consistent with the above.

---

## 12. Build order and time box

| When (Lagos) | Work | Gate |
|---|---|---|
| Fri night | Repo, schema, `ng-lagos` pack with fictional hospitals + partner organisation, seed sample reports. | |
| Sat AM | `/api/chat` state machine with hard-coded messages, no AI. Walk both branches by hand. | |
| Sat PM | Extraction call + schema validation. Web chat page. Write the 30 eval stories, first eval run. | Both branches work end to end in the browser |
| Sun AM | `/analyst` page: patterns table, detail, exclude, brief export, CSV. Ref code lookup, follow-up simulation. | Full loop works: report in, pattern on analyst screen, brief out |
| Sun PM | Tests, second eval run, README, `docs/ai-workflow.md`, polish. Draft video script. | **Sun 18:00: feature freeze.** Stretch (WhatsApp sandbox for filming) only if everything above is green |
| Mon AM | Record video (3 to 4 min: problem, Pidgin report on a phone, emergency branch, pattern appears on the organisation's analyst screen, brief exported, pack switch, eval table). | |
| Mon PM | Deck (PDF), written summary, final verification pass on every `verified: true` entry. **Submit by 18:00 UTC.** | |

Cut from the build, shown on one deck slide as the partner's job: open letter, public patterns page, response clock. Cut entirely: Telegram. Roadmap only: voice notes, USSD follow-up, Yoruba/Hausa/Igbo, evidence upload, partner verification, whistleblower mode.

---

## 13. Deck must answer

1. Why official channels fail (UCH Ibadan study figures `[VERIFY and cite]`) and why lone X call-outs depend on luck.
2. Prior art and the difference: I Paid A Bribe, Ushahidi, Care Opinion, Tracka, SERVICOM. Ours: health-specific, reporter gets immediate value, built for people with no audience, and designed as infrastructure for an organisation that already campaigns. Lesson taken from prior platforms: reporting decays when nobody on the other end acts, hence the deployment model. `[VERIFY claims about each before citing]`
3. Anonymity vs credibility: what we do now (section 6 controls, "unverified" labelling, partner's editorial checks before anything is public) and what comes next.
4. Why nothing is public, analysts see only redacted summaries, and the threshold is 5.
5. How patients find it: the partner organisation's community network, pharmacies, churches/mosques, radio, and the partner's own X campaigns. Not posters inside hospitals. `[TBD Ikechi: which of these are real in Lagos]`
6. Systems framing: patterns as evidence of unfunded emergency care, not staff villainy.
7. Scale: country packs + any organisation can deploy under its own name.
8. What the partner does with the data (the pressure channels), and why a solo tool should not be the publisher.
9. Limits: not an emergency service; escalation guidance needs medical and legal review before real-world use.

---

## 14. Open items

- [ ] `[TBD]` One or two real organisation types that would plausibly deploy this (deck only; demo stays fictional).
- [ ] `[TBD]` The real body responsible for Lagos general hospitals (deck only).
- [ ] `[TBD]` Keep or drop step 2 of the emergency message.
- [ ] Sharpen the asks per category.
- [ ] Verify: NHA s.20 text and penalties, 112/767, Patients' Bill of Rights wording, legal aid contacts, DSVA line, MDCN route, social services unit name.
- [ ] Correct all Pidgin.
- [ ] Name the product.
- [ ] Talk to one real patient/relative or nurse for 15 minutes; put one quote (with permission, anonymised) in the deck.
