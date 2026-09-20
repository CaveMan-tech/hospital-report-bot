"""Shared test helpers."""

from app.engine.packs import PROVENANCE, Pack


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
    return pack
