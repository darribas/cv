#!/usr/bin/env python3
"""tex2cv.py — one-shot migration helper.

Parses the Publications section of cv-darribas.tex into CSL-JSON
(src/publications.json). Deterministic where the source is regular; anything it
cannot confidently parse is emitted best-effort AND listed at the end so it can
be fixed by hand. This tool is disposable — once the JSON is the source of
truth, the .tex (and this script) are retired.

Usage:  python3 tools/tex2cv.py            # writes src/publications.json
        python3 tools/tex2cv.py --dry      # print summary + flags only
"""
import json, re, sys, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEX = (ROOT / "cv-darribas.tex").read_text(encoding="utf-8", errors="replace")

# --- category sub-headers -> (CSL type, category key) ----------------------
CATEGORIES = {
    "Books": ("book", "book"),
    "Peer-reviewed journal articles": ("article-journal", "journal-article"),
    "Conference Proceedings": ("paper-conference", "conference"),
    "Other academic articles": ("article-journal", "other-article"),
    "Book chapters": ("chapter", "book-chapter"),
    "Other": ("article", "other"),
    "Working Papers": ("manuscript", "working-paper"),
}

# ---------------------------------------------------------------------------
# LaTeX helpers
# ---------------------------------------------------------------------------

def strip_comments(s):
    out = []
    for line in s.splitlines():
        res, i = "", 0
        while i < len(line):
            if line[i] == "\\" and i + 1 < len(line):
                res += line[i:i+2]; i += 2; continue
            if line[i] == "%":
                break
            res += line[i]; i += 1
        out.append(res)
    return "\n".join(out)

ACCENTS = {"'": "́", "`": "̀", '"': "̈", "^": "̂", "~": "̃", "=": "̄",
           ".": "̇", "v": "̌", "u": "̆", "c": "̧", "H": "̋"}

def deaccent_cmds(s):
    # \'{o} / \'o / \~{n} / \c{c} ... -> composed unicode
    def repl(m):
        acc, ch = m.group(1), m.group(2)
        comb = ACCENTS.get(acc, "")
        return unicodedata.normalize("NFC", ch + comb)
    s = re.sub(r"\\([`'\"^~=.vcuH])\{(\\?[A-Za-z])\}", lambda m: repl((None, m.group(1), m.group(2).lstrip("\\"))[1:]), s) if False else s
    s = re.sub(r"\\([`'\"^~=.vcuH])\{([A-Za-z])\}", repl, s)
    s = re.sub(r"\\([`'\"^~=.vcuH])\s*([A-Za-z])", repl, s)
    return s

def latex_to_text(s):
    s = deaccent_cmds(s)
    s = s.replace("``", "“").replace("''", "”")
    s = s.replace("\\&", "&").replace("\\%", "%").replace("\\#", "#")
    s = s.replace("\\$", "$").replace("\\pounds", "£").replace("\\euro", "€")
    s = s.replace("\\ldots", "…").replace("~", " ").replace("\\,", " ")
    s = s.replace("\\\\", " ")
    for _ in range(6):
        s = re.sub(r"\\(emph|textit|textbf|texttt|underline|mbox|text|textsc|small|url)\s*\{([^{}]*)\}", r"\2", s)
    s = re.sub(r"\\[A-Za-z]+\s*\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\[A-Za-z]+", " ", s)
    s = s.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", s).strip()

# ---------------------------------------------------------------------------
# Structure: pull the Publications cvlist and split into \item chunks
# ---------------------------------------------------------------------------

def cvlist_block(title):
    m = re.search(r"\\begin\{cvlist\}\{" + re.escape(title) + r"\}", TEX)
    end = TEX.find(r"\end{cvlist}", m.end())
    return TEX[m.end():end]

def split_items(block):
    """Yield (raw_label, raw_body) for each top-level \\item[...]."""
    block = strip_comments(block)
    # find \item[ ... ] respecting one level of nested brackets in the label
    items = []
    for m in re.finditer(r"\\item\s*\[", block):
        # capture bracket-balanced label
        i = m.end(); depth = 1; label = ""
        while i < len(block) and depth:
            c = block[i]
            if c == "[": depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0: break
            label += c; i += 1
        items.append((m.start(), i + 1, label))
    out = []
    for idx, (start, body_start, label) in enumerate(items):
        body_end = items[idx + 1][0] if idx + 1 < len(items) else len(block)
        out.append((label, block[body_start:body_end]))
    return out

# ---------------------------------------------------------------------------
# Author parsing (best-effort; flags the uncertain ones)
# ---------------------------------------------------------------------------

INITIAL = re.compile(r"^(?:[A-Z]\.-?){1,3}[A-Z]?\.?$|^[A-Z]\.(?:\s*[A-Z]\.)*$")

