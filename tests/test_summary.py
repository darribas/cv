"""src/build_subset.py (spec P2): section summaries, totals, exchange rates.

Most tests run the summaries over a small made-up master (FIXTURE), whose
amounts give round, checkable figures; the count and build tests also use the
real data. The ECB fetch is always patched: tests never touch the network.
"""

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
import unittest
import zlib
from unittest import mock

from support import REPO, SRC, load

import build_subset
from test_subset import FIXED_EPOCH, HAS_TYPST, MASTER, TempConfig

TODAY = datetime.date(2026, 9, 28)
ECB_DAY = datetime.date(2026, 9, 26)
# Units per 1 EUR, as the feed gives them: £1 = €1/0.85, $1 = €1/1.10.
ECB = {"EUR": 1.0, "GBP": 0.85, "USD": 1.10}


def grant(rid, value=None, currency="GBP"):
    e = {"id": rid, "date": "2024", "title": rid.upper()}
    if value is not None:
        e["amount"] = {"value": value, "currency": currency}
    return e


FIXTURE = build_subset.Master({"basics": {"name": "Ada Lovelace"}, "sections": [
    {"title": "Home Grants", "type": "grant", "entries": [
        grant("h1", 54761), grant("h2", 12000.4), grant("h3", 1_200_000)]},
    {"title": "Mixed Grants", "type": "grant", "entries": [
        grant("m1", 1_000_000), grant("m2", 100_000, "EUR"),
        grant("m3", 50_000, "USD"), grant("m4")]},
    {"title": "Research Income", "groups": [
        {"title": "Awards", "type": "grant", "entries": [
            grant("a1", 2000), grant("a2", 3000, "EUR")]},
        {"title": "Projects", "type": "project", "entries": [
            {"id": "p1", "date": "2020", "title": "P", "funding": "£1M"}]}]},
    {"title": "Led Grants", "type": "grant", "entries": [
        dict(grant("pa", 500_000), role="PI"), dict(grant("pb", 300_000), role="CoI"),
        dict(grant("pc", 10_000, "EUR"), role="PI")]},
    {"title": "Talks", "type": "talks", "entries": [
        {"id": f"t{i}", "date": "2020", "title": "T"} for i in range(3)]},
    {"title": "Staff", "type": "people", "entries": [{"id": "s1", "name": "X"}]},
    {"title": "Languages", "type": "named", "entries": [
        {"id": "l1", "name": "English"}]},
]}, [])

CONFIG_RATES = """
    [money]
    source = "{source}"
    rates_date = {date}
    [money.rates]
    EUR = 0.9
    USD = 0.8
"""


def config_rates(source="config", date="2026-09-24"):
    return CONFIG_RATES.format(source=source, date=date)


class Run:
    """Parse a config against a master and compute its summaries, with the
    ECB fetch patched: `ecb` is its return value, or None for "unreachable"."""

    def __init__(self, text, master=FIXTURE, today=TODAY, ecb=(ECB_DAY, ECB)):
        with TempConfig(text) as c:
            self.plan = build_subset.parse_config(c.path, master)
        self.cv, _, _, scopes = build_subset.select_scoped(self.plan, master)
        self.warnings = []
        effect = {"return_value": ecb} if ecb else {
            "side_effect": build_subset.RatesUnavailable("URLError: offline")}
        with mock.patch.object(build_subset, "fetch_ecb_rates",
                               **effect) as self.fetch:
            self.record = build_subset.summarise(self.plan, master, scopes,
                                                 today, self.warnings)

    def heading(self, title, group=None):
        s = next(s for s in self.cv["sections"] if s["title"] == title)
        if group is not None:
            s = next(g for g in s["groups"] if g["title"] == group)
        return s

    def summary(self, title, group=None):
        return self.heading(title, group).get("summary")

    def note(self, title, group=None):
        return self.heading(title, group).get("summary_note")


def errors(text, master=FIXTURE, **kw):
    try:
        Run(text, master, **kw)
    except build_subset.BuildError as e:
        return e.problems
    raise AssertionError("expected a BuildError")


