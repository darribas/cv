---
name: add-cv-record
description: Add a new entry to Daniel Arribas-Bel's CV — a publication, job/appointment, degree, grant, award, talk, teaching course, software, or any other CV record. Use when asked to "add a paper/publication", "add a job/position", "add a grant/award", "add a talk", or otherwise record a new CV item. Handles the correct data file, schema-validates the edit, and opens it as a PR. Data-only: never edit the renderers.
---

# Add a CV record

This CV is **structured data with a swappable renderer** (see `ARCHITECTURE.md`).
Adding a record is therefore a **data-only** change: you edit one JSON file, and
both the PDF (`src/cv.typ`) and the web page (`src/render_html.py`) pick it up on
the next build. You never edit either renderer, and you never edit build outputs
in `docs/`.

This skill **appends new records**. Correcting or restructuring an existing entry
is out of scope — do that by hand.

## Where records live

| Record kind | File | Format |
|---|---|---|
| **Publications** (books, journal articles, chapters, conference papers, working papers, etc.) | `src/publications.json` | CSL-JSON array |
| **Everything else** (education, positions, editorial roles, awards, grants, projects, visits, talks, events, teaching, supervision, software, free-text service) | `src/cv.json` | CV JSON, validated by `src/cv.schema.json` |

Two supporting files, both of which you should lean on rather than reinventing:

- `src/cv.schema.json` — the contract for `cv.json`. It drives editor
  autocomplete and is what this skill validates against. **Read the field it
  documents; never guess a key name.**
- `src/cv.template.json` — one fully-worked, annotated example **per section
  type**. This is your copy-paste source. It is never rendered.

## Working interactively

This is a conversation, not a one-shot form. Gather the record's details by
talking to the user, and **only write files once the details are settled**:

- **Ask, don't invent.** If a field the record type needs is missing or
  ambiguous, ask the user rather than guessing. Use the section's `type` to know
  what to ask for — e.g. a `grant` needs funder, scheme, role, period, and
  amount+currency; a `talk` needs the title, venue, place, and date. The schema
  and `cv.template.json` tell you which fields apply.
- **A DOI collapses the conversation.** For a publication with a DOI, fetch the
  metadata (step 3a) and just confirm it back — usually no questions needed.
  Non-publication records are where the back-and-forth matters most.
- **Confirm before you write.** When the details are ready, show the user the
  exact JSON entry you're about to add and get a yes before touching any file.
- **The PR is the last step, on the user's go-ahead.** Draft → confirm →
  validate → commit → open PR. Don't open the PR until validation passes and the
  user is happy with the entry.

The steps below are that flow in order — they assume the details are settled by
the time you edit files.

## Workflow

Do not skip validation, and do not commit to `main`.

### 1. Start a branch

Every contribution lands as a PR — never a direct commit to `main`.

```bash
git fetch origin main
git checkout -B add-cv-<short-slug> origin/main   # e.g. add-cv-neurips-paper
```

### 2. Decide which file

- Is it a **publication** (something with authors, a title, and a year that
  belongs in a bibliography)? → `src/publications.json`, step 3a.
- Anything else → `src/cv.json`, step 3b.

### 3a. Add a publication (`src/publications.json`)

`publications.json` is a flat CSL-JSON array. The renderer groups entries by a
custom **`category`** key and sorts each group by year, descending — so you only
append; you do not place the entry in any particular position.

#### From a URL or DOI (the fast, reliable path)

Most "add this paper" requests come with a link. **If the link is or contains a
DOI, do not transcribe fields by hand** — fetch the record as CSL-JSON directly,
which is the exact format this file uses. DOI content negotiation returns it:

```bash
# <DOI> e.g. 10.1111/gean.12205  (strip any https://doi.org/ prefix)
curl -sSL -H "Accept: application/vnd.citationstyles.csl+json" "https://doi.org/<DOI>"
```

(If `curl` is unavailable, use the agent's own fetch tool against the same URL
with that `Accept` header.) Then:

