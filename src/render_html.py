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
    return entry(label, ". ".join(parts))


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


def render_nav():
    """A <details> disclosure — collapsible on mobile, forced open into a
    sidebar on wide viewports via CSS alone; no JS needed either way."""
    items = "".join(
        f'<li><a href="#{slug(s["title"])}">{esc(s["title"])}</a></li>'
        for s in cv["sections"]
    )
    return f'<nav><details id="toc" open><summary>Sections</summary><ul>{items}</ul></details></nav>'


def render_header():
    basics = cv["basics"]
    lines = "".join(f'{esc(l)}<br>' for l in basics["affiliation"])
    title = basics.get("title", "Curriculum Vitae")
    return f'''<header>
  <a class="btn-pdf" href="cv.pdf" download>PDF</a>
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
{nav}
<main>
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
        nav=render_nav(),
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
