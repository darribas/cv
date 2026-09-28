# Log

Completed items, moved here from `TODO.md` per that file's own convention.

## Reformatting and cleaning up

Migrated the CV from a single 1,760-line LaTeX file to structured JSON
(`src/cv.json`, `src/publications.json`) rendered by Typst (`src/cv.typ`).
Real Typst headings give the PDF genuine bookmarks/TOC (previously
`currvita`'s sections were visual-only), and commented-out cruft was dropped
rather than carried forward. See `ARCHITECTURE.md` for the design decisions
and `notes/MIGRATION-REVIEW.md` for the full migration log. The original
`.tex` and its one-shot migration parser were retired once every section was
verified verbatim against the source (commit `19784b5`).

## Considering different PDF engine

Decided on Typst over LaTeX/pandoc — see `ARCHITECTURE.md` Decision 1 for
the full comparison and rationale.

## GH Action for PDF build

Added `.github/workflows/build-pdf.yml`: rebuilds and commits `docs/cv.pdf`
on every push to `main` that touches `src/`, `fonts/`, or the `Makefile`;
validates + builds (no commit) on pull requests, so a broken source is caught
before merge. No TeXLive or system font install needed — Typst is downloaded
directly from its GitHub releases, and the Pagella font is bundled in
`fonts/`. Merged via PR #1.

## GH Pages rendering (HTML build)

Added `src/render_html.py`: a second, independent renderer over the same
`src/cv.json`/`src/publications.json` (per `ARCHITECTURE.md` Decision 2 —
never reads `cv.typ` or its output). Typst's own `--features html` export was
tried first and confirmed unusable for this document (it drops nearly all
content; see `ARCHITECTURE.md`), which is what settled on a second template
instead.

Styled in `src/style.css` to match the PDF's Palatino feel — TeX Gyre Pagella
loaded as a real `@font-face` from the same font files bundled for Typst —
with a "Download PDF" button and a "Sections" button that opens a floating,
two-column table of contents via the native Popover API (no JS: outside-click
and Escape dismissal are built in), and `prefers-color-scheme` dark mode.

`.github/workflows/build-pdf.yml` was renamed to `build-site.yml` and
extended to build and commit the whole `docs/` (PDF + HTML + CSS + fonts)
rather than just the PDF. See PR #3.

GitHub Pages itself (Settings → Pages → Deploy from branch → `main` /
`/docs`) is not yet switched on — that's a deliberate separate decision for
the author to make, not part of this build work.

## GitHub Pages switched on

The repo setting (Settings → Pages → Deploy from branch → `main` / `/docs`)
was flipped and the CV site is now publicly live. State at `382a755`
("Rebuild CV site [skip ci]"), 2026-07-14.

## Web-only publication links

First slice of the "Merging with online list of work" TODO item — the part that
covers extra URLs on outputs that are *already* in the CV. A publication in
`src/publications.json` may now carry an optional `links` array:

```json
"links": [{ "type": "code", "url": "https://github.com/…" }]
```

Design rationale is `ARCHITECTURE.md` Decision 4; in short: links carry a
**kind**, not a display string (the renderer owns wording and ordering, and a
kind is filterable — which is what the subset-CV TODO item will need); the PDF
excludes them by never naming the field, so `cv.typ` gained only a comment; and
the web page's show/hide switch is a hidden checkbox + `:checked` sibling
selector, keeping the page JavaScript-free like the Sections popover. The switch
defaults to on and resets on reload, which is the accepted price of no JS.

Touched: `src/render_html.py` (`LINK_LABELS`, `render_links`, the switch),
`src/style.css` (`.weblinks` pills, the switch, a `@media print` rule, and the
header button row refactored from corner-absolute buttons to a flex row now that
there are three controls), `src/cv.typ` (comment only), plus
`src/cv.template.json` and the `add-cv-record` skill — whose `validate_cv.py`
now checks link shape and rejects an unknown kind that has no `label` override.

**The data**: 140 links across 87 of the 110 publications, transcribed from
`me.darribas.org/research`. The 23 without links are the entries that page does
not list (book reviews, the "other" outputs, the SDG conference papers, the 2026
pieces). URLs are verbatim apart from stripped social-share fragments
(`…#.U9qo10gg7VE`). Vocabulary shaped by what the page actually distinguishes:
`accepted` (institutional-repository postprints) and `docs` were added on
contact with the data, and `project` became `site`.

Three discrepancies surfaced by cross-checking the transcription against the
data (every DOI in `publications.json` was compared with the page's `doi.org`
links, and every link URL checked for duplicates across entries):

- `calafiore2023inequalities` carried a truncated DOI
  (`10.1177/23998083231208`, missing `507`) — **fixed**, since the CV's own DOI
  did not resolve.
- Liu, Singleton & Arribas-Bel (2020), "Considering Context and Dynamics: A
  Classification of Transit-Oriented Development for New York City" (*Journal of
  Transport Geography*, 85, 102711) was on the research page but missing from
  `publications.json` entirely — **added** (`liu2020considering`), hand-built
  from the page's own metadata because `doi.org` is blocked by the build
  sandbox's egress policy.
