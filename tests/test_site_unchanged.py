"""Ids change nothing but the web page's per-item links: the PDF is identical
with and without them, and the HTML differs only by each item's `id` attribute
and permalink glyph (issue #17).

Both builds run in this test, side by side in temp copies of the repo — never
against the committed docs/, whose PDF embeds its build time and date (spec
§14.2). Typst's --creation-timestamp pins both the PDF metadata and
`datetime.today()` (checked with Typst 0.15: the trailing date line renders
the fixed date), so the PDFs can be compared byte for byte.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from support import copy_repo, strip_ids

FIXED_EPOCH = "1767225600"  # 2026-01-01T00:00:00Z

# What render_html.anchor() adds for a record with an id.
_ANCHOR = re.compile(rb'(<div class="(?:entry|named)") id="[^"]*">'
                     rb'<a class="permalink" [^>]*>.*?</a>')


def without_anchors(html):
    return _ANCHOR.sub(rb"\1>", html)


class SiteUnchangedByIdsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        cls.with_ids = copy_repo(tmp / "with-ids", with_fonts=True)
        cls.without_ids = copy_repo(tmp / "without-ids", with_fonts=True)
        cv = cls.without_ids / "src" / "cv.json"
        cv.write_text(strip_ids(cv.read_text(encoding="utf-8")),
                      encoding="utf-8")
        assert '"id"' not in cv.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def render_html(self, root):
        subprocess.run([sys.executable, str(root / "src" / "render_html.py")],
                       check=True, capture_output=True, cwd=root)
        return (root / "docs" / "index.html").read_bytes()

    def test_html_differs_only_by_anchors(self):
        with_ids = self.render_html(self.with_ids)
        # sanity: the stripped copy does lose its cv.json anchors
        self.assertIn(b'id="education-2010-phd-economics"', with_ids)
        self.assertEqual(without_anchors(with_ids),
                         without_anchors(self.render_html(self.without_ids)))

    @unittest.skipUnless(shutil.which("typst"), "typst not installed")
    def test_pdf_identical(self):
        def build(root):
            out = root / "cv.pdf"
            subprocess.run(
                ["typst", "compile", "--font-path", "fonts",
                 "--creation-timestamp", FIXED_EPOCH, "src/cv.typ", str(out)],
                check=True, capture_output=True, cwd=root,
                env={**os.environ, "SOURCE_DATE_EPOCH": FIXED_EPOCH})
            return out.read_bytes()

        self.assertEqual(build(self.with_ids), build(self.without_ids))


if __name__ == "__main__":
    unittest.main()
