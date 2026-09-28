#!/usr/bin/env python3
"""render_html.py — the second renderer: turns the same structured CV data
into a static HTML page for GitHub Pages.

This is the second bespoke artifact the architecture allows (ARCHITECTURE.md,
Decision 2): it reads src/cv.json + src/publications.json directly — the same
data cv.typ reads — and makes its own formatting decisions. Never reads or
depends on cv.typ; the two renderers are independent templates over shared
data, kept visually aligned by hand, not by shared code.

Build:  python3 src/render_html.py   (or: make html)
        python3 src/render_html.py --data PATH --out DIR
--data reads another cv.json (default src/cv.json; a publications section's
`source` stays relative to src/); --out writes somewhere other than docs/.
"""
import argparse
import json
import re
import shutil
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
DOCS = ROOT / "docs"
FONTS = ROOT / "fonts" / "texgyrepagella"

cv = None  # the CV data, loaded by main()


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


# A chain-link glyph, stroked in currentColor so it follows the theme.
LINK_ICON = ('<svg viewBox="0 0 24 24" width="1em" height="1em" aria-hidden="true" '
             'fill="none" stroke="currentColor" stroke-width="2" '
             'stroke-linecap="round" stroke-linejoin="round">'
             '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/>'
             '<path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/></svg>')


def anchor(rid):
    """A record's id attribute and its permalink (issue #17): the record's
    permanent id becomes a #fragment, so any single item can be linked to.
    Following one highlights the item (`:target` in style.css); the page's one
    script also copies the link (PAGE). An item without an id — only possible
    in hand-built data, the schema requires one — just renders without."""
    if not rid:
        return "", ""
    return (f' id="{esc(rid)}"',
            f'<a class="permalink" href="#{esc(rid)}" title="Copy link to this item" '
            f'aria-label="Link to this item">{LINK_ICON}</a>')


