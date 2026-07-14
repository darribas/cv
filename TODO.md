# To-Do

Tracker for important steps to complete on this project. Items will  be
removed as they are checked-off and moved to `LOG.md`.

**NOTE** - Both this file and `LOG.md` is mostly edited by AI agents, use it
as given if useful!

## Further extensions

### AI skill(s) for adding CV records

Author a Claude Code skill (or small set of skills) that lets an agent add a
new entry to the CV — a publication, job, grant, talk, etc. — consistently and
correctly, without re-deriving the data model from scratch each time.

Concretely, this means the skill should encode:

- **Where things live**: `src/cv.json` for CV-body entries, `src/publications.json`
  (CSL-JSON) for publications.
- **How to validate**: entries must conform to `src/cv.schema.json`; the skill
  should check/validate rather than guess at field names.
- **How to author**: use `src/cv.template.json`'s worked examples as the
  copy-paste starting point per section type, following the existing `"//"`/
  `note` comment convention.
- **What not to touch**: the renderers (`src/cv.typ`, `src/render_html.py`) —
  adding a record is a data-only change; it should never require editing
  either renderer.
- **How it lands**: every contribution is drafted on a branch and opened as a
  PR against the repo, never committed straight to `main` — so the change
  history stays clean and each addition is reviewable before it merges.

Open questions to settle before/while building it:

- One general "add a CV record" skill with section-type as an argument, vs.
  separate skills per section (publication vs. job vs. grant)?
- Should it also handle *editing* an existing record, or only appending new ones?
- Does it run any validation/build step itself (e.g. schema check, or a
  local `typst compile`/`render_html.py` dry run) to catch mistakes before
  they're committed, or leave that to the existing CI?

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

### Tooling for building subsets of the CV

In many contexts, organisations require a shorter version of the full CV. It'd
be useful to have an automated way of building these. This could be because
there's less content (e.g., only  a few recent papers) or because less
information needs including (e.g., no links to code repositories for papers,
related to previous point).

