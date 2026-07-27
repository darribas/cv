# To-Do

Tracker for important steps to complete on this project. Items will  be
removed as they are checked-off and moved to `LOG.md`.

**NOTE** - Both this file and `LOG.md` is mostly edited by AI agents, use it
as given if useful!

## Further extensions

### Deployment of other formats

Consider whether it is possible to have other formats (e.g., Word)
automatically built too. An extension of this is, would it be possible for the
GH Pages page to offer the visitor an export that gets built on the go (e.g.,
using pandoc WASM)? Consider, explore options and make a decision.

### Merging with online list of work

I currently maintain a separate list of publications and outputs at:

> https://me.darribas.org/research/

And a separate one for materials and other outputs:

> https://me.darribas.org/materials/

In an ideal world, it'd be good to merge everything into a single source of
truth. The main challenge here is that most of those outputs either don't fit
on a standard CV (e.g., podcast appearances) or do so with less information
(e.g., less URLs).

In this item, we will explore whether it is worth merging all of them, and
how. The key thing is whether doing so will become an issue to generate a clean,
standard academic CV, which is the main need this repo addresses.

**Progress.** The "less URLs" half is done for publications: a publication in
`src/publications.json` carries a `links` array of typed web-only URLs (official
version, code, data, visualisation, …), rendered on the web page behind a "Links"
switch and never in the PDF, and the research page's links are now transcribed in
(140 links, 88 publications). See `LOG.md` and `ARCHITECTURE.md` Decision 4. That
answers the key question above — merging this kind of information does *not*
compromise the clean academic PDF, because the PDF renderer simply never reads
the field.

**Direction settled.** This repo is intended to *replace* the website's research
page, not to sync with it. So the transcription above is a one-way import, and
there is no ongoing reconciliation to build: once the website points at (or is
generated from) this data, `publications.json` is the only copy.

What remains:

- **The `materials/` page** — split out into its own item below, since it turned
  out to be three separate problems rather than one.
- **One missing link** — tracked as issue #10. "Improving the Multi-Dimensional
  Comparison of Simulation Results" has no `official` link, because the
  website's published-version URL for it actually points at a different paper
  (see `LOG.md`) and `doi.org`/`api.crossref.org` were unreachable from the
  build sandbox to look up the real one. Needs the correct DOI adding by hand.
- Possibly **access status** (Open Access / paywalled), which the website marks
  on every link and this model does not carry. Would be a new optional key.
- Possibly **a schema for `publications.json`**. `cv.json` gets editor
  autocomplete, hover docs and live validation from `cv.schema.json`
  (`ARCHITECTURE.md` Decision 3); `publications.json` has never had a schema,
  because CSL-JSON is a standard the file simply conforms to. That asymmetry
  mattered less when every field was standard CSL. Now the file also carries a
  hand-authored, vocabulary-constrained `links` array, where a mistyped kind is
  caught only by running `validate_cv.py` — not by the editor, as you type.

### Bringing in the Materials page

The second website page the item above names:

> https://me.darribas.org/materials/

It holds **13 talk videos**, **4 audio appearances** (podcasts), and **30
artefacts** (courses, workshops, teaching materials, tools). This is a synthesis
of the design discussion; nothing here is built yet, and it is deliberately a
separate PR from the publications links.

**It is three problems, not one.** The page looks homogeneous but each third
wants a different treatment:

1. **Talk videos → enrich existing records.** Most of these talks are already in
   *Invited Lectures* (the CASA one, the Turing one, the AEG congress talk).
   They don't need new entries; they need a `video` link on the entry that
   already exists. This is exactly what publications just got, applied to
   `talks`.
2. **Audio / podcasts → genuinely new, and the only real modelling question.**
   Monocle, MapScaping, the Liverpool and Bedrock podcasts have no home in the
   CV at all. Options: a new section that is fine on an academic CV (e.g.
   "Media"), a web-only section, or leaving them on the website. **Undecided —
   decide this before writing anything.**
3. **Artefacts → an existing entry shape.** No date column, a name, a sentence
   of prose, and a list of links: that is almost exactly the current `named`
   type (used by *Scientific Software* — bold name, em-dash detail, URL,
   rendered full width). A Materials section could be `named` entries plus a
   `links` array, needing essentially no new layout code.

**It is partly deduplication, not just addition.** Measured against the current
data: of 28 artefact URLs sampled, **7 are already in the CV** (`gds_env`,
`gds_course`, `wmn`, `spa_notes`, `sdar_mini`, `WooWii` — sitting in *Teaching*
and *Scientific Software*, or already imported as publication links) and **21
are new**. So a chunk of the work is adding the repository link to a course that
already carries its website, *not* creating a second record for it. Check before
adding: duplicate entries would be worse than the current split.

**The vocabulary already covers it.** Every link kind the page uses exists:
`video` (YouTube/streams), `slides`, `notebook` (the Binder "Interactive App"
launchers), `site`, `code`, `docs`, and `data`/`official` for the Zenodo and
figshare DOI badges. The kinds left unused by the publications import turn out
to be precisely the ones this page needs — which is why they were kept.

**Known blocker — start here.** `links` currently only works in
`publications.json`. The moment a **`cv.json`** entry needs one — a talk with
its video, an artefact with its repository — `cv.schema.json` rejects it,
because `$defs/entry` sets `"additionalProperties": false`. Verified: adding
`links` to a `talks` or a `named` entry fails validation with *"unexpected key
'links'"*. So step one is adding `links` to `$defs/entry` (and to
`$defs/group`/`section` if a whole section should ever carry them). Not done as
part of the publications work, since no `cv.json` entry used the field yet.

**Renderer work is small.** `render_links()` in `render_html.py` is already
generic, and `entry()` is the shared row helper both `render_pub` and the
`cv.json` renderers use — so `render-talks`/`render-named` each need the same
one-line append that `render_pub` got. `cv.typ` needs nothing, as before.

**The actual decision is editorial, not technical.** Which of the 30 artefacts
belong on a standard academic CV's PDF, and which are web-only? The model
supports having it both ways — a section in `cv.json` whose name and description
print in the PDF while its link row stays on the web — so this is a judgement
about what the CV should say, not a constraint of the pipeline.

### Tooling for building subsets of the CV

In many contexts, organisations require a shorter version of the full CV. It'd
be useful to have an automated way of building these. This could be because
there's less content (e.g., only  a few recent papers) or because less
information needs including (e.g., no links to code repositories for papers,
related to previous point).

