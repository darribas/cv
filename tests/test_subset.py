"""src/build_subset.py (spec P1): config, selection, PDF, guards.

Configs are written inside each test into a temporary directory — none are
tracked, which also exercises "config and outputs outside the repo". The two
tests that put a config inside the repo use the gitignored subsets/ folder and
remove it afterwards.
"""

import contextlib
import copy
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from support import REPO, SRC, load

import build_subset
import validate_cv

FIXED_EPOCH = "1767225600"  # 2026-01-01T00:00:00Z — pins PDF metadata and date
HAS_TYPST = shutil.which("typst") is not None

MASTER = build_subset.load_master()
ALL_TITLES = [s["title"] for s in load("cv.json")["sections"]]


def toml_list(values):
    return "[" + ", ".join(json.dumps(v) for v in values) + "]"


def sections_config(titles):
    return "".join(f'[[section]]\ntitle = {json.dumps(t)}\n\n' for t in titles)


class TempConfig:
    """Write config text into a fresh temp dir; clean up on exit."""

    def __init__(self, text, stem="subset"):
        self.text, self.stem = textwrap.dedent(text), stem

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.path = self.dir / f"{self.stem}.toml"
        self.path.write_text(self.text, encoding="utf-8")
        return self

    def __exit__(self, *exc):
        self._tmp.cleanup()


def plan_of(text, stem="subset"):
    with TempConfig(text, stem) as c:
        return build_subset.parse_config(c.path, MASTER)


def derive(text):
    return build_subset.select(plan_of(text), MASTER)


def problems_of(text, stem="subset"):
    try:
        plan_of(text, stem)
    except build_subset.BuildError as e:
        return e.problems
    return []


def compile_full_cv(out):
    """Build A of the identity test: the full CV, no inputs, fixed time."""
    subprocess.run(
        ["typst", "compile", "--font-path", "fonts", "--creation-timestamp",
         FIXED_EPOCH, "src/cv.typ", str(out)],
        check=True, capture_output=True, cwd=REPO,
        env={**os.environ, "SOURCE_DATE_EPOCH": FIXED_EPOCH})
    return out.read_bytes()


def full_cv_as_derived():
    """What the derived data of an everything-included config must equal."""
    cv = copy.deepcopy(load("cv.json"))
    for s in cv["sections"]:
        if s.get("type") == "publications":
            s["source"] = "../build/.subset-work/publications.json"
    return cv, load("publications.json")


# ===========================================================================
# Identity (spec §14.2) and --scaffold.
# ===========================================================================

@unittest.skipUnless(HAS_TYPST, "typst not installed")
class IdentityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        cls.full_pdf = compile_full_cv(cls.tmp / "A.pdf")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def build(self, config):
        with mock.patch.dict(os.environ, {"SOURCE_DATE_EPOCH": FIXED_EPOCH}):
            return build_subset.build(config, master=MASTER)

    def assert_is_full_cv(self, out):
        cv, pubs = full_cv_as_derived()
        self.assertEqual(json.loads((out / "cv.json").read_text()), cv)
        self.assertEqual(json.loads((out / "publications.json").read_text()), pubs)

    def test_all_sections_is_the_full_cv(self):
        config = self.tmp / "everything.toml"
        config.write_text(sections_config(ALL_TITLES))
        m = self.build(config)
        out = Path(m["out"])
        self.assertEqual(len(ALL_TITLES), 17)
        self.assert_is_full_cv(out)
        self.assertEqual((out / "darribas-cv-everything.pdf").read_bytes(),
                         self.full_pdf)

        # HTML: bare render vs --data on the derived data, same run.
        def html(*args, dest):
            subprocess.run([sys.executable, str(SRC / "render_html.py"), *args,
                            "--out", str(dest)],
                           check=True, capture_output=True, cwd=REPO)
            return (dest / "index.html").read_bytes()

        self.assertEqual(html(dest=self.tmp / "html-a"),
                         html("--data", str(out / "cv.json"),
                              dest=self.tmp / "html-b"))

    def test_scaffold_builds_the_full_cv(self):
        config = self.tmp / "scaffolded.toml"
        config.write_text(build_subset.scaffold(MASTER), encoding="utf-8")
        out = Path(self.build(config)["out"])
        self.assert_is_full_cv(out)
        self.assertEqual((out / "darribas-cv-scaffolded.pdf").read_bytes(),
                         self.full_pdf)


