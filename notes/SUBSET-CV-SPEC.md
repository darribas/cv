# Subset CVs — feature specification

Status: **specified, not built** (revision 2). This is the implementation brief
for the `TODO.md` item "Tooling for building subsets of the CV", written to be
handed to an implementer (human or agent) without further design work. Every
decision below is made; the ones deliberately left open are marked **OPEN**.

Companion reading: `ARCHITECTURE.md` (Decision 2 — data/render split; Decision 5
— this feature's summary entry).

*Revision 2* replaces the tracked JSON "profiles" of revision 1 with a local,
untracked TOML config; reduces selection to one rule (list what you want,
omitted means everything); converts money to one currency at live rates; adds
per-subset typography (font, size, paper, margins); and bakes validation into
every build.

---

## 1. The need

Organisations routinely ask for something shorter than the full CV: a 2-page
version for a funder, a teaching-weighted version for a lectureship. Funders
often also dictate typography ("Arial, 11pt, 2cm margins"). Today that means
hand-editing a copy, which forks the content and rots.

The workflow:

1. Write a **config file** saying which sections to include, and, where only
   part of a section is wanted, which items.
2. Retained sections may carry standard summary lines at their top (number of
   papers, total income, …).
3. The config also says how to render: format (PDF, DOCX), font, size, paper,
   margins, currency.
4. One command builds the subset. Keeping the config means it can be rebuilt
   later — but the config is **not** committed to this repo.

## 2. Design in one line

**A subset is a data transform, not a renderer feature.** Config + master data
→ a *derived* `cv.json` + `publications.json` that still validate against
`cv.schema.json` → the existing renderers, unchanged in what they know. The
renderers learn nothing about configs or selection; the only things they gain
are generic knobs (read data from a given path; accept a font/size/paper) and
the ability to print a section's summary line.

```
subsets/erc-2027.toml ─┐
src/cv.json ───────────┼─► build_subset.py ─► build/subsets/erc-2027/
src/publications.json ─┘    (validate → select        cv.json, publications.json  (derived)
                             → summarise → FX)        config.toml, manifest.json  (snapshot)
                                                              │
                                     ┌────────────────────────┴──────────────┐
                                     ▼                                       ▼
                             cv.typ + style → PDF        render_markdown.py → pandoc → DOCX
```

### The one boundary this draws

`src/` holds **facts**; `build/` holds a **rendering-ready projection** of those
facts. The projection may contain derived text (a computed summary line, a
converted currency total) that would never be allowed in `src/`. That is what
lets summaries and currency conversion be computed once, in Python, rather than
re-implemented in Typst and again in each Python renderer.

## 3. What exists today (implementation context)

Verified against the tree at the time of writing:

- `src/cv.json` — `basics` + 17 `sections`. A section is either **flat**
  (`type` + `entries`) or **grouped** (`groups[]`, each with its own `type` +
  `entries`). `Publications` is `type: "publications"` with
  `source: "publications.json"`, its groups keyed by CSL `category`.
- `src/publications.json` — 112 CSL-JSON records, each with a unique `id`.
- 279 `cv.json` entries across 13 entry types. **None has an identifier.**
- `src/cv.typ` (PDF) and `src/render_html.py` (web): independent templates over
  the same data, both with hard-coded input paths. `cv.typ` hard-codes its look:
  TeX Gyre Pagella 12.5pt, **US Letter**, 1in margins, headings at absolute
  14pt/13pt, a 13mm date column.
- `.claude/skills/add-cv-record/validate_cv.py` — stdlib-only schema validator,
  stricter than CI's `make validate` (which only checks the JSON parses).
- The pipeline is stdlib-only Python plus the Typst binary; no pip installs.

### Data realities that shape the spec

| Fact | Consequence |
|---|---|
| Research Income → *Awards*: 22/22 entries carry a structured `amount` — 16 GBP, 5 EUR, 1 USD | Totals need currency conversion (§8.2) |
| Research Income → *Projects*: 0/6 carry `amount`; 5 carry free-text `funding` (`"€2,548,920"`) | Not convertible as-is; excluded from totals and disclosed (§8.2) |
| Grant `amount` is the **total award across partners**, not the author's share | Summary wording must not imply personal income (§8.2) |
| `role` holds both `"CoI"` (11) and `"Co-I"` (1) | Data-hygiene fix in P0 |
| The full CV is set in US Letter | UK/EU funders will want A4 — a style option (§9) |
| *Journal Referee* is one `text-list` entry holding ~50 journals | Item counts are meaningless there; such sections get no summary |

## 4. The config file

### 4.1 Format: TOML, not YAML

The config is **TOML**. It gives everything wanted from YAML — comments,
low noise, easy hand-editing — without the two costs YAML carries here:

- **No dependency.** Python reads TOML with the standard library (`tomllib`,
  Python ≥ 3.11; checked). YAML needs PyYAML, a pip install — the first in the
  pipeline, against its stdlib-only rule.
- **No whitespace or type-coercion footguns** — the reasons `ARCHITECTURE.md`
  Decision 3 already rejected YAML for the data. TOML is explicit about types,
  so `title = "Norway"` stays a string.

`[[section]]` tables preserve order, which is exactly what an ordered section
list needs.

### 4.2 Where it lives, and what "recreate later" means

| Path | Tracked? | What |
|---|---|---|
| `subsets/template.toml` | **yes** | Annotated template documenting every key. Copy it to start |
| `subsets/*.toml` (all others) | no (`.gitignore`) | Your configs, one per use case |
| `build/subsets/<name>/` | no (already ignored) | Outputs **plus a snapshot**: `config.toml` (copied verbatim) and `manifest.json` |

The editable config sits in `subsets/`, not inside `build/`: `build/` is
disposable output, and the only copy of something hand-written should not live
in a directory whose contract is "safe to delete". What `build/` does get is a
**snapshot** of the config used, so every built CV is self-describing. The build
takes any path, so `make subset CONFIG=build/subsets/erc-2027/config.toml`
rebuilds from a snapshot directly.

`manifest.json` records what is needed to reproduce the output: the data's git
commit (`git rev-parse HEAD`, plus a `dirty` flag), the build timestamp, the
exchange rates used and their date, the resolved font file, and item counts per
section.

"Recreate later" therefore has two meanings, and the config serves both:

- **Refresh** — rerun the config on today's data. Sections without an `ids`
  list pick up new records automatically; FX rates are today's.
- **Reproduce exactly** — check out the manifest's commit and pin the
  manifest's rates in the config (§8.2). Same data, same rates, same output.

Because configs are untracked, they exist only where you create them. A cloud
agent session is an ephemeral container: a config written there is gone when it
ends unless copied out.

### 4.3 Worked example

```toml
# subsets/erc-2027.toml — copy of subsets/template.toml, edited
name    = "erc-2027"                 # output dir + file names; defaults to the file stem
title   = "Curriculum Vitae"         # overrides basics.title for this subset
formats = ["pdf", "docx"]

[style]                              # all optional; omitted = the full CV's look
font    = "Arial"
size    = 11                         # pt
paper   = "a4"                       # "a4" | "us-letter"
margins = 20                         # mm, all sides

[money]
currency = "GBP"                     # default "GBP"
# rates = { EUR = 0.84, USD = 0.74 } # pin rates instead of fetching (§8.2)

[summary]
default = []                         # summary metrics applied to every section

# --- Sections: listed = included, in this order. Unlisted = dropped. ---

[[section]]
title = "Education"                  # no ids → the whole section

[[section]]
title = "Current Academic Appointments"

[[section]]
title   = "Research Income"
summary = ["count", "total"]
  [[section.group]]
  title = "Awards"                   # only this group, in full

[[section]]
title   = "Publications"
summary = ["count"]
ids = [
  "rey2023geographic",
  "sato2026city2graph",
  # …
]

[[section]]
title = "Invited Lectures"
rename = "Selected Invited Lectures"
  [[section.group]]
  title = "Keynote speeches"
  [[section.group]]
  title = "Seminars"
  ids = ["seminars-2026-beyond-the-thesis", "seminars-2024-…"]
```

### 4.4 Keys

Top level:

| Key | Type | Default | Meaning |
|---|---|---|---|
| `name` | string | file stem | Output directory and file names |
| `title` | string | `basics.title` | Document heading for this subset |
| `formats` | array | `["pdf"]` | Any of `"pdf"`, `"docx"` (`"md"` to keep the intermediate) |
| `style` | table | full CV's look | §9 |
| `money` | table | `currency = "GBP"` | §8.2 |
| `summary.default` | array | `[]` | Metrics applied to every section without its own `summary` |
| `section` | array of tables | — | Included sections, in render order (§5) |
| `drop` | array of titles | — | Alternative to `section`: everything **except** these, source order |

Per `[[section]]` / `[[section.group]]`:

| Key | Type | Meaning |
|---|---|---|
| `title` | string, required | Source title, matched exactly |
| `rename` | string | Heading in the output; matching still uses `title` |
| `ids` | array of strings | Only these items (§5) |
| `summary` | array | Metrics for this section (§8) |

**Unknown keys are errors.** TOML happily parses `idz = [...]`; silently
ignoring it would produce a CV with a whole section where a selection was meant.

## 5. Selection: one rule, applied at each level

> **Listed → included. Nothing more specified → included in full.
> `ids` given → only those.**

- **Sections.** Sections listed as `[[section]]` are included, **in config
  order** (so a funder's preferred order is expressible). Unlisted sections are
  dropped. `drop = [...]` is the inverse mode for "the full CV minus two
  sections"; giving both `section` and `drop` is an error.
- **Groups.** For a grouped section, `[[section.group]]` tables restrict to
  those groups, in config order. No group tables → all groups.
- **Items.** No `ids` → every item. `ids` → exactly those items, printed in
  **source order** (not list order), so the renderers' "show a repeated date
  once" convention keeps working. On a grouped section, section-level `ids` may
  name items from any of its groups; groups left with no selected item are
  dropped.
- `ids = []` is an error ("remove the key to include the whole section"), not a
  silent empty section.

This one rule removes the evaluation-order question from revision 1 — there is
a single mechanism, so nothing to order — and with it the undated-entries
problem, which only existed because of date predicates.

**Omitting `ids` and listing all of them are not the same thing.** Without
`ids`, a section means "the whole section *as it is when built*": a refresh next
year includes next year's papers. With `ids`, it means "exactly these", frozen.
Pick deliberately.

Rules (`since = 2019`, `limit = 10`, `role = "PI"`) are **dropped from this
revision.** They can return later as shorthand that expands to an id list,
without changing the rule above. The `--scaffold` command (§6.3) is what makes
hand-picking from 391 items practical without them.

## 6. Item identity

### 6.1 Ids for every record, going forward

Every record gets a stable, unique id, **required** by the schema, not optional.

- Publications already have unique CSL `id`s (112/112).
- `cv.json` entries gain `"id"`: `^[a-z0-9][a-z0-9-]*$`, unique across both
  files (so a config `ids` list never needs to say which file it means).
- **Migration (P0):** a one-off `src/assign_ids.py` writes a deterministic slug
  into every existing entry: section-or-group title + start year + the most
  distinguishing field, truncated, `-2`/`-3` on collision —
  `education-2010-phd-economics`, `seminars-2026-beyond-the-thesis`,
  `awards-2025-embed2social`. Idempotent and additive: it never rewrites an
  existing id, never reorders, touches nothing else.
- **Going forward:** the `add-cv-record` skill assigns the id when it adds a
  record (it runs `assign_ids.py` after the append); the validator rejects a
  record without one. Once all 279 entries have ids, the schema flips `id` from
  optional to `required` in the same PR.
- **Permanence.** Editing a record's wording never changes its id — that is why
  ids are written into the data, not derived at build time (a derived slug would
  let a typo fix silently change what a config selects). Rejected alternatives:
  array indices (silently wrong after any insertion) and tags (selection would
  live in the master data, and tuning one subset would mean editing `cv.json`).

Sections and groups are matched by **title**, keeping configs readable; a
renamed section fails the build loudly (§10) rather than vanishing.

### 6.2 Finding ids: `--list`

```
$ python3 src/build_subset.py --list "Invited Lectures"
seminars-2026-beyond-the-thesis   2026  "Beyond the Thesis: Helping your research find…"
seminars-2025-…                   2025  …
```

One line per record: id, date, a short rendering. Without an argument it lists
everything, section by section.

### 6.3 Starting a config: `--scaffold`

```
$ python3 src/build_subset.py --scaffold > subsets/erc-2027.toml
```

Writes a complete, valid config from the **current** data: every section in
source order, every group, and every id listed with its one-line description as
a trailing comment. Building a subset is then *deleting* what you don't want —
easier than typing ids. Deleting a section's whole `ids` key flips it back to
"whole section".

The tracked `subsets/template.toml` stays small and static — it documents keys,
it does not list records, so it never goes stale as the data grows. The
scaffold is the data-aware counterpart.

## 7. The build — `src/build_subset.py`

Stdlib-only Python.

```
python3 src/build_subset.py subsets/erc-2027.toml   # build
python3 src/build_subset.py --list [SECTION]        # find ids
python3 src/build_subset.py --scaffold              # new config on stdout
make subset CONFIG=subsets/erc-2027.toml
```

### 7.1 Pipeline

1. **Validate the master data** (§10) — refuse to build from broken data.
2. **Validate the config** — keys, types, references.
3. **Select** (§5) → derived `cv.json` + `publications.json`.
4. **Summarise** (§8), fetching FX rates if a `total` needs them.
5. **Validate the derived data** against `cv.schema.json`.
6. **Resolve the style** (§9), including the font availability check.
7. **Render** each requested format.
8. **Write** `config.toml` snapshot and `manifest.json`.

Steps 1–2 collect **every** problem before exiting, rather than stopping at the
first, so one run shows the full list.

### 7.2 Outputs

```
build/subsets/erc-2027/
  darribas-cv-erc-2027.pdf
  darribas-cv-erc-2027.docx
  cv.json, publications.json    # derived data — the debugging surface
  config.toml                   # snapshot of the config used
  manifest.json                 # commit, timestamp, FX rates, font, counts
```

Artifact names carry the author and subset name so they are self-describing as
email attachments.

### 7.3 Derived-data contract

The derived `cv.json` must:

- validate against `cv.schema.json` (plus §8.1's `summary` key);
- preserve every retained entry **verbatim** — a subset selects, it never
  rewrites. Wrong wording for an audience is a data fix in `src/`;
- carry the publications section's `source` rewritten to the derived
  publications file **relative to `src/`**
  (`"../build/subsets/erc-2027/publications.json"`), because Typst resolves
  `json()` relative to `cv.typ`.

### 7.4 Renderer changes — generic knobs only

- **`cv.typ`** reads its data path and style from `sys.inputs`:
  `json(sys.inputs.at("data", default: "cv.json"))`, compiled with
  `typst compile --root . --input data=… --input font=… src/cv.typ out.pdf`
  (`--root .` lets Typst read outside `src/`). Every input defaults to today's
  value, so a bare compile is byte-identical to now.
- **`render_html.py`** gains `--data`/`--out`, defaulting to today's paths.
- **`render_markdown.py`** (new, §11) is written against the same contract.

None of them knows what a config, an id list or a summary metric is.

## 8. Section summaries

### 8.1 How they reach the page

The derived data's section and group objects may carry
`"summary": ["12 of 112 publications"]` — **already-formatted strings** computed
by the build. Each renderer gains one generic block: print `summary` as a short
italic lead line under the heading, parts joined by " · ". The full CV never
sets it. `cv.schema.json` gains `summary` (array of strings) on sections and
groups.

The cost, stated plainly: these strings embed formatting (currency symbols,
separators, wording) made outside a renderer — a departure from Decision 2's
"renderers own all formatting", accepted because the alternative is
reimplementing metrics and currency conversion in Typst *and* twice in Python,
and because it lives only in `build/`.

### 8.2 Metrics

Values are shown **subset and full, side by side** whenever they differ
("12 of 112"); when nothing was dropped, just the number ("112 publications").

| Metric | Renders as | Applies to |
|---|---|---|
| `count` | `12 of 112 publications` | any section of countable items |
| `total` | `≈ £1.3M of ≈ £4.4M total award value` | sections/groups of type `grant` |

Both are opt-in per section (`summary = [...]`) or globally via
`summary.default`. That is deliberately the whole vocabulary for now; further
metrics (`span`, `ongoing`) can be added without touching the renderers, since
they only print strings. Sections whose entries are not countable things (the
*Journal Referee* blob) should not be given `count`; the build warns if they
are.

**`total` — money.** Rules, in order:

1. **One currency.** Every structured `amount` is converted to
   `money.currency` (default `GBP`) and summed. The output is a single figure.
2. **Rates fetched at build time, never committed.** Source: the European
   Central Bank's daily reference rates
   (`https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml`) — official,
   free, no API key, published since 1999, parseable with `urllib` +
   `xml.etree`. They are EUR-based; cross rates are derived via EUR. The rates
   and their date go into `manifest.json` (in `build/`), never into `src/`.
3. **No network, no guessing.** If the fetch fails and a conversion is needed,
   the build **fails** and says so, unless `money.rates` pins rates in the
   config. This is a real case, not a theoretical one: the proxy of the cloud
   sandbox this spec was written in refused `ecb.europa.eu` (HTTP 403). Pinned
   rates are also how to reproduce an old build exactly (copy them from its
   manifest). No silent fallback to stale or zero rates.
4. **Say it was converted.** A converted total is prefixed `≈`, and the
   document carries one small note at the end of the section:
   *"Converted to GBP at ECB reference rates of 24 September 2026."* An exact
   single-currency total (no conversion needed) carries neither.
5. **Never imply a personal share.** `amount` is the whole award across all
   partners; the label says *"total award value"*, not "income".
6. **Disclose what can't be counted.** `total` sums only entries with a
   structured `amount` and only groups of type `grant` — so the *Projects*
   group (free-text `funding`, and awards where the author was a researcher
   rather than an investigator) is not folded in. If entries in scope lack an
   `amount`, the line says so: `(3 awards without a recorded amount)`.

Converting a 2012 award at 2026 rates is a presentational choice, not a
historical valuation — see **OPEN** in §14.

## 9. Styles (typography per subset)

Funders set typography; the full CV's look is only one option.

```toml
[style]
font    = "Arial"        # family name
size    = 11             # body size, pt
paper   = "a4"           # "a4" | "us-letter"
margins = 20             # mm
```

Every key is optional; an omitted key keeps the full CV's value (Pagella,
12.5pt, US Letter, 1in ≈ 25.4mm). Units are fixed (pt, mm) and values are plain
numbers, validated in Python before reaching Typst — no string-to-length parsing
in the renderer.

**PDF.** `cv.typ` reads `font`, `size`, `paper`, `margins` from `sys.inputs`,
defaulting to today's values. One renderer refactor comes with it: the heading
sizes (14pt/13pt) and the header's 15pt/9pt become **relative to the body size**
(`em`), so an 11pt body gets proportionally smaller headings instead of
oversized ones. At the default size the result must be identical (§12).

**Fonts must actually exist — checked, not assumed.** Typst, asked for a font it
cannot find, substitutes a fallback and only warns. For a funder that demands
Arial, a PDF silently set in something else is a failed application. So the
build runs `typst fonts --font-path fonts`, and fails if the requested family is
not listed.

Arial specifically: it is proprietary, so it cannot be bundled in this public
repo. It is found on macOS/Windows via system fonts. Where it is missing (Linux,
CI, cloud sessions), `style.fallback = "Liberation Sans"` may be set explicitly:
Liberation Sans (OFL) is **metric-compatible** with Arial — identical widths,
identical page breaks — but the PDF will name the font Liberation Sans, which a
strict automated check could flag. The substitution is therefore never implicit,
and is recorded in `manifest.json`.

**DOCX.** Font, size, paper and margins are written into a **per-build copy** of
`src/reference.docx` (pandoc's style carrier) by patching its `styles.xml`
(fonts, sizes) and section properties (page size, margins) with stdlib
`zipfile`. The committed reference file is never modified.

## 10. Validation, baked into every build

A subset CV is sent to people who decide things. The build refuses to produce a
plausible-looking document with something quietly missing.

**The validator moves to `src/validate_cv.py`**, shared by the build and the
`add-cv-record` skill (whose `validate_cv.py` becomes a one-line shim, or the
skill's instructions point at the new path). One validator, two callers.

The build exits non-zero, naming file, key and value, on:

- master data that fails `cv.schema.json`, a record without an id, or a
  duplicate id across both files;
- an unknown config key, or a value of the wrong type;
- a `section`/`group` title that does not exist;
- an id that matches no record, or matches one outside the section it is listed
  under;
- `ids = []`; both `section` and `drop`; neither;
- a requested font that is not available (§9);
- a `total` needing conversion with no reachable rates and none pinned (§8.2);
- derived data that fails the schema.

Warnings: a `count` on an uncountable section; a `total` with partial coverage;
`fallback` font used.

Because configs are untracked, CI cannot check them against data changes: if a
record a config names is later deleted, the next build of that config fails
(loudly, with the id). That is the trade-off of keeping configs out of the repo,
and the loud failure is what makes it acceptable.

## 11. Formats

- **PDF** — `cv.typ` over the derived data, with `sys.inputs` style (§7.4, §9).
- **DOCX** — a third renderer, `src/render_markdown.py`, emits Markdown from the
  derived data; `pandoc cv.md -o cv.docx --reference-doc=<per-build copy>`. This
  is the route `ARCHITECTURE.md` already nominated. The date column becomes a
  bold lead-in (`**2026** — …`), since Markdown has no two-column row.
  - pandoc is a dependency **only** for DOCX: `make site` and PDF subsets must
    keep working without it; the build checks for it only when `docx` is
    requested.
  - Web-only `links` stay out by the same omission mechanism the PDF uses — the
    Markdown renderer never names the field.

**No publishing.** Subsets never land in `docs/`, and CI never builds them:
configs are not in the repo, so there is nothing for CI to build from. (Revision
1's `publish` flag is withdrawn — see **OPEN** in §14.)

## 12. Acceptance criteria

1. **Identity.** A config listing all 17 sections in source order, with no
   `ids`, no `style` and no `summary`, produces PDF and HTML identical to
   `docs/cv.pdf` / `docs/index.html` (modulo the trailing date stamp). The proof
   that the transform is transparent, and the regression guard for every later
   change.
2. **Scaffold round-trip.** `--scaffold` output, built unmodified, gives the
   same result as (1) — every id listed selects exactly every item.
3. **Renderer inertia.** `make site` output is unchanged by the whole feature;
   bare `typst compile src/cv.typ` and `render_html.py` still work.
4. **Loud failure.** Every §10 condition exits non-zero with a message naming
   file, key and value.
5. **Reproducibility.** Rebuilding from a `build/…/config.toml` snapshot, at the
   manifest's commit, with the manifest's rates pinned, gives identical derived
   JSON.
6. **Style.** An `Arial, 11, a4, 20` build produces an A4 PDF whose embedded
   text fonts are Arial (checked with the PDF's font list; the monospace face
   used for DOIs and grant codes is separate — see §14), or fails if Arial is
   unavailable and no fallback is set.
7. **Template.** `subsets/template.toml` builds as-is.

## 13. Phasing

| Phase | Content | Ships |
|---|---|---|
| **P0** | `id` on every `cv.json` entry via `src/assign_ids.py`, then required by the schema; uniqueness across both files; validator moved to `src/validate_cv.py`; `add-cv-record` assigns ids going forward; `Co-I` → `CoI` | Data + validator; no output change |
| **P1** | `build_subset.py` (validate → select → render PDF → snapshot), `--list`, `--scaffold`, `subsets/template.toml`, `.gitignore` rule, `cv.typ` data input, `make subset`, identity + scaffold tests | PDF subsets |
| **P2** | `summary` in schema + renderer lead line; `count`, `total`; ECB fetch, pinned rates, manifest | Summary lines, one-currency totals |
| **P3** | `[style]`: `cv.typ` style inputs + relative heading sizes; font check; `fallback` | Funder typography |
| **P4** | `render_markdown.py`, `src/reference.docx`, per-build style patching, pandoc | DOCX |

Each phase is shippable on its own; P1 is already useful.

## 14. Open questions

- **OPEN — FX basis.** Revision 2 converts at *today's* rates, as asked. The
  alternative is the rate in each award's year: arguably truer to what the award
  was worth, and available from the same source (the ECB's historical series,
  `eurofxref-hist.xml`, back to 1999). Could be `money.basis = "current" |
  "award-year"` later. Neither is inflation-adjusted.
- **OPEN — the Projects group's money.** Its five free-text `funding` values
  could become structured `amount`s (a one-off data fix). Whether they then
  belong in a "total award value" — they are projects the author worked on, not
  awards they held — is an editorial call, which is why `total` is limited to
  `grant` groups meanwhile.
- **OPEN — publishing a subset.** If a subset is ever wanted at a public URL, it
  needs a *tracked* config (e.g. `subsets/public/*.toml`, un-ignored) and a CI
  step. Deferred until one is wanted.
- **OPEN — header paragraph.** Shorter CVs often open with a short statement. It
  would be the first prose living in a config rather than in `src/`, against the
  "a subset never rewrites" rule.
- **OPEN — style presets.** If the same funder rules recur,
  `style.preset = "…"` naming a tracked preset file saves retyping. Only once a
  preset has been needed twice.
- **OPEN — the monospace face.** DOIs, grant codes and URLs are set in a
  monospace font (`raw()` in `cv.typ`). A funder's "Arial only" rule may or may
  not tolerate that; `style.mono` (or setting them in the body font) is a small
  addition if one objects.
- **OPEN — rules as shorthand.** `since`/`limit` could come back as sugar that
  expands to an id list at build time, without changing §5's rule.

## 15. Non-goals

- **No content rewriting.** A subset selects; it never edits an entry.
- **No page-count optimisation.** The build does not iterate to fit 2 pages;
  `manifest.json` reports the page count so the author can adjust.
- **No formats beyond PDF/DOCX** here. Browser-side export stays its own item.

## 16. Natural follow-on

Once P1 lands, a `build-cv-subset` agent skill could **draft a config from a
job advert or funder guidance** ("2 pages, Arial 11pt, publications from the
last five years"), running `--scaffold` and deleting what does not fit, then
show the TOML for approval and build it. The config stays the reviewable
artifact — the agent proposes, the author reads, the build is deterministic.
