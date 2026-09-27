#!/usr/bin/env python3
"""Give every cv.json entry a permanent, unique `id`.

Ids let a subset config (notes/SUBSET-CV-SPEC.md) name the records it keeps.
They are generated once from the entry's content and then never change — a
later wording fix must not change what a config selects — so this script only
ever ADDS ids to entries that lack one. Publications keep their CSL `id`s.

Id rule (spec §6.2):  <context>-<year>-<keywords>, parts omitted when empty,
truncated to 60 characters:

  context   first 2 significant words of the group title (grouped sections)
            or the section title (flat sections)
  year      first 4-digit run in `date`, else in `years`
  keywords  first 4 significant words of the type's key field (KEY_FIELD)

Collisions with any existing id (cv.json or publications.json) get -2, -3, …
in source order.

cv.json is hand-formatted and `json.dump` would reflow it, so ids are written
by inserting text right after each entry's opening `{` — nothing else in the
file moves. Deleting the inserted `"id": "…", ` (one-line objects) or
`"id": "…",` line (multi-line objects) gives back the original bytes.

Usage:  python3 src/assign_ids.py            # add missing ids, in place
        python3 src/assign_ids.py --check    # report missing ids, write nothing
        python3 src/assign_ids.py --src DIR  # operate on DIR/cv.json instead
Stdlib only.
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

SRC = Path(__file__).resolve().parent

MAX_LEN = 60
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
STOPWORDS = {
    "a", "an", "the", "of", "and", "in", "on", "for", "to", "at", "with",
    "from", "by", "de", "la", "el", "y",
}
# The field whose opening words describe an entry, per entry type.
KEY_FIELD = {
    "education": "degree", "positions": "role", "editorial": "journal",
    "awards": "title", "grant": "title", "project": "title",
    "visits": "institution", "talks": "title", "events": "title",
    "courses": "name", "people": "name", "text-list": "text",
    "named": "name",
}


# --------------------------------------------------------------------------
# The id rule.
# --------------------------------------------------------------------------

def slugify(text):
    """NFKD, ASCII only, lowercase, runs of non-alphanumerics -> '-'."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def significant_words(text, n):
    words = [w for w in slugify(text or "").split("-") if w]
    return [w for w in words if w not in STOPWORDS][:n]


def truncate(s, limit=MAX_LEN):
    return s[:limit].rstrip("-")


def base_id(entry, context, etype):
    """The un-deduplicated id for one entry (no collision suffix)."""
    year = None
    for field in ("date", "years"):
        m = re.search(r"\d{4}", str(entry.get(field, "")))
        if m:
            year = m.group(0)
            break
    parts = significant_words(context, 2)
    if year:
        parts.append(year)
    parts += significant_words(entry.get(KEY_FIELD.get(etype, ""), ""), 4)
    return truncate("-".join(parts)) or "entry"


def iter_entries(cv):
    """Yield (path, entry, context title, entry type) in source order.

    `path` is the entry's JSON path as a tuple, e.g.
    ("sections", 3, "groups", 0, "entries", 5).
    """
    for i, section in enumerate(cv.get("sections", [])):
        if "groups" in section:
            for k, group in enumerate(section["groups"]):
                for j, entry in enumerate(group.get("entries", [])):
                    yield (("sections", i, "groups", k, "entries", j), entry,
                           group.get("title", ""),
                           group.get("type", section.get("type")))
        for j, entry in enumerate(section.get("entries", [])):
            yield (("sections", i, "entries", j), entry,
                   section.get("title", ""), section.get("type"))


def new_ids(cv, reserved):
    """Map path -> new id for every entry without one.

    `reserved` is every id already in use (both files); it is extended in
    place as ids are handed out, so collisions resolve in source order.
    """
    out = {}
    for path, entry, context, etype in iter_entries(cv):
        if "id" in entry:
            continue
        base = base_id(entry, context, etype)
        candidate, n = base, 1
        while candidate in reserved:
            n += 1
            suffix = f"-{n}"
            candidate = truncate(base, MAX_LEN - len(suffix)) + suffix
        reserved.add(candidate)
        out[path] = candidate
    return out


# --------------------------------------------------------------------------
# Text-preserving insertion.
# --------------------------------------------------------------------------

