#!/usr/bin/env python3
"""Validate the CV data files before opening a PR.

Three checks, all stdlib-only (no pip installs — matches the repo's
no-extra-dependencies ethos; see ARCHITECTURE.md):

  1. src/cv.json  against  src/cv.schema.json  — a focused JSON Schema
     validator covering exactly the draft-2020-12 keywords the schema uses
     (type, required, properties, additionalProperties, patternProperties,
     enum, items, $ref/$defs, format, pattern, maxLength). It reads the
     schema, so it keeps working if the schema grows. The schema requires
     every entry to carry an `id` (see src/assign_ids.py).

  2. src/publications.json  (CSL-JSON, no schema) — structural sanity plus a
     cross-check that every entry's `category` matches a group declared in
     the `publications` section of cv.json, so a new publication actually
     lands in a rendered group instead of vanishing. Also checks the shape of
     the optional web-only `links` array (see LINK_TYPES below).

  3. Record ids are unique ACROSS both files — subset configs select records
     by id without saying which file they live in.

`make validate` runs this after its parse check. It never touches the
renderers or builds anything. Importable: `check(repo_root)` returns the list
of problems (empty = clean).

Usage:  python3 src/validate_cv.py [repo_root]
Exit code 0 = clean, 1 = problems (printed to stderr).
"""

import json
import re
import sys
from pathlib import Path


# --------------------------------------------------------------------------
# Minimal JSON Schema validator (only the keywords cv.schema.json uses).
# --------------------------------------------------------------------------

def _type_ok(value, t):
    if t == "object":
        return isinstance(value, dict)
    if t == "array":
        return isinstance(value, list)
    if t == "string":
        return isinstance(value, str)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return True  # unknown type keyword — don't fail on it


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_URI_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


class SchemaValidator:
    def __init__(self, root_schema):
        self.root = root_schema
        self.errors = []

    def _resolve(self, schema):
        # Follow local "#/..." $refs (the only kind this schema uses).
        seen = 0
        while isinstance(schema, dict) and "$ref" in schema:
            ref = schema["$ref"]
            if not ref.startswith("#/"):
                self.errors.append(f"unsupported $ref: {ref}")
                return {}
            node = self.root
            for part in ref[2:].split("/"):
                node = node[part]
            schema = node
            seen += 1
            if seen > 50:  # cycle guard
                return {}
        return schema

    def validate(self, value, schema, path):
        schema = self._resolve(schema)
        if not isinstance(schema, dict):
            return

        if "type" in schema:
            types = schema["type"]
            types = types if isinstance(types, list) else [types]
            if not any(_type_ok(value, t) for t in types):
                self.errors.append(
                    f"{path or '<root>'}: expected type {types}, got "
                    f"{type(value).__name__}"
                )
                return  # further checks assume the type held

        if "enum" in schema and value not in schema["enum"]:
            self.errors.append(
                f"{path or '<root>'}: {value!r} is not one of {schema['enum']}"
            )

        if isinstance(value, str):
            if "pattern" in schema and not re.search(schema["pattern"], value):
                self.errors.append(
                    f"{path}: {value!r} does not match {schema['pattern']!r}"
                )
            if "maxLength" in schema and len(value) > schema["maxLength"]:
                self.errors.append(
                    f"{path}: {value!r} is longer than {schema['maxLength']} "
                    "characters"
                )

        if schema.get("format") == "email" and isinstance(value, str):
            if not _EMAIL_RE.match(value):
                self.errors.append(f"{path}: {value!r} is not a valid email")
        if schema.get("format") == "uri" and isinstance(value, str):
            if not _URI_RE.match(value):
                self.errors.append(f"{path}: {value!r} is not a valid URI")

        if isinstance(value, dict):
            self._validate_object(value, schema, path)
        elif isinstance(value, list) and "items" in schema:
            for i, item in enumerate(value):
                self.validate(item, schema["items"], f"{path}[{i}]")

    def _validate_object(self, value, schema, path):
        for req in schema.get("required", []):
            if req not in value:
                self.errors.append(
                    f"{path or '<root>'}: missing required key {req!r}"
                )

        props = schema.get("properties", {})
        pattern_props = schema.get("patternProperties", {})
        compiled = [(re.compile(p), s) for p, s in pattern_props.items()]
        additional = schema.get("additionalProperties", True)

        for key, sub in value.items():
            child = f"{path}.{key}" if path else key
            if key in props:
                self.validate(sub, props[key], child)
                continue
            matched = [s for rx, s in compiled if rx.search(key)]
            if matched:
                for s in matched:
                    self.validate(sub, s, child)
                continue
            if additional is False:
                self.errors.append(
                    f"{path or '<root>'}: unexpected key {key!r} "
                    f"(not allowed by the schema)"
                )
            elif isinstance(additional, dict):
                self.validate(sub, additional, child)


