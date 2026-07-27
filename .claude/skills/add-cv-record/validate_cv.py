#!/usr/bin/env python3
"""Validate the CV data files before opening a PR.

Two checks, both stdlib-only (no pip installs — matches the repo's
no-extra-dependencies ethos; see ARCHITECTURE.md):

  1. src/cv.json  against  src/cv.schema.json  — a focused JSON Schema
     validator covering exactly the draft-2020-12 keywords the schema uses
     (type, required, properties, additionalProperties, patternProperties,
     enum, items, $ref/$defs, format). It reads the schema, so it keeps
     working if the schema grows.

  2. src/publications.json  (CSL-JSON, no schema) — structural sanity plus a
     cross-check that every entry's `category` matches a group declared in
     the `publications` section of cv.json, so a new publication actually
     lands in a rendered group instead of vanishing. Also checks the shape of
     the optional web-only `links` array (see LINK_TYPES below).

CI's `make validate` only checks that the JSON *parses*; this goes further.
It never touches the renderers or builds anything.

Usage:  python3 .claude/skills/add-cv-record/validate_cv.py [repo_root]
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
    return v.errors, data


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


def main():
    repo_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    # Allow running from anywhere inside the repo.
    if not (repo_root / "src" / "cv.json").exists():
        here = Path(__file__).resolve()
        for parent in here.parents:
            if (parent / "src" / "cv.json").exists():
                repo_root = parent
                break

    try:
        cv_errors, cv_data = validate_cv(repo_root)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"ERROR: cv.json / cv.schema.json is not valid JSON: {e}",
              file=sys.stderr)
        return 1

    try:
        pub_errors = validate_publications(repo_root, cv_data)
    except json.JSONDecodeError as e:
        print(f"ERROR: publications.json is not valid JSON: {e}",
              file=sys.stderr)
        return 1

    errors = cv_errors + pub_errors
    if errors:
        print(f"✗ {len(errors)} problem(s) found:\n", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("✓ cv.json conforms to cv.schema.json")
    print("✓ publications.json is well-formed and every category is rendered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