class CountTest(unittest.TestCase):
    def test_subset_and_full_forms(self):
        r = Run('''
            [[section]]
            title = "Talks"
            summary = ["count"]
            ids = ["t1"]
            [[section]]
            title = "Staff"
            summary = ["count"]
        ''')
        self.assertEqual(r.summary("Talks"), ["1 of 3 talks"])
        self.assertEqual(r.summary("Staff"), ["1 person"])
        self.assertEqual(r.warnings, [])
        self.assertIsNone(r.record)

    def test_publications_real_data(self):
        n = len(load("publications.json"))
        r = Run('''
            [summary]
            default = ["count"]
            [[section]]
            title = "Publications"
            ids = ["rey2023geographic"]
        ''', master=MASTER)
        self.assertEqual(r.summary("Publications"), [f"1 of {n} publications"])
        r = Run('[[section]]\ntitle = "Publications"\nrename = "Papers"\n'
                'summary = ["count"]\n', master=MASTER)
        # The noun is the source title, whatever the heading is renamed to.
        self.assertEqual(r.summary("Papers"), [f"{n} publications"])

    def test_group_count_and_nouns(self):
        r = Run('''
            [[section]]
            title = "Research Income"
            summary = ["count"]
              [[section.group]]
              title = "Awards"
              summary = ["count"]
              ids = ["a2"]
              [[section.group]]
              title = "Projects"
        ''')
        # Mixed entry types -> "items"; a grant group -> "awards".
        self.assertEqual(r.summary("Research Income"), ["2 of 3 items"])
        self.assertEqual(r.summary("Research Income", "Awards"), ["1 of 2 awards"])
        self.assertIsNone(r.summary("Research Income", "Projects"))

    def test_default_applies_to_sections_not_groups(self):
        r = Run('''
            [summary]
            default = ["count"]
            [[section]]
            title = "Talks"
            ids = ["t0", "t2"]
            [[section]]
            title = "Staff"
            summary = []
            [[section]]
            title = "Research Income"
              [[section.group]]
              title = "Awards"
        ''')
        self.assertEqual(r.summary("Talks"), ["2 of 3 talks"])
        self.assertIsNone(r.summary("Staff"))  # its own empty summary wins
        self.assertEqual(r.summary("Research Income"), ["2 of 3 items"])
        self.assertIsNone(r.summary("Research Income", "Awards"))

    def test_default_count_omitted_for_whole_sections(self):
        r = Run('''
            [summary]
            default = ["count"]
            [[section]]
            title = "Talks"
            [[section]]
            title = "Staff"
            summary = ["count"]
        ''')
        self.assertIsNone(r.summary("Talks"))  # nothing dropped: no summary
        self.assertEqual(r.summary("Staff"), ["1 person"])  # explicit: shown

    def test_count_on_named_warns(self):
        r = Run('[[section]]\ntitle = "Languages"\nsummary = ["count"]\n')
        self.assertEqual(r.summary("Languages"), ["1 item"])
        self.assertEqual(len(r.warnings), 1)
        self.assertIn("'Languages'", r.warnings[0])


