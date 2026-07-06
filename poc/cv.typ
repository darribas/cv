// cv.typ — minimal renderer over the structured CV data (proof-of-concept).
//
// This is the SINGLE bespoke artifact in the pipeline. It owns every formatting
// decision (venue italic, DOI monospace, £/€/$ symbols, sort-by-year, and the
// "year once per group" label convention); the data files hold only facts.
// Downstream formats (HTML, Word) will read the same JSON, never this file.
//
// Build:  typst compile cv.typ cv.pdf

#let cv = json("cv.json")

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// Group an integer with thousands separators: 6788641 -> "6,788,641".
#let group-thousands(n) = {
  let s = str(n)
  let parts = ()
  while s.len() > 3 {
    parts.insert(0, s.slice(s.len() - 3))
    s = s.slice(0, s.len() - 3)
  }
  parts.insert(0, s)
  parts.join(",")
}

// The renderer picks the symbol; the data only stores a currency code.
#let currency-symbol = ("GBP": "£", "EUR": "€", "USD": "$")
#let fmt-amount(a) = currency-symbol.at(a.currency) + group-thousands(a.value)

// "Levi J." -> "L. J."; "Daniel" -> "D."
#let initials(given) = (
  given
    .split(" ")
    .map(p => if p.len() > 0 { p.slice(0, 1) + "." } else { "" })
    .join(" ")
)
#let fmt-authors(authors) = (
  authors
    .map(a => a.family + ", " + initials(a.given))
    .join("; ")
)

#let pub-year(p) = p.issued.at("date-parts").at(0).at(0)

// A CV row: a right-aligned date label + the entry body, echoing currvita's
// LabelsAligned layout (cvlabelwidth 13mm, cvlabelsep 2mm).
#let entry(label, body) = block(above: 0.45em, below: 0.45em, grid(
  columns: (13mm, 1fr),
  column-gutter: 2mm,
  align(right + top, strong(label)),
  body,
))

// Pair each item with the label to display, blanking it when it repeats the
// one above. This reproduces the CV's "year on the first row of a group, blank
// on the rest" convention *from the data*: every entry carries its true date,
// and the renderer alone decides whether to print it — so inserting or
// reordering entries can never strand the label on the wrong row.
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

// ---------------------------------------------------------------------------
// Per-section renderers (keyed off section "type"); each takes the already
// resolved date label so the group-suppression above stays in one place.
// ---------------------------------------------------------------------------

#let render-education(label, e) = entry(label)[
  #e.degree, #e.institution#if "location" in e [ (#e.location)].
  #if "thesis" in e [ \ #emph(e.thesis)]
  #if "supervisor" in e [ \ #text(size: 9pt)[Supervisor: #e.supervisor]]
  #if "committee" in e [ \ #text(size: 9pt)[Committee: #e.committee]]
]

#let render-appointment(label, e) = entry(label)[
  #e.role#if "organisation" in e [, #e.organisation]
]

#let render-income(label, e) = entry(label)[
  #emph(e.funder) — #e.title#if "scheme" in e [ #e.scheme] #e.role.#if "period" in e [ #e.period.]#if "amount" in e [ #fmt-amount(e.amount)]
]

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
  if "URL" in p { parts.push(link(p.URL)) }
  entry(label, parts.join(". "))
}

// ---------------------------------------------------------------------------
// Page + typography
// ---------------------------------------------------------------------------

#set page(paper: "us-letter", margin: (x: 1in, y: 1in))
#set text(
  font: ("TeX Gyre Pagella", "Palatino", "Palatino Linotype", "New Computer Modern"),
  size: 11pt,
)
#set par(justify: true, leading: 0.55em)
#show link: set text(fill: rgb(0, 0, 77))
#set heading(numbering: none)
#show heading.where(level: 1): it => {
  v(0.9em, weak: true)
  text(size: 12pt, weight: "bold")[#smallcaps(it.body)]
  v(0.15em)
  line(length: 100%, stroke: 0.4pt)
  v(0.25em, weak: true)
}

// ---------------------------------------------------------------------------
// Header
// ---------------------------------------------------------------------------

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
    #link(cv.basics.url)
  ]
]
#v(1em)

// ---------------------------------------------------------------------------
// Sections (order = render order; each heading becomes a PDF bookmark)
// ---------------------------------------------------------------------------

#let by-date = e => e.at("date", default: "")

#for section in cv.sections {
  heading(level: 1)[#section.title]
  let kind = section.at("type")
  if kind == "education" {
    for (label, e) in with-labels(section.entries, by-date) { render-education(label, e) }
  } else if kind == "appointments" {
    for (label, e) in with-labels(section.entries, by-date) { render-appointment(label, e) }
  } else if kind == "research-income" {
    for (label, e) in with-labels(section.entries, by-date) { render-income(label, e) }
  } else if kind == "publications" {
    // Descending years, but stable within a year so source order is preserved.
    let pubs = json(section.at("source")).sorted(key: p => -pub-year(p))
    for (label, p) in with-labels(pubs, p => str(pub-year(p))) { render-pub(label, p) }
  }
}
