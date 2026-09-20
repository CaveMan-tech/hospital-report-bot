"""Country packs: everything jurisdiction-specific lives in packs/<id>/, nothing in code.

The verified gate is enforced here. The engine cannot send a message, right or
contact whose `verified` flag is false, unless ALLOW_UNVERIFIED is set for
local development.
"""

from __future__ import annotations

import json
import logging
import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

from .models import Hospital

log = logging.getLogger(__name__)

PACKS_DIR = Path(__file__).resolve().parents[2] / "packs"
_CONTACT_RE = re.compile(r"\{contact:([a-z_]+)\}")


class UnverifiedContent(Exception):
    pass


class Pack:
    def __init__(self, pack_id: str, allow_unverified: bool = False):
        root = PACKS_DIR / pack_id
        if not root.is_dir():
            raise FileNotFoundError(f"No pack named {pack_id!r}")
        self.id = pack_id
        self.allow_unverified = allow_unverified
        self.meta = self._load(root / "pack.json")
        self.messages: dict = self._load(root / "messages.json")
        self.labels: dict = self._load(root / "labels.json")
        self.rights: list[dict] = self._load(root / "rights.json")
        self.contacts = {c["id"]: c for c in self._load(root / "contacts.json")}
        self.asks = {a["category"]: a for a in self._load(root / "asks.json")}
        self.hospitals = [Hospital(pack=pack_id, **h) for h in self._load(root / "hospitals.seed.json")]
        # Documents a reporter can open to read the law or the policy for themselves. Optional.
        refs = root / "references.json"
        self.references: list[dict] = self._load(refs) if refs.exists() else []

    @staticmethod
    def _load(path: Path):
        return json.loads(path.read_text(encoding="utf-8"))

    @property
    def org_name(self) -> str:
        return self.meta["org_name"]

    @property
    def languages(self) -> list[str]:
        return self.meta["languages"]

    @property
    def title(self) -> str:
        return f"{self.meta['country']} ({self.meta['region']})"

    def language_or_default(self, lang: str | None) -> str:
        return lang if lang in self.languages else self.languages[0]

    def extraction_context(self) -> str:
        """What the extractor needs to know about this deployment. No legal content."""
        buckets = "; ".join(f"{k} = {v}" for k, v in self.meta["amount_buckets"].items())
        return (
            f"Country: {self.meta['country']}. Region: {self.meta['region']}.\n"
            f"Language codes in use: {', '.join(self.languages)}.\n"
            f"Currency: {self.meta['currency']}. Amount buckets: {buckets}.\n"
            f"Local terms: {self.meta.get('local_terms', 'none')}."
        )

    def _check(self, kind: str, key: str, entry: dict, always_gated: bool = False) -> None:
        if is_verified(entry, always_gated):
            return
        if self.allow_unverified:
            log.warning("Sending UNVERIFIED %s %r (ALLOW_UNVERIFIED is on)", kind, key)
            return
        raise UnverifiedContent(f"{kind} {key!r} is not verified")

    def message(self, key: str, lang: str = "en", **fields: str) -> str:
        """Return a bot message. Unverified content degrades to the safe fallback."""
        try:
            return self._message(key, lang, **fields)
        except UnverifiedContent:
            log.warning("Blocked unverified message %r; sending fallback", key)
            return self._message("E.unverified_fallback", lang)

    def message_or_none(self, key: str, lang: str = "en", **fields: str) -> str | None:
        """For channel notices where the fallback would be untrue (it says "I have recorded what
        you told me"). Same gate as `message`; unverified text is simply not sent."""
        try:
            return self._message(key, lang, **fields)
        except UnverifiedContent:
            log.warning("Skipped unverified message %r", key)
            return None

    def _message(self, key: str, lang: str, **fields: str) -> str:
        entry = self.messages[key]
        self._check("message", key, entry)
        text = entry.get(lang) or entry["en"]

        def contact(match: re.Match) -> str:
            c = self.contacts[match.group(1)]
            self._check("contact", c["id"], c, always_gated=True)
            return c["text"]

        text = _CONTACT_RE.sub(contact, text)
        fields.setdefault("org_name", self.org_name)
        for name, value in fields.items():
            text = text.replace("{" + name + "}", value)
        return text.strip()

    def _says_now(self, file: str, key: str, entry: dict) -> dict:
        """What a reporter gets today for this entry, with the gate on. ALLOW_UNVERIFIED is ignored
        on purpose: the reviewer needs to see what the public sees, not what a developer sees."""
        if file == "messages":
            blocked_by = [c for c in _CONTACT_RE.findall(entry["en"]) if not is_verified(self.contacts[c], True)]
            if is_verified(entry, always_gated=True) and not blocked_by:
                return {"kind": "as_written"}
            return {"kind": "fallback", "text": self.messages["E.unverified_fallback"]["en"],
                    "blocked_by": blocked_by}
        if is_verified(entry, always_gated=True):
            return {"kind": "as_written"}
        if file == "contacts":  # one unverified number holds back every message that includes it
            used_in = [k for k, m in self.messages.items() if "{contact:" + key + "}" in m["en"]]
            return {"kind": "fallback", "text": self.messages["E.unverified_fallback"]["en"], "used_in": used_in}
        return {"kind": "omitted"} if file in ("rights", "references") else {"kind": "brief_placeholder"}

    def gated_entries(self) -> list[dict]:
        """Everything a human must verify, for the content review page and the verify command."""
        out = []

        def row(file: str, key: str, text: str, entry: dict) -> None:
            out.append({
                "file": file, "id": key, "text": text, "citation": entry.get("source", ""),
                "check_against": entry.get("check_against", []), "note": entry.get("note", ""),
                "verified": is_verified(entry, always_gated=True),
                "claimed_without_provenance": bool(entry.get("verified")) and not is_verified(entry, True),
                "now": self._says_now(file, key, entry),
                **{f: entry.get(f, "") for f in PROVENANCE},
            })

        for key, e in self.messages.items():
            if e.get("gated"):
                row("messages", key, e["en"], e)
        for e in self.rights:
            row("rights", e["id"], e["text_en"], e)
        for e in self.contacts.values():
            row("contacts", e["id"], f"{e['label']}: {e['text']}", e)
        for e in self.asks.values():
            row("asks", e["category"], f"{e['ask_text']}  |  {e['law_line']}", e)
        for e in self.references:
            row("references", e["id"], f"{e['title_en']} ({e['note_en']}; {e['size_en']}): {e['url']}", e)
        return out

    def label(self, group: str, key: str, lang: str = "en") -> str:
        entry = self.labels[group][key] if group != "unknown_hospital" else self.labels[group]
        return entry.get(lang) or entry["en"]

    def quick(self, key: str, lang: str, sub: str | None = None) -> str:
        entry = self.labels["quick"][key][sub] if sub else self.labels["quick"][key]
        return entry.get(lang) or entry["en"]

    def category_plain(self, category: str, lang: str) -> str:
        return self.label("category_plain", category, lang)

    def rights_for(self, category: str, lang: str) -> list[tuple[str, str]]:
        """(id, rendered text) for each verified right that applies. Most specific first."""
        out = []
        ordered = sorted(self.rights, key=lambda r: len(r["category"]))
        for r in ordered:
            if category not in r["category"]:
                continue
            try:
                self._check("right", r["id"], r, always_gated=True)
            except UnverifiedContent:
                continue
            right_text = (r.get(f"text_{lang}") or r["text_en"])
            out.append((r["id"], self._message("B2.template", lang, right_text=right_text, source=r["source"])))
        return out[:1]

    def references_for(self, right_id: str, lang: str) -> list[str]:
        """"Read it for yourself" lines for the documents behind one right. A link is something a
        person acts on, so it is gated like a phone number: no sign-off, no link."""
        right = next((r for r in self.rights if r["id"] == right_id), None)
        return self._reference_lines(right.get("references", []) if right else [], lang, "B2.reference")

    def escalation_references(self, message_key: str, lang: str) -> list[str]:
        """The law to show the person refusing care. Sent after the escalation message, never
        before it, and only for the escalation messages that name a document."""
        return self._reference_lines(self.messages[message_key].get("references", []), lang, "A1.reference")

    def _reference_lines(self, ids: list[str], lang: str, template: str) -> list[str]:
        out = []
        for ref in self.references:
            if ref["id"] not in ids:
                continue
            try:
                self._check("reference", ref["id"], ref, always_gated=True)
                out.append(self._message(template, lang, url=ref["url"], **{
                    f: ref.get(f"{f}_{lang}") or ref[f"{f}_en"] for f in ("title", "note", "size")}))
            except UnverifiedContent:
                continue
        return out

    def match_hospital(self, raw: str | None) -> Hospital | None:
        if not raw:
            return None
        needle = _norm(raw)
        if not needle:
            return None
        best, best_score = None, 0.0
        for h in self.hospitals:
            for name in [h.name, *h.aliases]:
                cand = _norm(name)
                if cand == needle or (len(cand) >= 5 and (cand in needle or needle in cand) and len(needle) >= 5):
                    return h
                score = SequenceMatcher(None, needle, cand).ratio()
                if score > best_score:
                    best, best_score = h, score
        return best if best_score >= 0.82 else None


PROVENANCE = ("verified_by", "verified_on", "verified_source")


def is_verified(entry: dict, always_gated: bool = False) -> bool:
    """A gated entry (law, phone number, contact, organisation) only counts as verified when it
    says WHO checked it, WHEN, and AGAINST WHAT. `"verified": true` on its own is not enough."""
    if not entry.get("verified"):
        return False
    if always_gated or entry.get("gated"):
        return all(str(entry.get(f) or "").strip() for f in PROVENANCE)
    return True


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


@lru_cache(maxsize=8)
def get_pack(pack_id: str, allow_unverified: bool = False) -> Pack:
    return Pack(pack_id, allow_unverified)
