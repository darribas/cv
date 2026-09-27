"""src/validate_cv.py: the real data passes; each id rule is enforced."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from support import REPO, copy_repo

import validate_cv


class ValidateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = copy_repo(self._tmp.name)
        self.cv_path = self.root / "src" / "cv.json"
        self.cv = json.loads(self.cv_path.read_text(encoding="utf-8"))

    def tearDown(self):
        self._tmp.cleanup()

    def first_entry(self):
        return self.cv["sections"][0]["entries"][0]

    def errors_after_edit(self):
        self.cv_path.write_text(json.dumps(self.cv), encoding="utf-8")
        return validate_cv.check(self.root)

    def assert_one_error(self, *fragments):
        errors = self.errors_after_edit()
        self.assertEqual(len(errors), 1, errors)
        for f in fragments:
            self.assertIn(f, errors[0])

    def test_repo_data_is_clean(self):
        self.assertEqual(validate_cv.check(REPO), [])

    def test_missing_id(self):
        del self.first_entry()["id"]
        self.assert_one_error("cv.json", "sections[0].entries[0]",
                              "missing required key 'id'")

    def test_bad_pattern(self):
        self.first_entry()["id"] = "Bad_Id"
        self.assert_one_error("cv.json", "'Bad_Id'", "does not match")

    def test_too_long(self):
        self.first_entry()["id"] = "a" * 61
        self.assert_one_error("longer than 60")

    def test_duplicate_within_cv(self):
        entries = self.cv["sections"][0]["entries"]
        entries[1]["id"] = entries[0]["id"]
        self.assert_one_error("duplicate id", entries[0]["id"],
                              "sections[0].entries[1]", "sections[0].entries[0]")

    def test_duplicate_across_files(self):
        pubs = json.loads((self.root / "src" / "publications.json")
                          .read_text(encoding="utf-8"))
        self.first_entry()["id"] = pubs[0]["id"]
        self.assert_one_error("also a publications.json id", pubs[0]["id"])

    def test_shim_at_old_path_still_works(self):
        shim = REPO / ".claude" / "skills" / "add-cv-record" / "validate_cv.py"
        run = subprocess.run([sys.executable, str(shim)], capture_output=True,
                             text=True, cwd=REPO)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("unique across both files", run.stdout)


if __name__ == "__main__":
    unittest.main()
