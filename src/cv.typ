// cv.typ — the renderer: turns the structured CV data into a PDF.
//
// This is the single bespoke artifact in the pipeline (ARCHITECTURE.md,
// Decision 2). It owns EVERY formatting decision — what is italic, what is
// quoted, £/€/$ symbols, year-label suppression, sort order. The data files in
// this folder hold only facts. Downstream formats (HTML, Word) read the same
// JSON, never this file.
//
// Typst resolves json() relative to THIS file, so cv.json / publications.json
// must sit beside it in src/.
//
// Build:  typst compile src/cv.typ docs/cv.pdf   (or: make pdf)

#let cv = json("cv.json")

// ===========================================================================
// Helpers
// ===========================================================================

// Group an integer part with thousands separators, keeping any decimals:
// 6788641 -> "6,788,641";  138893.36 -> "138,893.36".
#let group-thousands(n) = {
  let s = str(n)
  let frac = ""
  if s.contains(".") {
    let bits = s.split(".")
    s = bits.at(0)
    frac = "." + bits.at(1)
  }
  let parts = ()
  while s.len() > 3 {
    parts.insert(0, s.slice(s.len() - 3))
    s = s.slice(0, s.len() - 3)
  }
  parts.insert(0, s)
  parts.join(",") + frac
}

// The renderer picks the symbol; the data only stores a currency code.
#let currency-symbol = ("GBP": "£", "EUR": "€", "USD": "$")
#let fmt-amount(a) = currency-symbol.at(a.currency) + group-thousands(a.value)

// Drop a trailing period so the renderer can place it OUTSIDE a closing quote
// (e.g. grant titles: `“…(Imago)”.`, matching the original).
#let unperiod(s) = if s.ends-with(".") { s.slice(0, s.len() - 1) } else { s }

// A URL: monospace (like DOIs) AND clickable. The link show-rule colours it.
#let weblink(url) = link(url, raw(url))

// "Levi J." -> "L. J."; "Daniel" -> "D."
#let initials(given) = (
  given
    .split(" ")
    .map(p => if p.len() > 0 { p.slice(0, 1) + "." } else { "" })
    .join(" ")
)
// Most authors are {family, given}; a corporate author (e.g. "The Alan Turing
// Institute") is CSL's {literal} form instead — print it as-is, no initials.
#let fmt-authors(authors) = (
  authors
    .map(a => if "literal" in a { a.literal } else { a.family + ", " + initials(a.given) })
    .join("; ")
)

#let pub-year(p) = p.issued.at("date-parts").at(0).at(0)

// A CV row: right-aligned label + the entry body, echoing currvita's
// LabelsAligned layout (cvlabelwidth 13mm, cvlabelsep 2mm).
#let entry(label, body) = block(above: 0.95em, below: 0.95em, grid(
  columns: (13mm, 1fr),
  column-gutter: 2mm,
  align(right + top, strong(label)),
  body,
))

// Pair each item with the label to show, blanking it when it repeats the one
// above — the CV's "year once per group, blank on the rest" convention, driven
// from the data (every entry carries its true date; the renderer decides
// display), so reordering can never strand a label on the wrong row.
#let with-labels(items, label-fn) = {
  let prev = none
  let out = ()
  for it in items {
    let d = label-fn(it)
    out.push((if d == prev { "" } else { d }, it))
    prev = d
  }
  out
}
#let by-date = e => e.at("date", default: "")

// small helper: join the present fields of an entry into ". "-separated content
#let sentence(..parts) = parts.pos().filter(p => p != none).join(". ")

// ===========================================================================
// Per-type entry renderers. Each takes the already-resolved date label.
// ===========================================================================

#let render-education(label, e) = entry(label)[
  #e.degree, #e.institution#if "location" in e [ (#e.location)].
  #if "thesis" in e [ \ #emph(e.thesis)]
  #if "supervisor" in e [ \ #text(size: 9pt)[Supervisor: #e.supervisor]]
  #if "committee" in e [ \ #text(size: 9pt)[Committee: #e.committee]]
]

#let render-positions(label, e) = entry(label)[
  #e.role#if "organisation" in e [, #e.organisation]
]

#let render-editorial(label, e) = entry(label)[
  #e.role, #emph(e.journal)
]

#let render-awards(label, e) = entry(label)[
  #emph(e.title)#if "detail" in e [ #e.detail]
]

#let render-grant(label, e) = entry(label)[
  #emph(e.funder) — “#unperiod(e.title)”.#if "scheme" in e [ #e.scheme]#if "code" in e [ #raw(e.code).]#if "role" in e [ #e.role.]#if "period" in e [ #e.period.]#if "amount" in e [ #fmt-amount(e.amount)]
]

