"""Record that a human has verified a piece of pack content.

    uv run python -m app.verify list <pack>
    uv run python -m app.verify mark <pack> messages A1.emergency_refused \
        --by "Your Name" --source "<statute and section>, <url>"
    uv run python -m app.verify unmark <pack> messages A1.emergency_refused

Verification lives in the pack files, so `git log -p packs/` is the audit trail: who signed off
what, when, against which source. The bot only sends gated content that carries all three.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime

from app.engine.packs import PACKS_DIR, PROVENANCE, Pack

ID_FIELD = {"messages": None, "rights": "id", "contacts": "id", "asks": "category", "references": "id"}


def _load(pack: str, file: str):
    path = PACKS_DIR / pack / f"{file}.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def _find(data, file: str, key: str) -> dict:
    entry = data.get(key) if file == "messages" else next((e for e in data if e.get(ID_FIELD[file]) == key), None)
    if entry is None:
        sys.exit(f"No entry {key!r} in {file}.json")
    if file == "messages" and not entry.get("gated"):
        sys.exit(f"{key!r} is plain copy with no legal or contact content; it does not need verifying.")
    return entry


def cmd_list(args) -> None:
    rows = Pack(args.pack).gated_entries()
    done = sum(r["verified"] for r in rows)
    print(f"{args.pack}: {done} of {len(rows)} gated entries verified\n")
    for r in rows:
        mark = "VERIFIED " if r["verified"] else ("NO PROVENANCE" if r["claimed_without_provenance"] else "to verify")
        print(f"[{mark:>13}] {r['file']:<9} {r['id']}")
        if r["verified"]:
            print(f"{'':16} by {r['verified_by']} on {r['verified_on']} against {r['verified_source']}")
        else:
            for c in r["check_against"]:
                print(f"{'':16} check: {c['label']}{'  ' + c['url'] if c.get('url') else ''}")


def cmd_mark(args) -> None:
    if len(args.source.strip()) < 10:
        sys.exit("--source must say what you checked it against (a citation and, ideally, a URL).")
    path, data = _load(args.pack, args.file)
    entry = _find(data, args.file, args.id)
    entry.update(verified=True, verified_by=args.by.strip(), verified_source=args.source.strip(),
                 verified_on=datetime.now(UTC).date().isoformat())
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Marked {args.pack}/{args.file}/{args.id} verified by {args.by}. Commit the change.")


def cmd_unmark(args) -> None:
    path, data = _load(args.pack, args.file)
    entry = _find(data, args.file, args.id)
    entry["verified"] = False
    for f in PROVENANCE:
        entry.pop(f, None)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Unmarked {args.pack}/{args.file}/{args.id}.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(required=True)
    p = sub.add_parser("list"); p.add_argument("pack"); p.set_defaults(fn=cmd_list)
    for name, fn in (("mark", cmd_mark), ("unmark", cmd_unmark)):
        p = sub.add_parser(name)
        p.add_argument("pack"); p.add_argument("file", choices=list(ID_FIELD)); p.add_argument("id")
        if name == "mark":
            p.add_argument("--by", required=True, help="your name")
            p.add_argument("--source", required=True, help="what you checked it against: citation and URL")
        p.set_defaults(fn=fn)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
