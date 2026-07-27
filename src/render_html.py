#!/usr/bin/env python3
"""render_html.py — the second renderer: turns the same structured CV data
into a static HTML page for GitHub Pages.

This is the second bespoke artifact the architecture allows (ARCHITECTURE.md,
Decision 2): it reads src/cv.json + src/publications.json directly — the same
data cv.typ reads — and makes its own formatting decisions. Never reads or
depends on cv.typ; the two renderers are independent templates over shared
data, kept visually aligned by hand, not by shared code.

Build:  python3 src/render_html.py   (or: make html)
"""
import json
import re
import shutil
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
DOCS = ROOT / "docs"
FONTS = ROOT / "fonts" / "texgyrepagella"

cv = json.loads((SRC / "cv.json").read_text(encoding="utf-8"))


# ===========================================================================
# Helpers
# ===========================================================================

def esc(s):
    """HTML-escape a value; pass through non-strings (e.g. filter default None)."""
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def group_thousands(n):
    """6788641 -> '6,788,641'; 138893.36 -> '138,893.36'."""
    s = str(n)
    frac = ""
    if "." in s:
        s, frac = s.split(".")
        frac = "." + frac
    parts = []
    while len(s) > 3:
        parts.insert(0, s[-3:])
        s = s[:-3]
    parts.insert(0, s)
    return ",".join(parts) + frac


CURRENCY_SYMBOL = {"GBP": "£", "EUR": "€", "USD": "$"}


def fmt_amount(a):
    return CURRENCY_SYMBOL[a["currency"]] + group_thousands(a["value"])


def unperiod(s):
    """Drop a trailing period so it can be placed OUTSIDE a closing quote."""
    return s[:-1] if s.endswith(".") else s


def weblink(url):
    return f'<a class="mono" href="{esc(url)}">{esc(url)}</a>'


# Web-only extras (ARCHITECTURE.md, "Web-only / PDF-extended fields"): a record
# may carry a `links` array of {type, url} — the material listed alongside the
# same output on me.darribas.org (official version, code, data, a live map…).
# The data stores only the link's *kind*; the renderer owns the wording, and
# this dict's ORDER is also the display order, so every record lists its extras
# in the same sequence regardless of how they were typed in. cv.typ never reads
# `links`, which is exactly why they stay out of the PDF.
LINK_LABELS = {
    # the version of record, and the versions that stand in for it
    "official": "Official version",
    "accepted": "Accepted version",
    "preprint": "Working paper",
    "pdf": "PDF",
    # what the work is made of
    "code": "Code",
    "data": "Data",
    "notebook": "Notebook",
    # where it can be seen or read about
    "viz": "Visualisation",
    "site": "Website",
    "docs": "Documentation",
    "slides": "Slides",
    "video": "Video",
    "poster": "Poster",
    "blog": "Blog post",
}


def link_label(l):
    """Renderer-owned wording. An explicit `label` wins (one-offs like
    'Interactive map'); an unknown type degrades to its own name rather than
    disappearing, so new kinds render before this dict learns about them."""
    if "label" in l:
        return l["label"]
    return LINK_LABELS.get(l["type"], l["type"].replace("-", " ").capitalize())


def link_rank(l):
    keys = list(LINK_LABELS)
    return keys.index(l["type"]) if l["type"] in keys else len(keys)


def render_links(links):
    """The web-only extras row. Hidden/shown wholesale by the header's "Links"
    switch — a checkbox in style.css, no JS (see render_links_switch)."""
    if not links:
        return ""
    pills = "".join(
        f'<a class="weblink" href="{esc(l["url"])}">{esc(link_label(l))}</a>'
        for l in sorted(links, key=link_rank)
    )
    return f'<div class="weblinks">{pills}</div>'


def initials(given):
    return " ".join(p[0] + "." for p in given.split(" ") if p)


def fmt_authors(authors):
    def one(a):
        if "literal" in a:
            return esc(a["literal"])
        return f'{esc(a["family"])}, {esc(initials(a["given"]))}'
    return "; ".join(one(a) for a in authors)


def pub_year(p):
    return p["issued"]["date-parts"][0][0]


def entry(label, body):
    """A CV row: label column + body, mirroring cv.typ's entry() grid."""
    return (f'<div class="entry"><div class="date">{esc(label)}</div>'
            f'<div class="body">{body}</div></div>')


def with_labels(items, label_fn):
    """Pair each item with its label, blanking repeats of the previous one."""
    out = []
    prev = None
    for it in items:
        d = label_fn(it)
        out.append(("" if d == prev else d, it))
        prev = d
    return out


def by_date(e):
    return e.get("date", "")


def sentence(*parts):
    return ". ".join(p for p in parts if p is not None)


# ===========================================================================
# Per-type entry renderers. Each takes the already-resolved date label.
# ===========================================================================

