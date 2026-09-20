"""Shared test helpers."""

from app.engine.packs import PROVENANCE, Pack

# Plain wording a person reviews and switches on by hand (no law or number in it, so no provenance).
NOTICES = ("B2.reference", "S0.privacy.telegram", "T.forgotten", "T.status_usage", "M1.more", "M1.more_again", "M1.auto")


def unsigned(pack_id: str = "ng-lagos", allow_unverified: bool = False) -> Pack:
    """The pack as it ships before anyone has reviewed it: every sign-off stripped, in memory only.
    Gate tests use this so they keep testing the gate whatever has been signed off in packs/."""
    pack = Pack(pack_id, allow_unverified)
    gated = [*pack.rights, *pack.contacts.values(), *pack.asks.values(), *pack.references,
             *(m for m in pack.messages.values() if m.get("gated"))]
    for entry in gated:
        entry["verified"] = False
        for f in PROVENANCE:
            entry.pop(f, None)
    for key in NOTICES:
        pack.messages[key]["verified"] = False
    return pack


async def say(engine, sid, text, finish=True, channel="web", **kw):
    """One turn. Most tests are not about the "have you finished?" step, so by default the reporter
    taps Done as soon as it appears and the two turns read as one. `finish=False` stops at the step."""
    r = await engine.handle_message(sid, channel, text, **kw)
    if finish and r.state == "M1":
        done = await engine.handle_message(r.session_id, channel, "tap:done", **kw)
        done.replies = r.replies[:-1] + done.replies
        return done
    return r


def chat(client, payload: dict) -> dict:
    """The same over HTTP: POST /api/chat, tapping Done when the step appears."""
    r = client.post("/api/chat", json=payload).json()
    if r["state"] == "M1":
        done = client.post("/api/chat", json={"session_id": r["session_id"], "text": "tap:done"}).json()
        done["replies"] = r["replies"][:-1] + done["replies"]
        return done
    return r
