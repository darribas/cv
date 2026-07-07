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
