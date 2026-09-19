# How AI coding tools were used

_Draft for Ikechi to review and edit before submission._

## Tools

Claude Code (Anthropic) for specification review, implementation, tests and evaluation.
OpenAI `gpt-5-mini` through Pydantic AI inside the product, for one narrow job: turning a
reporter's story into a validated structured record.

## Division of labour

**Decided by the author:** the problem (malpractice in public hospitals going unreported because
poor patients expect to be ignored); the core mechanism (official channels fail, only public
pressure works, and pressure only works on patterns, so collect privately and surface the pattern);
X as the pressure channel in Nigeria; the deployment model (the bot is one cog inside an advocacy
organisation that does the campaigning); the launch categories; the emotional-state design rule
(assume the user is angry, tired or stressed); triage before everything else; next-day follow-up;
the choice of extraction model; all Pidgin wording and the tone of the emergency messages.

**Done with AI assistance:** stress-testing the idea and finding holes in it; drafting and revising
the build spec; scaffolding; implementing the engine, storage layer, analyst view and pages;
writing tests and the evaluation runner; first drafts of message copy for the author to correct.

## Practices worth noting

- **Spec first.** `SPEC.md` was committed before any code, and the code was built from it in the
  order it sets out. `CLAUDE.md` holds the rules the coding agent had to follow.
- **Adversarial review before building.** The AI was asked to criticise the idea rather than agree
  with it. That review changed the design: no public live counts, no report numbers shown to
  reporters, fictional demo data, human organisations as publishers, and honest "unverified
  signals, not rates" wording.
- **The AI is boxed in inside the product.** It cannot author anything a frightened person will act
  on. A verified-content gate and deterministic severity rules sit between the model and the user,
  and both are enforced by tests.
- **Tests alongside code.** Privacy promises are executable: tests assert that the raw story and the
  reference code are never stored, that small groups never appear, and that masked cells cannot be
  recovered by subtraction.
- **Research with receipts.** The Kenya pack was built from a sourced research file
  (`docs/research/kenya-pack.md`) in which every claim carries a confidence label and a primary
  source, and everything still ships unverified until a human checks it.
- **Critical self-review.** Asked to find the weakest parts of its own build, the AI found that
  the bot failed outright when the model was unreachable, and that one of its own tests pointed
  to a list that did not exist. Both were fixed the same day.
- **Following a feature to its dead end.** Reports with an unrecognised hospital were "held for
  review" but no screen showed them. The review found it; the queue and a decision log fixed it.
- **Research that corrected us.** The sourced Nigeria research found that three statistics from
  early brainstorming had no source at all (the one real study says nearly the opposite), that
  two rights lines overstated the official text, and that a crisis line, not the sexual-violence
  agency, is the right handoff for someone who wants to end their life. All corrected.
- **Evaluation, not vibes.** A 30-story set with a single headline metric: missed emergencies.
- **AI output that was rejected or corrected:** _[Ikechi to fill in: e.g. the first stack choice
  and the first database choice were both changed after questioning; an AI-suggested alternative idea was set aside; a breakdown table
  leaked a masked value by subtraction and was fixed.]_