class ScaffoldTest(unittest.TestCase):
    def test_lists_every_section_group_and_id(self):
        text = build_subset.scaffold(MASTER)
        plan = plan_of(text)
        self.assertEqual([s["title"] for s in plan["sections"]], ALL_TITLES)
        listed = {i for s in plan["sections"]
                  for i in (s["ids"] or []) + [i for g in s["groups"] or []
                                               for i in g["ids"] or []]}
        self.assertEqual(listed, set(MASTER.owner))

    def test_write_to_new_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "new" / "erc.toml"  # parent created too
            build_subset.write_scaffold(MASTER, path)
            self.assertEqual(path.read_text(encoding="utf-8"),
                             build_subset.scaffold(MASTER))

    def test_write_inside_repo_allowed_and_untracked(self):
        before = git_status()
        folder = REPO / "subsets"
        existed = folder.exists()
        path = folder / "zz-test-scaffold.toml"
        try:
            build_subset.write_scaffold(MASTER, path)
            self.assertTrue(path.exists())
            self.assertEqual(git_status(), before)  # gitignored
        finally:
            path.unlink(missing_ok=True)
            if not existed:
                shutil.rmtree(folder, ignore_errors=True)

    def test_write_refuses_existing_and_non_toml(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp) / "mine.toml"
            existing.write_text("# hand-edited\n")
            for path, fragment in [
                (existing, "already exists"),
                (Path(tmp) / "x.txt", "must end in .toml"),
            ]:
                with self.subTest(path=path):
                    with self.assertRaises(build_subset.BuildError) as e:
                        build_subset.write_scaffold(MASTER, path)
                    self.assertIn(fragment, e.exception.problems[0])
            self.assertEqual(existing.read_text(), "# hand-edited\n")

    def test_ids_carry_a_description_comment(self):
        text = build_subset.scaffold(MASTER)
        self.assertIn('"education-2010-phd-economics",  # 2010 PhD Economics',
                      text)


# ===========================================================================
# Selection (spec §5).
# ===========================================================================