1. **Keep only the fields the renderer uses** (the table below) plus `id` and
   `category`. The response carries extras (`abstract`, `reference`, `license`,
   …) — drop them so the file stays consistent with existing entries.
2. **Set `id`** yourself (author+year+word, e.g. `smith2026spatial`) — the raw
   response has no citation key in that style.
3. **Set `category`** from the returned CSL `type`:

   | CSL `type` returned | `category` to set |
   |---|---|
   | `article-journal` | `journal-article` |
   | `book` | `book` |
   | `chapter` | `book-chapter` |
   | `paper-conference`, `article-proceedings` | `conference` |
   | `posted-content` (preprint) | `working-paper` |
   | anything else | judge: `other-article` or `other` |

For a **non-DOI URL** (a publisher/arXiv landing page with no usable DOI):
extract author/title/venue/year (and a DOI if one is on the page) from the page
content, then hand-build the entry using the table below. arXiv also exposes
metadata at `https://arxiv.org/abs/<id>` and its API. Always prefer a real DOI
when the page offers one.

After either path, continue to validation (step 4) — never trust the fetch
blindly; the validator confirms the shape and that `category` will render.

#### Fields the renderer uses

1. Pick the `category` from the groups declared in the `publications` section of
   `cv.json` (currently: `book`, `journal-article`, `conference`,
   `other-article`, `book-chapter`, `other`, `working-paper`). A category that
   matches no group **will not render** — the validator flags this.
2. Append one object to the array. Fields the renderers actually use:

   | Field | Notes |
   |---|---|
   | `id` | unique citation key, e.g. `smith2026spatial` (author+year+word) |
   | `type` | CSL type, e.g. `article-journal`, `book`, `chapter`, `paper-conference` |
   | `category` | grouping key (see step 1) — this, not `type`, controls the section |
   | `title` | rendered in quotes |
   | `author` | array of `{ "family": "...", "given": "..." }`; a corporate author is `{ "literal": "..." }` |
   | `issued` | `{ "date-parts": [[2026]] }` — the year is read from here |
   | `container-title` | journal/book title (italic); optional |
   | `volume`, `page` | optional, appended to the venue |
   | `publisher` | optional |
   | `DOI` | optional, monospace |
   | `URL` | optional, monospace + clickable |
   | `links` | optional, **web page only** — see below |

   Editors, `ISBN`, etc. are allowed (CSL-JSON is open) but only the fields above
   surface in the CV. Keep initials in `given` consistent with the file's style
   (e.g. `"given": "D"`).

   **`DOI` vs `URL`: set one, not both.** Both fields print unconditionally when
   present (`cv.typ` and `render_html.py` each render `DOI` then `URL` as
   separate items), so setting both prints the same link twice. Prefer `DOI`
   whenever one exists; fall back to `URL` only when there is no DOI. Don't set
   `URL` to a page that just resolves the same DOI (e.g. the publisher landing
   page) — that redundant link belongs in `links` (as an `official` entry)
   instead, where it renders as a web-only pill rather than a second inline
   link. Only set both `DOI` and `URL` if `URL` points somewhere the DOI does
   not resolve to.

#### Web-only extras: `links`

A publication may carry the extra material listed alongside it at
<https://me.darribas.org/research/> — official version, code repository, data,
a live visualisation. These are **deliberately absent from the PDF** (`cv.typ`
never reads the field, which is the whole mechanism); the web page shows them as
a row of small pills under the entry, behind the header's "Links" switch.

```json
"links": [
  { "type": "official", "url": "https://doi.org/10.1111/gean.12205" },
  { "type": "code",     "url": "https://github.com/darribas/some-paper" }
]
```

- `type` is the link's **kind**, not its wording — the renderer owns the wording
  (`LINK_LABELS` in `src/render_html.py`) so it stays consistent everywhere.
  Known kinds: `official`, `accepted`, `preprint`, `pdf`, `code`, `data`,
  `notebook`, `viz`, `site`, `docs`, `slides`, `video`, `poster`, `blog`.