def validate_cv(repo_root):
    schema_path = repo_root / "src" / "cv.schema.json"
    data_path = repo_root / "src" / "cv.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    data = json.loads(data_path.read_text(encoding="utf-8"))
    v = SchemaValidator(schema)
    v.validate(data, schema, "")
    return [f"cv.json: {e}" for e in v.errors], data


# --------------------------------------------------------------------------
# CSL-JSON (publications.json) checks.
# --------------------------------------------------------------------------

# Web-only extras: the curated set of link kinds a publication may carry. The
# display wording lives in src/render_html.py (LINK_LABELS) — the renderer owns
# formatting; this list owns the vocabulary, so a typo'd kind is caught here
# instead of silently rendering as itself. Any kind may still be overridden with
# an explicit "label" for a one-off (e.g. "Interactive map").
LINK_TYPES = {
    "official", "accepted", "preprint", "pdf", "code", "data", "notebook",
    "viz", "site", "docs", "slides", "video", "poster", "blog",
}


def validate_links(links, where):
    errors = []
    if not isinstance(links, list):
        return [f"{where}: 'links' must be an array of {{type, url}} objects"]
    for j, l in enumerate(links):
        at = f"{where}.links[{j}]"
        if not isinstance(l, dict):
            errors.append(f"{at}: link is not an object")
            continue
        for req in ("type", "url"):
            if req not in l:
                errors.append(f"{at}: missing required key {req!r}")
        extra = set(l) - {"type", "url", "label"}
        if extra:
            errors.append(f"{at}: unexpected key(s) {sorted(extra)} "
                          "(allowed: type, url, label)")
        url = l.get("url")
        if url is not None and not str(url).startswith(("http://", "https://")):
            errors.append(f"{at}: url {url!r} must be an http(s) URL")
        t = l.get("type")
        if t is not None and t not in LINK_TYPES and "label" not in l:
            errors.append(
                f"{at}: link type {t!r} is not a known kind and has no 'label' "
                f"to render instead. Known kinds: {sorted(LINK_TYPES)}"
            )
    return errors


def validate_publications(repo_root, cv_data):
    errors = []
    pubs_path = repo_root / "src" / "publications.json"
    pubs = json.loads(pubs_path.read_text(encoding="utf-8"))

    if not isinstance(pubs, list):
        return [f"{pubs_path.name}: expected a JSON array of CSL entries"]

    # Categories the renderer will actually display, gathered from the
    # publications section's groups in cv.json.
    rendered = set()
    for section in cv_data.get("sections", []):
        if section.get("type") == "publications":
            for g in section.get("groups", []):
                if "category" in g:
                    rendered.add(g["category"])

    seen_ids = set()
    for i, p in enumerate(pubs):
        where = f"publications.json[{i}]"
        if not isinstance(p, dict):
            errors.append(f"{where}: entry is not an object")
            continue
        for req in ("id", "type", "title", "issued", "category"):
            if req not in p:
                errors.append(f"{where}: missing required CSL field {req!r}")
        pid = p.get("id")
        if pid in seen_ids:
            errors.append(f"{where}: duplicate id {pid!r}")
        seen_ids.add(pid)
        if "author" not in p and "editor" not in p:
            errors.append(f"{where} ({pid}): has neither 'author' nor 'editor'")
        issued = p.get("issued")
        if isinstance(issued, dict):
            try:
                int(issued["date-parts"][0][0])
            except (KeyError, IndexError, TypeError, ValueError):
                errors.append(
                    f"{where} ({pid}): 'issued' must be "
                    "{{'date-parts': [[YEAR]]}}"
                )
        if "links" in p:
            errors.extend(validate_links(p["links"], f"{where} ({pid})"))
        cat = p.get("category")
        if cat is not None and rendered and cat not in rendered:
            errors.append(
                f"{where} ({pid}): category {cat!r} matches no group in the "
                f"publications section — it will not be rendered. Known "
                f"categories: {sorted(rendered)}"
            )
    return errors


