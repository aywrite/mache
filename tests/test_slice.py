# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

"""Which openings a shard is handed, as the play action works them out.

`book_slice` decides the arithmetic and has its own tests. What is pinned here
is the step above it: that the openings are counted from the file rather than
read off a number written down somewhere, and that the table is asked what the
format is rather than the count being guessed from the name. A book that
changed size would otherwise move every shard but the first onto its
neighbour's openings, with nothing failing.
"""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SLICE = ROOT / "actions" / "play-shard" / "slice.sh"
BOOKS = ROOT / "tests" / "fixtures" / "books.sh"

GAME = '[Event "?"]\n[Result "*"]\n\n1. e4 e5 *\n\n'


def book_of(directory, openings):
    """A pgn of the given number of openings, as the fixture table counts
    them."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "8moves_v3.pgn").write_text(GAME * openings, encoding="utf-8")
    return directory


def run(workdir, pairs, shards, shard, seed="7"):
    return subprocess.run(
        [
            str(SLICE),
            str(BOOKS),
            "8moves_v3",
            str(workdir),
            str(pairs),
            str(shards),
            str(shard),
            str(seed),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ},
    )


def sliced(result):
    assert result.returncode == 0, result.stderr
    return dict(line.split("=", 1) for line in result.stdout.splitlines())


def test_it_reports_the_file_and_the_format_the_table_names(tmp_path):
    workdir = book_of(tmp_path / "tools", 100)
    slice_ = sliced(run(workdir, pairs=10, shards=2, shard=0))
    assert slice_["book_file"] == "8moves_v3.pgn"
    # what fastchess reads the file as, which the count depends on: a pgn
    # holds a game per opening and an epd a position a line
    assert slice_["book_format"] == "pgn"


def test_the_openings_are_counted_from_the_file(tmp_path):
    workdir = book_of(tmp_path / "tools", 37)
    assert sliced(run(workdir, pairs=5, shards=2, shard=0))["openings"] == "37"


def test_two_shards_of_one_run_start_in_different_places(tmp_path):
    workdir = book_of(tmp_path / "tools", 1000)
    first = sliced(run(workdir, pairs=10, shards=2, shard=0))["start"]
    second = sliced(run(workdir, pairs=10, shards=2, shard=1))["start"]
    assert first != second


def test_a_seed_replays_the_schedule(tmp_path):
    # the seed is what a manifest records so a run can be played again
    workdir = book_of(tmp_path / "tools", 1000)
    again = sliced(run(workdir, pairs=10, shards=2, shard=1, seed="7"))["start"]
    assert again == sliced(run(workdir, pairs=10, shards=2, shard=1, seed="7"))["start"]


def test_a_different_seed_is_a_different_schedule(tmp_path):
    workdir = book_of(tmp_path / "tools", 1000)
    one = sliced(run(workdir, pairs=10, shards=2, shard=0, seed="7"))["start"]
    other = sliced(run(workdir, pairs=10, shards=2, shard=0, seed="8"))["start"]
    assert one != other


def test_a_book_that_is_not_there_fails_rather_than_slicing_nothing(tmp_path):
    (tmp_path / "tools").mkdir()
    assert run(tmp_path / "tools", pairs=10, shards=2, shard=0).returncode != 0


def test_an_empty_book_fails(tmp_path):
    workdir = book_of(tmp_path / "tools", 0)
    result = run(workdir, pairs=10, shards=2, shard=0)
    assert result.returncode != 0
    assert "no openings" in result.stderr


def test_a_run_wanting_more_openings_than_the_book_holds_says_so(tmp_path):
    # book_slice remarks on it rather than failing, and the remark has to
    # reach the caller as something other than silence
    workdir = book_of(tmp_path / "tools", 10)
    result = run(workdir, pairs=50, shards=2, shard=0)
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip()
