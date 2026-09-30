# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

"""The examples a caller copies, and the quickstart that walks through them.

Nothing here runs them, since a run needs a repository with an engine in it.
What is checked is what would go wrong quietly once they are copied: a pin at a
release that is not the current one, an input the pinned workflow does not
take, a build script that is not executable or does not do what the contract
says.

The pins name the version this tree is, like the self pins in the reusable
workflows, so they are moved in the same commit on a release branch.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
CALLERS = sorted(EXAMPLES.glob("*.yml"))
BUILD = EXAMPLES / "build_at.sh"

# the documents that show a call, and so name a release
DOCUMENTS = [
    ROOT / "docs" / "QUICKSTART.md",
    ROOT / ".github" / "workflows" / "README.md",
]

VERSION = re.compile(r'^__version__ = "(\d+\.\d+\.\d+)"$', re.MULTILINE)

# `uses: aywrite/mache/.github/workflows/<name>.yml@<ref>`
CALL = re.compile(
    r"^(?P<indent> *)uses: +aywrite/mache/\.github/workflows/"
    r"(?P<workflow>[a-z-]+\.yml)@(?P<ref>\S+)",
    re.MULTILINE,
)


def version_here():
    found = VERSION.search((ROOT / "mache" / "__init__.py").read_text("utf-8"))
    assert found, "mache/__init__.py has no version assignment"
    return found.group(1)


def release(tag):
    """A release tag as numbers to compare, or None for anything else."""
    found = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", tag)
    return tuple(int(part) for part in found.groups()) if found else None


def indent_of(line):
    return len(line) - len(line.lstrip())


def keys_at(lines, start, depth):
    """The mapping keys exactly `depth` spaces in, from `start` until the block
    ends."""
    found = []
    for number in range(start, len(lines)):
        line = lines[number]
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        here = indent_of(line)
        if here < depth:
            break
        if here == depth and (key := re.match(r"([^\s:#]+):", line.strip())):
            found.append((key.group(1), number))
    return found


def workflow_at(workflow, ref):
    """The reusable workflow as the caller would get it at `ref`. Off disk
    where that tag is this tree's version and not cut yet, which is a release
    branch."""
    tagged = subprocess.run(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if ref == f"v{version_here()}" and tagged.returncode != 0:
        # A checkout with no tags at all would land here too, and read the
        # tree rather than the release. So this is only a release branch when
        # there are tags and the version is newer than all of them.
        tags = subprocess.run(
            ["git", "tag", "--list", "v[0-9]*"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        if not tags:
            pytest.fail("this checkout has no release tags; fetch them to run this")
        newest = max(release(tag) for tag in tags if release(tag))
        assert release(ref) > newest, f"{ref} is not tagged and not new"
        return (ROOT / ".github" / "workflows" / workflow).read_text("utf-8")
    shown = subprocess.run(
        ["git", "show", f"{ref}:.github/workflows/{workflow}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert shown.returncode == 0, f"{workflow}@{ref} is not readable: {shown.stderr}"
    return shown.stdout


def declared_inputs(text):
    """Every input a reusable workflow takes, and which of them are required."""
    lines = text.splitlines()
    start = next(n for n, line in enumerate(lines) if line.strip() == "workflow_call:")
    block = next(
        n for n in range(start + 1, len(lines)) if lines[n].strip() == "inputs:"
    )
    inputs = keys_at(lines, block + 1, indent_of(lines[block]) + 2)
    required = set()
    for name, number in inputs:
        for line in lines[number + 1 :]:
            if line.strip() and indent_of(line) <= indent_of(lines[number]):
                break
            if line.strip() == "required: true":
                required.add(name)
    return {name for name, _ in inputs}, required


def calls(path):
    """Each call in a caller, as (workflow, ref, the inputs it passes)."""
    text = path.read_text("utf-8")
    lines = text.splitlines()
    found = []
    for match in CALL.finditer(text):
        number = text[: match.start()].count("\n")
        depth = len(match.group("indent"))
        passed = set()
        for offset in range(number + 1, len(lines)):
            line = lines[offset]
            if line.strip() and indent_of(line) < depth:
                break
            if indent_of(line) == depth and line.strip() == "with:":
                passed = {key for key, _ in keys_at(lines, offset + 1, depth + 2)}
        found.append((match.group("workflow"), match.group("ref"), passed))
    return found


def test_there_are_examples_to_check():
    # a glob that matched nothing would pass every test below
    assert [path.name for path in CALLERS] == ["sprt.yml", "strength.yml"]


@pytest.mark.parametrize("path", CALLERS + DOCUMENTS, ids=lambda path: path.name)
def test_every_call_names_the_current_release(path):
    found = CALL.findall(path.read_text("utf-8"))
    assert found, f"{path.name} shows no call"
    for _, workflow, ref in found:
        assert ref == f"v{version_here()}", f"{path.name} calls {workflow}@{ref}"


def test_the_readme_calls_the_root_action_at_the_current_release():
    # the action GitHub Marketplace lists, shown in the README the listing
    # displays, so it moves with the other pins
    text = (ROOT / "README.md").read_text("utf-8")
    found = re.findall(r"uses: +aywrite/mache@(\S+)", text)
    assert found, "the README shows no call of the root action"
    assert set(found) == {f"v{version_here()}"}, found


def test_the_quickstart_names_no_other_release():
    # the prose as well as the calls, so a sentence about what a release
    # takes is looked at again when the pins move. A tag with a suffix, such
    # as a pre-release given as an example, is not a release the guide names.
    text = (ROOT / "docs" / "QUICKSTART.md").read_text("utf-8")
    named = set(re.findall(r"\bv(\d+\.\d+\.\d+)(?![-\w.])", text))
    assert named == {version_here()}, f"the quickstart names {sorted(named)}"


def test_the_quickstart_shows_the_example_workflow_as_it_is():
    # the guide shows the whole file, so the two cannot be allowed to differ
    text = (ROOT / "docs" / "QUICKSTART.md").read_text("utf-8")
    shown = re.findall(r"```yaml\n(.*?)```", text, re.DOTALL)
    example = (EXAMPLES / "strength.yml").read_text("utf-8")
    body = re.sub(r"\A(#.*\n)+", "", example)
    assert body in shown, "the quickstart's copy of strength.yml has drifted"


@pytest.mark.parametrize("path", CALLERS, ids=lambda path: path.name)
def test_every_input_passed_is_one_the_pinned_workflow_takes(path):
    for workflow, ref, passed in calls(path):
        taken, required = declared_inputs(workflow_at(workflow, ref))
        assert passed <= taken, f"{workflow}@{ref} takes no {passed - taken}"
        assert required <= passed, f"{path.name} leaves out {required - passed}"


@pytest.mark.parametrize("path", CALLERS, ids=lambda path: path.name)
def test_the_caller_keeps_its_token_to_reading(path):
    text = path.read_text("utf-8")
    assert re.search(r"^permissions:\n  contents: read\n", text, re.MULTILINE)


def test_the_build_script_is_executable_in_git():
    staged = subprocess.run(
        ["git", "ls-files", "--stage", "--", str(BUILD.relative_to(ROOT))],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    if not staged:
        pytest.skip("build_at.sh is not in the index yet")
    assert staged.startswith("100755"), staged


def test_the_build_script_builds_the_commit_it_is_given(tmp_path):
    # A repository with two commits and a cargo that copies a file into the
    # place a release build would go. The script is handed the first commit
    # while the second is checked out, so the binary shows which one it built.
    repo = tmp_path / "engine"
    repo.mkdir()
    # kept away from the developer's own git config, which may sign commits
    # or run hooks
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(repo)]
    subprocess.run([*git, "init", "-q"], check=True, env=env)
    for version in ("first", "second"):
        (repo / "engine.txt").write_text(f"{version}\n")
        subprocess.run([*git, "add", "engine.txt"], check=True, env=env)
        # an old date, so an export stamped with the commit's time would show
        dated = {**env, "GIT_COMMITTER_DATE": "2001-01-01T00:00:00"}
        subprocess.run([*git, "commit", "-qm", version], check=True, env=dated)
    first = subprocess.run(
        [*git, "rev-parse", "HEAD~1"],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    ).stdout.strip()

    stubs = tmp_path / "bin"
    stubs.mkdir()
    stamped = tmp_path / "stamped"
    cargo = stubs / "cargo"
    cargo.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        # what the export was stamped with, read back below
        "python3 -c 'import os, sys; print(int(os.stat(\"engine.txt\").st_mtime))'"
        f" > {stamped}\n"
        "mkdir -p target/release\n"
        "cp engine.txt target/release/my-engine\n"
        "chmod +x target/release/my-engine\n"
    )
    cargo.chmod(0o755)

    # relative, and from the root of the checkout, as batch.yml calls it
    subprocess.run(
        ["bash", str(BUILD), first, "tools/new"],
        cwd=repo,
        env={**env, "PATH": f"{stubs}:{os.environ['PATH']}"},
        check=True,
    )
    binary = repo / "tools" / "new"
    assert binary.read_text() == "first\n"
    assert os.access(binary, os.X_OK)
    # stamped when it was extracted, not with the commit's date in 2001
    assert int(stamped.read_text()) > 1_000_000_000
    # the working tree was left as it was
    assert (repo / "engine.txt").read_text() == "second\n"