class TotalTest(unittest.TestCase):
    def test_single_currency_no_approx_no_note(self):
        r = Run('''
            [[section]]
            title = "Home Grants"
            summary = ["count", "total"]
            ids = ["h1", "h2"]
        ''')
        self.assertEqual(r.summary("Home Grants"),
                         ["2 of 3 awards", "£66,761 of £1.3M total award value"])
        self.assertIsNone(r.note("Home Grants"))
        self.assertIsNone(r.record)
        r.fetch.assert_not_called()  # nothing to convert, so no network

    def test_nothing_dropped_shows_one_figure(self):
        r = Run('[[section]]\ntitle = "Home Grants"\nsummary = ["total"]\n')
        self.assertEqual(r.summary("Home Grants"), ["£1.3M total award value"])

    def test_multi_currency(self):
        r = Run(config_rates() + '''
            [[section]]
            title = "Mixed Grants"
            summary = ["total"]
            ids = ["m2"]
        ''')
        # €100,000 × 0.9; the whole: £1,000,000 + £90,000 + $50,000 × 0.8.
        self.assertEqual(r.summary("Mixed Grants"),
                         ["≈ £90,000 of ≈ £1.1M total award value"])
        self.assertEqual(r.note("Mixed Grants"), "Converted to GBP at "
                         "exchange rates of 24 September 2026.")
        self.assertEqual(r.record["rates"], {"EUR": 0.9, "USD": 0.8})
        self.assertEqual(r.warnings, [])

    def test_partial_coverage_suffix(self):
        r = Run(config_rates() + '''
            [[section]]
            title = "Mixed Grants"
            summary = ["total"]
        ''')
        self.assertEqual(r.summary("Mixed Grants")[0],
                         "≈ £1.1M total award value "
                         "(1 award without a recorded amount)")
        self.assertEqual(len(r.warnings), 1)
        self.assertIn("without a recorded amount", r.warnings[0])

    def test_projects_never_count(self):
        r = Run(config_rates() + '''
            [[section]]
            title = "Research Income"
            summary = ["total"]
        ''')
        self.assertEqual(r.summary("Research Income")[0],
                         "≈ £4,700 total award value")  # £2,000 + €3,000 × 0.9

    def test_explicit_total_without_grants_is_an_error(self):
        problems = errors('[[section]]\ntitle = "Talks"\nsummary = ["total"]\n')
        self.assertIn("'Talks'", problems[0])
        self.assertIn("type grant", problems[0])

    def test_default_total_skips_sections_without_grants(self):
        r = Run('''
            [summary]
            default = ["count", "total"]
            [[section]]
            title = "Talks"
            [[section]]
            title = "Home Grants"
        ''')
        self.assertIsNone(r.summary("Talks"))
        # Whole section: the default count is left out, the total is not.
        self.assertEqual(r.summary("Home Grants"), ["£1.3M total award value"])

    def test_pi_share(self):
        r = Run(config_rates() + '''
            [[section]]
            title = "Led Grants"
            summary = ["total"]
        ''')
        # PI: £500,000 + €10,000 × 0.9; everything adds pb's £300,000.
        self.assertEqual(r.summary("Led Grants"), [
            "≈ £809,000 total award value", "≈ £509,000 as PI"])
        self.assertIsNotNone(r.note("Led Grants"))

    def test_pi_share_of_a_subset(self):
        r = Run(config_rates() + '''
            [[section]]
            title = "Led Grants"
            summary = ["total"]
            ids = ["pa", "pb"]
        ''')
        self.assertEqual(r.summary("Led Grants"), [
            "£800,000 of ≈ £809,000 total award value",
            "£500,000 of ≈ £509,000 as PI"])
        r = Run(config_rates() + '''
            [[section]]
            title = "Led Grants"
            summary = ["total"]
            ids = ["pb"]
        ''')
        self.assertEqual(r.summary("Led Grants")[1], "£0 of ≈ £509,000 as PI")

    def test_no_pi_awards_no_pi_part(self):
        r = Run('[[section]]\ntitle = "Home Grants"\nsummary = ["total"]\n')
        self.assertEqual(r.summary("Home Grants"), ["£1.3M total award value"])

    def test_money_format(self):
        fmt = build_subset.fmt_money
        self.assertEqual(fmt(54761, "GBP"), "£54,761")
        self.assertEqual(fmt(138893.36, "GBP"), "£138,893")
        self.assertEqual(fmt(1_000_000, "EUR"), "€1.0M")
        self.assertEqual(fmt(4_449_999, "USD"), "$4.4M")


class RatesTableTest(unittest.TestCase):
    """Spec §8.3: all six cells of the source × reachability table."""

    SECTION = '''
        [[section]]
        title = "Mixed Grants"
        summary = ["total"]
        ids = ["m2"]
    '''
    ECB_TEXT = ("≈ £85,000", "ECB reference rates of 26 September 2026")
    CONFIG_TEXT = ("≈ £90,000", "exchange rates of 24 September 2026")

    def assert_used(self, r, expected):
        figure, source = expected
        (line,) = r.summary("Mixed Grants")
        self.assertTrue(line.startswith(figure), line)
        self.assertEqual(r.note("Mixed Grants"), f"Converted to GBP at {source}.")

    def test_live_no_rates_reachable(self):
        r = Run(self.SECTION)
        self.assert_used(r, self.ECB_TEXT)
        r.fetch.assert_called_once()
        self.assertEqual(r.record["source"], "ECB")
        self.assertEqual(r.warnings, [])

    def test_live_no_rates_unreachable(self):
        problems = errors(self.SECTION, ecb=None)
        self.assertIn("could not fetch", problems[0])
        self.assertIn("[money.rates]", problems[0])
        self.assertIn("EUR = ", problems[0])

    def test_live_with_rates_reachable(self):
        r = Run(config_rates("live") + self.SECTION)
        self.assert_used(r, self.ECB_TEXT)  # config rates ignored
        self.assertEqual(r.warnings, [])

    def test_live_with_rates_unreachable(self):
        r = Run(config_rates("live") + self.SECTION, ecb=None)
        self.assert_used(r, self.CONFIG_TEXT)
        self.assertEqual(r.record["source"], "config")
        self.assertEqual(len(r.warnings), 1)
        self.assertIn("could not fetch the ECB", r.warnings[0])

    def test_config_reachable_makes_no_request(self):
        r = Run(config_rates() + self.SECTION)
        self.assert_used(r, self.CONFIG_TEXT)
        r.fetch.assert_not_called()

    def test_config_unreachable_makes_no_request(self):
        r = Run(config_rates() + self.SECTION, ecb=None)
        self.assert_used(r, self.CONFIG_TEXT)
        r.fetch.assert_not_called()
        self.assertEqual(r.warnings, [])


