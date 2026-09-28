# Subset CVs — implementation spec

**Status: final; P0–P2 implemented (PRs #14, #15, #18), P3–P5 to go.** This is
the brief for building the subset-CV feature (`TODO.md`, "Tooling for building
subsets of the CV"). It is written for the implementer — human or Claude Code —
to work from without further design discussion. Design rationale lives in
`ARCHITECTURE.md` Decision 5; this document says *what to build*. Anything not
decided is listed in §19 and is **out of scope** until decided.

Read before starting: `ARCHITECTURE.md` (Decisions 2 and 5), `src/cv.typ`,
`src/render_html.py`, `src/cv.schema.json`, `.claude/skills/add-cv-record/`.

---

## 1. Goal

Build shorter, audience-specific versions of the CV from the same data, on the
author's machine, reproducibly:

1. A **config file** (TOML) lists the sections to include and, where only part
   of a section is wanted, the ids of the items to keep.
2. Included sections can carry **summary lines** at their top ("12 of 112
   publications", total award value converted to one currency).
3. The config sets **how to render**: formats (PDF, DOCX), font, size, paper,
   margins, page numbers.
4. One command builds it. The config can be kept and rebuilt later.

## 2. Non-negotiable principles

1. **A subset is a data transform, not a renderer feature.** Config + master
   data → a *derived* `cv.json` + `publications.json` that still validate
   against `cv.schema.json` → the existing renderers. Renderers gain only
   *generic* knobs (read data from a path; font/size/paper/margins/page numbers;
   print a section's summary strings). They never learn what a config, an id
   list or a metric is.
2. **Subsets are private.** No subset config or output is ever committed to this
   repo or published (not on GitHub Pages, not by CI). Enforced in code (§13).
3. **Subsets select; they never rewrite.** Every retained entry reaches the
   renderer verbatim. Wrong wording is a data fix in `src/`.
4. **Fail loudly.** A subset CV goes to people who decide things. Any dangling
   reference, missing font or missing exchange rate stops the build with a
   message naming file, key and value. No silent omission, substitution or
   fallback — except the one explicitly configured rates fallback (§8.3), which
   warns.
5. **Stdlib-only Python + the Typst binary.** No pip installs. pandoc is needed
   **only** for DOCX, and nothing else may depend on it.
6. **`src/` holds facts; the build's work directory holds a rendering-ready
   projection.** Derived data may contain computed, pre-formatted text (summary
   lines); `src/` never does.
7. **The full CV does not change.** No code change may alter `make site`
   output (§14.2). The only output change in the whole feature is P0's
   deliberate one-entry data fix (`Co-I` → `CoI`).

## 3. The repository before P0 (verified facts)

- `src/cv.json`: `basics` + 17 `sections`. A section is **flat**
  (`type` + `entries`) or **grouped** (`groups[]`, each with `title`, `type`,
  `entries`). `Publications` is `type: "publications"`,
  `source: "publications.json"`, groups keyed by CSL `category`.
- 279 entries in `cv.json` across 13 entry types; **none has an id**. The file
  is **hand-formatted**: many entries are one-line objects, others span several
  lines, sections are separated by blank lines. `json.dump` does **not**
  round-trip it (a 1,843-line diff) — see §6.2.
- `src/publications.json`: 112 CSL-JSON records, each with a unique `id`;
  round-trips exactly with `json.dumps(indent=2, ensure_ascii=False)`.
- `src/cv.typ` reads `json("cv.json")` (relative to itself) and hard-codes:
  TeX Gyre Pagella 12.5pt, `paper: "us-letter"`, 1in margins, level-1 headings
  14pt, level-2 13pt, header name 15pt and contact lines 9pt, a 13mm date
  column, no page numbers, and a trailing `datetime.today()` date stamp.
  Monospace (`raw()`) is used for DOIs, grant codes and URLs.
- `src/render_html.py` hard-codes `SRC/cv.json` and writes `docs/`.
- `.claude/skills/add-cv-record/validate_cv.py`: stdlib schema validator
  (only the draft-2020-12 keywords `cv.schema.json` uses) plus structural checks
  on `publications.json`.
- CI (`.github/workflows/build-site.yml`): installs the **latest** Typst
  release, runs `make validate` (JSON parses), `make site`, commits `docs/` on
  pushes to `main`. There is **no test suite** and no `tests/` directory.
- `.gitignore` ignores `build/`.
- Research Income → *Awards*: 22 `grant` entries, all with structured
  `amount` (16 GBP, 5 EUR, 1 USD). *Projects*: 6 `project` entries, none with
  `amount`; 5 with free-text `funding`.
- `role` uses both `"CoI"` (11) and `"Co-I"` (1).
- The committed `docs/cv.pdf` embeds its creation time (`/CreationDate`,
  `xmp:CreateDate`) and prints its build date on the last page.

## 4. The config file

### 4.1 Format

TOML, parsed with `tomllib` (stdlib, Python ≥ 3.11). YAML is not used: it would
need PyYAML (a pip install).

### 4.2 Location

| What | Where | Tracked in git? |
|---|---|---|
| Annotated template | `src/subset.template.toml` | **yes** — the only subset file in the repo |
| The author's configs | the gitignored `subsets/` folder, e.g. `subsets/erc-2027.toml`, or anywhere outside the repo | never |
| Built outputs | beside the config by default: `<config dir>/<name>/`; `--out DIR` overrides. Inside the repo only where git ignores the path, never `docs/` or `src/` (§13) | never |
| Intermediate derived data | `build/.subset-work/` (gitignored; wiped at the start of each build) | never |

The intermediate data sits inside the repo only because Typst will not read
files outside its `--root`. Only finished artifacts are copied out.

### 4.3 Full example

```toml
# ~/cv-subsets/erc-2027.toml
name    = "erc-2027"            # output dir + file names; default: the file stem
formats = ["pdf", "docx"]       # "pdf" | "docx" | "md"; default ["pdf"]

[header]
title = "Curriculum Vitae"      # overrides basics.title (P1)
# affiliation = ["…", "…"]      # P5 — see §10
# email = false                 # P5
# url = false                   # P5

[style]                         # P3; every key optional
font         = "Arial"
size         = 11               # body size, pt
paper        = "a4"             # "a4" | "us-letter"
margins      = 20               # mm, all sides
page_numbers = true             # "1 of 3", centred footer
# fallback   = "Liberation Sans"  # explicit substitute if `font` is missing

[money]                         # P2
currency   = "GBP"              # default "GBP"
source     = "live"             # "live" (default) | "config" — §8.3
rates_date = 2026-09-24         # required whenever [money.rates] is given

[money.rates]                   # 1 unit of each currency = this many GBP
EUR = 0.87                      # €1 = £0.87
USD = 0.74                      # $1 = £0.74

[summary]                       # P2
default = []                    # metrics for every section without its own `summary`

# ---- Sections: listed = included, in this order; unlisted = dropped ----

[[section]]
title = "Education"             # no ids → the whole section

[[section]]
title = "Current Academic Appointments"

[[section]]
title   = "Research Income"
summary = ["count", "total"]
  [[section.group]]
  title = "Awards"              # only this group, in full

[[section]]
title   = "Publications"
summary = ["count"]
ids = [
  "rey2023geographic",
  # …
]

[[section]]
title  = "Invited Lectures"
rename = "Selected Invited Lectures"
  [[section.group]]
  title = "Keynote speeches"
  [[section.group]]
  title = "Seminars"
  ids   = ["seminars-2026-beyond-thesis-helping-your"]
```

### 4.4 Keys

Top level:

| Key | Type | Default | Phase |
|---|---|---|---|
| `name` | string, `^[a-z0-9][a-z0-9-]*$` | file stem | P1 |
| `formats` | array of `"pdf"`, `"docx"`, `"md"` | `["pdf"]` | P1 (`pdf`), P4 (`docx`, `md`) |
| `header` | table | — | P1 (`title`), P5 (rest) |
| `style` | table | full CV's look | P3 |
| `money` | table | `currency = "GBP"`, `source = "live"` | P2 |
| `summary.default` | array of metric names | `[]` | P2 |
| `section` | array of tables | — | P1 |
| `drop` | array of section titles | — | P1 |

Exactly one of `section` / `drop` must be present.

`[[section]]` and `[[section.group]]`:

| Key | Type | Meaning |
|---|---|---|
| `title` | string, required | Source title, matched exactly |
| `rename` | string | Output heading; matching still uses `title` |
| `ids` | non-empty array of strings | Only these items |
| `summary` | array of metric names | §8 (P2) |

**Unknown keys at any level are errors**, as are wrong types. A key belonging to
a later phase than the one implemented is an error saying which phase adds it.

## 5. Selection — one rule, at every level

> **Listed → included. Nothing more specified → included in full. `ids` given →
> only those.**

- **Sections.** `[[section]]` entries are included **in config order**;
  unlisted sections are dropped. `drop = [...]` is the inverse mode: all
  sections in source order except those named.
- **Groups.** In a grouped section, `[[section.group]]` tables restrict to those
  groups, in config order. No group tables → all groups, source order.
- **Items.** No `ids` → all items. `ids` → exactly those, **printed in source
  order** (not list order), so both renderers' "blank a repeated date label"
  logic keeps working. Section-level `ids` on a grouped section may name items
  in any of its groups; groups left empty are dropped.
- Publications keep their renderer-side sort (year descending) regardless.
- `ids = []` is an error ("remove `ids` to include the whole section").
- *(Settled in P1.)* A section with `[[section.group]]` tables takes its `ids`
  under those groups; section-level `ids` alongside group tables is an error,
  since which filter applies to which group would otherwise be ambiguous. An id
  listed twice, or a section/group listed twice, is also an error.

Omitting `ids` means "the whole section *as it is when built*" — a later rebuild
picks up new records. Listing ids freezes the selection. Both are intended.

## 6. Item ids (P0)

### 6.1 Rules

- Every record in both data files has an `id`, unique **across both files**.
- Publications keep their existing CSL `id`s untouched.
- `cv.json` ids match `^[a-z0-9][a-z0-9-]*$`, ≤ 60 characters.
- Ids are **permanent**: never regenerated, never changed when an entry's
  wording changes.
- After migration, `id` is **required** by `cv.schema.json` `$defs/entry`.

### 6.2 `src/assign_ids.py` — generation

Deterministic slug: `<context>-<year>-<keywords>`, each part omitted if empty,
truncated to 60 characters (trailing `-` stripped):

- **context**: first 2 significant words of the group title (grouped sections)
  or section title (flat sections).
- **year**: first 4-digit run in `date`, else in `years`, else omitted.
- **keywords**: first 4 significant words of the type's key field:

  | type | field | | type | field |
  |---|---|---|---|---|
  | education | `degree` | | talks | `title` |
  | positions | `role` | | events | `title` |
  | editorial | `journal` | | courses | `name` |
  | awards | `title` | | people | `name` |
  | grant | `title` | | text-list | `text` |
  | project | `title` | | named | `name` |
  | visits | `institution` | | | |

- **Slugging**: NFKD-normalise, drop non-ASCII, lowercase, non-alphanumerics →
  `-`. "Significant" = not in a small stopword set (`a an the of and in on for
  to at with from by de la el y`).
- **Collisions** (with any existing id in either file): append `-2`, `-3`, …
  in source order.

A prototype of exactly this rule over the current data gives 279 ids, 10
suffixed, max length 60 — e.g. `education-2010-phd-economics`,
`current-academic-2022-professor-geographic-data-science`,
`awards-2025-embedding-embeddings-across-social`,
`seminars-2026-beyond-thesis-helping-your`, `supervisor-2024-yuta-sato`,
`scientific-software-pysal`.

**Writing ids into `cv.json` must preserve its hand formatting.** Do not
`json.dump` the file. Instead:

1. Parse with `json` to compute ids in source order.
2. Locate each entry object's opening `{` in the raw text with a small
   position-tracking scanner (string/escape-aware brace walk, mapping each
   object to its JSON path `sections[i](.groups[k]).entries[j]`).
3. Insert text immediately after that `{`:
   - one-line object (`{` followed by a space): `"id": "<id>", `
   - multi-line object (`{` followed by a newline): a new line
     `<indent>"id": "<id>",` using the indentation of the following line.
4. Skip entries that already have an `id` (idempotent, additive).

Invariant, tested (§14): removing every inserted `"id": "…", ` / id line from
the new text yields the original file **byte-for-byte**, and `json.loads` of
the new text equals the old data plus `id` keys.

### 6.3 Discovery commands (P1)

- `python3 src/build_subset.py --list [SECTION]` — one line per record: id,
  date, short text. Without an argument: everything, section by section.
- `python3 src/build_subset.py --scaffold` — prints to stdout a complete, valid
  config: every section and group in source order, every id listed with its
  one-line description as a trailing TOML comment. Building a subset = deleting
  lines. Deleting a whole `ids` key reverts to "whole section".

`src/subset.template.toml` stays small and static: it documents every key; it
does not list records.

## 7. The build — `src/build_subset.py`

### 7.1 CLI

```
python3 src/build_subset.py CONFIG [--out DIR] [--strict]
python3 src/build_subset.py --list [SECTION]
python3 src/build_subset.py --scaffold [PATH]
make subset CONFIG=~/cv-subsets/erc-2027.toml [OUT=DIR]   # CONFIG --new-if-missing
make subset-list [SECTION="Teaching"]                     # --list
```

*(Settled in P1.)* `make` is the author's interface; the Python CLI is what it
runs. `make subset` builds CONFIG, or, if no file exists there, writes the
`--scaffold` config there and stops (the unedited scaffold is the full CV, so
building it would be pointless); the same command then builds it once edited.
Writing a scaffold to a path refuses to overwrite a file; `--scaffold`
without PATH prints to stdout.

Must be run from within the repo (it reads `src/`). `--strict` turns warnings
into errors.

### 7.2 Pipeline

1. Validate the master data (§12). Collect all errors; stop if any.
2. Validate the config (§12). Collect all errors; stop if any.
3. Resolve the output directory; refuse non-private repo paths (§13).
4. Select (§5) → derived data in `build/.subset-work/` (wiped first).
5. Summarise (§8) — obtaining exchange rates only if a `total` needs them.
6. Validate the derived data against `cv.schema.json`.
7. Resolve style (§9), including the font check.
8. Render each format (§11).
9. Copy artifacts to the output dir; write `config.toml` (verbatim copy of the
   config) and `manifest.json`.

### 7.3 Outputs

```
<out>/
  darribas-cv-<name>.pdf
  darribas-cv-<name>.docx       # if requested
  darribas-cv-<name>.md         # if requested
  cv.json, publications.json    # the derived data (debugging surface)
  config.toml                   # snapshot of the config used
  manifest.json
```

The `darribas` prefix comes from slugging the family name in `basics.name`.

`manifest.json`: data commit (`git rev-parse HEAD`) and `dirty` flag, build
timestamp, config path, formats, page count of the PDF, item counts per section
(kept / total), exchange rates used with their date and source (§8.3) in a form
pasteable into `[money.rates]`, resolved font family and file, warnings raised.

### 7.4 Derived-data contract

The derived `cv.json`:

- validates against `cv.schema.json` (with P2's `summary` addition);
- keeps retained entries verbatim, `id` included;
- has `basics.title` replaced if `header.title` is set;
- has sections/groups `title` replaced by `rename` where given;
- has the publications section's `source` rewritten to the derived publications
  file **relative to `src/`**: `"../build/.subset-work/publications.json"`.

### 7.5 Renderer changes (generic only)

**`src/cv.typ` (P1):**

```typ
#let cv = json(sys.inputs.at("data", default: "cv.json"))
```

Compiled by the build as:

```
typst compile --root . --font-path fonts \
  --input data=../build/.subset-work/cv.json [style inputs, §9] \
  src/cv.typ build/.subset-work/cv.pdf
```

**`src/render_html.py` (P1):** accept `--data PATH` and `--out DIR`, defaulting
to today's `src/cv.json` and `docs/`. Needed for the identity test (§14.2), not
as a subset format.

With no inputs/arguments both behave exactly as today.

## 8. Section summaries and money (P2)

### 8.1 Mechanism

*The output format in §8.1–8.2 is the original brief; what was built is
settled at the end of §8.3 (beside the heading, no nouns, kept figures only).*

`cv.schema.json` gains `"summary": {"type": "array", "items": {"type":
"string"}}` on `$defs/section` and `$defs/group`. The build writes
pre-formatted strings there. Each renderer prints them as one line directly
under the heading: italic, ~0.9× body size, parts joined by ` · `. No other
renderer logic. `src/cv.json` never sets `summary` (but see "Full CV" below).

A section whose `total` was converted also gets a final note line — appended by
the build as the last `summary` element, rendered the same way:
*"Converted to GBP at ECB reference rates of 24 September 2026."*

### 8.2 Metrics

Shown as subset **and** full, side by side, when they differ; just the number
when nothing was dropped.

| Metric | Output | Applies to |
|---|---|---|
| `count` | `12 of 112 publications` / `112 publications` | any section or group |
| `total` | `≈ £1.3M of ≈ £4.4M total award value` | entries of type `grant` only |

Noun for `count`: the section's own title, lowercased, for publications
("publications"), else "items" unless a per-type noun is defined (`grant` →
"awards", `talks` → "talks", `people` → "people", `courses` → "courses").
Warn (not fail) if `count` is set on a section of type `text-list` or `named`.

`total` rules:

1. Convert every structured `amount` in scope to `money.currency` and sum.
2. Prefix `≈` whenever any conversion happened; add the note line (§8.1).
3. Label as *total award value* — `amount` is the whole award across partners,
   not the author's share. Never "income".
4. Only `grant` entries count; `project` entries (free-text `funding`) never do.
   If some in-scope `grant` entries lack `amount`, append
   `(N awards without a recorded amount)`.
5. Format: `£1.3M` for ≥ 1,000,000 (one decimal), `£54,761` below; symbols from
   the renderers' existing currency map (GBP £, EUR €, USD $).

### 8.3 Exchange rates

A subset's rates are never committed to the repo (the full CV's are: see
below). Two sources:

- **Live** — ECB daily reference rates,
  `https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml`, via
  `urllib.request` + `xml.etree`, 10 s timeout. EUR-based; cross rates via EUR.
- **Config** — `[money.rates]`: value = units of `money.currency` per 1 unit of
  that currency. `rates_date` (TOML date) required when rates are given.

| `source` | ECB reachable | ECB unreachable |
|---|---|---|
| `"live"`, no `[money.rates]` | live | **error**, suggesting `[money.rates]` |
| `"live"`, with `[money.rates]` | live (config rates ignored) | config rates + **warning** |
| `"config"` | config rates, **no network request** | config rates |

Validation: keys are 3-letter uppercase codes; values positive numbers; the
target currency is not listed; every currency occurring in in-scope amounts has
a rate (missing → error naming it). Warn if `rates_date` is > 90 days before the
build date. Note wording: "ECB reference rates of <date>" for live,
"exchange rates of <rates_date>" for config.

Rates are **today's** (or the configured date's); award-year rates are a
tracked follow-up in `TODO.md`, not part of this spec.

Network access is only ever attempted when a `total` needs a conversion and
`source = "live"`. Tests never hit the network (§14).

*Settled in P2, with the author — supersedes the format in §8.1–8.2
("parsimony is king"):* the summary prints in parentheses after the heading's
title, not on a line below it, parts joined by `; `:
`Research Income (7 of 28; ≈ £11.1M, £7.5M as PI)`.

- `count` has no noun: `7 of 28`, or `28` for a whole section when asked for
  explicitly; a `count` that comes from `summary.default` is omitted for a
  section or group kept whole.
- `total` shows only the figures for the records kept (the count already
  says it is a selection; the full CV carries the complete figures) and no
  label: `≈ £11.1M`, then `, £7.5M as PI` — the part from awards whose
  `role` is "PI", omitted if none is — then `, N award(s) without an amount`
  if any. One `≈` leads the money when anything was converted; the
  conversion note goes in its own `summary_note` string, printed as a
  footnote (a tooltip in HTML). A total with no awards kept is omitted.
- `summary.default` applies to sections only, and a `total` that comes from
  it silently skips sections without `grant` entries (an explicit one is an
  error); rates are needed only for the currencies of the awards kept; cross
  rates are kept to six significant figures, the same figures the manifest
  records.

### 8.4 Full CV (added after P2, at the author's request)

The full CV carries heading summaries too. `src/summaries.json` names the
sections and their metrics (today: Research Income → `total`) and holds dated
exchange rates (`rates_date`, `rates_source`, `rates`); `src/build_site_data.py`
writes `build/site/cv.json` — `src/cv.json` plus the summary strings — and
`make site` / `make preview` render that. The site build never fetches: its
rates are tracked, refreshed on demand with `make rates` (ECB). Rates 90+ days
old warn; a missing currency fails the build. `make watch` still renders
`src/cv.json` directly, without summaries.

## 9. Style (P3)

| Key | Type | Default (= full CV) | Typst input |
|---|---|---|---|
| `font` | string | `"TeX Gyre Pagella"` | `font` |
| `size` | number, pt, 8–14 | `12.5` | `size` |
| `paper` | `"a4"` \| `"us-letter"` | `"us-letter"` | `paper` |
| `margins` | number, mm, 10–40 | `25.4` | `margins` |
| `page_numbers` | bool | `false` | `page-numbers` |
| `fallback` | string | — | (replaces `font` if used) |

`cv.typ` changes:

- Read each input with the current value as default; parse numbers with
  `float(...)` (values validated in Python first, so no free-form lengths).
- Express the currently absolute sizes **relative to the body size** so they
  scale: 14pt → `14/12.5 em`, 13pt → `13/12.5 em`, 15pt → `15/12.5 em`, 9pt →
  `9/12.5 em`. At the default size output must be identical (§14.2).
- `page_numbers = true`: `set page(footer: context align(center,
  text(size: 0.8em, counter(page).display("1 of 1", both: true))))`.

**Font check.** Typst silently substitutes a missing font. Before compiling, run
`typst fonts --font-path fonts` and require `font` in the list; else, if
`fallback` is set and listed, use it with a warning (recorded in the manifest);
else fail. Arial cannot be bundled (proprietary); it is found on macOS/Windows
via system fonts. Liberation Sans is metric-compatible with Arial but the PDF
will name it — hence explicit opt-in only.

**DOCX styles** (P4): write a per-build copy of `src/reference.docx`, patching
`word/styles.xml` (fonts, sizes) and the section properties in
`word/document.xml` (page size, margins; page-number footer if requested) with
stdlib `zipfile`. The committed file is never modified.

## 10. Header overrides (P5 — after the core works)

`[header]` beyond `title`:

| Key | Type | Effect |
|---|---|---|
| `affiliation` | array of strings | Replaces `basics.affiliation` |
| `email` | string or `false` | Replaces, or `false` omits the email |
| `url` | string or `false` | Replaces, or `false` omits the URL |

`name` is not overridable. Omitting email/url requires both renderers to treat
those fields as optional (today `cv.typ` and `render_html.py` assume them), and
the schema to drop them from `basics.required` — a small change, deliberately
kept out of the first pass.

## 11. Formats

- **PDF** (P1): `cv.typ` over derived data (§7.5), style inputs from P3.
- **DOCX** (P4): new `src/render_markdown.py` (same per-type dispatch shape as
  the other renderers; date column becomes a bold lead-in `**2026** — …`;
  summary lines as an italic paragraph; web-only `links` never read), then
  `pandoc cv.md -o cv.docx --reference-doc=<per-build copy>`. The build checks
  for `pandoc` only when `docx` is requested. `md` keeps the intermediate.

## 12. Validation (inside every build)

Move `.claude/skills/add-cv-record/validate_cv.py` to `src/validate_cv.py`
(P0), importable as a module and runnable as a script; leave a thin shim at the
old path (or update the skill's instructions) so the skill keeps working.

Errors (exit 1, all collected and printed together, each naming file, key and
value):

- master data fails the schema; a record lacks an `id`; duplicate ids across
  both files;
- config: unknown key, wrong type, key from an unimplemented phase, both or
  neither of `section`/`drop`, `ids = []`;
- a section/group title that does not exist; an id that matches no record; an
  id listed under a section it does not belong to;
- output path in `docs/`, `src/`, the repo root, the scratch directory, or
  anywhere else in the repo that git does not ignore (§13);
- exchange rates unavailable or incomplete; malformed `[money.rates]`; rates
  without `rates_date` (§8.3);
- requested font unavailable and no usable fallback (§9);
- derived data fails the schema.

Warnings (exit 0; errors under `--strict`): `count` on a `text-list`/`named`
section; `total` with entries lacking `amount`; fallback font used; config rates
used as fallback; config rates older than 90 days.

`make validate` runs `src/validate_cv.py` in addition to today's parse check.

## 13. Never in the repo, never published — guards (P1)

1. **Build refuses non-private repo paths.** *(Revised in P1: the build often
   runs in a container that mounts only the repository, so outputs must be
   able to land inside it.)* The resolved output dir (symlinks resolved) may
   be inside the repository only if `git check-ignore` confirms git ignores
   it — e.g. `subsets/<name>/` — and never in `docs/` (the public site),
   `src/`, the repo root or `build/.subset-work/`, ignored or not. If git
   cannot confirm, the build refuses.
2. **`.gitignore`**: add `subsets/` and `*.toml` with `!src/subset.template.toml`.
3. **CI tripwire** (new step in `build-site.yml`, before building): fail if
   `git ls-files` lists any `*.toml` other than `src/subset.template.toml`, or
   anything under `build/` or `subsets/`.
4. **CI never runs `build_subset.py`**, and `make site` never calls it.

*(Changed in P1, at the author's request.)* Configs may live inside the repo,
normally in `subsets/`; `.gitignore` and the CI tripwire keep them untracked,
and guard 1 keeps their outputs private.

Agents working on this repo never create configs inside it and never stage
subset files.

## 14. Tests

### 14.1 Infrastructure (P0 creates it)

- `tests/` with stdlib `unittest` modules: `tests/test_*.py`.
- `make test` → `python3 -m unittest discover -s tests -v`.
- CI: a `make test` step in `build-site.yml` after Typst is installed.
- Tests needing Typst use `@unittest.skipUnless(shutil.which("typst"), …)`;
  DOCX tests likewise for `pandoc` (CI runs the Typst ones; pandoc ones may
  skip in CI unless pandoc is added there in P4).
- **Configs are generated inside each test** into a `tempfile.TemporaryDirectory()`
  — no TOML fixtures are tracked, which also exercises "config and outputs
  outside the repo".
- **No network**: the ECB fetch is a single function, patched in tests
  (`unittest.mock`) to return canned XML or raise.

### 14.2 The identity test (the key regression guard)

Comparing against the committed `docs/cv.pdf` cannot work: the PDF embeds its
creation time, prints its build date, and CI uses the latest Typst. Instead,
**within one test run**:

1. Set a fixed timestamp: `SOURCE_DATE_EPOCH=1767225600` and pass
   `--creation-timestamp 1767225600` to Typst.
2. Build A: `typst compile` of `src/cv.typ` with no inputs.
3. Build B: the subset build of a config listing all 17 sections, no ids, no
   style, no summary.
4. Assert A and B are byte-identical. **Verify** that the fixed timestamp also
   pins `datetime.today()` in the document; if the installed Typst does not,
   compare the PDFs' extracted text with the final date line removed instead
   (and note it in the test).
5. Same for HTML: `render_html.py` bare vs `--data` on B's derived data, into
   temp dirs; byte-identical within one run.

### 14.3 Tests per phase

| Phase | Tests |
|---|---|
| P0 | id invariant (§6.2: stripping ids restores the original bytes; parsed data equals old + ids); every entry has an id; ids unique across files; `assign_ids.py` idempotent (second run = no change); slug rule on sample entries; `make site` output unchanged |
| P1 | identity (§14.2); `--scaffold` output parses and builds to the same result as identity; selection rule cases (section/group/ids, config order, source-order printing, `drop`); every §12 config error; output-path guard (`--out docs/x`, `--out src/` fail); a default build from a temp-dir config leaves `git status --porcelain` unchanged |
| P2 | `count` both forms; `total` single-currency (no ≈, no note) and multi-currency; partial-coverage suffix; rates table (all 6 cells, with patched fetch); `source = "config"` makes no fetch call; stale-rates warning; missing-currency error |
| P3 | defaults unchanged (identity still passes); A4 page size in output; page numbers present; unavailable font fails; fallback warns |
| P4 | Markdown renderer covers every entry type; DOCX builds when pandoc present; patched reference docx has requested font/size/paper |
| P5 | affiliation replaced; email/url omitted in PDF and DOCX |

## 15. Phases

Implement in order; one branch and one PR per phase; each must leave `make site`
output unchanged (bar P0's `CoI` fix) and `make test` green.

**P0 — ids, validator, tests scaffold.**
`src/assign_ids.py`; ids inserted into `src/cv.json` (text-preserving, §6.2);
`cv.schema.json`: `id` property (pattern) then `required`; `src/validate_cv.py`
(moved, + cross-file uniqueness, + required id) with a shim at the old path;
`CoI` normalisation (`Co-I` → `CoI`); `add-cv-record` skill: new records get an
id (run `assign_ids.py` after appending, then validate); `tests/` + `make test`
+ CI step; `make validate` runs the validator.
*Done when:* §14.3 P0 tests pass; the P0 diff to `cv.json` is only added ids
and the one `CoI` fix.

**P1 — config, selection, PDF.**
`src/build_subset.py` (config parsing/validation, selection, derived data,
PDF render, snapshot + manifest, `--list`, `--scaffold`, `--out`, `--strict`);
`src/subset.template.toml`; `cv.typ` `data` input; `render_html.py`
`--data/--out`; `make subset`; §13 guards.
*Done when:* identity and P1 tests pass; the author can build a real subset
from a config outside the repo.

**P2 — summaries and money.** Schema `summary`; the summary beside the
heading in `cv.typ` and `render_html.py` (§8.3 "Settled"); metrics; exchange
rates; then, at the author's request, the full CV's summaries (§8.4).

**P3 — style.** `[style]` keys, relative heading sizes, page numbers, font check.

**P4 — DOCX.** `render_markdown.py`, `src/reference.docx`, per-build patching,
pandoc wiring.

**P5 — header overrides.** §10.

After each phase: update `LOG.md` (what was done), trim `TODO.md`, and keep
`ARCHITECTURE.md` Decision 5 accurate if a decision changed.

## 16. Files touched

| File | P0 | P1 | P2 | P3 | P4 | P5 |
|---|---|---|---|---|---|---|
| `src/cv.json` | ids, CoI | | | | | |
| `src/cv.schema.json` | `id` | | `summary`, `summary_note` | | | basics.required |
| `src/assign_ids.py` | new | | | | | |
| `src/validate_cv.py` | moved | | | | | |
| `.claude/skills/add-cv-record/*` | ids, shim | | | | | |
| `src/build_subset.py` | | new | ✓ | ✓ | ✓ | ✓ |
| `src/subset.template.toml` | | new | ✓ | ✓ | ✓ | ✓ |
| `src/build_site_data.py`, `src/summaries.json` | | | new (§8.4) | | | |
| `src/cv.typ` | | `data` | summary | style | | optional contact |
| `src/render_html.py`, `src/style.css` | | args | summary | | | optional contact |
| `src/render_markdown.py`, `src/reference.docx` | | | | | new | ✓ |
| `Makefile` | `test`, validate | `subset` | site data, `rates` | | | |
| `.github/workflows/build-site.yml` | test step | tripwire | | | (pandoc?) | |
| `.gitignore` | | toml rules | | | | |
| `tests/` | new | ✓ | ✓ | ✓ | ✓ | ✓ |

## 17. Acceptance (feature complete)

1. `make site` output identical to before the feature (identity test), bar
   the full-CV summaries added deliberately in P2 (§8.4).
2. `make test` green locally and in CI.
3. A real config outside the repo builds PDF and DOCX, A4/Arial/11pt/page
   numbers, with count and converted-total summaries, into the config's
   directory, with snapshot and manifest; `git status` stays clean.
4. The same config with the network blocked and `[money.rates]` given builds
   with a warning; without rates it fails naming the currency.
5. Rebuilding from the snapshot at the manifest's commit with
   `source = "config"` and the manifest's rates gives identical derived JSON.

## 18. Non-goals

- Rewriting or abbreviating entry content.
- Page-count fitting or page-limit enforcement (the manifest reports the count).
- Formats beyond PDF/DOCX; HTML subsets.
- Publishing subsets in any form; CI building subsets.
- Date- or rule-based selection (`since`, `limit`).

## 19. Deferred (not in scope until decided)

- Award-year exchange rates (tracked in `TODO.md`).
- Whether the *Projects* group's free-text `funding` becomes structured
  `amount`, and whether it then counts towards `total`.
- A running header (name on each page).
- A profile-specific header paragraph.
- Style presets.
- A separate monospace font setting for DOIs/codes/URLs.
- A `build-cv-subset` agent skill that drafts a config from a job advert or
  funder guidance (via `--scaffold`), for the author to review and build.