# --------------------------------------------------------------------------
# Ids across both files.
# --------------------------------------------------------------------------

def _cv_entry_ids(cv_data):
    """Yield (JSON path, id) for every cv.json entry that has an id."""
    for i, section in enumerate(cv_data.get("sections", [])):
        where = f"sections[{i}]"
        for k, group in enumerate(section.get("groups", [])):
            for j, e in enumerate(group.get("entries", [])):
                if isinstance(e, dict) and "id" in e:
                    yield f"{where}.groups[{k}].entries[{j}]", e["id"]
        for j, e in enumerate(section.get("entries", [])):
            if isinstance(e, dict) and "id" in e:
                yield f"{where}.entries[{j}]", e["id"]


def validate_ids(repo_root, cv_data):
    """Duplicate ids within cv.json, or shared between the two files.

    (Duplicates *within* publications.json are reported by
    validate_publications; a missing cv.json id by the schema.)
    """
    pubs = json.loads(
        (repo_root / "src" / "publications.json").read_text(encoding="utf-8"))
    pub_ids = {p.get("id") for p in pubs if isinstance(p, dict)}
    errors, first_seen = [], {}
    for where, eid in _cv_entry_ids(cv_data):
        if eid in first_seen:
            errors.append(f"cv.json: {where}: duplicate id {eid!r} "
                          f"(also at {first_seen[eid]})")
        else:
            first_seen[eid] = where
        if eid in pub_ids:
            errors.append(f"cv.json: {where}: id {eid!r} is also a "
                          "publications.json id — ids must be unique across "
                          "both files")
    return errors


def find_repo_root(start=None):
    """`start` if it holds src/cv.json, else the repo this file lives in."""
    if start is not None and (Path(start) / "src" / "cv.json").exists():
        return Path(start)
    for parent in Path(__file__).resolve().parents:
        if (parent / "src" / "cv.json").exists():
            return parent
    return Path(start or Path.cwd())


def check(repo_root):
    """Every problem with the data under repo_root/src, as strings."""
    repo_root = Path(repo_root)
    try:
        cv_errors, cv_data = validate_cv(repo_root)
    except FileNotFoundError as e:
        return [f"{e}"]
    except json.JSONDecodeError as e:
        return [f"cv.json / cv.schema.json is not valid JSON: {e}"]
    try:
        return (cv_errors + validate_publications(repo_root, cv_data)
                + validate_ids(repo_root, cv_data))
    except FileNotFoundError as e:
        return [f"{e}"]
    except json.JSONDecodeError as e:
        return [f"publications.json is not valid JSON: {e}"]


def main():
    repo_root = find_repo_root(sys.argv[1] if len(sys.argv) > 1 else Path.cwd())
    errors = check(repo_root)
    if errors:
        print(f"✗ {len(errors)} problem(s) found:\n", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("✓ cv.json conforms to cv.schema.json")
    print("✓ publications.json is well-formed and every category is rendered")
    print("✓ every record has an id, unique across both files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
