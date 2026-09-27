#!/usr/bin/env python3
"""Build a subset CV: a shorter, audience-specific CV from the same data.

A TOML config (see src/subset.template.toml; git ignores every *.toml but
that template, so a config inside the repo stays untracked) names the sections to include and, optionally, the ids of the records to keep.
The build filters the master data into a derived cv.json + publications.json
that still validate against cv.schema.json, then runs the unchanged renderers
over it (ARCHITECTURE.md, Decision 5; the full brief is
notes/SUBSET-CV-SPEC.md). Renderers learn nothing about configs or ids.

    make subset      CONFIG=~/cv-subsets/erc-2027.toml [OUT=dir]
    make subset-list [SECTION="Research Income"]         # record ids

`make subset` builds CONFIG, or — if there is no file there yet — writes a
starter config listing every section and id, to edit and then build with
the same command. They run:

    python3 src/build_subset.py CONFIG --new-if-missing [--out DIR] [--strict]
    python3 src/build_subset.py --list [SECTION]
    python3 src/build_subset.py --scaffold [PATH]   # PATH, or stdout

Outputs go beside the config (<config dir>/<name>/) or to --out: the PDF,
the derived data, a verbatim copy of the config and a manifest.json recording
what was built from what. Outside the repository anywhere will do; inside it,
only where git ignores the path (e.g. subsets/) and never docs/ or src/, so a
subset can never be committed or published. Scratch data goes to
build/.subset-work/ (gitignored, wiped per build), because Typst will not
read files outside its --root.

Every problem — in the data, the config or the output path — stops the build
with a message naming the file, key and value; all are reported together.
Stdlib + the Typst binary only.
"""

import argparse
import copy
import datetime
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import validate_cv
from assign_ids import KEY_FIELD, slugify

SRC = Path(__file__).resolve().parent
REPO = SRC.parent
FONTS = REPO / "fonts"
WORK = REPO / "build" / ".subset-work"
# WORK as cv.typ and render_html.py see it: data paths are relative to src/.
WORK_FROM_SRC = "../build/.subset-work"

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# Config keys by table. A key in LATER belongs to a phase not built yet: it is
# an error that says which phase adds it, rather than being silently ignored.
TOP_KEYS = {"name", "formats", "header", "section", "drop"}
HEADER_KEYS = {"title"}
SECTION_KEYS = {"title", "rename", "ids", "group"}
GROUP_KEYS = {"title", "rename", "ids"}
LATER = {
    "top": {"style": "P3", "money": "P2", "summary": "P2"},
    "header": {"affiliation": "P5", "email": "P5", "url": "P5"},
    "section": {"summary": "P2"},
    "group": {"summary": "P2"},
}
FORMATS = {"pdf"}
LATER_FORMATS = {"docx": "P4", "md": "P4"}


class BuildError(Exception):
    """Stops the build. Carries every problem found, not just the first."""

    def __init__(self, problems):
        super().__init__("\n".join(problems))
        self.problems = list(problems)


# ===========================================================================
# The master data, indexed for selection.
# ===========================================================================

class Master:
    """src/cv.json + src/publications.json, with lookups by title and id."""

    def __init__(self, cv, pubs):
        self.cv = cv
        self.pubs = pubs
        self.sections = {s["title"]: s for s in cv["sections"]}
        # id -> (section title, group title or None)
        self.owner = {}
        for s in cv["sections"]:
            for g in self.groups(s) or [None]:
                for item in self.items(s, g):
                    self.owner[item["id"]] = (s["title"], g and g["title"])

    @staticmethod
    def is_pubs(section):
        return section.get("type") == "publications"

    @staticmethod
    def groups(section):
        """The section's groups, or None for a flat section."""
        return section.get("groups") if "groups" in section else None

    def items(self, section, group=None):
        """Records under a group, or a whole section, in source order."""
        if group is None and self.groups(section) is not None:
            return [i for g in self.groups(section) for i in self.items(section, g)]
        if self.is_pubs(section):
            return [p for p in self.pubs if p.get("category") == group.get("category")]
        return (group or section).get("entries", [])

    def kind(self, section, group=None):
        return (group or {}).get("type") or section.get("type")


