"""Record ids (spec §6): the rule, the text-preserving insertion, the data."""

import contextlib
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

from support import SRC, copy_repo, drop_id_keys, load, strip_ids

import assign_ids


class SlugRuleTest(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(assign_ids.slugify("Économie & Société — 2ª ed."),
                         "economie-societe-2a-ed")

    def test_context_year_keywords(self):
        self.assertEqual(
            assign_ids.base_id({"date": "2010", "degree": "PhD Economics"},
                               "Education", "education"),
            "education-2010-phd-economics")

    def test_stopwords_dropped_and_four_keywords(self):
        entry = {"date": "2026",
                 "title": "Beyond the Thesis: Helping your research find its way"}
        self.assertEqual(assign_ids.base_id(entry, "Seminars", "talks"),
                         "seminars-2026-beyond-thesis-helping-your")

    def test_year_from_years_then_omitted(self):
        self.assertEqual(
            assign_ids.base_id({"years": "2014-2020", "name": "Stats"},
                               "Undergraduate", "courses"),
            "undergraduate-2014-stats")
        self.assertEqual(
            assign_ids.base_id({"name": "PySAL"}, "Scientific software",
                               "named"),
            "scientific-software-pysal")

    def test_first_four_digit_run_only(self):
        self.assertEqual(
            assign_ids.base_id({"date": "Jun 2019-2021", "role": "Chair"},
                               "Other roles", "positions"),
            "other-roles-2019-chair")

    def test_truncated_to_60_without_trailing_dash(self):
        entry = {"date": "2024", "title": "Aaaaaaaaaaaaaaaaaaaa bbbbbbbbbbbbbbb "
                 "cccccccccccccccccccc ddddddddddddd"}
        got = assign_ids.base_id(entry, "Keynote speeches", "talks")
        self.assertLessEqual(len(got), 60)
        self.assertFalse(got.endswith("-"))
        self.assertTrue(got.startswith("keynote-speeches-2024-aaaa"))

    def test_collisions_suffixed_in_source_order(self):
        cv = {"sections": [{"title": "Talks", "type": "talks", "entries": [
            {"date": "2020", "title": "Same talk"},
            {"date": "2020", "title": "Same talk"},
            {"date": "2020", "title": "Same talk"},
        ]}]}
        ids = assign_ids.new_ids(cv, set())
        self.assertEqual(list(ids.values()), [
            "talks-2020-same-talk", "talks-2020-same-talk-2",
            "talks-2020-same-talk-3"])

    def test_collision_with_publication_id(self):
        cv = {"sections": [{"title": "Talks", "type": "talks",
                            "entries": [{"title": "X"}]}]}
        ids = assign_ids.new_ids(cv, {"talks-x"})
        self.assertEqual(list(ids.values()), ["talks-x-2"])

    def test_suffixed_id_still_within_60(self):
        base = "a" * 60
        cv = {"sections": [{"title": "", "type": "named",
                            "entries": [{"name": base}]}]}
        (got,) = assign_ids.new_ids(cv, {base}).values()
        self.assertEqual(got, "a" * 58 + "-2")

    def test_documented_examples_present(self):
        # The examples quoted in the spec (§6.2), from the real data.
        ids = {e["id"] for _, e, _, _ in assign_ids.iter_entries(load("cv.json"))}
        for expected in (
            "education-2010-phd-economics",
            "current-academic-2022-professor-geographic-data-science",
            "awards-2025-embedding-embeddings-across-social",
            "seminars-2026-beyond-thesis-helping-your",
            "supervisor-2024-yuta-sato",
            "scientific-software-pysal",
        ):
            self.assertIn(expected, ids)


# Awkward-but-valid formatting: one-line objects with and without a space
# after `{`, multi-line objects, nested non-entry objects, and braces, quotes
# and escapes inside strings.
FIXTURE = """{
  "basics": { "name": "X" },

  "sections": [
    {
      "title": "Talks { tricky }",
      "type": "talks",
      "entries": [
        { "date": "2020", "title": "A \\"quoted\\" {brace} talk" },
        {"date": "2019", "title": "No space after brace", "note": "}]"},
        {
          "date": "2018",
          "title": "Multi-line \\\\ entry"
        }
      ]
    },
    {
      "title": "Research Income",
      "groups": [
        {
          "title": "Awards",
          "type": "grant",
          "entries": [
            { "date": "2022", "title": "Grant", "amount": { "value": 1, "currency": "GBP" } }
          ]
        }
      ]
    }
  ]
}
"""


class InsertionTest(unittest.TestCase):
    def assert_invariant(self, before):
        cv = json.loads(before)
        ids = assign_ids.new_ids(cv, set())
        after = assign_ids.insert_ids(before, ids)
        self.assertEqual(strip_ids(after), before)
        parsed = json.loads(after)
        self.assertEqual(drop_id_keys(parsed), cv)
        got = {path: e["id"] for path, e, _, _ in assign_ids.iter_entries(parsed)}
        self.assertEqual(got, ids)
        return after

    def test_fixture(self):
        after = self.assert_invariant(FIXTURE)
        self.assertIn('{ "id": "talks-tricky-2020-quoted-brace-talk", "date"', after)
        self.assertIn('{"id": "talks-tricky-2019-no-space-after-brace", "date"', after)
        self.assertIn('\n        {\n          "id": "talks-tricky-2018-multi-line-entry",\n'
                      '          "date"', after)
        # Only entries get ids — not the nested amount, groups or sections.
        self.assertEqual(after.count('"id"'), 4)

    def test_real_cv_json(self):
        # Stripping the ids from the committed file gives id-less text; the
        # insertion must reproduce it exactly around the ids it adds.
        text = (SRC / "cv.json").read_text(encoding="utf-8")
        original = strip_ids(text)
        self.assertNotIn('"id"', original)
        self.assertEqual(json.loads(original), drop_id_keys(json.loads(text)))
        self.assert_invariant(original)


class DataTest(unittest.TestCase):
    def test_every_entry_has_a_valid_id(self):
        pattern = re.compile(r"^[a-z0-9][a-z0-9-]*$")
        for path, entry, _, _ in assign_ids.iter_entries(load("cv.json")):
            with self.subTest(path=path):
                self.assertIn("id", entry)
                self.assertRegex(entry["id"], pattern)
                self.assertLessEqual(len(entry["id"]), 60)

    def test_ids_unique_across_files(self):
        cv_ids = [e["id"] for _, e, _, _ in assign_ids.iter_entries(load("cv.json"))]
        pub_ids = [p["id"] for p in load("publications.json")]
        all_ids = cv_ids + pub_ids
        self.assertEqual(len(all_ids), len(set(all_ids)))

    def test_role_coi_normalised(self):
        roles = {e.get("role") for _, e, _, _ in
                 assign_ids.iter_entries(load("cv.json"))}
        self.assertNotIn("Co-I", roles)


class IdempotenceTest(unittest.TestCase):
    def run_assign(self, *args):
        """assign_ids.main(args), with its console output swallowed."""
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            return assign_ids.main([str(a) for a in args])

    def test_second_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = copy_repo(tmp) / "src"
            before = (src / "cv.json").read_bytes()
            self.assertEqual(self.run_assign("--src", src), 0)
            self.assertEqual((src / "cv.json").read_bytes(), before)
            self.assertEqual(self.run_assign("--check", "--src", src), 0)

    def test_only_missing_ids_added(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = copy_repo(tmp) / "src"
            cv_path = src / "cv.json"
            full = cv_path.read_text(encoding="utf-8")
            line = '          "id": "education-2010-phd-economics",\n'
            self.assertIn(line, full)
            cv_path.write_text(full.replace(line, "", 1), encoding="utf-8")
            self.assertEqual(self.run_assign("--src", src), 0)
            self.assertEqual(cv_path.read_text(encoding="utf-8"), full)

    def test_check_reports_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = copy_repo(tmp) / "src"
            cv_path = src / "cv.json"
            cv_path.write_text(strip_ids(cv_path.read_text(encoding="utf-8")),
                               encoding="utf-8")
            before = cv_path.read_bytes()
            self.assertEqual(self.run_assign("--check", "--src", src), 1)
            self.assertEqual(cv_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
