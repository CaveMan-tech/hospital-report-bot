# Pitch deck outline

_Draft for Ikechi. Export as PDF (limit 100 MB). 12 slides plus an appendix. One idea per slide,
big type, almost no bullets on screen: the words below are what the slide has to say, not what it
has to show. Judges score four things equally: uniqueness, scalability, AI coding tool usage,
presentation and track fit. Each slide is tagged with what it scores._

**For the designer.** Only what follows **On the slide** and **Visual** goes on a slide. **Say** is
the speaker note. Everything else (evidence notes, "how to use it honestly", "do not use", "be ready
for") is guidance for the presenter and must not appear on any slide. Do not add numbers, quotes,
logos, hospital names or organisation names that are not written here: the hospitals and the
organisation are fictional on purpose. Screenshots are real ones from the live app and will be
supplied; leave a labelled phone-frame placeholder for each. Anything in `[square brackets]` is
unresolved: leave it out rather than fill it in.

**Name.** The product is **Open Ward**. The fictional organisation that runs it in the demo is
Open Ward Initiative; keep the two distinct on slides.

---

## 1. Title · presentation
**On the slide:** the name. One line: "Private reports in. Public pressure out."
Tracks: Safety, Reporting & Protection + Transparency & Accountability.
Ikechi Okoro · web-production-e2ff0.up.railway.app · t.me/opidemo_bot
**Visual:** a phone showing the chat in Pidgin.

## 2. The problem · track fit
**On the slide:** "When a public hospital fails you in Nigeria, where does your complaint go?"
Then: "Back to the same hospital."
**Say:** official desks sit inside the institution being complained about; poor patients expect to
be ignored, and mostly do not complain at all.
**Evidence:** one hard number, with its source on the slide. Checked against the abstract:
"In a 2020 survey at a Nigerian teaching hospital, only about one in five patients (21.3%) had good
knowledge of the Patients' Bill of Rights. Among their doctors it was three in five (60.6%)."
(Adejumo et al., West Afr J Med 2020, PMID 33185254, https://pubmed.ncbi.nlm.nih.gov/33185254/)
The contrast is the point: the people who hold the rights know far less about them than the people
on the other side of the desk. The authors' own conclusion is quotable: knowledge "was
unsatisfactory especially among the patients".
**How to use it honestly:**
- Use 21.3%, not 46.8% or 23.8%. Those two describe the whole sample of 453, and 199 of them (44%)
  were physicians, so they overstate what patients know. 21.3% is the only patient-only figure in
  the abstract.
- Say "in a hospital-based survey". It was run inside the hospital by affiliated researchers, on
  patients who got into a teaching hospital, and knowledge tracked education. All three push the
  number up, so the real figure for poorer patients at general hospitals is plausibly lower. Say
  that as a reasoned inference, not as a finding.
- A pitch line that turns the weakness into the argument: "Most of what we know about patient
  experience comes from surveys run inside hospitals, by the hospitals' own staff. This collects
  what people say when the hospital is not the one asking."
**Do not use** the figures from the early brainstorm ("54 complaints in three years", "a quarter
aware", "83.7% never asserted their rights"): a literature search found no source for any of them.
Do not cite the 2013 Ibadan study either (PMID 24579387): it predates the Bill of Rights, surveys
outpatients inside the hospital, and its "75% would seek redress" is a stated intention, not action.
The structural point needs no statistic at all: the complaint desk sits inside the institution being
complained about. A first-hand story also works. One true story beats one shaky statistic.

## 3. What actually works · uniqueness
**On the slide:** "What works is X. If you have followers. Or if someone has already died."
**Visual:** mock-up of a call-out post with 40 followers and no replies, beside one with 40,000.
Invented handles and a fictional hospital only; no real person, hospital or logo.
**Say:** public pressure is the only lever, and today it is a lottery.

## 4. The insight · uniqueness
**On the slide, three lines, built one at a time:**
"Complaints die one by one." / "Pressure works." / "Pressure only works on patterns."
**Say:** one story is an anecdote; twenty-three reports of the same thing at the same hospital is a
headline. Nobody is collecting the twenty-three.

## 5. The idea · uniqueness, track fit
**On the slide:** the one diagram in the deck.
Many phones (web link, Telegram; WhatsApp next) → one engine → a partner organisation → X, press, regulators.
**Say:** I did not build another complaints channel. The bot is one cog inside an organisation that
already campaigns. It collects, protects and aggregates. They verify, publish and push.
A solo developer should not be the publisher.

## 6. For the reporter · track fit
**On the slide:** five screenshots in a row: tell it your way (Pidgin) → danger check → "anything
else?" with its Done button → your right and what to do now → your code. One of the five is the
Telegram chat, so both channels are seen.
**Say:** I assume the person is angry, tired and stressed. They use what they already have: a web
link or Telegram. No form, no app, no name, five kilobytes.
Help first, data second: they leave with something useful even if no pattern ever forms.
**One line on consent:** "Nothing is recorded until they say they have finished. In an emergency the
bot says 'if you need to go, go', and records it for them after two quiet minutes. Nobody has to
choose between the person beside them and their report."
**One line on insiders:** "A patient can say they were asked for money. Only an insider can say it
is policy. Staff can report safely too, and the bot adapts to who is writing: it never nudges them
to expose themselves." Do not say "identify" or "detect".

## 7. For the organisation · uniqueness
**On the slide:** the analyst screen with the SAMPLE DATA banner visible, and the one-click brief.
**Say:** a pattern appears only after five credible reports. Small groups are masked, and the other
numbers are rounded so you cannot subtract your way to a hidden one. The brief says "unverified
signals that warrant investigation, not rates, never a league table", and it frames the problem as
system failure, not staff villainy: deposits are often demanded because emergency care is unfunded.

## 8. Trust by design · AI usage, track fit
**On the slide:** "The AI writes nothing a frightened person reads."
Three short lines under it: "It only classifies." / "Rules decide danger. When unsure, it asks." /
"A human verifies every legal line and phone number, or the bot will not send it."
**Say:** most AI tools in this space improvise. This one cannot.

## 9. Measured, not claimed · AI usage
**On the slide:** one big number: "0 missed emergencies". Under it: "44 hand-written stories,
English and Pidgin, Nigeria and Kenya. 44/44 across three consecutive runs. About 4 seconds a reply."
**Say:** the privacy promises are tests, not promises: the original message and the code are never
stored, small groups never appear, identifiers are scrubbed from summaries.
**Be ready for:** "you wrote the stories yourself". Answer: yes, and the design assumes the model
will meet phrasings I did not imagine. A wrong guess never bypasses the danger question.

## 10. Scale · scalability
**On the slide:** two folders side by side: `packs/ng-lagos/`, `packs/ke-nairobi/`. "A new country
is a new folder, not new code."
**Visual:** the same report answered with Section 20 of Nigeria's National Health Act on the left
and Article 43(2) of Kenya's Constitution on the right.
**Say:** a test fails if any law, phone number or city name appears in the engine. Any advocacy
organisation in any country runs this under its own name. The engine does not know what a web
page is: the same engine already answers on Telegram through one small adapter, with no change to
the engine and no Telegram name, number or id kept. WhatsApp and USSD are the same kind of adapter.
**Honesty line:** the bot will not send a legal line or phone number until a person has checked it
against the primary source. I have done that for all 25 in the Lagos pack; the 27 in the Kenyan pack
are still waiting, so in Nairobi the bot sends a safe fallback instead. A local lawyer's review of
both packs comes before any pilot. That is the process working, not a gap.

## 11. How I built it with AI · AI usage
**On the slide:** a timeline: spec → adversarial review → tests with every feature → real-model
evaluation → fixes.
**Say:** spec first. Before writing code I asked the AI to attack the idea, not agree with it.
Then give two concrete catches, because specifics are what convince:
- a breakdown table leaked a hidden count by subtraction; found on review, fixed, now a test;
- running a whistleblower scenario live showed a nurse at home being told to call emergency
  services, and the one AI-written line coming back in the wrong language. Both fixed the same hour.
**Close the slide with:** "The idea and the decisions are mine. The speed and the scrutiny came from
the tools."

## 12. What next, and the ask · presentation
**On the slide:** three steps: (1) legal review of both packs, (2) a pilot with one health-rights
organisation in one hospital catchment, on WhatsApp with voice notes, (3) a third country pack.
**Name the kind of partner** you would approach first in Lagos, and why they would want it.
`[TBD Ikechi]`
**Last line:** "People are already telling these stories. Nobody is counting them. This counts them."

---

## Appendix slides (for questions, not for presenting)

- **A0. Why aggregated counts, never a single viral story.** Two Nigerian cases where a viral
  hospital allegation was disputed or a panel cleared the hospital (see
  `docs/research/nigeria-pack.md`, section H3) show how one account can be wrong. It is the
  strongest argument for this design: patterns, unverified-signal wording, and an organisation
  that checks before it publishes. `[VERIFY the two cases before citing]`
- **A. Prior art and the difference.** I Paid A Bribe, Ushahidi, Care Opinion, Tracka, SERVICOM.
  `[VERIFY each claim before citing]`. Difference: health-specific, help for the reporter first,
  built for people with no audience, designed as infrastructure for an organisation that already
  campaigns. Lesson taken: reporting platforms decay when nobody on the other end acts.
- **B. Anonymity versus credibility.** What exists now (rate limits, a duplicate key that cannot be
  linked to anyone after a day, implausible reports held for review, "unverified" on every
  surface, the partner's editorial checks). What is next (optional evidence, partner-verified reports).
- **C. How patients find it.** Through the partner's community network, pharmacies, churches and
  mosques, radio, and the partner's own campaigns. Not posters inside hospitals. `[TBD: which are real]`
- **D. Data protection.** No identity collected; original message not retained; an AI service
  abroad processes the text, which the greeting discloses. Nigeria's NDPA and Kenya's Data
  Protection Act (s.49 on sensitive data leaving the country) would need a proper assessment before
  a pilot. `[VERIFY]`
- **E. Limits.** Not an emergency service. Cannot send help and says so. Proof of concept.
- **F. Architecture**, for the technical judge: engine, packs, store, channel adapters (web, Telegram); over 200 automated tests, run against both the in-memory and
  the Postgres store. Every AI call is counted (model, tokens, latency, outcome) and linked to nothing.

## Design notes

- Use real screenshots from the deployed app, on a phone frame. No stock photos of hospitals.
- One accent colour. The chat's green works.
- Put "SAMPLE DATA, fictional hospitals" on every screenshot that shows numbers.
- Every number on a slide needs a source in the notes. If you cannot source it, cut it.
