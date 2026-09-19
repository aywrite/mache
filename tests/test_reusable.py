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
a composite action has no relative form from a workflow. That costs a tag that
has to be moved by hand: the release cannot move it, because a release commit
is pushed by GITHUB_TOKEN and GitHub refuses that token any write under
.github/workflows/. So what is checked here is the shape of the pins rather
than their freshness, and the readme beside the workflows says what the lag is.

One workflow calling another is the case that does have a relative form, and
strength.yml uses it for batch.yml. A run from a consuming repository
(35444376094, 19 September 2026) resolved the relative reference inside this
repository at this repository's own commit rather than inside the caller's, so
a caller pinning a release of strength.yml gets the batch.yml of that release.
A pin could not have said that on the release that first carried one.

The files are read as text as well as parsed, because what is being checked is
partly how they are written.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
REUSABLE = ["strength.yml", "calibrate.yml", "batch.yml"]

# the stages strength.yml has written out, which is the cap it accepts
LADDER = 4

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


def test_the_ladder_is_as_deep_as_the_input_it_accepts():
    # the two are written in different places and neither is derived from the
    # other, so a stage added without the guard moving would be unreachable
    # and a guard raised without a stage would take a test it cannot play
    body = text_of("strength.yml")
    stages = re.findall(r"\n  batch(\d+):\n", body)
    assert [int(stage) for stage in stages] == list(range(1, LADDER + 1))
    assert f"-le {LADDER} " in body, "the guard does not name the stages there are"


def test_every_stage_plays_a_batch_of_its_own():
    # the whole point: two stages given the same batch index would reserve the
    # same openings and the pooled estimate would count them twice
    body = text_of("strength.yml")
    assert re.findall(r"\n      batch: (\d+)\n", body) == [
        str(stage) for stage in range(LADDER)
    ]


def test_a_stage_plays_only_where_the_one_before_settled_nothing():
    # the early stop itself. A stage that ran unguarded would play games the
    # test had already decided it did not need
    body = text_of("strength.yml")
    for stage in range(2, LADDER + 1):
        guard = f"needs.batch{stage - 1}.outputs.verdict == 'inconclusive'"
        assert guard in body, f"batch{stage} is not guarded on batch{stage - 1}"
        carried = f"prior_pairs: ${{{{ needs.batch{stage - 1}.outputs.carried }}}}"
        assert carried in body, f"batch{stage} does not carry batch{stage - 1}'s pairs"


def test_a_batch_names_itself_in_the_artifacts_it_writes_and_reads():
    # every batch of one test shares a run id and an attempt. Without the
    # batch in the name, a later batch would collide on upload and its summary
    # would pool the earlier batch's games and add its counts on top
    body = text_of("batch.yml")
    naming = "format('-batch-{0}', inputs.batch)"
    assert body.count(naming) == 2, "the name and the pattern do not both carry it"
    assert body.count("${{ env.ARTIFACTS }}-shard-") == 3


def test_the_build_contract_is_documented_where_the_workflows_point():
    # both workflows tell a caller to read this file for the one thing they
    # require of it
    readme = (WORKFLOWS / "README.md").read_text(encoding="utf-8")
    assert "<build> <ref> <binary>" in readme
    for name in REUSABLE:
        assert "README.md" in text_of(name), f"{name} points nowhere for the contract"
