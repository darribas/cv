"""Shared helpers for the test suite (not a test module itself).

Puts src/ on sys.path so tests can import the pipeline's scripts as modules.
"""

import json
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# The exact text src/assign_ids.py inserts (spec §6.2): a whole line in a
# multi-line object, `"id": "…", ` in a one-line object.
_ID_LINE = re.compile(r'\r?\n[ \t]*"id": "[^"\\]*",(?=\r?\n)')
_ID_INLINE = re.compile(r'"id": "[^"\\]*"(, )?')


def strip_ids(text):
    """Remove every inserted id from cv.json text (inverse of insert_ids)."""
    return _ID_INLINE.sub("", _ID_LINE.sub("", text))


def drop_id_keys(value):
    """Parsed JSON with every "id" key removed, recursively."""
    if isinstance(value, dict):
        return {k: drop_id_keys(v) for k, v in value.items() if k != "id"}
    if isinstance(value, list):
        return [drop_id_keys(v) for v in value]
    return value


def load(name):
    return json.loads((SRC / name).read_text(encoding="utf-8"))


def copy_repo(dest, with_fonts=False):
    """Copy src/ (and optionally fonts/) under `dest`, mirroring the repo."""
    dest = Path(dest)
    shutil.copytree(SRC, dest / "src",
                    ignore=shutil.ignore_patterns("__pycache__"))
    if with_fonts:
        shutil.copytree(REPO / "fonts", dest / "fonts")
    return dest