class SelectionTest(unittest.TestCase):
    def titles(self, cv):
        return [s["title"] for s in cv["sections"]]

    def section(self, cv, title):
        return next(s for s in cv["sections"] if s["title"] == title)

    def master_section(self, title):
        return MASTER.sections[title]

    def test_config_order_and_unlisted_dropped(self):
        cv, _, _ = derive(sections_config(["Teaching", "Education"]))
        self.assertEqual(self.titles(cv), ["Teaching", "Education"])

    def test_whole_section_verbatim(self):
        cv, _, _ = derive(sections_config(["Education"]))
        self.assertEqual(cv["sections"][0], self.master_section("Education"))

    def test_ids_printed_in_source_order(self):
        src = self.master_section("Education")["entries"]
        wanted = [src[2]["id"], src[0]["id"]]
        cv, _, counts = derive(f'''
            [[section]]
            title = "Education"
            ids = {toml_list(wanted)}
        ''')
        self.assertEqual(cv["sections"][0]["entries"], [src[0], src[2]])
        self.assertEqual(counts[0], {"section": "Education",
                                     "heading": "Education",
                                     "kept": 2, "total": 3})

    def test_group_tables_restrict_and_order(self):
        cv, _, _ = derive('''
            [[section]]
            title = "Research Income"
              [[section.group]]
              title = "Projects (as researcher)"
              [[section.group]]
              title = "Awards"
        ''')
        groups = cv["sections"][0]["groups"]
        self.assertEqual([g["title"] for g in groups],
                         ["Projects (as researcher)", "Awards"])
        src = {g["title"]: g for g in self.master_section("Research Income")["groups"]}
        self.assertEqual(groups[1], src["Awards"])

    def test_group_ids(self):
        awards = self.master_section("Research Income")["groups"][0]["entries"]
        cv, _, _ = derive(f'''
            [[section]]
            title = "Research Income"
              [[section.group]]
              title = "Awards"
              ids = {toml_list([awards[3]["id"]])}
        ''')
        self.assertEqual(cv["sections"][0]["groups"][0]["entries"], [awards[3]])

    def test_section_ids_drop_emptied_groups(self):
        awards = self.master_section("Research Income")["groups"][0]["entries"]
        cv, _, counts = derive(f'''
            [[section]]
            title = "Research Income"
            ids = {toml_list([awards[0]["id"]])}
        ''')
        groups = cv["sections"][0]["groups"]
        self.assertEqual([g["title"] for g in groups], ["Awards"])
        self.assertEqual(groups[0]["entries"], [awards[0]])
        self.assertEqual(counts[0]["kept"], 1)

    def test_publications_by_id(self):
        pubs = load("publications.json")
        wanted = [pubs[5]["id"], pubs[0]["id"]]
        cv, derived_pubs, counts = derive(f'''
            [[section]]
            title = "Publications"
            ids = {toml_list(wanted)}
        ''')
        self.assertEqual(derived_pubs, [pubs[0], pubs[5]])  # verbatim, source order
        section = cv["sections"][0]
        self.assertEqual(section["source"],
                         "../build/.subset-work/publications.json")
        self.assertEqual({g["category"] for g in section["groups"]},
                         {pubs[0]["category"], pubs[5]["category"]})
        self.assertEqual(counts[0]["kept"], 2)
        self.assertEqual(counts[0]["total"], len(pubs))

    def test_publications_by_group(self):
        cv, derived_pubs, _ = derive('''
            [[section]]
            title = "Publications"
              [[section.group]]
              title = "Books"
        ''')
        category = cv["sections"][0]["groups"][0]["category"]
        self.assertEqual(derived_pubs, [p for p in load("publications.json")
                                        if p["category"] == category])

    def test_no_publications_section(self):
        _, derived_pubs, _ = derive(sections_config(["Education"]))
        self.assertEqual(derived_pubs, [])

    def test_drop(self):
        cv, _, _ = derive('drop = ["Teaching", "Publications"]')
        self.assertEqual(self.titles(cv),
                         [t for t in ALL_TITLES if t not in ("Teaching", "Publications")])

    def test_rename_and_header_title(self):
        cv, _, counts = derive('''
            [header]
            title = "Short CV"
            [[section]]
            title = "Research Income"
            rename = "Funding"
              [[section.group]]
              title = "Awards"
              rename = "Grants"
        ''')
        self.assertEqual(cv["basics"]["title"], "Short CV")
        self.assertEqual(cv["sections"][0]["title"], "Funding")
        self.assertEqual(cv["sections"][0]["groups"][0]["title"], "Grants")
        self.assertEqual(counts[0]["section"], "Research Income")
        self.assertEqual(counts[0]["heading"], "Funding")

    def test_master_untouched(self):
        before = copy.deepcopy(MASTER.cv)
        derive('[header]\ntitle = "X"\n' + sections_config(["Education"]))
        self.assertEqual(MASTER.cv, before)

    def test_derived_data_validates(self):
        schema = json.loads((SRC / "cv.schema.json").read_text())
        cv, _, _ = derive('drop = ["Teaching"]')
        v = validate_cv.SchemaValidator(schema)
        v.validate(cv, schema, "")
        self.assertEqual(v.errors, [])


# ===========================================================================
# Config errors (spec §12) — each must be reported, naming file, key, value.
# ===========================================================================