def load_master():
    """Load and validate the master data; BuildError if anything is wrong."""
    problems = [f"master data: {e}" for e in validate_cv.check(REPO)]
    if problems:
        raise BuildError(problems + ["fix the data in src/ first "
                                     "(python3 src/validate_cv.py)"])
    cv = json.loads((SRC / "cv.json").read_text(encoding="utf-8"))
    pubs = json.loads((SRC / "publications.json").read_text(encoding="utf-8"))
    titles = [s["title"] for s in cv["sections"]]
    for t in sorted({t for t in titles if titles.count(t) > 1}):
        problems.append(f"master data: cv.json: section title {t!r} is used "
                        "more than once, so a config cannot name it")
    for s in cv["sections"]:
        gt = [g["title"] for g in s.get("groups", [])]
        for t in sorted({t for t in gt if gt.count(t) > 1}):
            problems.append(f"master data: cv.json: section {s['title']!r} has "
                            f"two groups titled {t!r}")
        if Master.is_pubs(s) and s.get("source") != "publications.json":
            problems.append(f"master data: cv.json: section {s['title']!r}: "
                            f"source {s.get('source')!r} — only "
                            "'publications.json' is supported")
    if problems:
        raise BuildError(problems)
    return Master(cv, pubs)


# ===========================================================================
# Config: parse and validate into a plan.
# ===========================================================================

def _suggest(value, choices):
    close = difflib.get_close_matches(value, list(choices), n=1)
    return f" — did you mean {close[0]!r}?" if close else ""


def _keys(table, where, allowed, later, problems):
    for key in table:
        if key in later:
            problems.append(f"{where}: key {key!r} is not available yet — it is "
                            f"added in phase {later[key]} of the subset-CV "
                            "feature (notes/SUBSET-CV-SPEC.md §15)")
        elif key not in allowed:
            problems.append(f"{where}: unknown key {key!r} (allowed: "
                            f"{', '.join(sorted(allowed))})"
                            + _suggest(key, allowed))


def _is(value, kind):
    return isinstance(value, kind) and not isinstance(value, bool)


def _string_list(value, where, problems, empty_hint):
    """Validate a non-empty array of unique strings; return it or None."""
    if not isinstance(value, list):
        problems.append(f"{where}: expected an array of strings, got "
                        f"{type(value).__name__} {value!r}")
        return None
    if not value:
        problems.append(f"{where}: empty array — {empty_hint}")
        return None
    good = True
    for i, v in enumerate(value):
        if not _is(v, str):
            problems.append(f"{where}[{i}]: expected a string, got "
                            f"{type(v).__name__} {v!r}")
            good = False
    if not good:
        return None
    for v in sorted({v for v in value if value.count(v) > 1}):
        problems.append(f"{where}: {v!r} is listed more than once")
    return value


def _title(table, where, problems):
    t = table.get("title")
    if t is None:
        problems.append(f"{where}: missing required key 'title'")
    elif not _is(t, str):
        problems.append(f"{where}: 'title' must be a string, got {t!r}")
        t = None
    return t


def _rename(table, where, problems):
    r = table.get("rename")
    if r is not None and not (_is(r, str) and r.strip()):
        problems.append(f"{where}: 'rename' must be a non-empty string, got {r!r}")
        return None
    return r


def _ids(table, where, problems, master, section, group, what):
    """Check an `ids` array against the records under section (and group)."""
    if "ids" not in table:
        return None
    ids = _string_list(table["ids"], f"{where}.ids", problems,
                       f"remove 'ids' to include the whole {what}")
    if ids is None:
        return None
    here = (section["title"], group and group["title"])
    for i, rid in enumerate(ids):
        at = f"{where}.ids[{i}]"
        owner = master.owner.get(rid)
        if owner is None:
            pool = [r["id"] for r in master.items(section, group)]
            problems.append(f"{at}: {rid!r} matches no record" + _suggest(rid, pool))
        elif owner != here and not (group is None and owner[0] == here[0]):
            place = f"section {owner[0]!r}" + (f", group {owner[1]!r}" if owner[1] else "")
            problems.append(f"{at}: {rid!r} is not in this {what} — it belongs "
                            f"to {place}")
    return ids


