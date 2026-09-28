#!/usr/bin/env python3
"""Summaries on the full CV: the data `make site` renders.

The full CV carries a few heading summaries too — e.g. Research Income's
"(≈ £12.5M, £7.7M as PI)". Which headings get which
metrics, and the exchange rates the totals use, live in src/summaries.json.
This script computes them with the subset build's machinery
(build_subset.summarise, spec §8) and writes build/site/cv.json: src/cv.json
verbatim plus the `summary` strings. `make site` renders that file; the
renderers print a summary if one is there, as for a subset.

The rates are tracked and dated, so the site build is reproducible and never
touches the network; `make rates` refreshes them from the ECB's daily
reference rates. The one network step is that explicit refresh.

    python3 src/build_site_data.py [--out build/site/cv.json]
    python3 src/build_site_data.py --update-rates
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

import build_subset
import validate_cv
from build_subset import BuildError

SRC = Path(__file__).resolve().parent
REPO = SRC.parent
SETTINGS = SRC / "summaries.json"
OUT = REPO / "build" / "site" / "cv.json"
SETTINGS_KEYS = {"//", "sections", "money"}
MONEY_KEYS = {"//", "currency", "rates_date", "rates_source", "rates"}


def load_settings(master, path=SETTINGS):
    """Read and check summaries.json. Returns (per-section metrics, money)."""
    name = path.name
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise BuildError([f"{name}: cannot read: {e}"])
    problems = []
    build_subset._keys(raw, name, SETTINGS_KEYS, problems)

    sections = raw.get("sections", {})
    if not isinstance(sections, dict):
        problems.append(f"{name}: sections: expected an object of section "
                        "title -> [metrics]")
        sections = {}
    for title in sections:
        if title not in master.sections:
            problems.append(f"{name}: sections: no section titled {title!r}"
                            + build_subset._suggest(title, master.sections))
        build_subset._metrics(sections, title, f"{name}: sections", problems)

    table = raw.get("money", {})
    money = {"currency": "GBP", "source": "config", "rates_date": None,
             "rates": None, "refresh": "run `make rates` to refresh them"}
    if not isinstance(table, dict):
        problems.append(f"{name}: money: expected an object")
    else:
        build_subset._keys(table, f"{name}: money", MONEY_KEYS, problems)
        money["currency"] = table.get("currency", "GBP")
        if money["currency"] not in build_subset.CURRENCY_SYMBOL:
            problems.append(f"{name}: money.currency: {money['currency']!r} "
                            "is not supported")
        if "rates_source" in table:
            money["label"] = table["rates_source"]
        if "rates" in table or "rates_date" in table:
            try:
                money["rates_date"] = datetime.date.fromisoformat(
                    table.get("rates_date", ""))
            except (TypeError, ValueError):
                problems.append(f"{name}: money.rates_date: expected "
                                f"YYYY-MM-DD, got {table.get('rates_date')!r}")
            rates = table.get("rates", {})
            if not isinstance(rates, dict) or not all(
                    build_subset._is(v, (int, float)) and v > 0
                    for v in rates.values()):
                problems.append(f"{name}: money.rates: expected currency "
                                "code -> positive number")
            else:
                money["rates"] = rates
    if problems:
        raise BuildError(problems)
    return sections, money


def site_data(master, sections, money, today):
    """The full CV's data with its summaries. Returns (cv, warnings)."""
    plan = {"name": "site", "formats": [], "header_title": None,
            "money": money, "summary_default": [],
            "sections": [{"title": t, "rename": None, "ids": None,
                          "summary": sections.get(t), "groups": None}
                         for t in master.sections]}
    if money["rates"] is None:
        money = dict(money, rates={})
        plan["money"] = money
    cv, _, _, scopes = build_subset.select_scoped(plan, master)
    for out, src in zip(cv["sections"], master.cv["sections"]):
        if "source" in src:  # the real publications file, not a subset's
            out["source"] = src["source"]
    warnings = []
    try:
        build_subset.summarise(plan, master, scopes, today, warnings)
    except BuildError as e:
        raise BuildError([f"summaries.json: {p}" for p in e.problems]
                         + ["refresh the rates with `make rates`"])
    return cv, warnings


def write_site_data(out=OUT):
    master = build_subset.load_master()
    sections, money = load_settings(master)
    cv, warnings = site_data(master, sections, money,
                             build_subset.build_now().date())
    schema = json.loads((SRC / "cv.schema.json").read_text(encoding="utf-8"))
    check = validate_cv.SchemaValidator(schema)
    check.validate(cv, schema, "")
    if check.errors:
        raise BuildError([f"site cv.json: {e}" for e in check.errors])
    out.parent.mkdir(parents=True, exist_ok=True)
    build_subset._write_json(out, cv)
    return warnings


def update_rates(path=SETTINGS):
    """Fetch today's ECB rates for every currency the awards use; rewrite the
    money block of summaries.json in place."""
    master = build_subset.load_master()
    raw = json.loads(path.read_text(encoding="utf-8"))
    money = raw.setdefault("money", {})
    target = money.get("currency", "GBP")
    needed = sorted({e["amount"]["currency"] for s in master.cv["sections"]
                     for g in master.groups(s) or [None]
                     for e in master.items(s, g)
                     if isinstance(e.get("amount"), dict)} - {target})
    try:
        date, eur = build_subset.fetch_ecb_rates()
    except build_subset.RatesUnavailable as e:
        raise BuildError([f"could not fetch the ECB reference rates ({e}); "
                          f"{path.name} left unchanged"])
    missing = [c for c in needed + [target] if c not in eur]
    if missing:
        raise BuildError([f"the ECB reference rates of {date} have no rate "
                          f"for {', '.join(missing)}"])
    money["rates_date"] = date.isoformat()
    money["rates_source"] = "ECB reference rates"
    money["rates"] = {c: build_subset._sig(eur[target] / eur[c])
                      for c in needed}
    build_subset._write_json(path, raw)
    return date, money["rates"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=OUT,
                    help=f"where to write the data (default: "
                         f"{OUT.relative_to(REPO)})")
    ap.add_argument("--update-rates", action="store_true",
                    help="refresh the exchange rates in summaries.json from "
                         "the ECB (network)")
    args = ap.parse_args(argv)
    try:
        if args.update_rates:
            date, rates = update_rates()
            print(f"Updated {SETTINGS.relative_to(REPO)}: ECB reference rates "
                  f"of {date}: " + ", ".join(f"{c} = {v}"
                                             for c, v in rates.items()))
        else:
            for w in write_site_data(args.out):
                print(f"warning: {w}", file=sys.stderr)
            print(f"Wrote {args.out}")
    except BuildError as e:
        print(f"✗ {len(e.problems)} problem(s):\n", file=sys.stderr)
        for p in e.problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