class ConfigErrorTest(unittest.TestCase):
    def assert_problem(self, text, *fragments, stem="subset"):
        problems = problems_of(text, stem)
        self.assertTrue(
            any(all(f in p for f in fragments) for p in problems),
            f"no problem mentions {fragments}; got {problems}")

    def test_not_toml(self):
        self.assert_problem("[[section]\n", "subset.toml", "not valid TOML")

    def test_unknown_keys(self):
        self.assert_problem('colour = 1\n' + sections_config(["Education"]),
                            "subset.toml", "unknown key 'colour'")
        self.assert_problem('[[section]]\ntitle = "Education"\nidz = ["x"]\n',
                            "[[section]] #1", "unknown key 'idz'", "did you mean 'ids'")
        self.assert_problem('''
            [[section]]
            title = "Research Income"
              [[section.group]]
              title = "Awards"
              colour = 1
        ''', "[[section.group]] #1", "unknown key 'colour'")
        self.assert_problem('[header]\nsubtitle = "x"\n' + sections_config(["Education"]),
                            "[header]", "unknown key 'subtitle'")

    def test_wrong_types(self):
        base = sections_config(["Education"])
        self.assert_problem('formats = "pdf"\n' + base, "formats",
                            "expected an array")
        self.assert_problem('[[section]]\ntitle = 3\n', "'title' must be a string")
        self.assert_problem('[[section]]\ntitle = "Education"\nids = "x"\n',
                            ".ids", "expected an array")
        self.assert_problem('[[section]]\ntitle = "Education"\nids = [1]\n',
                            ".ids[0]", "expected a string")
        self.assert_problem('[[section]]\ntitle = "Education"\nrename = 1\n',
                            "'rename' must be a non-empty string")
        self.assert_problem('drop = "Teaching"\n', "drop", "expected an array")
        self.assert_problem('name = 3\n' + base, "name", "must match")
        self.assert_problem('header = 3\n' + base, "header", "expected a table")

    def test_later_phase_keys(self):
        base = sections_config(["Education"])
        for text, key, phase in [
            ('[style]\nfont = "Arial"\n' + base, "'style'", "P3"),
            ('[money]\ncurrency = "GBP"\n' + base, "'money'", "P2"),
            ('[summary]\ndefault = []\n' + base, "'summary'", "P2"),
            ('[header]\nemail = false\n' + base, "'email'", "P5"),
            ('[[section]]\ntitle = "Education"\nsummary = ["count"]\n',
             "'summary'", "P2"),
            ('formats = ["pdf", "docx"]\n' + base, "'docx'", "P4"),
        ]:
            with self.subTest(key=key):
                self.assert_problem(text, key, "not available yet", phase)

    def test_section_or_drop(self):
        self.assert_problem('name = "x"\n', "exactly one of", "found neither")
        self.assert_problem('drop = ["Teaching"]\n' + sections_config(["Education"]),
                            "exactly one of", "not both")

    def test_empty_ids(self):
        self.assert_problem('[[section]]\ntitle = "Education"\nids = []\n',
                            "'Education'.ids", "empty array",
                            "remove 'ids' to include the whole section")

    def test_unknown_titles(self):
        self.assert_problem(sections_config(["Educaton"]),
                            "'Educaton'", "no section titled",
                            "did you mean 'Education'")
        self.assert_problem('drop = ["Teachin"]\n', "drop[0]", "no section titled")
        self.assert_problem('''
            [[section]]
            title = "Research Income"
              [[section.group]]
              title = "Award"
        ''', "'Research Income'", "no group titled 'Award'")

    def test_unknown_id(self):
        self.assert_problem('''
            [[section]]
            title = "Education"
            ids = ["education-2010-phd-economic"]
        ''', "'Education'.ids[0]", "'education-2010-phd-economic'",
            "matches no record", "did you mean 'education-2010-phd-economics'")

    def test_id_from_another_section_or_group(self):
        self.assert_problem('''
            [[section]]
            title = "Education"
            ids = ["rey2023geographic"]
        ''', "'Education'.ids[0]", "not in this section",
            "belongs to section 'Publications'")
        awards_id = MASTER.sections["Research Income"]["groups"][0]["entries"][0]["id"]
        self.assert_problem(f'''
            [[section]]
            title = "Research Income"
              [[section.group]]
              title = "Projects (as researcher)"
              ids = ["{awards_id}"]
        ''', "not in this group", "group 'Awards'")

    def test_structure(self):
        self.assert_problem('''
            [[section]]
            title = "Education"
              [[section.group]]
              title = "x"
        ''', "'Education'", "the section has no groups")
        awards_id = MASTER.sections["Research Income"]["groups"][0]["entries"][0]["id"]
        self.assert_problem(f'''
            [[section]]
            title = "Research Income"
            ids = ["{awards_id}"]
              [[section.group]]
              title = "Awards"
        ''', "both 'ids' and [[section.group]]")
        self.assert_problem(sections_config(["Education", "Education"]),
                            "listed more than once")
        self.assert_problem('''
            [[section]]
            title = "Education"
            ids = ["education-2010-phd-economics", "education-2010-phd-economics"]
        ''', "listed more than once")

    def test_name_from_file_stem(self):
        self.assertEqual(plan_of(sections_config(["Education"]), "erc-2027")["name"],
                         "erc-2027")
        self.assert_problem(sections_config(["Education"]), "set 'name'",
                            stem="ERC 2027")

    def test_all_problems_reported_together(self):
        problems = problems_of('colour = 1\n' + sections_config(["Nope", "Nada"]))
        self.assertEqual(len(problems), 3, problems)

    def test_template_is_a_valid_config(self):
        plan = build_subset.parse_config(SRC / "subset.template.toml", MASTER)
        self.assertEqual(plan["name"], "example")

    def test_master_data_problems_stop_the_build(self):
        with mock.patch.object(build_subset.validate_cv, "check",
                               return_value=["cv.json: broken"]):
            with self.assertRaises(build_subset.BuildError) as e:
                build_subset.load_master()
        self.assertIn("master data: cv.json: broken", e.exception.problems[0])