def render_education(label, e):
    body = f'{esc(e["degree"])}, {esc(e["institution"])}'
    if "location" in e:
        body += f' ({esc(e["location"])})'
    body += "."
    if "thesis" in e:
        body += f'<br>{"".join(["<em>", esc(e["thesis"]), "</em>"])}'
    if "supervisor" in e:
        body += f'<br><span class="small">Supervisor: {esc(e["supervisor"])}</span>'
    if "committee" in e:
        body += f'<br><span class="small">Committee: {esc(e["committee"])}</span>'
    return entry(label, body)


def render_positions(label, e):
    body = esc(e["role"])
    if "organisation" in e:
        body += f', {esc(e["organisation"])}'
    return entry(label, body)


def render_editorial(label, e):
    return entry(label, f'{esc(e["role"])}, <em>{esc(e["journal"])}</em>')


def render_awards(label, e):
    body = f'<em>{esc(e["title"])}</em>'
    if "detail" in e:
        body += f' {esc(e["detail"])}'
    return entry(label, body)


def render_grant(label, e):
    body = f'<em>{esc(e["funder"])}</em> — “{esc(unperiod(e["title"]))}”.'
    if "scheme" in e:
        body += f' {esc(e["scheme"])}'
    if "code" in e:
        body += f' <code>{esc(e["code"])}</code>.'
    if "role" in e:
        body += f' {esc(e["role"])}.'
    if "period" in e:
        body += f' {esc(e["period"])}.'
    if "amount" in e:
        body += f' {esc(fmt_amount(e["amount"]))}'
    return entry(label, body)


def render_project(label, e):
    head = f'<em>{esc(e["title"])}</em>'
    if "code" in e:
        head += f' <code>{esc(e["code"])}</code>'
    parts = [head]
    if "people" in e:
        parts.append(esc(e["people"]))
    if "role" in e:
        parts.append(esc(e["role"]))
    if "sponsor" in e:
        parts.append(f'Sponsor: {esc(e["sponsor"])}')
    if "funding" in e:
        parts.append(esc(e["funding"]))
    return entry(label, ". ".join(parts) + ".")


def render_visits(label, e):
    parts = [esc(e["institution"])]
    if "location" in e:
        parts.append(esc(e["location"]))
    if "role" in e:
        parts.append(esc(e["role"]))
    return entry(label, ". ".join(parts) + ".")


def render_talks(label, e):
    body = f'“{esc(e["title"])}”'
    if "venue" in e:
        body += f'. {esc(e["venue"])}'
    return entry(label, body)


def render_events(label, e):
    body = f'<em>{esc(e["title"])}</em>'
    if "detail" in e:
        body += f'. {esc(e["detail"])}'
    return entry(label, body)


def render_courses(label, e):
    body = esc(e["name"])
    if "years" in e:
        body += f' ({esc(e["years"])})'
    if "url" in e:
        body += f'. {weblink(e["url"])}'
    return entry(label, body)


def render_people(label, e):
    body = esc(e["name"])
    if "detail" in e:
        body += f'. {esc(e["detail"])}'
    return entry(label, body)


def render_textlist(label, e):
    body = esc(e["text"])
    if "url" in e:
        body += f'. {weblink(e["url"])}'
    return entry(label, body)


def render_named(e):
    """software / language: the name replaces the date column, full width."""
    body = f'<strong>{esc(e["name"])}</strong>'
    if "detail" in e:
        body += f' — {esc(e["detail"])}'
    if "url" in e:
        body += f' {weblink(e["url"])}'
    return f'<div class="named">{body}</div>'


def render_pub(label, p):
    parts = [f'{fmt_authors(p["author"])} “{esc(p["title"])}”']
    if "container-title" in p:
        venue = f'<em>{esc(p["container-title"])}</em>'
        if "volume" in p:
            venue += f', {esc(p["volume"])}'
        if "page" in p:
            venue += f', {esc(p["page"])}'
        parts.append(venue)
    if "publisher" in p:
        parts.append(esc(p["publisher"]))
    if "DOI" in p:
        parts.append(f'<code>{esc(p["DOI"])}</code>')
    if "URL" in p:
        parts.append(weblink(p["URL"]))
    return entry(label, ". ".join(parts) + render_links(p.get("links")))


# ===========================================================================
# Dispatch
# ===========================================================================

RENDERERS = {
    "education": render_education,
    "positions": render_positions,
    "editorial": render_editorial,
    "awards": render_awards,
    "grant": render_grant,
    "project": render_project,
    "visits": render_visits,
    "talks": render_talks,
    "events": render_events,
    "courses": render_courses,
    "people": render_people,
    "text-list": render_textlist,
}


def render_entry(kind, label, e):
    fn = RENDERERS.get(kind)
    if fn:
        return fn(label, e)
    return entry(label, esc(e.get("text", "")))


