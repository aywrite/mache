# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

"""Every source file carries the licence notice, so a new one cannot ship
without it.

The repository is MIT and says so in LICENSE, but a scanner reads files rather
than repositories, and a file that travels on its own says nothing about its
terms unless it carries them. The header is two lines and this test is what
keeps them there.
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SPDX = "SPDX-License-Identifier: MIT"

# What counts as a source file, by extension rather than by where it sits, so
# that a new directory of sources is covered the day it appears.
SUFFIXES = {".py", ".sh"}

PRUNE = {".git", "__pycache__", ".venv", "build", "dist"}


def source_files():
    for directory, subdirectories, names in os.walk(ROOT):
        subdirectories[:] = [
            d for d in subdirectories if d not in PRUNE and not d.endswith(".egg-info")
        ]
        for name in names:
            if Path(name).suffix in SUFFIXES:
                yield Path(directory) / name


def test_every_source_file_states_its_licence():
    missing = []
    for path in source_files():
        # the notice sits in the first few lines: after a shebang if there is
        # one, and nowhere lower, or a scanner reading heads will not see it
        head = "".join(path.read_text(encoding="utf-8").splitlines(keepends=True)[:3])
        if SPDX not in head:
            missing.append(str(path.relative_to(ROOT)))
    assert not missing, f"no licence header in: {', '.join(sorted(missing))}"


def test_the_walk_actually_finds_the_sources():
    # a walk that silently matched nothing would pass the test above forever.
    # It finds fifteen today, which is the six modules, the eight test files
    # and the fixture book table. The floor is under that, because what is being
    # caught is a walk that has stopped working rather than one that drifted by
    # a file.
    found = list(source_files())
    assert len(found) > 8, f"only {len(found)} source files found, the walk has drifted"


def test_the_walk_reaches_every_directory_that_holds_sources():
    # one per directory the sources live in. A walk that stops covering a
    # directory fails here rather than going quiet.
    found = {Path(p).resolve().relative_to(ROOT).as_posix() for p in source_files()}
    for path in (
        "mache/match_estimate.py",
        "tests/conftest.py",
        "tests/fixtures/books.sh",
    ):
        assert path in found, f"{path} is not covered by the licence walk"