# ===========================================================================
# Never in the repo (spec §13).
# ===========================================================================

def git_status():
    return subprocess.run(["git", "status", "--porcelain", "--ignored=no"],
                          cwd=REPO, capture_output=True, text=True,
                          check=True).stdout


class OutputGuardTest(unittest.TestCase):
    def assert_refused(self, out, fragment="private"):
        with TempConfig(sections_config(["Education"])) as c:
            with self.assertRaises(build_subset.BuildError) as e:
                build_subset.build(c.path, out=out, master=MASTER)
        self.assertIn(fragment, e.exception.problems[0])
        self.assertIn("subsets/", e.exception.problems[0])  # says where to go

    def test_public_and_source_dirs_refused(self):
        for out in (REPO / "docs" / "x", REPO / "docs", REPO / "src",
                    REPO / "src" / "x", REPO):
            with self.subTest(out=out):
                self.assert_refused(out, "never go there")
        self.assertFalse((REPO / "docs" / "x").exists())

    def test_tracked_or_unignored_repo_paths_refused(self):
        for out in (REPO / "notes" / "x", REPO / "tests" / "x"):
            with self.subTest(out=out):
                self.assert_refused(out, "not ignored by git")
        self.assertFalse((REPO / "notes" / "x").exists())

    def test_scratch_dir_refused(self):
        for out in (REPO / "build", REPO / "build" / ".subset-work",
                    REPO / "build" / ".subset-work" / "x"):
            with self.subTest(out=out):
                self.assert_refused(out, "overlaps")

    def test_ignored_repo_paths_allowed(self):
        for out in (REPO / "subsets" / "erc", REPO / "build" / "mine"):
            with self.subTest(out=out):
                self.assertEqual(
                    build_subset.resolve_out(REPO / "x.toml", "x", out), out)

    def test_relative_repo_path_refused(self):
        cwd = os.getcwd()
        os.chdir(REPO)
        try:
            self.assert_refused(Path("docs/x"), "never go there")
        finally:
            os.chdir(cwd)

    def test_symlink_into_repo_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / "link"
            link.symlink_to(REPO / "docs")
            self.assert_refused(link / "x", "never go there")

    def test_config_in_src_means_default_out_refused(self):
        # Default output = beside the config: src/example, so refused.
        # (Uses the one tracked TOML file, so nothing is created.)
        with self.assertRaises(build_subset.BuildError) as e:
            build_subset.build(SRC / "subset.template.toml", master=MASTER)
        self.assertIn("never go there", e.exception.problems[0])


@unittest.skipUnless(HAS_TYPST, "typst not installed")
class BuildTest(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SRC / "build_subset.py"),
                               *map(str, args)], capture_output=True, text=True,
                              cwd=REPO)

    def test_default_build_beside_config_leaves_repo_clean(self):
        before = git_status()
        with TempConfig('''
            [header]
            title = "Short CV"
            [[section]]
            title = "Education"
            [[section]]
            title = "Publications"
            ids = ["rey2023geographic"]
        ''', stem="erc-2027") as c:
            run = self.run_cli(c.path)
            self.assertEqual(run.returncode, 0, run.stderr)
            out = c.dir / "erc-2027"
            self.assertEqual(
                sorted(p.name for p in out.iterdir()),
                ["config.toml", "cv.json", "darribas-cv-erc-2027.pdf",
                 "manifest.json", "publications.json"])
            self.assertEqual((out / "config.toml").read_bytes(), c.path.read_bytes())
            m = json.loads((out / "manifest.json").read_text())
            self.assertEqual(m["name"], "erc-2027")
            self.assertEqual(m["config"], str(c.path.resolve()))
            self.assertEqual(m["formats"], ["pdf"])
            self.assertEqual(m["files"], ["darribas-cv-erc-2027.pdf"])
            # The PDF is the subset, not the full CV (30 pages at the time of
            # writing): the renderer really read the derived data.
            self.assertIn(m["pages"], (1, 2, 3))
            self.assertRegex(m["data_commit"], r"^[0-9a-f]{40}$")
            self.assertIsInstance(m["dirty"], bool)
            self.assertEqual([(s["section"], s["kept"]) for s in m["sections"]],
                             [("Education", 3), ("Publications", 1)])
            self.assertEqual(m["warnings"], [])
            self.assertTrue((out / "darribas-cv-erc-2027.pdf").read_bytes()
                            .startswith(b"%PDF"))
        self.assertEqual(git_status(), before)

    def test_bad_config_exits_1_and_writes_nothing(self):
        with TempConfig(sections_config(["Nope"])) as c:
            run = self.run_cli(c.path)
            self.assertEqual(run.returncode, 1)
            self.assertIn("no section titled 'Nope'", run.stderr)
            self.assertFalse((c.dir / "subset").exists())

    def test_out_flag(self):
        with TempConfig(sections_config(["Education"])) as c:
            run = self.run_cli(c.path, "--out", c.dir / "elsewhere", "--strict")
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertTrue((c.dir / "elsewhere" / "darribas-cv-subset.pdf").exists())


