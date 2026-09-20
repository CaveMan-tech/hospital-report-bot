# Written summary

_Draft for Ikechi to rewrite in his own voice. The submission asks the summary to cover: the
track, information sources, the approach to trust and accuracy, and how AI tools were used.
About 750 words. Resolve every `[ ]` before submitting._

---

## Open Ward: private reports in, public pressure out

**Tracks:** Safety, Reporting & Protection, and Transparency & Accountability.

### The problem

When a public hospital in Nigeria refuses emergency care until a deposit is paid, holds a patient
over a bill, or a member of staff abuses someone, the official complaint goes to a desk inside the
same hospital. The people who use public hospitals are mostly poor, expect to be ignored, and
usually do not complain at all. What does move these institutions is public pressure, and in
Nigeria that means X. But a call-out only works if you have followers, or if someone has already
died. And a single story is easy to dismiss.

### The idea

Pressure works on patterns, not anecdotes. So I did not build another complaints channel. I built
the missing piece: a safe way to collect the reports nobody hears and turn them into patterns an
advocacy organisation can campaign on.

A reporter opens a link on any phone. There is no app, no sign-up and no name, and the whole page
is about five kilobytes. They describe what happened in their own words, in English or Pidgin. The
bot checks first whether anyone is in danger right now. Then the person gets something useful
immediately: the right that was violated and where it comes from, practical next steps, and a
private reference code. Staff can report from the inside too, and receive guidance written for
their situation rather than a patient's.

The partner organisation sees only patterns: a hospital and a problem appear once five separate
credible reports exist. Analysts see redacted summaries, masked breakdowns, and a one-click brief
with the numbers, the relevant law, a specific ask and honest caveats. The organisation verifies
and publishes. A solo developer should not be the publisher of allegations about hospitals.

### Information sources

All country-specific content lives in a "country pack", not in code. The Lagos pack draws on the
National Health Act 2014 (sections 20 and 30, read from the Official Gazette), the 1999 Constitution,
and the FCCPC Patients' Bill of Rights (2018), which is policy rather than law and is described that
way. The research behind it is in the repository (`docs/research/nigeria-pack.md`), with a primary
source and a confidence label for every claim, and it corrected my first drafts: the bot no longer
tells a reporter "this is against the law" about facts it cannot check, and it never says care is free.
The Nairobi pack draws on the Constitution of Kenya 2010 (Article 43(2)), the Health Act 2017
(section 7), the Kenya National Patients' Rights Charter (2013) and High Court decisions on the
detention of patients and bodies. The Kenya research is in the repository
(`docs/research/kenya-pack.md`) with a primary source and a confidence label for every claim.

All hospitals and both partner organisations in the demo are fictional, and all seeded reports are
generated sample data, labelled as such wherever they appear. Publishing invented numbers against
real hospitals would be exactly the harm this project is meant to avoid.

### Trust and accuracy

- **The AI writes nothing a reporter reads.** It has one job: turn a story into a structured,
  validated record. Every message is pre-written. Every legal statement and phone number also
  carries a `verified` flag, and the bot refuses to send it until a human has checked it against
  the primary source; until then it sends a safe fallback. At submission, legal lines in both packs
  are still awaiting that review, by design.
- **Rules decide danger, not the model.** When the situation is ambiguous, the bot asks. On top of
  the model sit deterministic checks for self-harm and sexual violence wording, language detection,
  and scrubbing of names, phone numbers and bed numbers from stored summaries.
- **It is measured.** 44 hand-written stories in English and Pidgin across both countries, covering
  emergencies, past events, ambiguous reports, prompt injection, safety handoffs, privacy and who is
  writing. Headline metric: missed emergencies. Result with `gpt-5-mini`: zero, with 44 of 44
  stories passing in three consecutive runs, at about four seconds per reply. I wrote these stories,
  so this is evidence, not proof; the design assumes the model will sometimes be wrong, and a wrong
  guess can never bypass the danger question.
- **Privacy promises are tests.** No identity is collected. The original message is deleted the
  moment the report is written. The reference code is never stored, only a keyed hash. IP addresses
  are never written to a database or a log. Small groups never appear, and masked numbers cannot be
  recovered by subtraction. The greeting tells the reporter plainly that an AI service reads their
  words.
- **Honest outputs.** Every brief says: anonymous, unverified, self-selected; signals that warrant
  investigation, not rates; never a ranking. It frames the problem as system failure, because
  deposits are often demanded where emergency care is unfunded.

### How AI tools were used

I built this in four days with Claude Code, spec first. The problem, the core mechanism (pressure
through patterns), X as the pressure channel, the partner-organisation model, the design rule that
the user is angry, tired and stressed, and the product decisions along the way are mine. I used the
AI to attack the idea before building it, to implement and test it, to research Kenyan law with
sources, and to draft copy for me to correct.

The most valuable use was adversarial. That review removed live public counts, moved publishing to
a partner, and made the demo data fictional. Later, running a whistleblower scenario live exposed
two real bugs within minutes, both fixed the same hour. Inside the product, the model is deliberately
boxed in. `docs/ai-workflow.md` and the commit history show the process.

### Scale, and what comes next

A new country is a new folder: laws, contacts, messages, languages, currency and organisation name.
A test fails if any of that leaks into the engine. The demo switches from Lagos to Nairobi live,
with no code change. The engine knows nothing about web pages: the same engine already answers on
Telegram through one small adapter that keeps no Telegram name, number or id, and WhatsApp and USSD
are the same kind of adapter. Next: legal review of both packs, then a pilot with one health-rights organisation in
one hospital catchment, on WhatsApp with voice notes.

This is a proof of concept. It is not an emergency service and says so.

**Links:** live demo https://web-production-e2ff0.up.railway.app · analyst view https://web-production-e2ff0.up.railway.app/analyst (password in submission notes) ·
Telegram https://t.me/opidemo_bot · repository `[URL]` · video `[URL]`
