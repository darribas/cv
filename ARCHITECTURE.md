# Architecture & Design Decisions

This document records the design decisions behind the CV build pipeline: the
alternatives considered, their trade-offs, and why we chose what we chose. It
is a decision log, not a how-to — implementation details live elsewhere as they
are built.

## Context

The repository currently holds a single source file, `cv-darribas.tex` (~1,760
lines): an `article` + `currvita` LaTeX CV. The `TODO.md` goals are, in order:

1. Clean up the source and give it **real sectioning** (the current sections
   are visual only — `currvita`'s `\begin{cvlist}{...}` emits no `\section`, so
   the PDF has no bookmarks/TOC).
2. Decide on a **PDF engine** (keep LaTeX, or move to something like Typst).
3. A **GitHub Action** that rebuilds and commits the PDF on every push.
4. A **GitHub Pages HTML** version generated from the same source (elegant,
   aligned with the PDF look, *no per-format manual edits* — the source must
   stay the single source of truth).
5. Later: **other formats** (Word, on-the-fly export), **merging** the online
   publication/materials lists at `me.darribas.org`, and **subset CVs** (shorter
   or reduced-information variants).

A key early finding shaped everything: **the CV is typographically trivial.**
It defines exactly one custom macro (`\ac`, a cosmetic `\mbox`), is
near-pure-ASCII (only 3 non-ASCII characters, all in commented-out lines), and
every entry follows the same regular shape (`[date] authors "title" venue doi`).
It is, in effect, **structured data wearing a thin LaTeX coat** — with ~305
commented-out lines and vim fold markers as cruft. This means a migration is
low-risk, and that the content wants to be modelled as data.

## Decision 1 — Build engine: **Typst**

### Alternatives considered

- **Stay with LaTeX (restructured).** Keep content and typography; clean the
  cruft, move to UTF-8, add real `\section` + `hyperref` bookmarks.
  - *Pros:* zero migration risk; content untouched.
  - *Cons:* heavy CI (full TeXLive); HTML export (make4ht / lwarp) is the
    painful, rarely-elegant path; subset builds mean LaTeX conditionals. Weakest
    on exactly the two things we most want (elegant HTML, low-friction
    multi-format), and its one advantage (no migration) barely matters given how
    simple the content is.
- **Typst.** Modern single-binary engine.
  - *Pros:* real headings → **free PDF outline/TOC**; near-instant builds →
    trivial GitHub Action (no TeXLive); it is a real programming language, so
    **subset CVs become a function argument** rather than conditional hell; the
    regular entry shape collapses into one reusable render function; UTF-8 native
    (the `latin9`/`eurosym` legacy just disappears).
  - *Cons:* young (2023); **HTML export is experimental**; **no native Word
    export** and pandoc cannot read Typst (see Decision 2 for how we neutralise
    this).
- **Structured content + pandoc/templates.** Move content into data and render
  PDF/HTML/Word all through pandoc.
  - *Pros:* best native multi-format story (HTML and Word first-class).
  - *Cons:* largest rewrite; least fine-grained typographic control over the PDF.

### Why Typst

Typst wins clearly on cleanup, sectioning/TOC, CI, and subset builds, and the
migration risk that would normally count against it is small here because the
content is so simple and regular. Its real weaknesses (HTML, Word) are addressed
by Decision 2, not by the engine choice.

### The caveat that forced Decision 2: "Typst is an ecosystem island"

Every genuinely hard TODO item is one where **another tool must consume the
source**: HTML export, Word, feeding the website. Markdown is parseable by
everything; LaTeX by a lot (pandoc, TeX4ht, lwarp); **Typst only by Typst.** So
choosing Typst is only safe if no downstream tool ever has to read Typst — which
leads directly to separating data from rendering.

## Decision 2 — Separate **data** from **rendering**

