# Subset CVs — feature specification

Status: **specified, not built.** This document is the implementation brief for
the `TODO.md` item "Tooling for building subsets of the CV". It is written to be
handed to an implementer (human or agent) without further design work: every
decision below is made, and the ones deliberately left open are marked
**OPEN**.

Companion reading: `ARCHITECTURE.md` (Decision 2 — data/render split; Decision 5
— this feature's summary entry).

---

## 1. The need

Organisations routinely ask for something shorter than the full CV: a 2-page
version for a funder, a teaching-weighted version for a lectureship, a version
with no code/data links for a formal panel. Today that means hand-editing a
copy, which forks the content and rots.

The workflow to support, in the author's words:

1. Set which sections to retain or drop.
2. For each retained section, specify which items to include.
3. Each retained section may carry a few standard summary items at its top
   (number of papers, total income, …).
4. Build the result in the desired format (PDF or DOCX to begin with).

## 2. Design in one line

**A subset is a data transform, not a renderer feature.** A *profile* (JSON)
plus the master data produces a *derived* `cv.json` + `publications.json` that
still validate against `cv.schema.json`; the existing renderers then run over
the derived data unchanged. `ARCHITECTURE.md` already nominates this route —
"Subset CVs ← filter the data before rendering" — and it is what keeps three
renderers (Typst/HTML/Markdown) from each growing their own filtering logic.

```
profiles/teaching.json ─┐
src/cv.json ────────────┼─► build_subset.py ─► build/subsets/teaching/cv.json
src/publications.json ──┘                       build/subsets/teaching/publications.json
                                                         │
                          ┌──────────────────────────────┼───────────────────┐
                          ▼                              ▼                   ▼
                     cv.typ (PDF)            render_markdown.py → pandoc   render_html.py
                                                        (DOCX)              (optional)
```

### The one line this feature draws

`src/` holds **facts**; `build/` holds a **rendering-ready projection** of those
facts. The projection may contain derived text (a computed summary line) that
would never be allowed in `src/`. This is what lets summaries be computed once,
in Python, instead of three times (Typst cannot import the Python helpers, and
duplicating currency/thousands formatting into a third renderer is exactly the
"fiddly scripts, plural" the architecture avoids).

## 3. What exists today (implementation context)

Verified against the tree at the time of writing:

- `src/cv.json` — `basics` + 17 `sections`. A section is either **flat**
  (`type` + `entries`) or **grouped** (`groups[]`, each with its own `type` +
  `entries`). One section (`Publications`) is `type: "publications"` with
  `source: "publications.json"` and groups keyed by `category`.
- `src/publications.json` — 112 CSL-JSON records, each with a unique `id` and a
  `category` in {`journal-article` 71, `other-article` 16, `other` 9,
  `book-chapter` 7, `conference` 5, `working-paper` 3, `book` 1}; 89 carry a
  `links` array.
- 279 `cv.json` entries across 13 entry types. **None has an identifier.**
- `src/cv.typ` (PDF) and `src/render_html.py` (web) are independent templates
  over the same data. Both hard-code their input paths.
- `.claude/skills/add-cv-record/validate_cv.py` is a stdlib-only schema
  validator, stricter than CI's `make validate` (which only parses).
- CI (`build-site.yml`) installs the Typst binary, runs `make validate`, then
  `make site`, and commits `docs/` on pushes to `main`.

### Data realities that shape the spec

| Fact | Consequence |
|---|---|
| `date` shapes are `YYYY` (188), `YYYY-YYYY` (26), `YYYY-YY` (22), `YYYY-` open (21), absent (20), one `YYYY/YY`, one `""` | A single date-parsing rule covers everything (§6.3); undated entries need an explicit policy |
| `courses` entries have no `date`, they have free-text `years` | Date resolution must fall back per type |
| `named` entries (software, languages) have neither | They are order-based only; date predicates cannot apply |
| Research Income → *Awards*: 22/22 entries carry a structured `amount` (16 GBP, 5 EUR, 1 USD) | Totals are computable — but **never across currencies** (§7.3) |
| Research Income → *Projects*: 0/6 carry `amount`; 5 carry free-text `funding` (e.g. `"€2,548,920"`) | That group cannot be totalled; the metric must disclose coverage, not silently undercount |
| `role` values include both `"CoI"` (11) and `"Co-I"` (1) | A `where: {role: ["CoI"]}` predicate silently misses one. **Data-hygiene fix is a P0 prerequisite** |
| Grant `amount` is the **total award**, not the author's share | Summary wording must say so (§7.3) |
| *Journal Referee* is one `text-list` entry holding ~50 journals with counts | One entry ≠ one item; item-count metrics would report "1". Sections like this opt out of summaries |

## 4. Profile format

One JSON file per use case, in `profiles/`, validated by
`src/subset.schema.json` (new). Worked example:

```json
{
  "$schema": "../src/subset.schema.json",
  "id": "teaching",
  "label": "Teaching-weighted CV",
  "//": "For teaching-track applications. Target: 4 pages.",
  "publish": false,
  "basics": { "title": "Curriculum Vitae — Teaching" },
  "defaults": { "summary": "auto" },
  "sections": [
    { "section": "Education" },
    { "section": "Current Academic Appointments" },
    { "section": "Prior Academic Appointments", "limit": 4 },

    { "section": "Teaching" },

    { "section": "Publications",
      "summary": ["count", "span"],
      "groups": [
        { "group": "Books" },
        { "group": "Peer-reviewed journal articles",
          "since": 2018, "limit": 10,
          "include": ["rey2023geographic"],
          "and-more": true }
      ] },

    { "section": "Invited Lectures", "rename": "Selected Invited Lectures",
      "groups": [
        { "group": "Keynote speeches" },
        { "group": "Seminars", "limit": 5, "and-more": true }
      ] },

    { "section": "Research Income",
      "summary": ["count", "total-amount"],
      "groups": [ { "group": "Awards", "where": { "role": ["PI"] },
                    "since": 2015 } ] },

    { "section": "Scientific Software" }
  ]
}
```

### 4.1 Top-level keys

| Key | Type | Meaning |
|---|---|---|
| `id` | string, required | Slug; names the output directory and files. Must match the filename stem |
| `label` | string, required | Human title for listings/logs. Not printed |
| `publish` | bool, default `false` | `true` ⇒ CI builds it into `docs/subsets/<id>/` (§9) |
| `basics` | object | Shallow override of `cv.json`'s `basics` (typically just `title`) |
| `defaults` | object | Defaults applied to every section entry (`summary`, `sort`, `and-more`) |
| `sections` | array, required | **Ordered allowlist.** Array order is render order |
| `drop` | array of strings | Mutually exclusive with `sections`: keep everything *except* these, in source order |
| `//`, `//*` | any | Comments, per the repo's JSON-comment convention |

`sections` and `drop` are the two forms of "retain or drop". Exactly one must be
present; supplying both is an error. `drop` exists for the common "the full CV
minus two sections" case, where restating 15 section titles is pure noise.

### 4.2 Per-section / per-group keys

Applied to a section (flat) or to each named group. A section that is grouped in
the source may either list `groups` (ordered allowlist, same semantics) or omit
it (all groups, source order).

| Key | Type | Meaning |
|---|---|---|
| `section` / `group` | string, required | The source `title`, matched exactly. Unknown ⇒ build error (§8) |
| `rename` | string | Heading text in the output; does not change matching |
| `include` | array of ids | Items to keep **regardless of predicates** (rescue list) |
| `exclude` | array of ids | Items to drop, applied last; always wins |
| `since` / `until` | integer year | Keep items whose resolved year is ≥ / ≤ this |
| `where` | object | Field ⇒ list of accepted values, ANDed across fields, ORed within one (`{"role": ["PI","CoI"]}`) |
| `limit` | integer | Keep at most N, after `sort` |
| `sort` | `"recent"` (default) / `"source"` | Ordering used by `limit`; output order is always re-normalised to the renderer's convention (§6.4) |
| `and-more` | bool, default `false` | Append an elision line when items were dropped (§7.4) |
| `summary` | `"auto"` / `false` / array of metric names | §7 |
| `allow-empty` | bool, default `false` | Permit a retained section to render with zero items |

### 4.3 Selection semantics (fixed evaluation order)

1. Start from the section/group's entries in source order.
2. Apply `where`, then `since`/`until` → *predicate set*.
3. Sort by `sort`, apply `limit` → *kept set*.
4. Union with the items named in `include` (rescue: an item on this list is kept
   even if steps 2–3 dropped it, and does **not** count against `limit`).
5. Subtract the items named in `exclude`.

This reads exactly as intended in prose: *"the last five years, plus these two
classics, minus that one"*. An `include` list on its own (no predicates) is the
pure hand-picked case; predicates on their own are the pure rule case.

## 5. Item identity

**Decision: stable ids in the data, referenced from the profile.**

- Publications already have unique `id`s (verified: 112/112 unique) — usable
  today.
- `cv.schema.json`'s `$defs/entry` gains an optional `"id"`: string,
  `^[a-z0-9][a-z0-9-]*$`, **unique across `cv.json`**, checked by
  `validate_cv.py`.
- Ids are generated once by a new `src/assign_ids.py`: a deterministic slug from
  the section (or group) title, the resolved start year, and the entry's most
  distinguishing field (`degree` / `role` / `name` / `title` / first words of
  `text`), truncated, with `-2`, `-3` … for collisions. Examples:
  `education-2010-phd-economics`, `seminars-2026-beyond-the-thesis`,
  `awards-2025-embed2social`.
- The script is **idempotent and additive**: it never rewrites an id that
  already exists, and never reorders or otherwise touches the data. Running it
  after adding records fills in only the new ones.
- Once assigned, an id is permanent. Editing an entry's wording must not change
  its id — that is the whole point of writing ids into the file rather than
  deriving them at build time.

Rejected: addressing by array index (silently wrong after any insertion);
deriving slugs at build time (any wording fix would silently change what a
profile selects); tags-only (see below).

**Tags are a deliberate later addition, not part of P1.** An optional
`"tags": ["flagship", "policy"]` on an entry lets several profiles share one
editorial grouping, and `where: {"tags": ["flagship"]}` would pick it up with no
new machinery. Specified here so the schema change is designed once; not built
until a second profile actually wants the same hand-picked set.

Sections and groups are referenced by **exact title**, not id: profiles stay
readable, and §8's validation turns a renamed section into a loud failure rather
than a silent omission. A section-level `id` can be added later if titles start
churning.

## 6. The build step — `src/build_subset.py`

Stdlib-only Python, consistent with the rest of the pipeline.

```
python3 src/build_subset.py profiles/teaching.json \
        [--format pdf docx html] [--out build/subsets] [--strict]
```

### 6.1 Outputs

```
build/subsets/teaching/
  cv.json              # derived, schema-valid
  publications.json    # derived, only the retained records
  cv.md                # when docx/md requested
  darribas-cv-teaching.pdf
  darribas-cv-teaching.docx
```

Artifact filenames carry the author slug and profile id so the file is
self-describing once it is an email attachment. The derived JSON is always
written — it is the debugging surface when a profile does not do what was meant,
and it is what the acceptance tests compare.

### 6.2 Derived-data contract

The derived `cv.json` must:

- validate against `cv.schema.json` (plus the `summary` addition of §7.1);
- preserve every retained entry **verbatim** — a subset never rewrites content.
  If wording is wrong for a given audience, that is a data fix in `src/`, not a
  profile feature;
- carry `"source"` on the publications section rewritten to the derived
  publications file, expressed **relative to `src/`** (e.g.
  `"../build/subsets/teaching/publications.json"`), because Typst resolves
  `json()` relative to `cv.typ`;
- record provenance in a `"//built"` comment key: profile id, ISO timestamp,
  and the `git rev-parse --short HEAD` of the data it was built from. Comment
  keys are already ignored by every renderer.

### 6.3 Date resolution (one rule, used everywhere)

For a `cv.json` entry: take `date` if present and non-empty, else `years`, else
**undated**. From that string:

| Shape | Start | End |
|---|---|---|
| `YYYY` | YYYY | YYYY |
| `YYYY-YYYY` | first | second |
| `YYYY-YY`, `YYYY/YY` | first | century-completed second (`2015-20` → 2020) |
| `YYYY-` (open) | YYYY | ongoing (sorts as +∞) |
| anything else | first 4-digit run, if any | = start |

For a publication: `issued.date-parts[0][0]`.

**Undated items are never removed by `since`/`until`.** Dropping something
because it lacks a date would be a silent, invisible loss; entries such as
*Scientific Software* or *Language Skills* have no dates by design. They are
removable only by `exclude`, by a `limit` (they sort last under `sort:
"recent"`), or by dropping the section. `--strict` turns "a date predicate met
an undated entry" into a warning listing the entries, so the author can see what
the rule let through.

### 6.4 Output ordering

Selection order and print order are separate. `sort` governs only which items
survive `limit`. What is printed keeps the source array order, so the renderers'
"blank a repeated date label" convention (`with-labels` in both renderers) keeps
working exactly as it does on the full CV. Publications are an exception and
stay as they are: the renderers themselves sort them by year descending.

### 6.5 Renderer changes required

Small, and both are already anticipated by `ARCHITECTURE.md`:

- **`cv.typ`**: read the data path from `sys.inputs` —
  `json(sys.inputs.at("data", default: "cv.json"))` — and compile with
  `typst compile --root . --input data=../build/subsets/teaching/cv.json
  --font-path fonts src/cv.typ <out>.pdf`. `--root .` is required for Typst to
  read outside `src/`. Default behaviour (no `--input`) is byte-identical to
  today.
- **`render_html.py`**: accept `--data` and `--out`, defaulting to the current
  hard-coded paths. Same file, no behavioural change when called bare.

Neither renderer learns anything about profiles, predicates or ids.

## 7. Section summaries

### 7.1 How they reach the page

The derived data's section (and group) objects may carry:

```json
"summary": ["12 of 112 publications", "2009–2026"]
```

— an array of **already-formatted** strings, computed by `build_subset.py`.
Each renderer gains one small generic block: print a section's `summary` lines
above its items, as a single italic, slightly smaller lead line joined by " · ".
That is ~5 lines in `cv.typ`, ~5 in `render_html.py`, ~3 in the Markdown
renderer, and none of them knows what a metric is.

`cv.schema.json` gains `summary` on `$defs/section` and `$defs/group` (array of
strings). The full CV never sets it — but *can*, which is a free side benefit:
"112 publications" at the top of the full Publications section is one profile
key away.

**The known cost**, stated plainly: those strings contain formatting decisions
(currency symbols, thousands separators, en-dashes, wording) made outside a
renderer, which is a departure from Decision 2's "renderers own all formatting".
It is accepted because (a) the alternative is reimplementing the same metric
formatting in Typst *and* twice in Python, and (b) it lands in `build/`, never
in `src/` — the §2 line. If a fourth renderer ever wants different wording, the
escape hatch is to emit structured metrics alongside the strings.

### 7.2 Metric vocabulary

Values are reported **subset-and-full, side by side**, whenever the two differ;
when nothing was dropped, the parenthetical is omitted rather than printed as
"12 of 12".

| Metric | Renders as |
|---|---|
| `count` | `12 of 112 publications` |
| `span` | `2009–2026` (of the printed items) |
| `recent` | `8 in the last 5 years` |
| `total-amount` | see §7.3 |
| `count-by-group` | `6 journal articles · 3 book chapters` (section level) |
| `ongoing` | `19 supervised, 2 ongoing` (open-ended date ranges) |

`summary: "auto"` — the recommended default — shows `count` **only when items
were actually dropped**, and nothing otherwise. A stat line over three Education
entries is noise; a stat line over 5 of 55 seminars is the reason the feature
exists. Sections whose entries are not countable things (the *Journal Referee*
blob) set `summary: false`.

Default metrics by section type, used by `"auto"`:

- `publications` → `count`, `span`
- `grant` → `count`, `total-amount`
- `talks`, `courses`, `visits`, `people` → `count`
- `people` also → `ongoing`
- everything else → `count`, but only when truncated
- `named`, `text-list` → none

### 7.3 Money, honestly

Three rules, all forced by the data:

1. **Never sum across currencies.** The Awards group holds GBP, EUR and USD.
   Output lists each currency separately:
   `£1,254,000 of £4,214,560 awarded (plus €1,225,000, $50,000)`.
   No FX conversion, ever — a rate would date the document.
2. **Never imply a personal share.** `amount` is the total value of the award
   across all partners; the CV does not record a share. Default wording is
   *"total value of awards (all partners)"*, rendered once per section rather
   than per line. A profile may override the phrasing via
   `"summary-labels": {"total-amount": "…"}`.
3. **Disclose coverage.** Where some entries in scope lack a structured
   `amount` (the *Projects* group: 0 of 6), the metric appends
   `(3 entries without a recorded amount)` rather than quietly totalling a
   subset. If **no** entry in scope has an `amount`, the metric is omitted and
   `--strict` warns.

### 7.4 Elision lines

With `"and-more": true`, a group that dropped items appends one final row:
`… and 45 further seminars (2009–2024)`. It is emitted as an ordinary entry of
the group's own type with an empty date label, so no renderer changes. This is
the graceful-degradation counterpart to the summary line: the summary says how
much exists, the elision line says what was left out *here*.

## 8. Validation and failure modes

A subset CV is sent to people who decide things. The build must fail loudly
rather than produce a plausible-looking document with a section quietly missing.

`build_subset.py` exits non-zero, naming profile, key and offending value, on:

- a `section`/`group` title that does not exist in `cv.json`;
- an `include`/`exclude` id that matches no entry (typo, or a record deleted
  since the profile was written);
- an id that is ambiguous (duplicate ids in `cv.json` — also caught by
  `validate_cv.py`);
- a retained section or group that ends up empty, unless `allow-empty: true`;
- `sections` and `drop` both present, or neither;
- a `where` field the section's entry type does not define;
- derived data that fails `cv.schema.json`.

Warnings (non-fatal, promoted to errors under `--strict`): a date predicate that
met undated entries; a `total-amount` with partial coverage; a `limit` larger
than the number of available items.

`make validate` is extended to build **every tracked profile** (JSON only, no
PDF) so that a data edit which breaks a profile — deleting a paper a profile
names — fails CI on the PR that causes it, not months later when the CV is
needed.

## 9. Formats, CLI and CI

### 9.1 Makefile

```make
## subset: build one profile   (make subset PROFILE=teaching FORMATS="pdf docx")
subset:
	$(PYTHON) src/build_subset.py profiles/$(PROFILE).json --format $(FORMATS)

## subsets: build every profile marked "publish": true, into docs/
subsets:
	$(PYTHON) src/build_subset.py --all-published --out docs/subsets
```

### 9.2 DOCX

Per `ARCHITECTURE.md`'s nominated route: a third renderer `src/render_markdown.py`
emits Markdown from the derived data, then
`pandoc cv.md -o cv.docx --reference-doc=src/reference.docx`.

- `reference.docx` is a committed style carrier (Palatino body, the heading
  scale, the label/body indent approximating the two-column row). It is a
  binary asset — acceptable, since it is a *style* file, not content.
- The Markdown renderer is a third template over the same data, following the
  same per-type dispatch shape as the other two. The date column becomes a bold
  lead-in (`**2026** — …`) since Markdown has no two-column row.
- pandoc becomes a build dependency for DOCX **only**: `make site` must keep
  working without it. CI installs pandoc only in the subsets job.
- Link handling: `links` stays out of the DOCX by the same omission mechanism
  the PDF uses — the Markdown renderer simply never names the field. A future
  `"links": true` profile key could opt in.

### 9.3 Publishing

Default is private: `build/` is already gitignored, so a CV tailored to one
employer does not become a public URL by accident.

`"publish": true` opts a profile into `docs/subsets/<id>/`, built and committed
by a new CI job (or a new step in `build-site.yml`, gated on
`profiles/**` + `src/**` changes). A published subset is world-readable at
`darribas.org/cv/subsets/<id>/…` the moment it merges.

**Profiles are themselves public**, since `profiles/` is tracked in a public
repo. Keep `label` and `//` comments free of employer names; for a genuinely
private one-off, `profiles/local/` is gitignored and still builds.

## 10. Acceptance criteria

1. **Identity.** A profile retaining all 17 sections with no predicates
   produces a derived `cv.json` that renders byte-identical PDF and HTML to
   `docs/cv.pdf` / `docs/index.html` (modulo the trailing date stamp). This is
   the proof that the filter layer is transparent, and the regression guard for
   every later change.
2. **Schema.** Derived data passes `validate_cv.py` unmodified.
3. **Renderer inertia.** `make site` output is unchanged by the whole feature
   (bare `render_html.py` and `typst compile src/cv.typ` still work).
4. **Loud failure.** Every §8 condition exits non-zero with a message naming
   profile, key and value. No silent omissions.
5. **Determinism.** Same inputs ⇒ byte-identical derived JSON. The build
   timestamp lives only in the `//built` comment; `SOURCE_DATE_EPOCH` (or
   `--date`) pins the document date stamp for reproducible comparison.
6. **Two real profiles ship with the feature** — one length-driven
   (`short`: 2 pages, everything truncated), one audience-driven
   (`teaching`) — because a mechanism with no worked example rots.

## 11. Phasing

| Phase | Content | Ships |
|---|---|---|
| **P0** | `id` (+ optional `tags`) in `cv.schema.json`; `src/assign_ids.py`; ids written into all 279 entries; uniqueness check in `validate_cv.py`; normalise `Co-I` → `CoI`; `add-cv-record` skill updated to run `assign_ids.py` | A data-only PR, no behaviour change |
| **P1** | `subset.schema.json`, `build_subset.py` (retain/drop, include/exclude, since/until/where/limit/sort), `cv.typ` `sys.inputs`, `render_html.py` args, `make subset`, identity test, `profiles/short.json` + `profiles/teaching.json` | PDF subsets |
| **P2** | `summary` in schema + the three renderer lead-line blocks; metric vocabulary; `and-more` elision | Summary lines |
| **P3** | `render_markdown.py`, `reference.docx`, pandoc wiring | DOCX subsets |
| **P4** | `publish: true`, `docs/subsets/`, CI job, profile validation in `make validate`, a "Variants" link on the web page | Published subsets |

P1 is usable on its own; each later phase is independently shippable.

## 12. Non-goals

- **No content rewriting.** A subset selects; it never edits an entry's wording.
- **No page-count optimisation.** The tool will not iterate to "fit 2 pages";
  the author tunes `limit` and reads the PDF. (`--strict` could later report the
  page count as a convenience.)
- **No new formats beyond PDF/DOCX** in this feature. Browser-side on-the-fly
  export stays its own `TODO.md` item.
- **No cross-repo publishing**, no mail-merge, no per-application tracking.

## 13. Open questions

- **OPEN — `basics` for a subset.** Overriding `title` is clearly wanted. Should
  a profile also be able to add a short profile-specific summary paragraph under
  the header (common on shorter CVs)? That would be the first piece of prose
  living in a profile rather than in `src/`, which cuts against §12's
  no-rewriting rule. Deferred until a real profile needs it.
- **OPEN — profile inheritance.** `"extends": "short"` is obvious once there are
  five profiles and a bug fix has to be made in each. Cheap to add later;
  premature now.
- **OPEN — HTML subsets.** The machinery supports it (`--format html`), but a
  published HTML subset needs its own `style.css` copy and asset paths. Worth
  doing only if a subset is ever linked rather than attached.

## 14. Natural follow-on

The repo already ships an agent skill for adding records
(`.claude/skills/add-cv-record/`). The obvious sibling, once P1 lands, is a
`build-cv-subset` skill that **drafts a profile from a job advert or a funder's
CV requirements** ("2 pages, teaching-weighted, publications since 2018"), shows
it for approval, and builds it. The profile stays the reviewable artifact — the
agent proposes JSON, the author reads a diff, the build is deterministic. That
is a much safer division of labour than an agent editing a CV directly, and it
is only sensible once selection is data rather than prose.
