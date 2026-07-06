# Migration review log

Tracks the LaTeX → JSON migration: light-cleanup edits applied, decisions
taken, and items flagged for the author to confirm. See `notes/migration-plan.md`
for the overall plan.

## Status

| Section | Status |
|---|---|
| Education | ✅ migrated (`src/cv.json`) |
| Current / Honorary / Editorial / Other / Prior Appointments | ✅ migrated |
| Honors and Awards | ✅ migrated |
| Research Income (Awards + Projects) | ✅ migrated |
| Research Visits | ✅ migrated |
| Scientific Software · Language Skills | ✅ migrated |
| **Publications** | ⏳ Stage 1 — via `tools/tex2cv.py` parser |
| Invited Lectures (Keynotes, Seminars) | ⏳ pending |
| Conferences and Events | ⏳ pending |
| Teaching | ⏳ pending |
| Line management — Supervision | ⏳ pending |
| Service to University and Community | ⏳ pending |

## Light-cleanup edits applied (Stage 0)

- **Typo:** `Bello Horizonte` → `Belo Horizonte` (Research Visits, 2019 CEDEPLAR).
- **Amount normalisation (Projects):** the `.tex` mixed formats — trailing-euro
  and US-dollar variants (`42.900€`, `$US 500,000`, `$US 1.4 million`). Normalised
  to a consistent style: `€42,900`, `€34,485`, `US$500,000`, `US$1.4 million`,
  `€2,548,920`. No values changed.
- **Amounts (Awards):** modelled as `{value, currency}`; the renderer prints the
  £/€/$ symbol, so no symbol is hard-coded in the data.

## Reference

- Ground-truth PDF saved at `notes/cv-current.pdf` (28 pages, currvita/LaTeX).
  Used to spot-check the migration, especially publications.

## Decisions

- **Last-updated date stamp** reproduced from currvita's trailing `\today`
  (original showed "June 30, 2026"). Rendered via `datetime.today()`, so it
  auto-updates on every rebuild rather than being hard-coded.

- **Grant (Awards) titles are quoted**, matching the original (`“Title”.` with the
  period outside the closing quote). The renderer wraps the title and italicises
  the funder. The "Projects (as researcher)" titles stay *italic* (no quotes), as
  in the original; Honors & Awards names likewise stay italic.
- **"Together with …" collaborator lines** on two 2019 grants are stored in the
  grant `scheme` field (there is no dedicated collaborators field for grants).
- **Talk self-author dropped** (planned for the Lectures section): the `.tex`
  repeats `Arribas-Bel, D.` before every talk title; on a personal CV this is
  redundant, so `talks` entries store only the title + venue.

## Verification (Stage 0)

Compared `src/cv.json` against the original `cv-darribas.tex` (the source that
produced `notes/cv-current.pdf`): every text value must appear in the original,
and per-section entry counts must match.

- **Entry counts:** all 11 migrated sections match exactly (Education 3, Current 2,
  Honorary 6, Editorial 8, Other 3, Prior 9, Awards 5, Research Income 27,
  Visits 17, Software 5, Languages 3).
- **Text:** only 3 values differ from verbatim, all intentional — the two typo
  fixes below, plus the author's own addition of "Amsterdam (The Netherlands)" to
  the 2012-2014 VU postdoctoral appointment. No accidental changes.

## Flagged for author confirmation

- **`Rachel Frankling` → `Rachel Franklin`** (Honors and Awards, 2026 Media
  Achievement Award). Applied as a likely typo of a collaborator's name — please
  confirm the correct spelling.