- The page gives "Improving the Multi-Dimensional Comparison of Simulation
  Results" the same published-version URL as "High Performers in Complex Spatial
  Systems" (an Annals of Regional Science link) — a copy-paste slip on the page.
  That entry therefore carries no `official` link: the correct one could not be
  looked up either, since `api.crossref.org` is blocked as well. Left on
  `TODO.md` as the one outstanding gap.

**Sticky controls.** With links adding a row to most publications, the header's
buttons were worth keeping reachable, so the control bar (Sections / Links /
PDF) now `position: sticky`s to the top of the viewport for the whole page. That
required moving it out of `<header>` and into `<main>`: sticky only holds while
its containing block is on screen, and `<header>` scrolls away almost
immediately, whereas `<main>` spans the document. Anchor targets gained
`scroll-margin-top` so a jump from the Sections menu lands below the bar rather
than under it.

## AI skill for adding CV records

Added `.claude/skills/add-cv-record/` — a Claude Code skill that lets an agent
append a new CV entry (publication, job, grant, award, talk, course, software,
etc.) without re-deriving the data model each time. It encodes where records
live (`src/cv.json` vs. `src/publications.json`), authors from
`src/cv.template.json`'s per-type examples, validates against
`src/cv.schema.json`, keeps the change data-only (never the renderers), and
lands it as a PR off `main`.

