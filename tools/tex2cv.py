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

INITIAL = re.compile(r"^(?:[A-Z]\.?-?){1,3}$")

def parse_authors(text):
    """Return (authors, ok). authors = list of {family, given} (or {literal} for orgs).

    Author lists mix two separator conventions — plain commas ("Family, Init,
    Family, Init") and a semicolon or "&"/"and" before the last name in an
    otherwise comma-separated list ("Family, Init, ..., & Family, Init"). Both
    are tokenized the same way: split on every comma AND semicolon, keeping
    track of which delimiter preceded each token, then walk left to right —
    a token followed by a comma-preceded initial pairs with it as one author;
    anything else starts a new author (comma- or space-joined "Family Init").
    """
    text = text.strip()
    # Trailing sentence period doubles as the last initial's abbreviation dot
    # (e.g. "...Nijkamp, P.") — don't strip it, or the pair-matching below breaks.
    text = text.rstrip(",;").strip()
    text = text.replace(" and ", "; ").replace(" & ", "; ").replace("&", ";")
    text = re.sub(r"\bet al\.?", "", text).strip().rstrip(";,").strip()
    if not text:
        return [], False

    raw = re.split(r"([,;])", text)
    # Strip stray leading/trailing periods per chunk — recovers from source
    # typos like "Arribas-Bel, D,. Evans" (comma/period swapped) and from a
    # redundant comma before "&" ("Family, B., & Family2, S.").
    tokens = [(None, raw[0].strip(" ."))]
    for i in range(1, len(raw) - 1, 2):
        tok = raw[i + 1].strip(" .")
        if tok:
            tokens.append((raw[i], tok))

    ok = True
    people = []
    i = 0
    while i < len(tokens):
        _, tok = tokens[i]
        nxt_d, nxt_tok = tokens[i + 1] if i + 1 < len(tokens) else (None, None)
        if nxt_tok is not None and nxt_d == "," and INITIAL.match(nxt_tok.replace(" ", "")):
            people.append({"family": tok, "given": nxt_tok}); i += 2
        else:
            fam, giv, good = split_name(tok)
            ok = ok and good
            people.append({"family": fam, "given": giv})
            i += 1

    if not people:
        ok = False
    elif len(people) == 1 and people[0]["given"] == "" and len(tokens) == 1:
        # A single title-case blob with no initials at all: treat as an
        # organizational author (CSL "literal") rather than flag as broken.
        people = [{"literal": people[0]["family"]}]
        ok = True
    return people, ok

def split_name(chunk):
    """'Wolf, L. J.' -> ('Wolf', 'L. J.', True); 'Arribas-Bel D.' -> ('Arribas-Bel', 'D.', True)."""
    chunk = chunk.strip()
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

    # title: first quoted group — LaTeX `` '' (already converted to “...”) or
    # straight ASCII "..." (a handful of entries use plain quotes directly).
    raw = body
    tconv = raw.replace("``", "“").replace("''", "”")
    tm = re.search(r"“(.+?)”", tconv, re.S) or re.search(r'"(.+?)"', tconv, re.S)
    title = latex_to_text(tm.group(1)) if tm else ""
    if not title:
        flags.append("no title")

    authors_raw = tconv[:tm.start()] if tm else ""
    tail = tconv[tm.end():] if tm else tconv

    authors, aok = parse_authors(latex_to_text(authors_raw)) if authors_raw.strip() else ([], False)
    if not aok:
        flags.append("authors?")

    # venue: first \emph{...}, else first \textit{...}, in the tail
    vm = re.search(r"\\emph\{([^{}]*)\}", tail) or re.search(r"\\textit\{([^{}]*)\}", tail)
    # A trailing period is the sentence's, not the venue name's — the renderer
    # adds its own separators, so keeping it would print a double "..".
    container = latex_to_text(vm.group(1)).rstrip(".") if vm else ""

    # DOI / ISBN / URL: from \texttt{...} or \url{...}
    doi, isbn, url = None, None, None
    for m in re.finditer(r"\\(?:texttt|url)\{([^{}]*)\}", tail):
        val = latex_to_text(m.group(1))
        if val.lower().startswith("http"):
            url = val
        elif val.lower().startswith("isbn"):
            isbn = re.sub(r"(?i)^isbn:?\s*", "", val)
        else:
            doi = doi or re.sub(r"(?i)^doi:?\s*", "", val)

    # volume/issue/page: whatever bibliographic detail trails the venue, up to
    # the first DOI/URL token — kept as one "volume" string (the renderer just
    # joins "venue, volume" so "13, 575" or "44(9), 2041-2046" print as-is).
    vol = None
    if vm:
        rest = tail[vm.end():]
        cut = re.search(r"\\(?:texttt|url)\{", rest)
        rest_txt = latex_to_text(rest[:cut.start()] if cut else rest)
        # Strip boilerplate that carries no data of its own (the DOI/URL is
        # already captured separately above).
        rest_txt = re.sub(r"(?i)\bdoi:?\s*$", "", rest_txt)
        rest_txt = re.sub(r"(?i)\bavailable\s+at:?\s*$", "", rest_txt)
        rest_txt = rest_txt.strip(" .,")
        if rest_txt:
            rest_txt = re.sub(r"(?i)^(?:vol\.?|volume)\s*", "", rest_txt)
            rest_txt = re.sub(r"(?i)\bpp\.?\s*", "", rest_txt)
            rest_txt = re.sub(r"\s*[-–]\s*", "-", rest_txt)
            m2 = re.match(r"^(\d+)\s*,?\s*(?:\((\d+)\))?\s*[:,.]?\s*([\w\-:]+)?$", rest_txt)
            if m2:
                n, issue, page = m2.groups()
                vol = f"{n}({issue})" if issue else n
                if page:
                    vol += f", {page}"
            else:
                flags.append(f"venue detail unparsed: {rest_txt!r}")
    if not vol:
        # Rare irregular ordering: "Volume N." stated before the \emph venue.
        pre = latex_to_text(tail[:vm.start()]) if vm else ""
        m3 = re.search(r"(?i)\b(?:vol\.?|volume)\s*(\d+)\b", pre)
        if m3:
            vol = m3.group(1)

    entry = {"id": mk_id(authors, year, title), "type": csl_type,
             "title": title, "author": authors,
             "issued": {"date-parts": [[year]]} if year else {},
             "category": category}
    if container:
        entry["container-title"] = container
    if vol:
        entry["volume"] = vol
    if doi:
        entry["DOI"] = doi
    if isbn:
        entry["ISBN"] = isbn
    if url:
        entry["URL"] = url
    return entry, year, flags

def mk_id(authors, year, title):
    first = authors[0].get("family", authors[0].get("literal", "")) if authors else "anon"
    fam = re.sub(r"[^a-z]", "", first.lower()) if authors else "anon"
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

    # de-duplicate ids (same author/year/first-title-word can collide)
    seen = {}
    for p in pubs:
        base = p["id"]
        n = seen.get(base, 0)
        seen[base] = n + 1
        if n:
            p["id"] = f"{base}-{chr(ord('a') + n)}"

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