def parse_config(path, master):
    """Read and validate a config file. Returns the plan; BuildError if bad.

    The plan: {"name", "formats", "header_title", "sections": [
        {"title", "rename", "ids", "groups": None | [{"title", "rename", "ids"}]}
    ]} — sections in output order, every title and id checked against master.
    """
    fname = path.name
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BuildError([f"{path}: config file not found"])
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        raise BuildError([f"{fname}: not valid TOML: {e}"])

    problems = []
    _keys(raw, fname, TOP_KEYS, LATER["top"], problems)

    name = raw.get("name", path.stem)
    if not (_is(name, str) and NAME_RE.match(name)):
        if "name" in raw:
            problems.append(f"{fname}: name: {name!r} must match {NAME_RE.pattern}")
        else:
            problems.append(f"{fname}: the file name {path.stem!r} cannot be the "
                            f"subset's name (must match {NAME_RE.pattern}); set "
                            "'name' in the config")

    formats = raw.get("formats", ["pdf"])
    formats = _string_list(formats, f"{fname}: formats", problems,
                           "remove 'formats' for the default [\"pdf\"]") or []
    for i, f in enumerate(formats):
        if f in LATER_FORMATS:
            problems.append(f"{fname}: formats[{i}]: {f!r} is not available yet "
                            f"— it is added in phase {LATER_FORMATS[f]}")
        elif f not in FORMATS:
            problems.append(f"{fname}: formats[{i}]: unknown format {f!r} "
                            f"(available: {', '.join(sorted(FORMATS))})")

    header_title = None
    header = raw.get("header", {})
    if not isinstance(header, dict):
        problems.append(f"{fname}: header: expected a table, got {header!r}")
    else:
        _keys(header, f"{fname}: [header]", HEADER_KEYS, LATER["header"], problems)
        header_title = header.get("title")
        if header_title is not None and not _is(header_title, str):
            problems.append(f"{fname}: [header].title: must be a string, got "
                            f"{header_title!r}")
            header_title = None

    if ("section" in raw) == ("drop" in raw):
        problems.append(f"{fname}: needs exactly one of [[section]] (list what to "
                        "include) or drop = [...] (list what to leave out), "
                        + ("not both" if "section" in raw else "found neither"))
        sections = []
    elif "drop" in raw:
        sections = _plan_drop(raw["drop"], fname, master, problems)
    else:
        sections = _plan_sections(raw["section"], fname, master, problems)

    if problems:
        raise BuildError(problems)
    return {"name": name, "formats": formats, "header_title": header_title,
            "sections": sections}


def _plan_drop(drop, fname, master, problems):
    if not isinstance(drop, list) or not all(_is(t, str) for t in drop):
        problems.append(f"{fname}: drop: expected an array of section titles, "
                        f"got {drop!r}")
        return []
    for i, t in enumerate(drop):
        if t not in master.sections:
            problems.append(f"{fname}: drop[{i}]: no section titled {t!r}"
                            + _suggest(t, master.sections))
    for t in sorted({t for t in drop if drop.count(t) > 1}):
        problems.append(f"{fname}: drop: {t!r} is listed more than once")
    return [{"title": t, "rename": None, "ids": None, "groups": None}
            for t in master.sections if t not in drop]


def _plan_sections(tables, fname, master, problems):
    if not isinstance(tables, list) or not all(isinstance(t, dict) for t in tables):
        problems.append(f"{fname}: 'section' must be written as [[section]] "
                        "tables")
        return []
    plan, seen = [], set()
    for n, table in enumerate(tables, 1):
        where = f"{fname}: [[section]] #{n}"
        _keys(table, where, SECTION_KEYS, LATER["section"], problems)
        title = _title(table, where, problems)
        rename = _rename(table, where, problems)
        if title is None:
            continue
        where = f"{where} {title!r}"
        if title in seen:
            problems.append(f"{where}: section listed more than once")
        seen.add(title)
        section = master.sections.get(title)
        if section is None:
            problems.append(f"{where}: no section titled {title!r}"
                            + _suggest(title, master.sections))
            continue
        ids = _ids(table, where, problems, master, section, None, "section")
        groups = None
        if "group" in table:
            groups = _plan_groups(table["group"], where, master, section, problems)
            if "ids" in table:
                problems.append(f"{where}: has both 'ids' and [[section.group]] "
                                "tables — put the ids under the groups they "
                                "belong to, or drop the group tables")
        plan.append({"title": title, "rename": rename, "ids": ids,
                     "groups": groups})
    return plan


