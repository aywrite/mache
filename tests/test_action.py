# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

"""What the composite action promises, read off the action itself.

Running it needs a runner, which the Action workflow does. What is checked here
is the part a green run would not notice: that the books are checked on the path
most runs take rather than only on the path that fetched them, that the cache
key is built from what the table says its pin is rather than from a pin written
down a second time, and that the action asks a table for nothing the contract in
actions/setup/README.md does not name.

The file is read as text rather than parsed as yaml, because the package needs
nothing outside the standard library and a yaml parser for one test would be the
only dependency in the repository.
"""

import re
from pathlib import Path

ACTION = Path(__file__).resolve().parent.parent / "actions" / "setup" / "action.yml"
README = ACTION.parent / "README.md"


def steps() -> list[str]:
    """The action's steps, as the blocks of text they are written in."""
    body = ACTION.read_text(encoding="utf-8").split("steps:", 1)[1]
    blocks = re.split(r"\n(?=    - )", body)
    # the comment standing above the first step is not a step
    return [block for block in blocks if block.lstrip().startswith("- ")]


def test_the_books_are_checked_even_when_the_cache_hits():
    # the fetch is skipped on a cache hit, so a check carrying the same
    # condition would leave the file most runs play unchecked
    checking = [step for step in steps() if "verify" in step]
    assert checking, "no step checks the books against the table"
    for step in checking:
        assert "cache-hit" not in step, step


def test_the_cache_key_is_the_pin_the_table_reports():
    key = next(line for line in ACTION.read_text().splitlines() if "key:" in line)
    assert "steps.books.outputs.pin" in key, key
    # a pin written out here as well as in the table is two things to keep level
    assert not re.search(r"books-[0-9a-f]{7,40}", key), key


def test_the_table_is_asked_for_nothing_the_contract_does_not_name():
    contract = {"list", "pin", "fetch", "verify"}
    asked = set(re.findall(r'"\$BOOK_TABLE" (\w+)', ACTION.read_text()))
    assert asked, "the action does not call the table at all"
    assert asked <= contract, asked - contract
    for command in asked:
        assert f"`<table> {command}" in README.read_text(), command


def test_every_action_it_uses_is_pinned_to_a_commit():
    # a tag is mutable and this action runs in other repositories' jobs
    for used in re.findall(r"uses: (\S+)", ACTION.read_text()):
        assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", used), used


def test_estimator_only_skips_everything_but_the_path():
    # the mode exists so that a job which only reads games does not build a
    # harness it will not run
    for step in steps():
        if "PYTHONPATH" in step:
            assert "estimator_only" not in step, step
        else:
            assert "inputs.estimator_only != 'true'" in step, step
