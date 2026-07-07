# To-Do

Tracker for important steps to complete on this project. Items will  be
removed as they are checked-off and moved to `LOG.md`.

**NOTE** - Both this file and `LOG.md` is mostly edited by AI agents, use it
as given if useful!

## Important

### GH Pages rendering

Once the PDF build is stable, add a HTML build that creates a web version of
the CV. This should be elegant, aligned with the look of the PDF, and require
no changes from the source file so that can remain the main source of truth
and is the only one to be edited.

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

### Tooling for building subsets of the CV

In many contexts, organisations require a shorter version of the full CV. It'd
be useful to have an automated way of building these. This could be because
there's less content (e.g., only  a few recent papers) or because less
information needs including (e.g., no links to code repositories for papers,
related to previous point).

