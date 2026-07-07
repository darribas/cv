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
| **Publications** | ✅ migrated (`src/publications.json`, via `tools/tex2cv.py`) |
| Invited Lectures (Keynotes, Seminars) | ✅ migrated |
| Conferences and Events | ✅ migrated |
| Teaching | ✅ migrated |
| Line management — Supervision | ✅ migrated |
| Service to University and Community | ✅ migrated |

All sections of `cv-darribas.tex` are now migrated to `src/cv.json` /
`src/publications.json`. The `.tex` file and `tools/tex2cv.py` become
disposable once this is confirmed correct.

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
- **Section order is array order in `cv.json`** — `cv.typ` just does
  `#for section in cv.sections`, with no ordering knowledge of its own (already
  documented via the schema's field description and a comment above the loop).
  Considered encoding order in `cv.typ` instead, on the worry that array order
  is implicit/brittle, but rejected it: JSON arrays (unlike objects) have
  spec-guaranteed order, so there's no real ambiguity, and putting order in the
  renderer would violate ARCHITECTURE.md Decision 2 (the renderer must stay
  content-agnostic and swappable) — it would create a second source of truth
  that has to be kept in sync with the section list, and every future renderer
  (HTML, Word) would need to duplicate that same order list instead of
  inheriting it for free from the data.

## Publications (Stage 1)

`tools/tex2cv.py` parses the Publications `cvlist` (110 entries across 7
categories) into CSL-JSON. The parser handles the dominant citation styles
(semicolon- and comma-separated authors, `` '' and straight `"..."` quoted
titles, `\emph`/`\textit` venues, DOI/ISBN/URL extraction, volume/issue/page)
and de-duplicates ids that collide (same author/year/first-title-word).

**Entry counts match the source exactly:** Books 1, Peer-reviewed journal
articles 69, Conference Proceedings 5, Other academic articles 16, Book
chapters 7, Other 9, Working Papers 3 — 110 total, verified against
`\item[` counts per sub-header in `cv-darribas.tex`.

**Content verified verbatim, all 110 entries:** a check script re-parses the
`.tex` Publications block (comments stripped, whitespace/line-wraps
collapsed) and confirms, for every entry in `publications.json`, that its
title (quote-style-agnostic), every author's family name (or literal, for
the one organizational author), and its DOI/ISBN/URL all appear in the
source verbatim. 0 failures. This is the same verbatim-match method used
for Stage 0 (see below), automated rather than eyeballed given the volume.

10 of 110 entries needed hand fixes after parsing (all one-off source
irregularities, not parser gaps) — applied directly to `src/publications.json`:

- **Two book chapters had no quoted title at all** ("Statistics, Modelling,
  and Data Science" and "Demographic Aging and Employment Dynamics...") —
  title, authors, pages and publisher added by hand from the surrounding text.
- **Two author lists had source typos**: `Garcia-Lopez, M.-A. Garcia-Lopez`
  (family name duplicated) and `Birkin, M. (2024)` (year restated after the
  initial) — corrected to the evident intended author list.
- **Two chapters' editor lists** and **three "Other"-category blog/report
  entries' trailing publisher text** (e.g. "Kinder Institute for Urban
  Research, Rice University") were folded into `editor`/`publisher` fields
  rather than left as unparsed trailing text.
- The one **organizational author** ("The Alan Turing Institute", report)
  is stored as CSL `{"literal": ...}`; `cv.typ`'s `fmt-authors` was updated
  to print literal authors as-is.

**Flagged for author confirmation — resolved:**

- Three DOIs were missing their registrant prefix in the source `.tex` itself
  (not a parsing artifact). **Confirmed and fixed:** `liu2021identifying` and
  `calafiore2021a` → `10.1016/...` (both *Computers, Environment and Urban
  Systems*), `arribasbel2024in` ("In praise of (spatial) bundles") →
  `10.1177/...`.
- `patias2021sustainable` ("Sustainable urban development indicators...") had
  volume `214, 0169-2046` — `0169-2046` looked like the journal's ISSN, not a
  page/article number. **Confirmed via Crossref** (`api.crossref.org/works/`
  lookup on the DOI): the article number is **104148** — the source had
  substituted the ISSN for it. Fixed to `214, 104148`; the DOI (previously
  stored as a full `https://doi.org/...` URL, inconsistent with every other
  entry) was also normalised to the bare `DOI` field.

## Invited Lectures, Conferences, Teaching, Supervision, Service (Stage 2)

Parsed with one-off Python extraction scripts (not folded into `tools/tex2cv.py`,
which is Publications-specific) mirroring the same approach: mechanical
extraction + verbatim-fidelity check + hand fixes for genuine one-offs.
187 entries total (Invited Lectures 58, Conferences and Events 25, Teaching 43,
Supervision 43, Service 18), all verified verbatim against `cv-darribas.tex`
the same way as Publications (0 failures).

Two source-structure quirks these sections needed, not present elsewhere:

- **Bracket-less `\item`** (no `[label]` at all) for the Teaching section's
  Postgraduate/Undergraduate course lists — required separate extraction
  logic rather than the bracket-based `\item[...]` splitter Publications uses.
- **Curly-brace sub-headers** (`\item{\underline{Supervisor}}` etc.) instead of
  the usual `\item[\textbf{...}]` — used inside "PhD" in the Supervision
  section for its Supervisor/Visitor Host/Committee Member sub-groups.

Renderer changes: `cv.typ`'s `render-textlist` gained an optional trailing
`url` (matching the pattern already used by `courses`/`named`), needed for
the Service section's podcast link and used generally for Conferences'
"Participation" and Service's flat list-style entries.

**Hand fixes applied** (genuine one-off source irregularities):

- Two unquoted, title-less entries in Teaching (`OpenGeoDa, GeoDaSpace and
  PySAL Lab instructor`; `Microeconomics II`) — title/venue split by hand.
- A source typo mixing quote styles across three apostrophes
  (`Building 'Geographic Data Science…'''`, `` `` `` `` opened, `'''` closed)
  produced a truncated title the first time through; fixed by treating a
  run of 3 apostrophes as [closing single-quote][closing double-quote] in
  that order, not the reverse.
- A name/detail splitter for Supervision's "people" entries originally split
  on the *first* period, breaking on middle initials (`Helen V. Roberts` →
  `Helen V.` / `Roberts...`); fixed to skip a period immediately preceded by
  a lone capital letter.

**Flagged for author confirmation — resolved:**

- **"Unfinnished"** (sic) appeared 4 times in the Supervision/Supervisor group
  (Sian Teesdale, John Freeman, Meruyert Kenzhebay, Melanie Green). **Confirmed
  typo** — fixed to "Unfinished" in all 4 entries.
- **Co-presenter dropped**: the Invited Lectures/Seminars "An introduction to
  R" (2012) entry is co-presented with "Malizia, N." in the source, but
  `talks` entries store title+venue only (no author field). **Resolved**:
  rather than a schema change, the co-presenter is named inline in the title
  — `"An introduction to R (with Nick Malizia)"`.

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

## Flagged for author confirmation — resolved

- **`Rachel Frankling` → `Rachel Franklin`** (Honors and Awards, 2026 Media
  Achievement Award). **Confirmed**: corroborated by two other mentions in the
  CV (Conferences and Events' "Spatial Analytics and Data" series, and
  publication co-author "Franklin, R.") — both spell it "Franklin."
