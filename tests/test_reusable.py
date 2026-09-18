# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

"""What the reusable workflows promise, read off the workflows themselves.

Running them needs a caller, and a caller that is not this repository is the one
thing phase 4 does not have. What is checked here is the part a green run in
some other repository would not tell us either: that the actions they name exist
in this repository, that every one of them is pinned at the same tag, and that
the workflows take nothing from a caller they do not use.

The self pin is the fragile part. These workflows call actions out of the
repository they live in, by name and tag rather than by a relative path, because
a relative path inside a called workflow is resolved against something this
repository cannot test from here. That buys certainty and costs a tag that has
to be moved by hand: the release cannot move it, because a release commit is
pushed by GITHUB_TOKEN and GitHub refuses that token any write under
.github/workflows/. So what is checked here is the shape of the pins rather
than their freshness, and the readme beside the workflows says what the lag is.

The files are read as text as well as parsed, because what is being checked is
partly how they are written.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
REUSABLE = ["strength.yml", "calibrate.yml"]

# `uses: aywrite/mache/actions/<name>@<ref>`
SELF_USE = re.compile(r"uses:\s*aywrite/mache/actions/([a-z-]+)@(\S+)")


def text_of(name):
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def pins(name):
    return SELF_USE.findall(text_of(name))


@pytest.mark.parametrize("name", REUSABLE)
def test_every_action_it_names_is_in_this_repository(name):
    found = pins(name)
    assert found, f"{name} calls none of this repository's actions"
    for action, _ in found:
        assert (ROOT / "actions" / action / "action.yml").is_file(), (
            f"{name} calls actions/{action}, which is not here"
        )


def test_every_self_pin_names_one_tag():
    # a workflow running half its actions from one release and half from
    # another would be a version nobody chose
    seen = {ref for name in REUSABLE for _, ref in pins(name)}
    assert len(seen) == 1, f"the reusable workflows are pinned at {sorted(seen)}"


def test_the_self_pins_are_a_release_tag():
    # a branch or a moving name would make the workflow at a tag mean
    # something different next week
    (ref,) = {ref for name in REUSABLE for _, ref in pins(name)}
    assert re.fullmatch(r"v\d+\.\d+\.\d+", ref), f"{ref} is not a release tag"


@pytest.mark.parametrize("name", REUSABLE)
def test_it_is_callable_and_nothing_else(name):
    # a workflow with a trigger of its own would run on this repository's
    # pushes, where there is no engine to build
    body = text_of(name)
    triggers = re.search(r"\non:\n(.*?)\n\S", body, re.DOTALL).group(1)
    assert "workflow_call" in triggers
    for trigger in ("push:", "pull_request:", "schedule:", "workflow_dispatch:"):
        assert trigger not in triggers, f"{name} also runs on {trigger}"


@pytest.mark.parametrize("name", REUSABLE)
def test_it_asks_for_no_more_than_it_needs(name):
    # a match plays games and reads them. Anything that writes to the calling
    # repository is the caller's to do with the line it gets back
    body = text_of(name)
    block = re.search(r"\npermissions:\n(.*?)\n\S", body, re.DOTALL).group(1)
    assert "contents: read" in block
    assert "write" not in block, f"{name} asks for write access"


@pytest.mark.parametrize("name", REUSABLE)
def test_it_does_not_persist_the_token_it_checked_out_with(name):
    # the checkout is the caller's repository, and nothing here pushes to it
    body = text_of(name)
    checkouts = body.count("actions/checkout@")
    assert body.count("persist-credentials: false") == checkouts, (
        f"{name} has {checkouts} checkouts and does not disarm all of them"
    )


def test_the_build_contract_is_documented_where_the_workflows_point():
    # both workflows tell a caller to read this file for the one thing they
    # require of it
    readme = (WORKFLOWS / "README.md").read_text(encoding="utf-8")
    assert "<build> <ref> <binary>" in readme
    for name in REUSABLE:
        assert "README.md" in text_of(name), f"{name} points nowhere for the contract"