#let render-project(label, e) = {
  let head = emph(e.title)
  if "code" in e { head = [#head #raw(e.code)] }
  let parts = (head,)
  if "people" in e { parts.push([#e.people]) }
  if "role" in e { parts.push([#e.role]) }
  if "sponsor" in e { parts.push([Sponsor: #e.sponsor]) }
  if "funding" in e { parts.push([#e.funding]) }
  entry(label, parts.join(". ") + ".")
}

#let render-visits(label, e) = {
  let parts = (e.institution,)
  if "location" in e { parts.push(e.location) }
  if "role" in e { parts.push(e.role) }
  entry(label, parts.join(". ") + ".")
}

#let render-talks(label, e) = entry(label)[
  “#e.title”#if "venue" in e [. #e.venue]
]

#let render-events(label, e) = entry(label)[
  #emph(e.title)#if "detail" in e [. #e.detail]
]

#let render-courses(label, e) = entry(label)[
  #e.name#if "years" in e [ (#e.years)]#if "url" in e [. #weblink(e.url)]
]

#let render-people(label, e) = entry(label)[
  #e.name#if "detail" in e [. #e.detail]
]

#let render-textlist(label, e) = entry(label)[#e.text]

// software / language: the name replaces the date column, so render full width.
#let render-named(e) = block(above: 0.95em, below: 0.95em)[
  #strong(e.name)#if "detail" in e [ — #e.detail]#if "url" in e [ #weblink(e.url)]
]

// CSL-JSON reference, segments joined by ". " so neither an author initial nor a
// closing quote can produce a doubled period.
#let render-pub(label, p) = {
  let parts = ([#fmt-authors(p.author) “#p.title”],)
  if "container-title" in p {
    let venue = emph(p.container-title)
    if "volume" in p { venue = [#venue, #p.volume] }
    if "page" in p { venue = [#venue, #p.page] }
    parts.push(venue)
  }
  if "publisher" in p { parts.push([#p.publisher]) }
  if "DOI" in p { parts.push(raw(p.DOI)) }
  if "URL" in p { parts.push(weblink(p.URL)) }
  entry(label, parts.join(". "))
}

// ===========================================================================
// Dispatch
// ===========================================================================

#let render-entry(kind, label, e) = {
  if kind == "education" { render-education(label, e) }
  else if kind == "positions" { render-positions(label, e) }
  else if kind == "editorial" { render-editorial(label, e) }
  else if kind == "awards" { render-awards(label, e) }
  else if kind == "grant" { render-grant(label, e) }
  else if kind == "project" { render-project(label, e) }
  else if kind == "visits" { render-visits(label, e) }
  else if kind == "talks" { render-talks(label, e) }
  else if kind == "events" { render-events(label, e) }
  else if kind == "courses" { render-courses(label, e) }
  else if kind == "people" { render-people(label, e) }
  else if kind == "text-list" { render-textlist(label, e) }
  else if kind == "named" { render-named(e) }
  else { entry(label, [#e.at("text", default: "")]) }
}

#let render-list(kind, entries) = {
  if kind == "named" {
    for e in entries { render-named(e) }
  } else {
    for (label, e) in with-labels(entries, by-date) { render-entry(kind, label, e) }
  }
}

#let render-publications(section) = {
  let all = json(section.source)
  for g in section.groups {
    heading(level: 2)[#g.title]
    let items = all.filter(p => p.at("category", default: none) == g.category).sorted(key: p => -pub-year(p))
    for (label, p) in with-labels(items, p => str(pub-year(p))) { render-pub(label, p) }
  }
}

// ===========================================================================
// Page + typography
// ===========================================================================

#set page(paper: "us-letter", margin: (x: 1in, y: 1in))
#set text(
  font: ("TeX Gyre Pagella", "Palatino", "Palatino Linotype", "New Computer Modern"),
  size: 12.5pt,
)
// Tight leading WITHIN an item; the larger gap BETWEEN items comes from the
// entry() block spacing below. This contrast (between > within) is what makes
// each multi-line entry read as one visual group, like the LaTeX original.
#set par(justify: true, leading: 0.68em)
#show link: set text(fill: rgb(0, 0, 77))
#set heading(numbering: none)

// Section heading. Spacing is set via block margins + a stack (not loose v()),
// so it is exact and doesn't fight Typst's default block spacing:
//   - generous space ABOVE  -> separates one section from the previous one
//   - title snug to its rule -> the rule reads as part of the title
//   - comfortable space BELOW the rule -> before the section's items
#show heading.where(level: 1): it => block(above: 1.7em, below: 0.8em, stack(
  spacing: 0.3em,
  text(size: 14pt, weight: "bold")[#smallcaps(it.body)],
  line(length: 100%, stroke: 0.5pt),
))

// Sub-section heading (e.g. Awards within Research Income): room above so it
// doesn't crowd the section rule, and a little gap before its own items.
#show heading.where(level: 2): it => block(above: 1.05em, below: 0.7em,
  text(size: 13pt, weight: "bold")[#it.body],
)

// ===========================================================================
// Header
// ===========================================================================

#align(center)[
  #text(tracking: 0.2em)[#upper[#cv.basics.at("title", default: "Curriculum Vitae")]]
  #v(0.15in)
  #text(size: 15pt, weight: "bold")[#smallcaps(cv.basics.name)]
  #v(0.12in)
  #for line in cv.basics.affiliation [#text(size: 9pt)[#line] \ ]
  #v(0.4em)
  #text(size: 9pt)[
    #link("mailto:" + cv.basics.email)[#cv.basics.email]
    #h(1.5em)
    #weblink(cv.basics.url)
  ]
]
#v(1em)

// ===========================================================================
// Sections  (order = render order; each heading becomes a PDF bookmark)
// ===========================================================================

#for section in cv.sections {
  heading(level: 1)[#section.title]
  let kind = section.at("type", default: none)
  if kind == "publications" {
    render-publications(section)
  } else if "groups" in section {
    for g in section.groups {
      heading(level: 2)[#g.title]
      render-list(g.type, g.entries)
    }
  } else {
    render-list(kind, section.entries)
  }
}

// ===========================================================================
// Last-updated stamp at the very end — reproduces currvita's trailing \today,
// so the CV dates itself on every rebuild (e.g. "June 30, 2026").
// ===========================================================================

#v(1.5em)
#datetime.today().display("[month repr:long] [day padding:none], [year]")
