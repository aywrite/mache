# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

"""What the reusable workflows promise, read off the workflows themselves.

Running them needs a caller, and a caller that is not this repository is the one
thing phase 4 does not have. What is checked here is the part a green run in
some other repository would not tell us either: that the actions they name exist
in this repository, that every one of them is pinned at the same tag, and that
the workflows take nothing from a caller they do not use.

The self pin is the fragile part. These workflows call actions out of the
repository they live in, by name and ref rather than by a relative path. Two
runs from a consuming repository settled why, and they went opposite ways for
the same syntax:

- A workflow reaching a workflow beside it resolves in the repository that
  holds it, at that repository's own commit (35444376094). strength.yml uses
  that for batch.yml, so a caller pinning a release gets that release's file.
- A workflow reaching an action beside it resolves in the caller's workspace
  (35489144466): "Can't find action.yml under /home/runner/work/arche/arche/
  actions/probe-only", with and without a checkout alike. So the actions have
  to be named by ref, and there is no relative form to fall back on.

The ref costs a pin that is moved by hand: the release cannot move it, because
a release commit is pushed by GITHUB_TOKEN and GitHub refuses that token any
write under .github/workflows/. So the pins name the release before, and the
readme beside the workflows says what the lag is.

What the lag cannot do is carry an action input added in the same release, and
that is what the coverage test below exists for. Shape alone did not catch a
ladder pinned at a summarise-match with no verdict to read, which would have
run one batch of four and said nothing.

The files are read as text as well as parsed, because what is being checked is
partly how they are written.
"""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
REUSABLE = ["strength.yml", "calibrate.yml", "batch.yml"]

# the stages strength.yml has written out, which is the cap it accepts
LADDER = 4

# `uses: aywrite/mache/actions/<name>@<ref>`
SELF_USE = re.compile(r"uses:\s*aywrite/mache/actions/([a-z-]+)@(\S+)")

# the same, as a whole step line, so the block under it can be read
STEP = re.compile(
    r"^(?P<indent> *)- +uses: +aywrite/mache/actions/(?P<action>[a-z-]+)@(?P<ref>\S+)"
)

# `steps.<id>.outputs.<key>`, anywhere an expression can appear
READ = re.compile(r"steps\.([A-Za-z_][\w-]*)\.outputs\.([A-Za-z_]\w*)")


def text_of(name):
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def pins(name):
    return SELF_USE.findall(text_of(name))


def indent_of(line):
    return len(line) - len(line.lstrip())


def keys_at(lines, start, depth):
    """The mapping keys exactly `depth` spaces in, from `start` until the block
    ends. Exactly, so the prose inside a folded value is not read as keys."""
    found = set()
    for line in lines[start:]:
        if not line.strip():
            continue
        here = indent_of(line)
        if here < depth:
            break
        if here == depth and (key := re.match(r"([a-z_]+):", line.strip())):
            found.add(key.group(1))
    return found


def steps_using_actions(body):
    """Every step calling one of this repository's actions, as
    (action, ref, id, the inputs it passes)."""
    lines = body.splitlines()
    found = []
    for number, line in enumerate(lines):
        match = STEP.match(line)
        if not match:
            continue
        step = indent_of(line)
        step_id, passed = None, set()
        for offset, rest in enumerate(lines[number + 1 :], start=number + 1):
            if rest.strip() and indent_of(rest) <= step:
                break
            if rest.strip().startswith("id:"):
                step_id = rest.split(":", 1)[1].strip()
            elif rest.strip() == "with:":
                passed = keys_at(lines, offset + 1, indent_of(rest) + 2)
        found.append((match.group("action"), match.group("ref"), step_id, passed))
    return found


