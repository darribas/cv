#!/usr/bin/env python3
"""Shim: the validator now lives at src/validate_cv.py (the subset-CV build
imports it too). Kept so existing instructions and habits keep working.

Usage:  python3 .claude/skills/add-cv-record/validate_cv.py [repo_root]
"""

import runpy
from pathlib import Path

runpy.run_path(
    str(Path(__file__).resolve().parents[3] / "src" / "validate_cv.py"),
    run_name="__main__",
)
