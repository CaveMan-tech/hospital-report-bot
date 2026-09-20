"""Shared test helpers."""

from app.engine.packs import PROVENANCE, Pack

# Plain wording a person reviews and switches on by hand (no law or number in it, so no provenance).
NOTICES = ("B2.reference", "S0.privacy.telegram", "T.forgotten", "T.status_usage")


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