def surface_at(action, ref):
    """What `actions/<action>` declared at `ref`, as (inputs, outputs). Read
    out of git rather than off disk, because the pin is the whole point: what
    the workflow will run is that ref's action, not this checkout's."""
    shown = subprocess.run(
        ["git", "show", f"{ref}:actions/{action}/action.yml"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if shown.returncode != 0:
        raise AssertionError(
            f"{action}@{ref} is not readable from this checkout, so the pin"
            f" cannot be checked: {shown.stderr.strip()}"
        )
    lines = shown.stdout.splitlines()
    surface = {}
    for number, line in enumerate(lines):
        if line.rstrip() in ("inputs:", "outputs:"):
            surface[line.strip(": ")] = keys_at(lines, number + 1, 2)
    return surface.get("inputs", set()), surface.get("outputs", set())


@pytest.mark.parametrize("name", REUSABLE)
def test_every_action_it_names_is_in_this_repository(name):
    found = pins(name)
    assert found, f"{name} calls none of this repository's actions"
    for action, _ in found:
        assert (ROOT / "actions" / action / "action.yml").is_file(), (
            f"{name} calls actions/{action}, which is not here"
        )


def test_every_workflow_pins_its_actions_at_one_thing():
    # a workflow running half its actions from one release and half from
    # another would be a version nobody chose
    for name in REUSABLE:
        seen = {ref for _, ref in pins(name)}
        assert len(seen) <= 1, f"{name} pins its actions at {sorted(seen)}"


@pytest.mark.parametrize("name", REUSABLE)
def test_the_self_pins_cannot_move(name):
    # a branch or a moving name would make the workflow at a tag mean
    # something different next week. A release tag is the ordinary form; a
    # commit is the exception batch.yml takes, and the reason is in its own
    # comment and in the readme
    for action, ref in pins(name):
        release = re.fullmatch(r"v\d+\.\d+\.\d+", ref)
        commit = re.fullmatch(r"[0-9a-f]{40}", ref)
        assert release or commit, (
            f"{name} pins {action} at {ref}, which is neither a release tag"
            " nor a full commit, so it can be moved under the workflow"
        )
        if commit:
            # and a commit of this repository, not a string of the right shape
            assert (
                subprocess.run(
                    ["git", "cat-file", "-e", f"{ref}^{{commit}}"],
                    cwd=ROOT,
                    capture_output=True,
                    check=False,
                ).returncode
                == 0
            ), f"{name} pins {action} at {ref}, which is not a commit here"


def test_only_the_batch_workflow_pins_at_a_commit():
    # the exception earns its place once, for the release that first carries
    # a file whose actions did not exist in the release before it. Anywhere
    # else it is a pin nobody will remember to move back to a tag
    for name in REUSABLE:
        if name == "batch.yml":
            continue
        for action, ref in pins(name):
            assert re.fullmatch(r"v\d+\.\d+\.\d+", ref), (
                f"{name} pins {action} at {ref} rather than at a release tag"
            )


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


@pytest.mark.parametrize("name", REUSABLE)
def test_the_pinned_action_takes_every_input_it_is_handed(name):
    # The pin names a release before this one, so an input added in the same
    # release as the workflow that passes it is not there yet. Actions warn
    # about an input they do not declare and carry on, so the workflow runs
    # and the input is simply dropped: batch and batches going missing is
    # every batch of a test starting at the same opening
    for action, ref, _, passed in steps_using_actions(text_of(name)):
        declared, _ = surface_at(action, ref)
        missing = sorted(passed - declared)
        assert not missing, (
            f"{name} hands {action}@{ref} the input(s) {missing}, which that"
            " version does not declare, so they would be dropped in silence"
        )


@pytest.mark.parametrize("name", REUSABLE)
def test_the_pinned_action_hands_back_every_output_it_is_read_for(name):
    # the other half, and the one that bites harder: an output that is not
    # there reads as empty rather than failing, so a guard on it is simply
    # false. A ladder pinned at a summarise-match with no verdict runs its
    # first stage, skips the rest and says nothing
    body = text_of(name)
    read = {}
    for step_id, key in READ.findall(body):
        read.setdefault(step_id, set()).add(key)
    for action, ref, step_id, _ in steps_using_actions(body):
        if step_id is None:
            continue
        _, declared = surface_at(action, ref)
        missing = sorted(read.get(step_id, set()) - declared)
        assert not missing, (
            f"{name} reads {missing} off {action}@{ref}, which that version"
            " does not hand back, so it would read as empty"
        )


def test_the_build_contract_is_documented_where_the_workflows_point():
    # both workflows tell a caller to read this file for the one thing they
    # require of it
    readme = (WORKFLOWS / "README.md").read_text(encoding="utf-8")
    assert "<build> <ref> <binary>" in readme
    for name in REUSABLE:
        assert "README.md" in text_of(name), f"{name} points nowhere for the contract"
