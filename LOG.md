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