@unittest.skipUnless(HAS_TYPST and shutil.which("make"), "needs typst and make")
class MakeTargetsTest(unittest.TestCase):
    """The make interface: `make subset` twice — starter, then build."""

    def make(self, *args, home):
        return subprocess.run(["make", "-s", *args], cwd=REPO, text=True,
                              capture_output=True, env={**os.environ, "HOME": home})

    def test_new_then_build(self):
        before = git_status()
        with tempfile.TemporaryDirectory() as home:
            config = "~/cv-subsets/everything.toml"  # expanded by the build
            written = Path(home) / "cv-subsets" / "everything.toml"
            out = Path(home) / "cv-subsets" / "everything"

            # First run: no config yet -> writes the starter, builds nothing.
            run = self.make("subset", f"CONFIG={config}", home=home)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("wrote a starter one", run.stdout)
            self.assertEqual(written.read_text(encoding="utf-8"),
                             build_subset.scaffold(MASTER))
            self.assertFalse(out.exists())

            # Edit it, then the same command builds it, leaving it untouched.
            edited = sections_config(["Education"])
            written.write_text(edited, encoding="utf-8")
            run = self.make("subset", f"CONFIG={config}", home=home)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("Built everything", run.stdout)
            self.assertTrue((out / "darribas-cv-everything.pdf").exists())
            self.assertEqual(written.read_text(encoding="utf-8"), edited)
        self.assertEqual(git_status(), before)

    def test_usage_without_config(self):
        run = subprocess.run(["make", "-s", "subset"], cwd=REPO,
                             capture_output=True, text=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("usage: make subset", run.stdout)

    def test_config_in_subsets_folder(self):
        # The container workflow: config and outputs both inside the repo,
        # in the gitignored subsets/ folder, relative path, no OUT.
        before = git_status()
        folder = REPO / "subsets"
        existed = folder.exists()
        config = folder / "zz-test.toml"
        try:
            def make_subset():
                return subprocess.run(
                    ["make", "-s", "subset", "CONFIG=subsets/zz-test.toml"],
                    cwd=REPO, capture_output=True, text=True)
            run = make_subset()
            self.assertEqual(run.returncode, 0, run.stderr)  # starter written
            self.assertTrue(config.exists())
            config.write_text(sections_config(["Education"]))
            run = make_subset()
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertTrue((folder / "zz-test" / "darribas-cv-zz-test.pdf").exists())
            self.assertEqual(git_status(), before)
        finally:
            config.unlink(missing_ok=True)
            shutil.rmtree(folder / "zz-test", ignore_errors=True)
            if not existed:
                shutil.rmtree(folder, ignore_errors=True)

    def test_list(self):
        run = subprocess.run(["make", "-s", "subset-list", "SECTION=Education"],
                             cwd=REPO, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("education-2010-phd-economics", run.stdout)
        self.assertNotIn("rey2023geographic", run.stdout)


class ListTest(unittest.TestCase):
    def test_everything(self):
        text = build_subset.listing(MASTER)
        for rid in MASTER.owner:
            self.assertIn(rid, text)
        self.assertIn("== Research Income", text)
        self.assertIn("-- Awards", text)

    def test_one_section(self):
        text = build_subset.listing(MASTER, "education")  # case-insensitive
        self.assertIn("education-2010-phd-economics", text)
        self.assertNotIn("rey2023geographic", text)

    def test_unknown_section(self):
        with self.assertRaises(build_subset.BuildError) as e:
            build_subset.listing(MASTER, "Educaton")
        self.assertIn("did you mean 'Education'", e.exception.problems[0])

    def test_cli_needs_exactly_one_mode(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                build_subset.main([])
            with self.assertRaises(SystemExit):
                build_subset.main(["x.toml", "--scaffold"])
            with self.assertRaises(SystemExit):
                build_subset.main(["--list", "--scaffold", "x.toml"])


if __name__ == "__main__":
    unittest.main()
