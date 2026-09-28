"""src/build_site_data.py: the full CV's heading summaries (make site).

The site build uses the dated rates tracked in src/summaries.json and must
never touch the network; `make rates` is the one step that fetches, and here
its fetch is patched.
"""

import contextlib
import datetime
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from support import REPO, load

import build_site_data
import build_subset
from test_subset import FIXED_EPOCH, HAS_TYPST, MASTER

TODAY = datetime.date(2026, 9, 28)
NO_NETWORK = mock.patch.object(
    build_subset, "fetch_ecb_rates",
    side_effect=AssertionError("the site build must not fetch rates"))


def settings(path=build_site_data.SETTINGS):
    return build_site_data.load_settings(MASTER, path)


def research_income(cv):
    return next(s for s in cv["sections"] if s["title"] == "Research Income")


class SiteDataTest(unittest.TestCase):
    def test_research_income_total_and_pi(self):
        sections, money = settings()
        with NO_NETWORK:
            cv, warnings = build_site_data.site_data(MASTER, sections, money,
                                                     TODAY)
        ri = research_income(cv)
        (total,) = ri["summary"]
        self.assertRegex(total, r"^≈ £\d+\.\dM, £\d+\.\dM as PI$")
        date = money["rates_date"]
        self.assertEqual(ri["summary_note"],
                         f"Converted to GBP at ECB reference rates of "
                         f"{date.day} {date:%B %Y}.")
        self.assertEqual(warnings, [])

    def test_otherwise_the_source_data(self):
        with NO_NETWORK:
            cv, _ = build_site_data.site_data(MASTER, *settings(), TODAY)
        for s in cv["sections"]:
            s.pop("summary", None)
            s.pop("summary_note", None)
        self.assertEqual(cv, load("cv.json"))

    def test_stale_rates_warn_with_make_rates_hint(self):
        sections, money = settings()
        later = money["rates_date"] + datetime.timedelta(days=91)
        with NO_NETWORK:
            _, warnings = build_site_data.site_data(MASTER, sections, money,
                                                    later)
        self.assertEqual(len(warnings), 1)
        self.assertIn("make rates", warnings[0])

    def test_missing_rate_fails(self):
        sections, money = settings()
        money = dict(money, rates={"EUR": 0.86})
        with NO_NETWORK, self.assertRaises(build_subset.BuildError) as cm:
            build_site_data.site_data(MASTER, sections, money, TODAY)
        text = "\n".join(cm.exception.problems)
        self.assertIn("no rate for USD", text)
        self.assertIn("make rates", text)


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "summaries.json"
        self.raw = load("summaries.json")

    def tearDown(self):
        self._tmp.cleanup()

    def problems(self):
        self.path.write_text(json.dumps(self.raw), encoding="utf-8")
        with self.assertRaises(build_subset.BuildError) as cm:
            settings(self.path)
        return "\n".join(cm.exception.problems)

    def test_unknown_section(self):
        self.raw["sections"] = {"Research Incom": ["total"]}
        self.assertIn("did you mean 'Research Income'", self.problems())

    def test_unknown_metric(self):
        self.raw["sections"] = {"Research Income": ["totl"]}
        self.assertIn("unknown metric 'totl'", self.problems())

    def test_bad_rates(self):
        self.raw["money"]["rates_date"] = "25/09/2026"
        self.assertIn("rates_date", self.problems())
        self.raw["money"]["rates_date"] = "2026-09-25"
        self.raw["money"]["rates"] = {"EUR": -1}
        self.assertIn("positive number", self.problems())

    def test_update_rates(self):
        self.path.write_text(json.dumps(self.raw), encoding="utf-8")
        ecb = (datetime.date(2026, 9, 26), {"EUR": 1.0, "GBP": 0.85, "USD": 1.10})
        with mock.patch.object(build_subset, "fetch_ecb_rates",
                               return_value=ecb):
            build_site_data.update_rates(self.path)
        new = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(new["money"]["rates"], {"EUR": 0.85, "USD": 0.772727})
        self.assertEqual(new["money"]["rates_date"], "2026-09-26")
        self.assertEqual(new["sections"], self.raw["sections"])  # untouched

    def test_update_rates_offline_leaves_file(self):
        self.path.write_text(json.dumps(self.raw), encoding="utf-8")
        before = self.path.read_bytes()
        with mock.patch.object(build_subset, "fetch_ecb_rates",
                               side_effect=build_subset.RatesUnavailable("x")):
            with self.assertRaises(build_subset.BuildError):
                build_site_data.update_rates(self.path)
        self.assertEqual(self.path.read_bytes(), before)


@unittest.skipUnless(HAS_TYPST, "typst not installed")
class RenderTest(unittest.TestCase):
    """The PDF `make site` builds shows the summary beside the heading."""

    def test_pdf(self):
        work = REPO / "build" / ".site-test"
        self.addCleanup(shutil.rmtree, work, ignore_errors=True)
        with NO_NETWORK, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(build_site_data.main(["--out", str(work / "cv.json")]), 0)
        subprocess.run(
            ["typst", "compile", "--root", ".", "--font-path", "fonts",
             "--creation-timestamp", FIXED_EPOCH, "--input",
             "data=../build/.site-test/cv.json", "src/cv.typ",
             str(work / "cv.pdf")], check=True, capture_output=True, cwd=REPO)
        if shutil.which("pdftotext"):
            text = subprocess.run(["pdftotext", str(work / "cv.pdf"), "-"],
                                  capture_output=True, text=True,
                                  check=True).stdout
            self.assertRegex(text, r"Research Income \(≈ £\d+\.\dM, "
                                   r"£\d+\.\dM as PI\)")


if __name__ == "__main__":
    unittest.main()