class _Scanner:
    """Walk raw JSON text, recording the offset of every object's `{` by path.

    Only positions are recorded; values are parsed by `json` elsewhere. The
    input is assumed to be valid JSON (callers `json.loads` it first).
    """

    def __init__(self, text):
        self.text = text
        self.pos = 0
        self.objects = {}

    def ws(self):
        while self.pos < len(self.text) and self.text[self.pos] in " \t\r\n":
            self.pos += 1

    def string(self):
        start = self.pos
        self.pos += 1  # opening quote
        while self.text[self.pos] != '"':
            self.pos += 2 if self.text[self.pos] == "\\" else 1
        self.pos += 1
        return json.loads(self.text[start:self.pos])

    def value(self, path):
        self.ws()
        c = self.text[self.pos]
        if c == "{":
            self.objects[path] = self.pos
            self.pos += 1
            self.ws()
            if self.text[self.pos] == "}":
                self.pos += 1
                return
            while True:
                self.ws()
                key = self.string()
                self.ws()
                self.pos += 1  # ':'
                self.value(path + (key,))
                self.ws()
                c = self.text[self.pos]
                self.pos += 1
                if c == "}":
                    return
        elif c == "[":
            self.pos += 1
            self.ws()
            if self.text[self.pos] == "]":
                self.pos += 1
                return
            i = 0
            while True:
                self.value(path + (i,))
                i += 1
                self.ws()
                c = self.text[self.pos]
                self.pos += 1
                if c == "]":
                    return
        elif c == '"':
            self.string()
        else:  # number, true, false, null
            m = re.compile(r"[^\s,\]}]+").match(self.text, self.pos)
            self.pos = m.end()


def object_positions(text):
    s = _Scanner(text)
    s.value(())
    return s.objects


def insert_ids(text, ids):
    """Return `text` with `"id": "<id>"` inserted into each object in `ids`.

    `ids` maps JSON path -> id. One-line objects get `"id": "<id>", ` before
    their first key; multi-line objects get a new first line, indented like
    the line after the `{`.
    """
    positions = object_positions(text)
    edits = []
    for path, new_id in ids.items():
        brace = positions[path]
        quoted = json.dumps(new_id)
        nl = re.compile(r"[ \t]*\r?\n([ \t]*)").match(text, brace + 1)
        if nl:
            # Multi-line: new line right after `{`, same indent as the next.
            edits.append((brace + 1, f"\n{nl.group(1)}\"id\": {quoted},"))
        else:
            # One-line: before the first key, after any spaces following `{`.
            at = re.compile(r"[ \t]*").match(text, brace + 1).end()
            empty = text[at] == "}"
            edits.append((at, f"\"id\": {quoted}" + ("" if empty else ", ")))
    for at, s in sorted(edits, reverse=True):
        text = text[:at] + s + text[at:]
    return text


# --------------------------------------------------------------------------
# CLI.
# --------------------------------------------------------------------------

def existing_ids(cv, pubs):
    ids = {p["id"] for p in pubs if isinstance(p, dict) and "id" in p}
    ids |= {e["id"] for _, e, _, _ in iter_entries(cv) if "id" in e}
    return ids


def assign(src_dir):
    """Compute and insert missing ids. Returns (new text, {path: id})."""
    cv_path = src_dir / "cv.json"
    text = cv_path.read_text(encoding="utf-8")
    cv = json.loads(text)
    pubs = json.loads((src_dir / "publications.json").read_text(encoding="utf-8"))
    ids = new_ids(cv, existing_ids(cv, pubs))
    return (insert_ids(text, ids) if ids else text), ids


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="list entries lacking an id and exit 1 if any; write nothing")
    ap.add_argument("--src", type=Path, default=SRC,
                    help="directory holding cv.json + publications.json (default: src/)")
    args = ap.parse_args(argv)

    new_text, ids = assign(args.src)
    cv_path = args.src / "cv.json"
    if not ids:
        print(f"✓ every entry in {cv_path.name} already has an id")
        return 0
    if args.check:
        print(f"✗ {len(ids)} entr{'y' if len(ids) == 1 else 'ies'} without an id "
              f"(run python3 src/assign_ids.py):", file=sys.stderr)
        for path, new_id in ids.items():
            print(f"  - {'.'.join(map(str, path))}  (would get {new_id!r})",
                  file=sys.stderr)
        return 1
    cv_path.write_text(new_text, encoding="utf-8")
    for new_id in ids.values():
        print(f"  + {new_id}")
    print(f"Added {len(ids)} id(s) to {cv_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