def _plan_groups(tables, where, master, section, problems):
    src_groups = master.groups(section)
    if src_groups is None:
        problems.append(f"{where}: has [[section.group]] tables but the section "
                        "has no groups")
        return None
    if not isinstance(tables, list) or not all(isinstance(t, dict) for t in tables):
        problems.append(f"{where}: 'group' must be written as [[section.group]] "
                        "tables")
        return None
    by_title = {g["title"]: g for g in src_groups}
    plan, seen = [], set()
    for n, table in enumerate(tables, 1):
        gwhere = f"{where} [[section.group]] #{n}"
        _keys(table, gwhere, GROUP_KEYS, LATER["group"], problems)
        title = _title(table, gwhere, problems)
        rename = _rename(table, gwhere, problems)
        if title is None:
            continue
        gwhere = f"{gwhere} {title!r}"
        if title in seen:
            problems.append(f"{gwhere}: group listed more than once")
        seen.add(title)
        group = by_title.get(title)
        if group is None:
            problems.append(f"{gwhere}: section {section['title']!r} has no group "
                            f"titled {title!r}" + _suggest(title, by_title))
            continue
        ids = _ids(table, gwhere, problems, master, section, group, "group")
        plan.append({"title": title, "rename": rename, "ids": ids})
    return plan


# ===========================================================================
# Selection: plan + master -> derived data.
# ===========================================================================

def select(plan, master):
    """Apply the plan. Returns (derived cv, derived publications, counts).

    Listed -> included; nothing more specified -> included in full; ids given
    -> only those, in source order. Retained records are copied verbatim.
    """
    cv = {k: copy.deepcopy(v) for k, v in master.cv.items() if k != "sections"}
    if plan["header_title"] is not None:
        cv["basics"]["title"] = plan["header_title"]
    sections, counts, kept_pubs = [], [], set()

    for sp in plan["sections"]:
        src = master.sections[sp["title"]]
        wanted = set(sp["ids"]) if sp["ids"] else None
        kept = 0
        out = {}
        for key, value in src.items():
            if key == "title":
                out[key] = sp["rename"] or value
            elif key == "source":
                out[key] = f"{WORK_FROM_SRC}/publications.json"
            elif key == "groups":
                chosen = sp["groups"] or [
                    {"title": g["title"], "rename": None, "ids": None}
                    for g in value]
                by_title = {g["title"]: g for g in value}
                out[key] = []
                for gp in chosen:
                    g = by_title[gp["title"]]
                    keep = set(gp["ids"]) if gp["ids"] else wanted
                    items = master.items(src, g)
                    if keep is not None:
                        items = [i for i in items if i["id"] in keep]
                        if not items:
                            continue  # emptied by the section's ids: drop it
                    kept += len(items)
                    new = {}
                    for gkey, gvalue in g.items():
                        if gkey == "title":
                            new[gkey] = gp["rename"] or gvalue
                        elif gkey == "entries":
                            new[gkey] = copy.deepcopy(items)
                        else:
                            new[gkey] = copy.deepcopy(gvalue)
                    if master.is_pubs(src):
                        kept_pubs.update(p["id"] for p in items)
                    out[key].append(new)
            elif key == "entries":
                items = [e for e in value if wanted is None or e["id"] in wanted]
                kept += len(items)
                out[key] = copy.deepcopy(items)
            else:
                out[key] = copy.deepcopy(value)
        sections.append(out)
        counts.append({"section": sp["title"], "heading": out["title"],
                       "kept": kept, "total": len(master.items(src))})

    cv["sections"] = sections
    pubs = [copy.deepcopy(p) for p in master.pubs if p["id"] in kept_pubs]
    return cv, pubs, counts


# ===========================================================================
# Build.
# ===========================================================================

def inside_repo(path):
    """Whether a resolved path is the repository or anything under it."""
    repo = REPO.resolve()
    return path == repo or repo in path.parents