Bundled with it is `validate_cv.py`, a stdlib-only validator (no pip installs,
matching the pipeline's ethos): it runs the subset of JSON Schema that
`cv.schema.json` uses against `cv.json`, and structurally checks
`publications.json` — including that every entry's `category` maps to a group
the publications section actually renders. This is stricter than CI's `make
validate`, which only checks that the JSON parses; the schema is otherwise only
enforced by editor tooling, so the skill closes that gap at author time. The
full Typst/HTML build stays CI's job on the PR.

Settled the three open questions the TODO raised: **one** general skill
(section-type chosen from the record, not separate skills per type);
**append-only** (editing an existing record is left to hand-editing); and
**schema-validation only** locally (no local Typst/HTML dry-run — that needs the
Typst binary + fonts and belongs in CI). Developed on branch
`claude/architecture-logs-todos-review-505c4r`.

Follow-up, same branch — two usage paths made first-class:

- **Add from a URL/DOI.** The skill now documents fetching a publication as
  CSL-JSON directly via DOI content negotiation (`Accept:
  application/vnd.citationstyles.csl+json` against `doi.org`) — the exact format
  `publications.json` uses — with a CSL-`type` → `category` mapping and a
  non-DOI/arXiv fallback. So "Add this paper: <url>" mostly needs no hand-typed
  fields.
- **Cross-agent / local LLM.** It's a standard Agent Skills `SKILL.md`, and
  OpenCode discovers `.claude/skills/` natively (Agent Skills open standard),
  so the skill runs unmodified there, including with a local model — the DOI
  fetch + `validate_cv.py` gate keep it reliable even on weaker models. `README.md`
  now carries brief install/use guidance for both Claude Code and OpenCode.

## Subset CVs — P0: record ids, validator, tests

First phase of `notes/SUBSET-CV-SPEC.md` (§15 P0); the rest stays in `TODO.md`.

- **Ids.** All 279 `cv.json` entries now carry a permanent `id`
  (`<context>-<year>-<keywords>`, e.g. `education-2010-phd-economics`; 10 got a
  `-2`/`-3` collision suffix), unique across both data files. Publications
  keep their CSL ids. `src/assign_ids.py` generates them and writes them by
  text insertion right after each entry's `{`, so the hand formatting is
  untouched — stripping the inserted text gives the old file back byte for
  byte (tested). It only adds ids to entries that lack one, so it is the
  add-record skill's step after pasting an entry (`--check` reports without
  writing). `cv.schema.json` requires `id` (pattern `^[a-z0-9][a-z0-9-]*$`,
  ≤ 60 characters).
- **Validator** moved to `src/validate_cv.py` (importable: `check(root)`), now
  also enforcing `pattern`/`maxLength` and id uniqueness within `cv.json` and
  across both files. A shim keeps the old skill path working. `make validate`
  runs it after the parse check, so CI now enforces the schema.
- **Data fix:** the one `"role": "Co-I"` is now `CoI` like the other 11 — the
  only change in the built site.
- **Tests:** `tests/` (stdlib `unittest`), `make test`, and a CI step. Covers
  the id rule, the insertion invariant (on awkward fixtures and the real
  file), idempotence, the validator's id errors, and that ids never reach the
  output: HTML and PDF are built with and without ids in the same run and
  compared byte for byte. Typst's `--creation-timestamp` was verified to pin
  `datetime.today()` too (Typst 0.15), so the PDF comparison needs no
  text-extraction fallback.

## Subset CVs — P1: config, selection, PDF

Second phase of `notes/SUBSET-CV-SPEC.md` (§15 P1); P2–P5 stay in `TODO.md`.

- **`src/build_subset.py`**: `CONFIG [--out DIR] [--strict]` validates the
  master data and the TOML config, selects into a derived `cv.json` +
  `publications.json` under `build/.subset-work/` (schema-checked), renders
  the PDF with the unchanged `cv.typ`, and writes `darribas-cv-<name>.pdf`,
  the derived data, a verbatim `config.toml` and `manifest.json` (data commit
  and dirty flag, build time, per-section kept/total counts, page count)
  beside the config. Every problem is reported at once, naming file, key and
  value, with "did you mean" suggestions for titles and ids; later-phase keys
  are errors naming their phase. `--list [SECTION]` and `--scaffold [PATH]`
  (a config listing every section, group and id, with one-line
  descriptions; never overwriting an existing file) make picking
  records practical.
- **`make` is the interface**: `make subset CONFIG=… [OUT=…]` builds the
  config, or writes a starter one there if none exists yet (then stops, to
  be edited); `make subset-list [SECTION=…]` prints record ids.
- **Renderers, generic knobs only**: `cv.typ` reads an optional `data` input;
  `render_html.py` takes `--data`/`--out`. Bare, both behave exactly as before.
- **Never tracked, never published**: configs and outputs normally live in
  the gitignored `subsets/` folder (the build often runs in a container that
  mounts only the repo), or anywhere outside the repo. Inside the repo the
  build writes only where `git check-ignore` confirms the path is ignored,
  never `docs/`, `src/` or the repo root (symlinks resolved). `.gitignore`
  ignores `subsets/` and every `*.toml` but `src/subset.template.toml`; a CI
  step fails if any such file is tracked. (First built as "outputs never
  inside the repo"; relaxed at the author's request for the container case —
  ARCHITECTURE.md Decision 5.)
- **Settled** (spec §5): section-level `ids` together with group tables is an
  error — ids go under the groups.
- **Tests** (79 total): the identity test (an all-sections config and the
  `--scaffold` output both build a PDF byte-identical to plain `cv.typ`, and
  the same HTML), the selection rule, every P1 config error, the output-path
  guard, and a real build from a temp-dir config leaving `git status`
  unchanged.

## Subset CVs — P2: summaries and money

Third phase of `notes/SUBSET-CV-SPEC.md` (§15 P2); P3–P5 stay in `TODO.md`.

- **Summaries**: `summary = ["count", "total"]` on a `[[section]]` or
  `[[section.group]]`, or `[summary] default = [...]` for every section
  without its own. The build writes the finished strings into the derived
  data's new `summary` array (and a currency note into `summary_note`,
  `cv.schema.json`); `cv.typ` and `render_html.py` print them in
  parentheses after the heading's title, smaller, italic, joined by "; " —
  no extra vertical space: "Research Income (7 of 28; ≈ £11.1M, £7.5M as
  PI)" — and the note as a footnote (a tooltip on the
  web page). In Typst the summary reaches the heading's show rule through a
  `state`, so the PDF bookmarks keep the bare title; the footnote marker is
  set small and italic like the summary.
- **`count`**: "1 of 112", no noun; "112" when nothing was dropped, but
  only when asked for on that section: a count from `summary.default` is
  left out for sections kept whole. A warning on text-list/named sections.
- **`total`**: the summed `amount` of the award (type `grant`) entries kept,
  unlabelled, then the part held as PI: "≈ £11.1M, £7.5M as PI" (role "PI";
  left out when none is). One `≈` and a "Converted to GBP at … of <date>."
  footnote when currencies were converted; ", N awards without an amount"
  plus a warning for gaps. Projects never count. An explicit `total` on a section without
  awards is an error; one from `summary.default` just skips such sections.
- **`[money]`**: `currency` (GBP/EUR/USD), `source = "live" | "config"`,
  `rates_date`, `[money.rates]`. Live rates are the ECB daily reference rates
  (cross rates via EUR, six significant figures), fetched only when a total
  needs converting; config rates are the fallback (with a warning) or, with
  `source = "config"`, always used without any network request. Missing
  rates, a missing currency, malformed rates and stale (90+ day) rates are
  errors or warnings per spec §8.3/§12. `manifest.json` gains `rates`: source,
  date, the rates used and a snippet ready to paste into the config.
- **Settled with the author** ("parsimony is king"): summaries sit beside the
  heading rather than on a line of their own; no nouns; subsets show only
  their own money, not "of" the whole; `source = "config"` without
  `[money.rates]` is an error even if nothing needs converting.
- **Full CV summaries** (added at the author's request): `make site` now
  renders `build/site/cv.json`, written by `src/build_site_data.py` —
  `src/cv.json` plus the summaries configured in the new, tracked
  `src/summaries.json` (Research Income: "(≈ £12.5M, £7.7M as PI)",
  with a footnote on the conversion). Its dated rates are tracked so CI
  builds offline and reproducibly; `make rates` refreshes them from the ECB.
  ARCHITECTURE.md Decision 5 records why.
- **Tests**: `tests/test_summary.py` (33) and `tests/test_site_data.py` (10),
  the ECB fetch always patched:
  both `count` forms, single- and multi-currency totals, the partial-coverage
  suffix, all six cells of the rates table, no fetch with `source =
  "config"`, stale and missing-currency rates, the `[money]`/`summary`
  config errors, and a real build through both renderers (summary beside
  the heading, footnote, bookmarks unchanged) and `--strict`.

## Web page: Links switch keeps the reader's place (#16)

Toggling "Links" jumped to the top of the page: clicking the `<label>`
focuses the visually-hidden checkbox, and the browser scrolls focus into view
— and the checkbox sat at the top. One CSS rule (`#show-links { position:
fixed }`) keeps it always in view, so toggling no longer scrolls. Checked in
headless Chromium and Firefox and by hand in Firefox; Safari unchecked. Known
residue: the text can shift by up to one row of link pills when an entry
partly under the sticky bar gains or loses its links row. PR #19.

## Web page: per-item links (#17)

Every item renders with its record id as its HTML `id` and a faint link glyph
in the left margin (shown on hover/focus, dimly on touch screens). Opening a
`#<id>` URL makes the item `:target`: a soft wash, and `main:has(:target)`
fades the rest back until the URL points elsewhere; a half-viewport
`scroll-margin-top` lands it mid-screen. The page gained its first script —
progressive enhancement — which copies the permalink on click and handles a
new `?links=on|off` parameter: it overrides the switch's default and is
rewritten as the switch flips, so a reload or a shared link keeps the view.
That supersedes the "resets on reload" trade-off recorded under *Web-only
publication links* above. `test_site_unchanged` now allows the HTML to differ
only by these anchors. `ARCHITECTURE.md` Decision 4 has the design. PR #20.