def render_list(kind, entries):
    if kind == "named":
        return "".join(render_named(e) for e in entries)
    return "".join(render_entry(kind, label, e)
                   for label, e in with_labels(entries, by_date))


def render_publications(section):
    all_pubs = json.loads((SRC / section["source"]).read_text(encoding="utf-8"))
    out = []
    for g in section["groups"]:
        out.append(f'<h3 id="{slug(section["title"])}-{slug(g["title"])}">{esc(g["title"])}</h3>')
        items = sorted(
            (p for p in all_pubs if p.get("category") == g["category"]),
            key=pub_year, reverse=True,
        )
        labelled = with_labels(items, lambda p: str(pub_year(p)))
        out.append("".join(render_pub(label, p) for label, p in labelled))
    return "".join(out)


# ===========================================================================
# Page assembly
# ===========================================================================

def slug(title):
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s


def render_section(section):
    title = section["title"]
    kind = section.get("type")
    out = [f'<section id="{slug(title)}"><h2>{esc(title)}</h2>']
    if kind == "publications":
        out.append(render_publications(section))
    elif "groups" in section:
        for g in section["groups"]:
            out.append(f'<h3 id="{slug(title)}-{slug(g["title"])}">{esc(g["title"])}</h3>')
            out.append(render_list(g["type"], g["entries"]))
    else:
        out.append(render_list(kind, section["entries"]))
    out.append("</section>")
    return "".join(out)


def render_toc_popover():
    """A floating panel via the native Popover API (see the "Sections" button
    in render_header) — no JS: the popovertarget attribute wires up show/hide,
    outside-click and Escape dismissal for free."""
    items = "".join(
        f'<li><a href="#{slug(s["title"])}">{esc(s["title"])}</a></li>'
        for s in cv["sections"]
    )
    return f'<nav id="toc-pop" popover><ul>{items}</ul></nav>'


def render_links_switch():
    """The state half of the "Links" toggle: a visually-hidden checkbox placed
    before <main>, so style.css can drive the whole page from `#show-links:checked
    ~ main …`. Its visible half is the <label> button in render_header(). No JS —
    same spirit as the Sections popover. The trade-off is that the choice resets
    on reload (there is nowhere to persist it without script); `checked` here is
    what the page opens with."""
    return '<input type="checkbox" id="show-links" class="visually-hidden" checked>'


def render_actions():
    """The control bar. It is a sibling of <header> rather than a child so that
    its containing block is <main> — which spans the whole document — letting
    `position: sticky` keep it pinned all the way down the page. Inside
    <header> it would unstick as soon as the header scrolled away."""
    return '''<div class="header-actions">
  <div class="btn-group">
    <button popovertarget="toc-pop" class="btn-pdf btn-toc">Sections</button>
    <label class="btn-pdf btn-links" for="show-links">Links</label>
  </div>
  <a class="btn-pdf" href="cv.pdf" download>PDF</a>
</div>'''


def render_header():
    basics = cv["basics"]
    lines = "".join(f'{esc(l)}<br>' for l in basics["affiliation"])
    title = basics.get("title", "Curriculum Vitae")
    return f'''<header>
  <p class="doctitle">{esc(title.upper())}</p>
  <h1>{esc(basics["name"])}</h1>
  <p class="affiliation">{lines}</p>
  <p class="contact">
    <a href="mailto:{esc(basics["email"])}">{esc(basics["email"])}</a>
    &emsp;{weblink(basics["url"])}
  </p>
</header>'''


def render_footer():
    stamp = datetime.date.today().strftime("%B %-d, %Y")
    return f'<footer>{stamp}</footer>'


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} — {doctitle}</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
{links_switch}
{toc_popover}
<main>
{actions}
{header}
{sections}
{footer}
</main>
</body>
</html>
"""


def main():
    sections_html = "\n".join(render_section(s) for s in cv["sections"])
    html = PAGE.format(
        name=esc(cv["basics"]["name"]),
        doctitle=esc(cv["basics"].get("title", "Curriculum Vitae")),
        links_switch=render_links_switch(),
        toc_popover=render_toc_popover(),
        actions=render_actions(),
        header=render_header(),
        sections=sections_html,
        footer=render_footer(),
    )
    DOCS.mkdir(exist_ok=True)
    (DOCS / "index.html").write_text(html, encoding="utf-8")
    print(f"Wrote {(DOCS / 'index.html').relative_to(ROOT)}")

    shutil.copy(SRC / "style.css", DOCS / "style.css")
    print(f"Wrote {(DOCS / 'style.css').relative_to(ROOT)}")

    docs_fonts = DOCS / "fonts"
    docs_fonts.mkdir(exist_ok=True)
    for otf in FONTS.glob("*.otf"):
        shutil.copy(otf, docs_fonts / otf.name)
    print(f"Staged {len(list(FONTS.glob('*.otf')))} font files into {docs_fonts.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