# Never written to, even if gitignored: the public site and the master data.
FORBIDDEN = ("docs", "src")
PRIVATE_HINT = ("Keep configs in the gitignored subsets/ folder (make subset "
                "CONFIG=subsets/<name>.toml), or set OUT=subsets/<name> or a "
                "directory outside the repository.")


def check_out_in_repo(target):
    """Problems with an output dir inside the repo, or [] if it is private.

    Subsets are private (spec §13): inside the repository an output may only
    go where git ignores it, so it can never be committed or published —
    and never into docs/ (the public site) or src/, ignored or not.
    """
    repo = REPO.resolve()
    rel = target.relative_to(repo)
    if not rel.parts or rel.parts[0] in FORBIDDEN:
        where = "the repository root" if not rel.parts else f"{rel.parts[0]}/"
        return [f"output directory {target} is in {where} — subset CVs are "
                "private and never go there. " + PRIVATE_HINT]
    work = WORK.resolve()
    if target == work or work in target.parents or target in work.parents:
        return [f"output directory {target} overlaps the build's scratch "
                f"directory {WORK.relative_to(REPO)}/. " + PRIVATE_HINT]
    try:
        run = subprocess.run(["git", "check-ignore", "-q", "--", str(rel)],
                             cwd=REPO, capture_output=True, text=True)
        code = run.returncode
    except FileNotFoundError:
        code = None
    if code == 0:
        return []
    if code == 1:
        return [f"output directory {target} is inside the repository but not "
                "ignored by git, so the subset could be committed. "
                + PRIVATE_HINT]
    return [f"output directory {target} is inside the repository and git "
            "could not confirm it is ignored (is git installed?). "
            + PRIVATE_HINT]


def resolve_out(config_path, name, out=None):
    """The output directory. BuildError unless it is private (see above)."""
    target = Path(out).expanduser() if out else config_path.parent / name
    target = target.resolve()  # follows symlinks, so a link into docs/ fails
    if inside_repo(target):
        problems = check_out_in_repo(target)
        if problems:
            raise BuildError(problems)
    if target.exists() and not target.is_dir():
        raise BuildError([f"output path {target} exists and is not a directory"])
    return target


def file_prefix(basics):
    """'Daniel Arribas-Bel' -> 'darribas': given-name initial + first surname."""
    parts = basics["name"].split()
    if len(parts) < 2:
        return slugify(basics["name"])
    return slugify(parts[0][0] + re.split(r"[-\s]", parts[-1])[0])


def _write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def render_pdf(pdf):
    typst = shutil.which("typst")
    if typst is None:
        raise BuildError(["typst not found on PATH — install it from "
                          "https://github.com/typst/typst/releases"])
    run = subprocess.run(
        [typst, "compile", "--root", str(REPO), "--font-path", str(FONTS),
         "--input", f"data={WORK_FROM_SRC}/cv.json",
         str(SRC / "cv.typ"), str(pdf)],
        cwd=REPO, capture_output=True, text=True)
    if run.returncode != 0:
        raise BuildError([f"typst failed:\n{run.stderr.strip()}"])


def pdf_pages(pdf):
    m = re.search(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)", pdf.read_bytes())
    return int(m.group(1)) if m else None


def _git(*args):
    try:
        run = subprocess.run(["git", *args], cwd=REPO, capture_output=True,
                             text=True)
    except FileNotFoundError:
        return None
    return run.stdout.strip() if run.returncode == 0 else None


def build_time():
    """UTC build time; honours SOURCE_DATE_EPOCH (as Typst does)."""
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    t = (datetime.datetime.fromtimestamp(int(epoch), datetime.timezone.utc)
         if epoch else datetime.datetime.now(datetime.timezone.utc))
    return t.replace(microsecond=0).isoformat()


