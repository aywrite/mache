# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

"""The book table this repository ships, and how the actions fall back to it.

The table is run as a caller runs it. Nothing here downloads a book: the fetch
is what the Action workflow exercises on a runner. What is pinned here is the
part that needs no network, and that the default can be replaced. Every action
that takes a table defaults to none and settles on the shipped one only then,
so a table the caller names is the one that is asked.
"""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TABLE = ROOT / "bin" / "book_table.sh"
SETUP = ROOT / "actions" / "setup" / "action.yml"
ACTIONS = sorted((ROOT / "actions").glob("*/action.yml"))
WORKFLOWS = [
    ROOT / ".github" / "workflows" / name
    for name in ("strength.yml", "calibrate.yml", "batch.yml")
]

BOOKS = {
    "8moves_v3": ("8moves_v3.pgn", "pgn"),
    "UHO_4060_v2": ("UHO_4060_v2.epd", "epd"),
}


def table(*arguments):
    return subprocess.run(
        [str(TABLE), *[str(argument) for argument in arguments]],
        capture_output=True,
        text=True,
        check=False,
    )


def answer(*arguments):
    result = table(*arguments)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_it_lists_the_books_it_has():
    assert answer("list").splitlines() == list(BOOKS)


def test_the_pin_is_a_commit():
    assert re.fullmatch(r"[0-9a-f]{40}", answer("pin"))


@pytest.mark.parametrize("book", BOOKS)
def test_each_book_names_its_file_and_format(book):
    assert (answer("file", book), answer("format", book)) == BOOKS[book]


@pytest.mark.parametrize("verb", ["file", "format"])
def test_a_book_it_does_not_have_is_refused(verb):
    result = table(verb, "no_such_book")
    assert result.returncode != 0
    assert "no book named no_such_book" in result.stderr


def test_a_pgn_counts_its_games(tmp_path):
    book = tmp_path / "8moves_v3.pgn"
    book.write_text('[Event "a"]\n\n1. e4 *\n\n[Event "b"]\n\n1. d4 *\n')
    assert answer("count", "8moves_v3", book) == "2"


def test_an_epd_counts_its_lines(tmp_path):
    book = tmp_path / "UHO_4060_v2.epd"
    book.write_text("8/8/8/8/8/8/8/K6k w - -\n8/8/8/8/8/8/8/k6K b - -\n")
    assert answer("count", "UHO_4060_v2", book) == "2"


def test_a_file_that_is_not_the_book_fails_the_check(tmp_path):
    (tmp_path / "8moves_v3.pgn").write_text("not the book\n")
    result = table("verify", "8moves_v3", tmp_path)
    assert result.returncode != 0
    assert "not the" in result.stderr


def test_a_missing_file_fails_the_check(tmp_path):
    result = table("verify", "UHO_4060_v2", tmp_path)
    assert result.returncode != 0
    assert "not there" in result.stderr


def test_the_cache_holds_the_files_of_the_shipped_table():
    # otherwise the default would fetch its books on every run
    text = SETUP.read_text(encoding="utf-8")
    for file, _ in BOOKS.values():
        assert f"tools/{file}" in text, file


# the actions that take a table
TAKING = [path for path in ACTIONS if "book_table:" in path.read_text()]


def named(path):
    return path.name if path.parent.name == "workflows" else path.parent.name


def book_table_default(text):
    found = re.search(r"\n\s+book_table:\n(?:.*\n)*?\s+default: (.*)\n", text)
    assert found, "no book_table input"
    return found.group(1)


@pytest.mark.parametrize("path", TAKING + WORKFLOWS, ids=named)
def test_the_default_is_empty_so_a_named_table_always_wins(path):
    # a path of the caller's as the default would be a file a new repository
    # does not have, and the shipped table as the default would hide it from
    # a caller reading the input
    assert book_table_default(path.read_text(encoding="utf-8")) == '""'


@pytest.mark.parametrize("path", TAKING, ids=named)
def test_every_action_falls_back_to_the_shipped_table(path):
    text = path.read_text(encoding="utf-8")
    fallback = "${BOOK_TABLE:-${GITHUB_ACTION_PATH}/../../bin/book_table.sh}"
    settled = "steps.books.outputs.table"
    for block in re.split(r"\n(?=    - )", text)[1:]:
        if "inputs.book_table" in block:
            assert fallback in block, block
    for block in re.split(r"\n(?=    - )", text)[1:]:
        if '"$BOOK_TABLE"' in block and "inputs.book_table" not in block:
            assert settled in block, block
