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
(140 links, 87 publications). See `LOG.md` and `ARCHITECTURE.md` Decision 4. That
answers the key question above — merging this kind of information does *not*
compromise the clean academic PDF, because the PDF renderer simply never reads
the field.

**Direction settled.** This repo is intended to *replace* the website's research
page, not to sync with it. So the transcription above is a one-way import, and
there is no ongoing reconciliation to build: once the website points at (or is
generated from) this data, `publications.json` is the only copy.

What remains:

- **Decide about outputs that don't fit a CV at all** (podcast appearances,
  blog posts, the `materials/` page). These are a different question from
  extra URLs on an existing entry: they need either new CV sections, a
  web-only section type, or to stay on the website. Undecided.
- **One missing link.** "Improving the Multi-Dimensional Comparison of
  Simulation Results" has no `official` link, because the website's published-
  version URL for it actually points at a different paper (see `LOG.md`) and
  `doi.org`/`api.crossref.org` were unreachable from the build sandbox to look
  up the real one. Needs the correct DOI adding by hand.
- Possibly **access status** (Open Access / paywalled), which the website marks
  on every link and this model does not carry. Would be a new optional key.

### Tooling for building subsets of the CV

In many contexts, organisations require a shorter version of the full CV. It'd
be useful to have an automated way of building these. This could be because
there's less content (e.g., only  a few recent papers) or because less
information needs including (e.g., no links to code repositories for papers,
related to previous point).

