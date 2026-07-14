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