def build(config, out=None, strict=False, master=None):
    """Build one subset CV. Returns the manifest; BuildError on any problem."""
    config = Path(config).expanduser().resolve()
    master = master or load_master()
    plan = parse_config(config, master)
    target = resolve_out(config, plan["name"], out)

    warnings = []  # none raised yet in this phase; later phases add them
    cv, pubs, counts = select(plan, master)

    schema = json.loads((SRC / "cv.schema.json").read_text(encoding="utf-8"))
    check = validate_cv.SchemaValidator(schema)
    check.validate(cv, schema, "")
    if check.errors:
        raise BuildError([f"derived cv.json: {e}" for e in check.errors])
    if strict and warnings:
        raise BuildError([f"warning (--strict): {w}" for w in warnings])

    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    _write_json(WORK / "cv.json", cv)
    _write_json(WORK / "publications.json", pubs)

    stem = f"{file_prefix(cv['basics'])}-cv-{plan['name']}"
    files = []
    if "pdf" in plan["formats"]:
        render_pdf(WORK / "cv.pdf")
        files.append((WORK / "cv.pdf", f"{stem}.pdf"))

    commit = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain", "--untracked-files=no", "--",
                  "src", "fonts")
    manifest = {
        "name": plan["name"],
        "built": build_time(),
        "config": str(config),
        "data_commit": commit,
        "dirty": None if status is None else bool(status),
        "formats": plan["formats"],
        "files": [name for _, name in files],
        "pages": pdf_pages(WORK / "cv.pdf") if "pdf" in plan["formats"] else None,
        "sections": counts,
        "warnings": warnings,
    }

    target.mkdir(parents=True, exist_ok=True)
    for src, name in files:
        shutil.copyfile(src, target / name)
    shutil.copyfile(WORK / "cv.json", target / "cv.json")
    shutil.copyfile(WORK / "publications.json", target / "publications.json")
    shutil.copyfile(config, target / "config.toml")
    _write_json(target / "manifest.json", manifest)
    manifest["out"] = str(target)
    return manifest


# ===========================================================================
# Discovery: --list and --scaffold.
# ===========================================================================

def _oneline(s, width=None):
    s = " ".join(str(s).split())
    return s if width is None or len(s) <= width else s[:width - 1] + "…"


def describe(master, section, group, item):
    """(date, short text) for one record."""
    if master.is_pubs(section):
        year = str(item["issued"]["date-parts"][0][0])
        authors = item.get("author") or item.get("editor") or []
        first = authors[0] if authors else {}
        who = first.get("family") or first.get("literal") or ""
        if len(authors) > 1:
            who += " et al."
        return year, f"{who} — {item.get('title', '')}"
    date = item.get("date") or item.get("years") or ""
    field = KEY_FIELD.get(master.kind(section, group))
    text = item.get(field) or next(
        (v for k, v in item.items() if k != "id" and isinstance(v, str)), "")
    return date, text


def _find_section(master, title):
    if title in master.sections:
        return master.sections[title]
    folded = {t.casefold(): s for t, s in master.sections.items()}
    if title.casefold() in folded:
        return folded[title.casefold()]
    raise BuildError([f"--list: no section titled {title!r}"
                      + _suggest(title, master.sections)
                      + ". Sections: " + "; ".join(master.sections)])


def listing(master, title=None):
    sections = [_find_section(master, title)] if title else master.cv["sections"]
    width = max((len(i["id"]) for s in sections for i in master.items(s)),
                default=0)
    lines = []
    for s in sections:
        lines.append(f"== {s['title']}  ({len(master.items(s))} records)")
        for g in master.groups(s) or [None]:
            if g is not None:
                lines.append(f"-- {g['title']}")
            for item in master.items(s, g):
                date, text = describe(master, s, g, item)
                lines.append(f"{item['id']:<{width}}  {date:<10}  {_oneline(text, 70)}")
        lines.append("")
    return "\n".join(lines).rstrip("\n")


def _toml_str(s):
    # A JSON string is a valid TOML basic string (same escapes).
    return json.dumps(s, ensure_ascii=False)


def _ids_block(master, section, group, indent):
    items = master.items(section, group)
    if not items:
        return []
    lines = [f"{indent}ids = ["]
    for item in items:
        date, text = describe(master, section, group, item)
        note = _oneline(f"{date} {text}".strip(), 90)
        lines.append(f"{indent}  {_toml_str(item['id'])},  # {note}")
    lines.append(f"{indent}]")
    return lines