def entry(label, body, rid=None):
    """A CV row: label column + body, mirroring cv.typ's entry() grid. The
    permalink is absolutely positioned into the left margin, so it takes no
    grid cell."""
    attr, link = anchor(rid)
    return (f'<div class="entry"{attr}>{link}<div class="date">{esc(label)}</div>'
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
    return entry(label, body, e.get("id"))


def render_positions(label, e):
    body = esc(e["role"])
    if "organisation" in e:
        body += f', {esc(e["organisation"])}'
    return entry(label, body, e.get("id"))


def render_editorial(label, e):
    return entry(label, f'{esc(e["role"])}, <em>{esc(e["journal"])}</em>',
                 e.get("id"))


def render_awards(label, e):
    body = f'<em>{esc(e["title"])}</em>'
    if "detail" in e:
        body += f' {esc(e["detail"])}'
    return entry(label, body, e.get("id"))


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
    return entry(label, body, e.get("id"))


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
    return entry(label, ". ".join(parts) + ".", e.get("id"))


def render_visits(label, e):
    parts = [esc(e["institution"])]
    if "location" in e:
        parts.append(esc(e["location"]))
    if "role" in e:
        parts.append(esc(e["role"]))
    return entry(label, ". ".join(parts) + ".", e.get("id"))


def render_talks(label, e):
    body = f'“{esc(e["title"])}”'
    if "venue" in e:
        body += f'. {esc(e["venue"])}'
    return entry(label, body, e.get("id"))


def render_events(label, e):
    body = f'<em>{esc(e["title"])}</em>'
    if "detail" in e:
        body += f'. {esc(e["detail"])}'
    return entry(label, body, e.get("id"))


def render_courses(label, e):
    body = esc(e["name"])
    if "years" in e:
        body += f' ({esc(e["years"])})'
    if "url" in e:
        body += f'. {weblink(e["url"])}'
    return entry(label, body, e.get("id"))


def render_people(label, e):
    body = esc(e["name"])
    if "detail" in e:
        body += f'. {esc(e["detail"])}'
    return entry(label, body, e.get("id"))


def render_textlist(label, e):
    body = esc(e["text"])
    if "url" in e:
        body += f'. {weblink(e["url"])}'
    return entry(label, body, e.get("id"))


def render_named(e):
    """software / language: the name replaces the date column, full width."""
    body = f'<strong>{esc(e["name"])}</strong>'
    if "detail" in e:
        body += f' — {esc(e["detail"])}'
    if "url" in e:
        body += f' {weblink(e["url"])}'
    attr, link = anchor(e.get("id"))
    return f'<div class="named"{attr}>{link}{body}</div>'


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
    return entry(label, ". ".join(parts) + render_links(p.get("links")),
                 p.get("id"))


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
    return entry(label, esc(e.get("text", "")), e.get("id"))


def render_list(kind, entries):
    if kind == "named":
        return "".join(render_named(e) for e in entries)
    return "".join(render_entry(kind, label, e)
                   for label, e in with_labels(entries, by_date))


def heading_text(x):
    """A heading's title, plus a subset build's summary in parentheses after
    it (and its currency note as a tooltip). Summaries are set by the subset
    build, and on the full CV by src/build_site_data.py; src/cv.json itself
    never has one."""
    if "summary" not in x:
        return esc(x["title"])
    note = x.get("summary_note")
    tip = f' title="{esc(note)}"' if note else ""
    mark = "*" if note else ""
    return (f'{esc(x["title"])} <span class="summary"{tip}>'
            f'({esc("; ".join(x["summary"]))}){mark}</span>')


def render_publications(section):
    all_pubs = json.loads((SRC / section["source"]).read_text(encoding="utf-8"))
    out = []
    for g in section["groups"]:
        out.append(f'<h3 id="{slug(section["title"])}-{slug(g["title"])}">{heading_text(g)}</h3>')
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
    out = [f'<section id="{slug(title)}"><h2>{heading_text(section)}</h2>']
    if kind == "publications":
        out.append(render_publications(section))
    elif "groups" in section:
        for g in section["groups"]:
            out.append(f'<h3 id="{slug(title)}-{slug(g["title"])}">{heading_text(g)}</h3>')
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
    ~ main …`. Its visible half is the <label> button in render_header(). The
    toggle itself needs no JS — same spirit as the Sections popover; `checked`
    here is what the page opens with.

    A `?links=on|off` in the URL overrides that default, so a shared link can
    say which view it means (SCRIPT keeps the parameter in step with the
    switch). The script sits right after the checkbox so it runs before
    <main> is parsed: the page never paints in the wrong state, and the jump
    to a #fragment lands on the final layout."""
    return ('<input type="checkbox" id="show-links" class="visually-hidden" checked>\n'
            '<script>(() => {\n'
            '  const v = new URLSearchParams(location.search).get("links");\n'
            '  if (v === "on" || v === "off")\n'
            '    document.getElementById("show-links").checked = v === "on";\n'
            '})();</script>')


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


# The page's main script, and optional: a permalink is a plain #fragment link
# that already jumps to and highlights its item without it. This adds the copy
# — the full URL onto the clipboard, and a brief "copied" note (style.css) —
# and keeps a `?links=on|off` in the URL, and so in every copied link, in step
# with the "Links" switch (render_links_switch reads it back on load).
SCRIPT = """<script>
const links = document.getElementById("show-links");
const withLinks = href => {
  const u = new URL(href);
  u.searchParams.set("links", links.checked ? "on" : "off");
  return u.href;
};
links.addEventListener("change", () =>
  history.replaceState(history.state, "", withLinks(location.href)));
document.addEventListener("click", ev => {
  const a = ev.target.closest(".permalink");
  if (!a || !navigator.clipboard) return;
  navigator.clipboard.writeText(withLinks(a.href)).then(() => {
    a.classList.add("copied");
    setTimeout(() => a.classList.remove("copied"), 1500);
  }, () => {});
});
</script>"""


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
{script}
</body>
</html>
"""


def shown(path):
    """A path for log lines: repo-relative when inside the repo."""
    try:
        return path.resolve().relative_to(ROOT)
    except ValueError:
        return path


def main(argv=None):
    global cv
    ap = argparse.ArgumentParser(description="Render the CV as a static HTML page.")
    ap.add_argument("--data", type=Path, default=SRC / "cv.json",
                    help="cv.json to render (default: src/cv.json)")
    ap.add_argument("--out", type=Path, default=DOCS,
                    help="output directory (default: docs/)")
    args = ap.parse_args(argv)
    cv = json.loads(args.data.read_text(encoding="utf-8"))
    out = args.out

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
        script=SCRIPT,
    )
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    print(f"Wrote {shown(out / 'index.html')}")

    shutil.copy(SRC / "style.css", out / "style.css")
    print(f"Wrote {shown(out / 'style.css')}")

    out_fonts = out / "fonts"
    out_fonts.mkdir(exist_ok=True)
    for otf in FONTS.glob("*.otf"):
        shutil.copy(otf, out_fonts / otf.name)
    print(f"Staged {len(list(FONTS.glob('*.otf')))} font files into {shown(out_fonts)}")


if __name__ == "__main__":
    main()