def parse_authors(text):
    """Return (authors, ok). authors = list of {family, given}."""
    text = text.strip().rstrip(".").strip()
    text = text.replace(" and ", "; ").replace(" & ", "; ").replace("&", ";")
    text = text.replace("et al.", "").replace("et al", "")
    ok = True
    people = []
    if ";" in text:
        chunks = [c.strip() for c in text.split(";") if c.strip()]
        for c in chunks:
            fam, giv, good = split_name(c)
            ok = ok and good
            people.append({"family": fam, "given": giv})
    else:
        # comma-separated: pair up Family, Initials, Family, Initials, ...
        toks = [t.strip() for t in text.split(",") if t.strip()]
        i = 0
        while i < len(toks):
            fam = toks[i]
            giv = ""
            if i + 1 < len(toks) and INITIAL.match(toks[i + 1].replace(" ", "")):
                giv = toks[i + 1]; i += 2
            else:
                ok = False; i += 1
            people.append({"family": fam, "given": giv})
    if not people:
        ok = False
    return people, ok

def split_name(chunk):
    """'Wolf, L. J.' -> ('Wolf', 'L. J.', True)."""
    if "," in chunk:
        fam, giv = chunk.split(",", 1)
        return fam.strip(), giv.strip(), True
    parts = chunk.split()
    if len(parts) >= 2 and INITIAL.match(parts[-1].replace(" ", "")):
        return " ".join(parts[:-1]), parts[-1], True
    return chunk.strip(), "", False

# ---------------------------------------------------------------------------
# Publication entry parsing
# ---------------------------------------------------------------------------

def parse_pub(label, body, category, csl_type, prev_year):
    flags = []
    # year from label (\textit{2025} etc.), else inherit
    ytxt = latex_to_text(label)
    ym = re.search(r"(19|20)\d\d", ytxt)
    year = int(ym.group()) if ym else prev_year
    if not ym and prev_year is None:
        flags.append("no year")

    # title: first ``...'' group (already converted to “...”)
    raw = body
    tconv = raw.replace("``", "“").replace("''", "”")
    tm = re.search(r"“(.+?)”", tconv, re.S)
    title = latex_to_text(tm.group(1)) if tm else ""
    if not title:
        flags.append("no title")

    authors_raw = tconv[:tm.start()] if tm else ""
    tail = tconv[tm.end():] if tm else tconv

    authors, aok = parse_authors(latex_to_text(authors_raw)) if authors_raw.strip() else ([], False)
    if not aok:
        flags.append("authors?")

    # venue: first \emph{...} in the tail
    vm = re.search(r"\\emph\{([^{}]*)\}", tail)
    container = latex_to_text(vm.group(1)) if vm else ""

    # DOI / URL: from \texttt{...} or \url{...}
    doi, url = None, None
    for m in re.finditer(r"\\(?:texttt|url)\{([^{}]*)\}", tail):
        val = latex_to_text(m.group(1))
        if val.lower().startswith("http"):
            url = val
        elif re.match(r"10\.\d{4,}/", val) or "/" in val and "." in val:
            doi = val
        else:
            doi = doi or val
    # volume / pages heuristics from the plain tail
    ptail = latex_to_text(tail)
    vol = None
    vm2 = re.search(r"(?:Vol\.?\s*|Volume\s*)?\b(\d{1,3})\s*(?:\(\d+\))?[.,]", ptail)
    if container and vm2:
        vol = vm2.group(1)

    entry = {"id": mk_id(authors, year, title), "type": csl_type,
             "title": title, "author": authors,
             "issued": {"date-parts": [[year]]} if year else {},
             "category": category}
    if container:
        entry["container-title"] = container
    if doi:
        entry["DOI"] = doi
    if url:
        entry["URL"] = url
    return entry, year, flags

def mk_id(authors, year, title):
    fam = re.sub(r"[^a-z]", "", authors[0]["family"].lower()) if authors else "anon"
    word = re.sub(r"[^a-z]", "", title.lower().split(" ")[0]) if title else "x"
    return f"{fam}{year or ''}{word}"[:40]

# ---------------------------------------------------------------------------
# Drive
# ---------------------------------------------------------------------------

def main():
    block = cvlist_block("Publications")
    pubs, review = [], []
    category = csl_type = None
    prev_year = None
    for label, body in split_items(block):
        if re.search(r"\\textbf", label):                       # sub-header
            name = latex_to_text(label)
            if name in CATEGORIES:
                csl_type, category = CATEGORIES[name]
                prev_year = None
            else:
                review.append(("?", f"unknown sub-header: {name}"))
            continue
        if category is None:
            continue
        if not latex_to_text(body).strip():
            continue
        entry, prev_year, flags = parse_pub(label, body, category, csl_type, prev_year)
        pubs.append(entry)
        if flags:
            review.append((entry["id"], ", ".join(flags) + f"  ::  {latex_to_text(body)[:120]}"))

    # summary
    from collections import Counter
    counts = Counter(p["category"] for p in pubs)
    print(f"Parsed {len(pubs)} publications:")
    for k, v in counts.items():
        print(f"  {v:>3}  {k}")
    print(f"\nFlagged for manual review: {len(review)}")
    for pid, msg in review:
        print(f"  [{pid}] {msg}")

    if "--dry" not in sys.argv:
        out = ROOT / "src" / "publications.json"
        out.write_text(json.dumps(pubs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote {out.relative_to(ROOT)}")

if __name__ == "__main__":
    main()