- Order doesn't matter — the renderer sorts links into a fixed sequence.
- For a one-off wording no kind captures, add `"label": "Interactive map"`. A
  `type` outside the known set is only accepted **with** a `label`; the
  validator flags it otherwise, which is what catches typos.
- Only add links the user gives you or that are listed on the page above. **Never
  guess a repository URL** from a paper's title or authors.

### 3b. Add a CV-body record (`src/cv.json`)

1. Find the target **section** in `cv.json` by its `title` (e.g. "Honors and
   Awards"). Note its `type` — or, for a grouped section like "Research Income",
   the `type` of the specific group you're adding to.
2. Open `src/cv.template.json`, find the block with that **same `type`**, and
   copy one entry object.
3. Paste it into the section's (or group's) `entries` array and edit the values.
   **Delete every `//`-prefixed hint key** you copied — those are authoring notes,
   not data. (`//`-prefixed keys are legal and ignored by the renderer, so a
   leftover won't break the build, but they don't belong in real records.)
4. Only use fields the schema lists for that `type` — check `cv.schema.json`'s
   `entry` definition, where each field's `description` says which types use it.
   A misspelled or wrong-type key is a hard schema error (caught in step 4).
5. Ordering within a section is manual and meaningful (usually reverse-chronological
   by `date`); place the new entry where it reads correctly. The `date` column
   blanks automatically when consecutive entries repeat a value.

Money uses `"amount": { "value": <number>, "currency": "GBP" | "EUR" | "USD" }` —
never a hard-coded symbol; the renderer prints the symbol.

### 4. Validate

Run the bundled schema validator. It checks `cv.json` against `cv.schema.json`
and sanity-checks `publications.json` (including that every `category` maps to a
rendered group). It is stdlib-only — no installs.

```bash
python3 .claude/skills/add-cv-record/validate_cv.py
```

Fix anything it reports and re-run until it prints both ✓ lines. This is stricter
than CI's `make validate` (which only checks that JSON parses), so a clean run
here is the meaningful gate. Optionally, `make validate` mirrors the CI parse
check.

> Do **not** run a Typst/HTML build as part of this skill. The build needs the
> Typst binary + bundled fonts and is the CI's job on the PR; schema validation
> is the local gate we rely on.

### 5. Commit and open a PR

Only reach this step once the user has approved the entry (see *Working
interactively*) and validation passes.

```bash
git add src/cv.json src/publications.json      # only the file(s) you changed
git commit -m "Add <record>: <short description>"
git push -u origin add-cv-<short-slug>
```

Then open a PR against `main` (do not merge it). In the PR body, state what was
added and note that `validate_cv.py` passed. CI will run the full Typst + HTML
build on the PR as the final check before a human merges.

## Do not touch

- `src/cv.typ`, `src/render_html.py`, `src/style.css` — renderers. Adding a
  record never requires editing them. If a record seems to *need* a renderer
  change, stop: it's either the wrong section `type` or genuinely new modelling
  that's out of scope for this skill.
- `docs/**` — build outputs, regenerated by CI.
- `cv.schema.json` / `cv.template.json` — the contract and the examples. Adding a
  record uses them; it doesn't change them.

## Quick reference: section types in `cv.json`

`education`, `positions`, `editorial`, `awards`, `grant`, `project`, `visits`,
`talks`, `events`, `courses`, `people`, `text-list`, `named`, `publications`.
Each has a worked example in `src/cv.template.json`; each field's applicable
types are documented in `src/cv.schema.json`.

## Compatibility

This is a standard Agent Skills `SKILL.md`, so it works unmodified in any agent
that discovers `.claude/skills/` — **Claude Code** and **OpenCode** both do (see
`README.md` for how to run it in each). Nothing here is Claude-specific: the
steps use `curl`, `git`, and stdlib `python3`, all of which OpenCode's built-in
bash tool provides too.

When driven by a **smaller local model** (e.g. via OpenCode + Ollama), lean on
the DOI → CSL-JSON path above rather than asking the model to transcribe
bibliographic fields — fetching structured data and trimming it is far more
reliable than free-form extraction, and `validate_cv.py` is the safety net that
catches a malformed entry before it becomes a PR.