class RatesTest(unittest.TestCase):
    def test_cross_rates_via_eur_and_pasteable_record(self):
        r = Run('[[section]]\ntitle = "Mixed Grants"\nsummary = ["total"]\n')
        # GBP per USD = 0.85 / 1.10, kept to six significant figures.
        self.assertEqual(r.record["rates"], {"EUR": 0.85, "USD": 0.772727})
        self.assertEqual(r.record["date"], "2026-09-26")
        pasted = tomllib.loads("[money]\n" + r.record["toml"])
        self.assertEqual(pasted["money"]["rates"], r.record["rates"])
        self.assertEqual(pasted["money"]["rates_date"], ECB_DAY)

    def test_ecb_target_currency(self):
        r = Run('[money]\ncurrency = "EUR"\n'
                '[[section]]\ntitle = "Home Grants"\nsummary = ["total"]\n')
        # £1,266,761.4 at €1/0.85 per £.
        self.assertEqual(r.summary("Home Grants"), ["≈ €1.5M total award value"])
        self.assertEqual(r.note("Home Grants"), "Converted to EUR at ECB "
                         "reference rates of 26 September 2026.")

    def test_stale_rates_warn(self):
        section = '[[section]]\ntitle = "Mixed Grants"\nsummary = ["total"]\nids = ["m2"]\n'
        r = Run(config_rates(date="2026-01-02") + section)
        self.assertEqual(len(r.warnings), 1)
        self.assertIn("2026-01-02", r.warnings[0])
        self.assertIn("269 days", r.warnings[0])
        r = Run(config_rates(date="2026-07-01") + section)  # 89 days: fine
        self.assertEqual(r.warnings, [])

    def test_missing_currency_is_an_error(self):
        problems = errors('''
            [money]
            source = "config"
            rates_date = 2026-09-24
            [money.rates]
            EUR = 0.9
            [[section]]
            title = "Mixed Grants"
            summary = ["total"]
            ids = ["m1"]
        ''')
        # Only m1 (GBP) is kept, but the whole section's USD is shown too.
        self.assertEqual(len(problems), 1)
        self.assertIn("no rate for USD", problems[0])

    def test_missing_currency_in_ecb_feed(self):
        problems = errors(RatesTableTest.SECTION,
                          ecb=(ECB_DAY, {"EUR": 1.0, "GBP": 0.85}))
        self.assertIn("no rate for USD", problems[0])


class MoneyConfigErrorTest(unittest.TestCase):
    def assert_problem(self, text, *fragments):
        with TempConfig(text + '[[section]]\ntitle = "Talks"\n') as c:
            with self.assertRaises(build_subset.BuildError) as cm:
                build_subset.parse_config(c.path, FIXTURE)
        problems = cm.exception.problems
        self.assertTrue(any(all(f in p for f in fragments) for p in problems),
                        f"no problem mentions {fragments}; got {problems}")

    def test_rates_need_a_date(self):
        self.assert_problem('[money.rates]\nEUR = 0.9\n', "needs rates_date")
        self.assert_problem('[money]\nrates_date = 2026-09-24\n',
                            "no [money.rates]")

    def test_bad_rates(self):
        base = '[money]\nrates_date = 2026-09-24\n[money.rates]\n'
        self.assert_problem(base + 'eur = 0.9\n', "[money.rates].eur",
                            "3-letter uppercase")
        self.assert_problem(base + 'EUR = -1\n', "[money.rates].EUR",
                            "positive number")
        self.assert_problem(base + 'EUR = "0.9"\n', "positive number")
        self.assert_problem(base + 'GBP = 1\n', "[money.rates].GBP",
                            "target currency")
        self.assert_problem('[money]\nrates_date = "2026-09-24"\n'
                            '[money.rates]\nEUR = 0.9\n', "rates_date",
                            "no quotes")

    def test_bad_money_keys(self):
        self.assert_problem('[money]\nsource = "ecb"\n', "[money].source")
        self.assert_problem('[money]\ncurrency = "JPY"\n', "[money].currency",
                            "'JPY'")
        self.assert_problem('[money]\nsource = "config"\n', "needs the rates")
        self.assert_problem('[money]\nrate = 1\n', "unknown key 'rate'",
                            "did you mean 'rates'")

    def test_bad_metrics(self):
        self.assert_problem('[summary]\ndefault = ["cuont"]\n',
                            "default[0]", "unknown metric 'cuont'",
                            "did you mean 'count'")
        self.assert_problem('[summary]\ndefault = "count"\n', "expected an array")
        self.assert_problem('[summary]\nfoo = []\n', "[summary]",
                            "unknown key 'foo'")
        with TempConfig('[[section]]\ntitle = "Talks"\n'
                        'summary = ["count", "count"]\n') as c:
            with self.assertRaises(build_subset.BuildError) as cm:
                build_subset.parse_config(c.path, FIXTURE)
        self.assertIn("more than once", cm.exception.problems[0])