def scaffold(master):
    commit = _git("rev-parse", "--short", "HEAD") or "unknown"
    lines = [
        "# Subset CV config — generated by `make subset` (no config existed yet)",
        f"# from the data at commit {commit}. Every section, group and record is",
        "# listed, so as it stands this builds the full CV. Build a subset by",
        "# deleting lines:",
        "#   - a whole [[section]] (or [[section.group]]) block drops it;",
        "#   - an id line drops that record;",
        "#   - deleting an entire `ids = [...]` keeps the whole section/group,",
        "#     including records added later.",
        "# Sections print in the order listed here; records in data order.",
        "# See src/subset.template.toml for every key.",
        "#",
        "# Build it with `make subset CONFIG=<this file>`; outputs are written",
        "# beside it, in a folder named after it. Inside the cv repository, keep",
        "# it in the gitignored subsets/ folder so the outputs stay private.",
        "",
        "# name    = \"my-subset\"   # default: this file's name",
        "formats = [\"pdf\"]",
        "",
        "# [header]",
        f"# title = {_toml_str(master.cv['basics'].get('title', 'Curriculum Vitae'))}",
    ]
    for s in master.cv["sections"]:
        lines += ["", "[[section]]", f"title = {_toml_str(s['title'])}"]
        groups = master.groups(s)
        if groups is None:
            lines += _ids_block(master, s, None, "")
            continue
        for g in groups:
            lines += ["  [[section.group]]", f"  title = {_toml_str(g['title'])}"]
            lines += _ids_block(master, s, g, "  ")
    return "\n".join(lines) + "\n"


def write_scaffold(master, path):
    """Write scaffold() to a new .toml file; never overwrite."""
    path = Path(path).expanduser().resolve()
    if path.suffix != ".toml":
        raise BuildError([f"{path}: a config file name must end in .toml"])
    if path.exists():
        raise BuildError([f"{path} already exists — not overwriting it. "
                          "Pick a new name, or delete it first."])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(scaffold(master), encoding="utf-8")
    return path


# ===========================================================================
# CLI.
# ===========================================================================

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Build a subset CV from a TOML config (see "
                    "src/subset.template.toml).")
    ap.add_argument("config", nargs="?", type=Path, help="the subset's TOML config")
    ap.add_argument("--out", type=Path,
                    help="output directory (default: <config dir>/<name>/)")
    ap.add_argument("--strict", action="store_true",
                    help="treat warnings as errors")
    ap.add_argument("--new-if-missing", action="store_true",
                    help="if CONFIG does not exist, write a starter config "
                         "there (as --scaffold PATH) instead of building")
    ap.add_argument("--list", nargs="?", const="", metavar="SECTION",
                    help="list every record (or one section's) with its id")
    ap.add_argument("--scaffold", nargs="?", const="-", metavar="PATH",
                    help="write a config listing every section and id to "
                         "PATH (a new .toml file), or to stdout")
    args = ap.parse_args(argv)

    modes = [args.config is not None, args.list is not None,
             args.scaffold is not None]
    if sum(modes) != 1:
        ap.error("give exactly one of CONFIG, --list or --scaffold")

    try:
        master = load_master()
        if args.list is not None:
            print(listing(master, args.list or None))
        elif args.scaffold == "-":
            sys.stdout.write(scaffold(master))
        elif args.scaffold is not None:
            path = write_scaffold(master, args.scaffold)
            print(f"Wrote {path}\nDelete the sections and ids you don't want, "
                  f"then build it with:\n  make subset CONFIG={path}")
        elif args.new_if_missing and not args.config.expanduser().exists():
            path = write_scaffold(master, args.config)
            print(f"No config at {path} yet, so wrote a starter one listing "
                  "every section and record (as it stands, the full CV).\n"
                  "Delete the sections and ids you don't want, then run the "
                  "same command again to build it:\n"
                  f"  make subset CONFIG={path}")
        else:
            m = build(args.config, out=args.out, strict=args.strict, master=master)
            for w in m["warnings"]:
                print(f"warning: {w}", file=sys.stderr)
            kept = sum(c["kept"] for c in m["sections"])
            total = len(master.owner)
            n, pages = len(m["sections"]), m["pages"]
            print(f"Built {m['name']}: {n} section{'s' * (n != 1)}, {kept} of "
                  f"{total} records, {pages} page{'s' * (pages != 1)}")
            for f in m["files"]:
                print(f"  {Path(m['out']) / f}")
    except BuildError as e:
        print(f"✗ {len(e.problems)} problem(s):\n", file=sys.stderr)
        for p in e.problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
