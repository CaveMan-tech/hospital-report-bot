# Demo video script

_Draft for Ikechi to rewrite in his own voice. Target length 3:45 to 4:00 (about 560 spoken words
at a calm pace). Upload limit is 250 MB: 1080p H.264 at this length is roughly 60 to 120 MB._

**What the video has to do.** Four criteria, 25% each: uniqueness, scalability across geographies,
use of AI coding tools, presentation and track fit. Every section below is tagged with the
criterion it is scoring. If a shot does not score one of them, cut it.

**The one sentence a judge should be able to repeat afterwards:**
"It lets people with no audience report privately, and turns their reports into patterns an
advocacy organisation can campaign on."

---

## 0:00 to 0:25 · Hook (presentation)

| Picture | Voice |
|---|---|
| You, on camera, plain background. No slides yet. | "In Nigeria, when a public hospital fails you, there are two ways to complain. The official way, where your complaint goes to the same hospital and quietly dies. And the way that actually works: X. If your post blows up, somebody answers." |
| Cut to a phone showing an X profile with a tiny follower count (mock-up, no real account). | "But that only works if you have followers, or if somebody has already died. A market trader sitting in a general hospital corridor at 2 a.m. has neither." |

_Optional, and stronger if true: replace the first two sentences with 15 seconds of something you
or someone close to you actually went through. `[Ikechi: your story, or leave as is]`_

## 0:25 to 0:50 · The insight (uniqueness)

| Picture | Voice |
|---|---|
| Three lines appear one at a time, plain text on screen: "Complaints die one by one." / "Pressure works." / "Pressure only works on patterns." | "Three things I know from living here. Individual complaints get ignored. Public pressure is the only thing that moves these institutions. And pressure only works when there is a pattern. One story is an anecdote. Twenty-three reports of the same thing at the same hospital is a headline." |
| Simple diagram: many phones → one engine → an organisation → X, press, regulators. | "So I did not build another complaints channel. I built the piece that is missing: a safe way to collect the reports nobody hears, and turn them into patterns that an organisation with a voice can campaign on." |

## 0:50 to 1:50 · Demo 1: the reporter (track fit, uniqueness)

Film this on a **real phone held in a hand**, not a desktop browser. Type in Pidgin.

| Picture | Voice |
|---|---|
| Phone opens the link. Greeting appears. Point at the small privacy line. | "No app, no sign-up, no name. The whole page is five kilobytes, so it loads on a bad network. And it tells you straight away that an AI reads your words and that your original message is not kept." |
| Type a Pidgin report of a nurse abusing a relative. Send. | "I assume the person is angry, tired and stressed. So there is no form. They tell it their way, in English or Pidgin." |
| Bot asks the danger question. Answer "no". | "Before anything else, it checks whether someone is in danger right now." |
| Bot asks one missing detail, then shows the right, the steps, the code. | "It asks at most three questions, only for what is missing. Then the person gets something useful immediately: the right that was violated and where it comes from, what they can do now, and a code. The code is the only link to their report. We never store it, only a scrambled version." |
| **New chat.** Type the emergency story: relative bleeding, hospital demanding a deposit. | "Now the case that matters most." |
| Escalation message appears instantly, with no danger question. Hold on it for 3 seconds. | "No questions. It goes straight to what to do, and what the law says. And it is honest: it says it cannot send help." |
| Optional, 8 seconds: a nurse's message on screen, then the staff reply ("You do not have to confront anyone… do not use a work phone"). | "A patient can say they were asked for money. Only an insider can say it is policy. Staff can report safely too, and the bot adapts to who is writing." |

_Recording note: the emergency message only shows its real text once you have verified it against
the National Health Act and flipped its `verified` flag. Do that before filming. Do not film with
`ALLOW_UNVERIFIED` on and present it as production behaviour._

## 1:50 to 2:35 · Demo 2: the organisation (uniqueness, track fit)

| Picture | Voice |
|---|---|
| Laptop. Open `/analyst`. SAMPLE DATA banner clearly visible. | "This is what the partner organisation sees. Everything here is sample data on fictional hospitals. A pattern only appears once five separate credible reports exist, because a count of one on a quiet ward can identify somebody." |
| Refresh: the count for the hospital you just reported goes up by one. | "There is the report I just sent. Counted, anonymous." |
| Open a pattern. Show the breakdown with "fewer than 5" cells. | "They can see it is mostly at night, mostly in maternity. Small groups are hidden, and the other numbers are rounded so you cannot work the hidden ones out by subtraction." |
| Scroll to **Ready to post**: the thread and the share card. Click **Open in X** so the composer opens with the first post filled in. Do not post it. | "And this is the point of the whole thing. The pattern becomes a thread, addressed to the people responsible, with a specific ask and a card to go with it. Every number comes from the data. Nothing here is written by AI." |
| Click **Copy brief**. Paste into a blank document. | "One click gives them a brief: the numbers, the law, a specific ask, and honest caveats. These are unverified signals that deserve investigation, not rates, and never a league table. The organisation checks it, then takes it to X, to the press, and to the people responsible. They are the publisher. A solo developer should not be." |

