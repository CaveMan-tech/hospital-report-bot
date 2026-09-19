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

    def gated_entries(self) -> list[dict]:
        """Everything a human must verify, for the content review page and the verify command."""
        out = []

        def row(file: str, key: str, text: str, entry: dict) -> None:
            out.append({
                "file": file, "id": key, "text": text, "citation": entry.get("source", ""),
                "check_against": entry.get("check_against", []), "note": entry.get("note", ""),
                "verified": is_verified(entry, always_gated=True),
                "claimed_without_provenance": bool(entry.get("verified")) and not is_verified(entry, True),
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