def pdf_bookmarks(pdf):
    """The PDF outline's titles (Typst writes them as plain literal strings
    in compressed object streams)."""
    data = pdf.read_bytes()
    chunks = [data]
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        try:
            chunks.append(zlib.decompress(m.group(1)))
        except zlib.error:
            pass
    return [t.decode("latin-1") for c in chunks
            for t in re.findall(rb"/Title\s*\(((?:[^()\\]|\\.)*)\)", c)]


def render_html(data, out):
    subprocess.run([sys.executable, str(SRC / "render_html.py"), "--data",
                    str(data), "--out", str(out)], check=True,
                   capture_output=True, cwd=REPO)
    return (out / "index.html").read_text(encoding="utf-8")


@unittest.skipUnless(HAS_TYPST, "typst not installed")
class BuildTest(unittest.TestCase):
    """A real build: summaries reach the derived data, both renderers, the
    manifest; --strict turns the warnings into errors."""

    CONFIG = '''
        [money]
        source = "config"
        rates_date = 2025-06-01
        [money.rates]
        EUR = 0.85
        USD = 0.75
        [[section]]
        title = "Research Income"
        summary = ["count", "total"]
          [[section.group]]
          title = "Awards"
          ids = ["awards-2024-sdr-uk-imagery-data",
                 "awards-2024-eurofab-european-urban-fabric"]
    '''

    def build(self, c, *args):
        return subprocess.run(
            [sys.executable, str(SRC / "build_subset.py"), str(c.path), *args],
            capture_output=True, text=True, cwd=REPO,
            env={**os.environ, "SOURCE_DATE_EPOCH": FIXED_EPOCH})

    def test_summary_everywhere(self):
        with TempConfig(self.CONFIG, stem="money") as c:
            run = self.build(c)
            self.assertEqual(run.returncode, 0, run.stderr)
            out = c.dir / "money"
            cv = json.loads((out / "cv.json").read_text(encoding="utf-8"))
            summary = cv["sections"][0]["summary"]
            self.assertEqual(len(summary), 3)
            self.assertEqual(summary[0], "2 of 28 items")
            # £6,788,641 + €250,000 × 0.85 of the whole Awards group.
            self.assertRegex(summary[1], r"^≈ £7\.0M of ≈ £\d+\.\dM total "
                                         r"award value$")
            # The first one is held as PI (in GBP), the second as CoI.
            self.assertRegex(summary[2], r"^£6\.8M of ≈ £\d+\.\dM as PI$")
            self.assertEqual(cv["sections"][0]["summary_note"],
                             "Converted to GBP at exchange rates of 1 June 2025.")
            m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(m["rates"]["source"], "config")
            self.assertEqual(m["rates"]["rates"], {"EUR": 0.85, "USD": 0.75})
            # Rates of 2025-06-01, built "on" 2026-01-01: 214 days old.
            self.assertEqual(len(m["warnings"]), 1)
            self.assertIn("214 days", m["warnings"][0])
            self.assertIn("warning:", run.stderr)

            html = render_html(out / "cv.json", c.dir / "html")
            self.assertIn('<h2>Research Income <span class="summary" title='
                          '"Converted to GBP at exchange rates of 1 June 2025.">'
                          '(2 of 28 items · ≈ £7.0M', html)
            pdf = out / "darribas-cv-money.pdf"
            # In the heading line, not the PDF bookmark: that is the title.
            self.assertEqual(pdf_bookmarks(pdf), ["Awards", "Research Income"])
            if shutil.which("pdftotext"):
                text = subprocess.run(["pdftotext", str(pdf), "-"],
                                      capture_output=True, text=True,
                                      check=True).stdout
                self.assertIn("Research Income (2 of 28 items", text)
                self.assertIn("Converted to GBP at exchange rates of 1 June "
                              "2025.", text)  # the footnote

            strict = self.build(c, "--strict", "--out", c.dir / "strict")
            self.assertEqual(strict.returncode, 1)
            self.assertIn("warning (--strict)", strict.stderr)
            self.assertFalse((c.dir / "strict").exists())


if __name__ == "__main__":
    unittest.main()