## 2:35 to 3:05 · Trust and safety by design (track fit, AI usage)

Fast cuts, one line each. Show code or a test name on screen for each claim.

| Picture | Voice |
|---|---|
| `extract.py` prompt header. | "The AI has one job: read the story and fill in a structured record." |
| `packs/ng-lagos/messages.json` showing a `verified` flag. | "It writes nothing the person reads. Every message is pre-written, and the bot refuses to send a legal claim or a phone number until a human has verified it." |
| `severity.py`. | "It never decides alone whether someone is in danger. Rules do, and when in doubt, it asks." |
| Terminal: `pytest` going green, then `evals/RESULTS.llm.md` with the headline line. | "The privacy promises are tests, not promises. And I measured it: fifty hand-written stories, English and Pidgin, two countries. Missed emergencies: zero." |

## 3:05 to 3:45 · Scale (scalability)

| Picture | Voice |
|---|---|
| Folder tree: `packs/ng-lagos/`, `packs/ke-nairobi/`. | "Nothing about Nigeria is in the code. Laws, contacts, messages, hospitals and the organisation's name live in a country pack." |
| Switch the demo to the Kenya pack. Send one report. Kenyan law and numbers appear. | "Here is Nairobi. Same engine, different folder, no code change. Any advocacy organisation in any country can run this under its own name." |
| Phone: open the bot in Telegram. Tap **Menu** so the commands show, send a short report, tap the **No** button on the danger question. | "And the engine does not know what a web page is. This is the same engine on Telegram. Same questions, the same verified messages, with Telegram's own buttons. It keeps no Telegram name, number or id." |
| Cut to the laptop: refresh `/analyst`, the same count goes up again. | "Same analyst screen. The Telegram channel is one small file that only translates; the engine did not change to make it work. WhatsApp and USSD are the same kind of adapter." |

_If the Kenya pack is not ready, cut the second row and show the folder structure only. Do not
fake it._

_The Telegram rows add about 15 seconds. To stay under four minutes, drop the optional staff row in
Demo 1 or shorten the brief row in Demo 2. If the bot misbehaves on the day, cut both Telegram rows
and keep the old line: "The engine does not know what a web page is. Telegram already runs on it;
WhatsApp and USSD are the same kind of small adapter."_

## 3:45 to 4:00 · How it was built, and close (AI usage, presentation)

| Picture | Voice |
|---|---|
| Scroll `SPEC.md`, then the commit history. | "I built this in four days with AI coding tools, spec first. Before writing code I asked the AI to attack the idea, not to agree with me. That review is why there are no live public counts, why the demo hospitals are fictional, and why an organisation, not me, is the publisher." |
| You, on camera again. | "The idea and the decisions are mine. The speed came from the tools. What I want to develop next is a pilot with one health-rights organisation and one hospital catchment, on WhatsApp, with voice notes." |
| Title card: product name, link, "Proof of concept. Not an emergency service." | "People are already telling these stories. Nobody is counting them. This counts them." |

---

## Before you record

- [ ] Verify pack content so the real messages show: open `/analyst/content`, check each entry
      against its source, and sign it off with `uv run python -m app.verify mark ...`. Do not
      flip flags by hand; a bare flag is ignored on purpose.
- [ ] Re-run the evaluation the day you record (`uv run python -m evals.run`) and quote that
      day's result. If it is not zero, say the real number and what you did about it. An honest
      number beats a suspicious one.
- [ ] Deploy, then film against the deployed link, so the URL on screen is the one judges will open.
- [ ] Correct the Pidgin. Judges from the region will notice.
- [ ] Telegram: send one full report through the deployed bot the day you record, and check it on
      `/analyst`. The three Telegram notices (`S0.privacy.telegram`, `T.forgotten`,
      `T.status_usage`) stay silent until you have reviewed them and switched them on.
- [ ] Reset the demo data so the count you watch go up is easy to spot.
- [ ] Phone on Do Not Disturb. Hide bookmarks, tabs and notifications on the laptop.

## Recording tips

- Record the screen and the voice separately; read the voice from this script afterwards and cut
  the picture to fit. It is far quicker than trying to talk and click at once.
- Phone footage: film the phone in your hand in decent light rather than using a screen recorder.
  It reads as real. Keep a screen recording as a backup for legibility.
- Zoom the browser to 125 to 150% for laptop shots. Small text is the most common demo video flaw.
- Add captions. Judges often watch without sound, and it is an accessibility point you are
  otherwise claiming without showing.
- Leave half a second of silence between sections. Do not add music under speech.

## What to leave out

Tech stack lists, architecture diagrams beyond the one simple picture, the follow-up feature
(mention it in the deck instead), the reference-code lookup, and anything you would have to
apologise for. Four minutes is short. The deck and the README carry the rest.
