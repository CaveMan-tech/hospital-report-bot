# Teleprompter: voice only

Read at a calm pace. About 530 words, 3:45. One recording per section. Shot notes are in brackets;
do not read them. The full shot list is in `video-script.md`.

---

**1. Hook** [you, on camera]

In Nigeria, when a public hospital fails you, there are two ways to complain. The official way,
where your complaint goes to the same hospital and quietly dies. And the way that actually works:
X. If your post blows up, somebody answers.

But that only works if you have followers, or if somebody has already died. A market trader
sitting in a general hospital corridor at 2 a.m. has neither.

**2. The insight** [three lines of text, then the deck diagram as a still]

Three things I know from living here. Individual complaints get ignored. Public pressure is the
only thing that moves these institutions. And pressure only works when there is a pattern. One
story is an anecdote. Twenty reports of the same thing at the same hospital is a headline.

So I did not build another complaints channel. I built the missing piece: a safe way to collect
the reports nobody hears, and turn them into patterns that an organisation with a voice can
campaign on.

**3. The reporter** [phone: chat A]

No app, no sign-up, no name. The page is a few kilobytes, so it loads on a bad network. It says
straight away that an AI reads your words and that your original message is not kept.

I assume the person is angry, tired and stressed. So there is no form. They tell it their way, in
English or Pidgin.

[danger question appears] Before anything else, it checks whether someone is in danger right now.

[rights, steps, code appear] Then they get something useful immediately: the right that was
violated and where it comes from, what they can do now, and a code. The code is the only link to
their report. We never store it, only a scrambled version.

[phone: chat B, emergency] Now the case that matters most. [hold 3 seconds] No danger question.
Straight to what to do, the emergency numbers, and what the law says.

**4. The organisation** [laptop: /analyst]

This is what the partner organisation sees. Everything here is sample data on fictional hospitals.
A pattern only appears once five separate credible reports exist, because a count of one on a
quiet ward can identify somebody.

[refresh, Lagoon View goes up by one] There is the report I just sent. Counted, anonymous.

[open the pattern, breakdown] They can see it is mostly in maternity. Small groups are hidden.

[Ready to post, Open in X] And this is the point of the whole thing. The pattern becomes a thread,
addressed to the people responsible, with a specific ask. Every number comes from the data.
Nothing here is written by AI.

[Copy brief, paste] One click gives them a brief: the numbers, the law, the ask, and honest
caveats. These are unverified signals that deserve investigation, not rates, and never a league
table. The organisation checks it and publishes it. They are the publisher. A solo developer
should not be.

**5. Trust by design** [fast cuts: extract.py, a verified flag, severity.py, pytest, eval results]

The AI has one job: read the story and fill in a structured record. It writes nothing the person
reads. Every message is pre-written, and the bot refuses to send a legal claim or a phone number
until a human has verified it against the source.

It never decides alone whether someone is in danger. Rules do, and when in doubt, it asks.

The privacy promises are tests, not promises. And I measured it, today: fifty hand-written stories, English
and Pidgin, two countries. Thirteen of them are emergencies. Missed emergencies: zero.
[show evals/RESULTS.llm.md, run of 2026-09-21 20:39 UTC]

**6. Scale** [packs/ folder tree, then chat K, then Telegram]

Nothing about Nigeria is in the code. Laws, contacts, messages and hospitals live in a country
pack.

[Kenya chat] Here is Nairobi. Same engine, different folder, no code change. It knows the Kenyan
hospital and the Kenyan partner. And look at what it does not do: I have not yet checked the
Kenyan law against its source, so the bot refuses to quote it. That is the gate working.

[Telegram] And the engine does not know what a web page is. This is the same engine on Telegram,
with Telegram's own buttons. It keeps no Telegram name, number or id. WhatsApp and USSD are the
same kind of small adapter.

**7. Close** [SPEC.md and git log, then you on camera]

I built this in four days with AI coding tools, spec first. Before writing code I asked the AI to
attack the idea, not agree with me. That review is why there are no public counts, why the demo
hospitals are fictional, and why an organisation, not me, is the publisher.

The idea and the decisions are mine. The speed came from the tools. Next is a pilot with one
health-rights organisation and one hospital catchment, on WhatsApp, with voice notes.

People are already telling these stories. Nobody is counting them. This counts them.
