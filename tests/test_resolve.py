# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

"""What a match is asked to play, turned into a commit.

Two things are pinned here. The first is the refusal: the caller builds and
runs whatever this prints, and a pull request head is anybody's to write, so
under a trigger that carries the repository's secrets it declines rather than
resolving. The second is what an empty ref means, which differs by caller: a
gauntlet measures the commit it is running on, and a strength match with no
baseline named compares against the last release.

The tests build a small repository rather than mocking git, because what is
being checked is the shape of the tags a real `git tag --list` returns.
"""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RESOLVE = ROOT / "actions" / "resolve-ref" / "resolve.sh"
RESOLVE_REF = ROOT / "bin" / "resolve_ref.sh"

# the triggers where the ref was chosen by somebody who can already push
ALLOWED = ["workflow_dispatch", "push", "schedule", "release"]
# a fork can choose the ref, and the job holds this repository's secrets
REFUSED = ["pull_request_target", "workflow_run", "issue_comment", "pull_request"]


def git(repository, *arguments):
    subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repository(tmp_path):
    """A repository with three commits and two releases on it, plus a
    pre-release tag that a baseline should skip."""
    path = tmp_path / "engine"
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "Test")
    shas = {}
    for name in ("first", "second", "third"):
        (path / name).write_text(name, encoding="utf-8")
        git(path, "add", name)
        git(path, "commit", "-qm", name)
        shas[name] = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    git(path, "tag", "v0.1.0", shas["first"])
    git(path, "tag", "v0.2.0", shas["second"])
    git(path, "tag", "v0.3.0-rc1", shas["third"])
    return path, shas


def resolve(repository, ref, when_empty="fail", glob="v[0-9]*", **environment):
    path, _ = repository
    env = {
        **os.environ,
        # the guard reads this, and unset means it is not a runner at all
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        **environment,
    }
    return subprocess.run(
        [str(RESOLVE), ref, when_empty, glob],
        cwd=path,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def lines(result):
    assert result.returncode == 0, result.stderr
    name, sha = result.stdout.splitlines() or ["", ""]
    return name, sha


class TestTheGuard:
    @pytest.mark.parametrize("trigger", ALLOWED)
    def test_it_resolves_under_a_trigger_the_ref_cannot_be_chosen_by_a_fork(
        self, repository, trigger
    ):
        result = resolve(repository, "v0.2.0", GITHUB_EVENT_NAME=trigger)
        assert result.returncode == 0, result.stderr

    @pytest.mark.parametrize("trigger", REFUSED)
    def test_it_refuses_under_a_trigger_that_carries_the_secrets(
        self, repository, trigger
    ):
        result = resolve(repository, "v0.2.0", GITHUB_EVENT_NAME=trigger)
        assert result.returncode != 0
        assert "refusing to resolve a ref" in result.stderr

    def test_an_unset_trigger_is_not_a_runner(self, repository):
        # somebody running it by hand in a clone, where there is nothing to take
        path, shas = repository
        result = subprocess.run(
            [str(RESOLVE_REF), "v0.2.0"],
            cwd=path,
            capture_output=True,
            text=True,
            check=False,
            env={k: v for k, v in os.environ.items() if k != "GITHUB_EVENT_NAME"},
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == shas["second"]

    def test_the_refusal_names_the_trigger_it_refused(self, repository):
        # a message that does not say which trigger leaves the reader guessing
        result = resolve(repository, "v0.2.0", GITHUB_EVENT_NAME="pull_request_target")
        assert "pull_request_target" in result.stderr


class TestWhatItResolves:
    def test_a_tag_resolves_to_its_commit_and_keeps_its_name(self, repository):
        _, shas = repository
        name, sha = lines(resolve(repository, "v0.2.0"))
        # the name is what a report calls the side: a reader can look up a tag
        # and cannot look up the sha it stood for on the day
        assert name == "v0.2.0"
        assert sha == shas["second"]

    def test_a_commit_resolves_to_itself(self, repository):
        _, shas = repository
        name, sha = lines(resolve(repository, shas["first"]))
        assert sha == shas["first"]
        assert name == shas["first"]

    def test_a_ref_that_is_not_there_fails(self, repository):
        # the fetch it falls back to has no remote to ask in this fixture,
        # which is the same answer as a name nobody pushed
        assert resolve(repository, "v9.9.9").returncode != 0


class TestAnEmptyRef:
    def test_head_is_the_commit_the_workflow_runs_on(self, repository):
        name, sha = lines(
            resolve(
                repository,
                "",
                when_empty="head",
                GITHUB_REF_NAME="master",
                GITHUB_SHA="cafe",
            )
        )
        assert (name, sha) == ("master", "cafe")

    def test_last_release_is_the_newest_release(self, repository):
        _, shas = repository
        name, sha = lines(resolve(repository, "", when_empty="last-release"))
        assert name == "v0.2.0"
        assert sha == shas["second"]

    def test_last_release_skips_a_pre_release(self, repository):
        # a release is measured against the last thing a user could have been
        # running, and v0.3.0-rc1 is on a newer commit than v0.2.0
        name, _ = lines(resolve(repository, "", when_empty="last-release"))
        assert name == "v0.2.0"

    def test_last_release_skips_the_tag_being_released(self, repository):
        # a release match runs on its own tag, and comparing it against itself
        # would report zero
        _, shas = repository
        name, sha = lines(
            resolve(repository, "", when_empty="last-release", GITHUB_REF_NAME="v0.2.0")
        )
        assert name == "v0.1.0"
        assert sha == shas["first"]

    def test_the_first_release_of_a_repository_has_nothing_to_compare_against(
        self, repository
    ):
        # empty rather than an error: the caller skips the match and says so
        result = resolve(repository, "", when_empty="last-release", glob="z[0-9]*")
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == ""

    def test_fail_is_what_a_caller_with_no_default_asks_for(self, repository):
        result = resolve(repository, "", when_empty="fail")
        assert result.returncode != 0
        assert "no default" in result.stderr

    def test_a_mode_nobody_defined_is_refused(self, repository):
        assert resolve(repository, "", when_empty="whatever").returncode != 0