The CV content is stored as structured **data**; the Typst file is a *renderer*
over that data, not the content itself. All formatting decisions ("venue is
italic", "DOI is monospace", "amounts use £", "sort by year") live in the
renderer; the data holds only facts.

### Why this is the load-bearing decision

- It dissolves the "Typst is an island" problem: **no downstream tool ever reads
  Typst** — they all read the data. PDF ← Typst; HTML ← a second template/script
  over the same data; Word ← data → Markdown → pandoc; website ← the same
  structured publications; subsets ← filter the data before rendering.
- It **de-risks the young engine.** The durable asset is the data; the renderer
  is swappable. If Typst stalls in five years, the validated data is untouched
  and re-renders with whatever is best then. The data/render split is what makes
  betting on a 2023 engine safe.
- It must be committed to **now (in the cleanup phase)**, because retrofitting a
  data layer after hand-authoring everything in Typst markup is the expensive
  path.

The one honest limit: no format removes *all* bespoke code. A custom look (the
Palatino academic feel, an elegant HTML twin) means *someone* writes a template.
The irreducible bespoke artifact is a single renderer template — not "fiddly
scripts", plural. Everything else is standards.

## Decision 3 — Data format: **JSON** (+ JSON Schema), publications as **CSL-JSON**

We explored the format question at length because it governs day-to-day
authoring. The guiding criteria (stated by the author) were: **robust · easy to
keep updating by hand · minimal reliance on fiddly scripts · built on long-lived
standards.**

### Alternatives considered

- **YAML.** Same data model as JSON; Typst reads it natively; JSON Schema can
  validate it.
  - *Pros:* comments; low visual noise; nice multiline prose (block scalars).
  - *Cons:* whitespace-sensitive footguns; type-coercion gotchas (the "Norway
    problem", unquoted `:`); a complex spec. Weaker on *robustness* and *simple
    standard* — two of the stated criteria. Rejected primarily because the author
    does not like editing YAML.
- **Structured Markdown (headings = sections, bullets = entries, `key: value`
  sub-bullets = fields).**
  - *Pros:* the most pleasant to hand-write, especially for the ~80% of the CV
    that is narrative prose.
  - *Cons:* freeform markdown is **lossy to parse back into fields** — extracting
    author/title/venue from typographic cues is fragile scraping. Requires a
    **bespoke parser**, i.e. exactly the "fiddly script" we want to avoid.
    Rejected on the minimal-scripts criterion.
- **Everything as BibTeX/BibLaTeX** (custom entry types like `@education`,
  `@grant`).
  - *Pros:* one format; stable citation keys; native name-list handling.
  - *Cons:* bib's tooling superpowers (Zotero/ORCID export, pandoc/Typst native
    reading) are **bibliography-shaped** — they only apply to standard entry
    types. Custom `@education`/`@grant` types are off-label: external tools ignore
    them, so the ecosystem advantage evaporates for the non-publication ~80% of
    the CV, where bib also re-imports the very record-noise that made YAML
    unappealing. Rejected as the *universal* format (but retained in spirit for
    publications — see below).
- **JSON (+ JSON Schema).**
  - *Pros:* the most durable, universal standard; **parser-free** (built into
    Typst's `json()` and every language — no bespoke parser to maintain);
    robust/unambiguous; **JSON Schema** (itself a standard) gives editor
    autocomplete, hover docs, and live validation, which both hardens the data
    and makes hand-editing pleasant.
  - *Cons:* no native comments; brace/quote/trailing-comma noise; awkward
    multiline prose. The comment gap is addressed below.

### Why JSON

The author's stated criteria (robust, long-lived standard, minimal scripts)
point at JSON, and away from markdown-with-a-parser. JSON's one real weakness —
hand-editing ergonomics — is closed with **standards, not scripts**:

- A **JSON Schema** (`"$schema": "./cv.schema.json"`) gives VS Code field
  autocomplete, per-field descriptions on hover, and red-underlines for missing
  or mistyped keys as you edit.
- **Comments** are provided via `"//"` / `"note"` fields that the renderer
  ignores (it only reads keys it knows). This stays **strict, Typst-readable
  JSON with no preprocessing step** — unlike JSONC/JSON5, whose real `//`
  comments would need a strip step (a fiddly script) because Typst's `json()`
  parses strict JSON only. A key may also be prefixed with `//` to annotate one
  specific field (e.g. `"//url": "optional — delete if no link"`); the schema
  allows keys matching `^//`.
- A **`cv.template.json`** holds one fully-worked, annotated example per section
  type. Adding an entry = copy a block, paste into the section's array, change
  the values, delete the `//` hints. The schema guides and checks the edit.

Note this is *architecturally identical* to the YAML proposal — same separation,
same schema, same CSL for publications, same swappable renderer. The choice is
pure surface syntax, and it is **the most reversible decision in the project**: a
one-line converter flips JSON↔YAML with nothing else downstream changing.

### Publications: **CSL-JSON**

Publications are the one section where a purpose-built format genuinely pays off,
and CSL-JSON keeps the "everything is JSON" principle intact:

- It is the JSON standard for bibliographic data — what **Zotero exports**, what
  **pandoc** consumes, and what **Typst** reads.
- It is therefore also the zero-script answer to the "merge my online
  publication list" goal, and it unlocks sort-by-year, dedup, and per-format link
  inclusion for free.

## Chosen architecture (summary)

- **Source of truth:** structured data.
  - CV body → **JSON** validated by a **JSON Schema**, with `"//"`/`note` fields
    for comments and a `cv.template.json` of copy-paste examples.
  - Publications → **CSL-JSON**.
- **Rendering:** **Typst** reads the JSON directly (no preprocessing) and
  produces the PDF; real headings give a free PDF outline/TOC. The renderer owns
  all formatting and is the single bespoke artifact.
- **Downstream (later), all consuming the same data, never Typst:**
  - HTML (GitHub Pages) ← a second template/script over the data.
  - Word ← data → Markdown → pandoc.
  - Website feed ← the CSL-JSON publications.
  - Subset CVs ← filter the data before rendering.
- **CI:** a GitHub Action installs the Typst binary (seconds, no TeXLive),
  rebuilds, and commits the PDF. Fonts are solved by bundling TeX Gyre Pagella
  in `fonts/` and passing `--font-path fonts` (wired into the Makefile), so
  the runner needs nothing beyond the Typst binary itself — no system font
  install step.

### Why this satisfies the criteria

- **Robust:** strict JSON + schema validation; unambiguous, parser-free.
- **Long-lived standards:** JSON, JSON Schema, CSL-JSON — all durable and
  engine-independent. The data outlives any renderer.
- **Minimal scripts:** Typst reads the data directly; the only bespoke code is
  one renderer template. Comments and templates use conventions, not tooling.
- **Easy to update:** copy a template block and edit; the editor autocompletes,
  documents, and validates as you go.

## Known costs & open questions

- **HTML is a second Python renderer, not Typst's HTML export** — tested
  directly against `cv.typ` (Typst 0.15, `--features html`): it silently drops
  nearly all content, because `grid`/`stack`/`align`/`v()` are ignored during
  HTML export, and `entry()` — the layout helper every section type but
  `named` routes through — is built on `grid`. Confirms Decision 2's plan
  (HTML ← a second template/script over the same data) rather than reworking
  the PDF renderer's layout to accommodate an incomplete export path.
- **Web-only / PDF-extended fields** (e.g. a publication's code-repository
  URL — informal for a standard academic PDF, but worth showing on the web,
  and possibly in an alternate PDF variant): no data-model change needed for
  the web-only case — a renderer only shows a field if its template
  references it, so a new field just stays invisible to whichever renderer
  doesn't mention it. For an *extended PDF variant* that opts into such
  fields, the plan is a `sys.inputs` flag in `cv.typ` (e.g. `variant`,
  read via `--input variant=extended`), gating the one or two spots that
  read extra fields — deferred until the website-merge TODO item actually
  introduces the first such field, since it costs nothing to add then and
  there's nothing to scaffold against yet.

## Status

Decisions 1–3 validated and the full migration is complete: every section of
the original `.tex` now lives in `src/cv.json`/`src/publications.json`, spot-
checked verbatim against the source (see `notes/MIGRATION-REVIEW.md`).
Hand-editing JSON did feel good in practice — the schema's autocomplete/hover
docs and the template file were enough; a scratchpad proof-of-concept validated
this early on and has since been removed as redundant with `src/`. The
original `.tex` and its one-shot migration parser have likewise been retired
(`notes/MIGRATION-REVIEW.md` has the commit).
