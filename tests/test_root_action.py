# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

"""The action at the root of the repository, which is the one GitHub
Marketplace lists.

It reads games already on the runner, so its script is run here on a real pgn
with the real estimator rather than a stub. What is pinned is what a caller
depends on: which files a pattern reaches, what goes on each stream, that the
caller's working directory is left alone, and that the metadata is what the
Marketplace accepts.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ACTION = ROOT / "action.yml"
ESTIMATE = ROOT / "bin" / "estimate.sh"
GAMES = ROOT / "tests" / "fixtures" / "pairs.pgn"

# the pair counts the fixture was written with, in score order
COUNTS = "1,2,6,3,1"

# the badge colours the Marketplace accepts
COLOURS = {
    "white",
    "black",
    "yellow",
    "blue",
    "green",
    "orange",
    "red",
    "purple",
    "gray-dark",
}


def estimate(cwd, outputs, *patterns, **environment):
    return subprocess.run(
        [str(ESTIMATE), str(outputs), *patterns],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "PYTHONPATH": str(ROOT),
            "CANDIDATE": "new",
            "BASELINE": "old",
            "TIME_CONTROL": "10+0.1",
            **environment,
        },
    )


def outputs_of(path):
    return dict(line.split("=", 1) for line in path.read_text().splitlines())


@pytest.fixture
def shards(tmp_path):
    """Two shards laid out as a download of two artifacts would leave them."""
    for index in (0, 1):
        shard = tmp_path / "games" / f"shard-{index}"
        shard.mkdir(parents=True)
        (shard / "games.pgn").write_text(GAMES.read_text())
    work = tmp_path / "work"
    work.mkdir()
    return tmp_path, work


class TestTheScript:
    def test_an_estimate_reports_and_hands_back_its_line(self, shards):
        root, work = shards
        outputs = root / "outputs"
        result = estimate(work, outputs, str(root / "games" / "shard-0" / "games.pgn"))
        assert result.returncode == 0, result.stderr
        assert "Elo (26 games)" in result.stdout
        written = outputs_of(outputs)
        assert "Elo (26 games)" in written["line"]
        assert written["trailer"].startswith("Elo: ")
        # no test, so nothing to chain
        assert written["verdict"] == ""
        assert written["carried"] == ""

    def test_a_glob_reaches_every_shard(self, shards):
        root, work = shards
        outputs = root / "outputs"
        result = estimate(work, outputs, str(root / "games" / "**" / "*.pgn"))
        assert result.returncode == 0, result.stderr
        assert "Elo (52 games)" in outputs_of(outputs)["line"]
        assert "shard-0" in result.stdout and "shard-1" in result.stdout

    def test_several_patterns_are_pooled(self, shards):
        root, work = shards
        outputs = root / "outputs"
        patterns = [str(root / "games" / f"shard-{i}" / "games.pgn") for i in (0, 1)]
        result = estimate(work, outputs, *patterns)
        assert result.returncode == 0, result.stderr
        assert "Elo (52 games)" in outputs_of(outputs)["line"]

    def test_a_sequential_test_hands_back_its_verdict_and_counts(self, shards):
        root, work = shards
        outputs = root / "outputs"
        result = estimate(
            work,
            outputs,
            str(GAMES),
            SPRT="true",
            ELO0="0",
            ELO1="10",
            SPRT_ALPHA="0.01",
            SPRT_BETA="0.01",
        )
        assert result.returncode == 0, result.stderr
        written = outputs_of(outputs)
        assert written["verdict"] == "inconclusive"
        assert written["carried"] == COUNTS
        # the rates reached the estimate, since the line names them
        assert "alpha=0.01 beta=0.01" in written["line"]

    def test_a_pattern_that_matches_nothing_is_an_error(self, shards):
        root, work = shards
        result = estimate(work, root / "outputs", str(root / "nowhere" / "*.pgn"))
        assert result.returncode != 0
        assert "nothing matches" in result.stderr

    def test_the_callers_working_directory_is_left_alone(self, shards):
        root, work = shards
        estimate(work, root / "outputs", str(GAMES))
        assert list(work.iterdir()) == []

    def test_the_summary_gets_the_report_and_the_trailer(self, shards):
        root, work = shards
        summary = root / "summary.md"
        result = estimate(
            work, root / "outputs", str(GAMES), GITHUB_STEP_SUMMARY=str(summary)
        )
        assert result.returncode == 0, result.stderr
        written = summary.read_text()
        assert written.startswith("new against old, over 1 pgn files at 10+0.1.")
        assert "Elo (26 games)" in written
        assert "As the trailer for the commit" in written

    def test_the_outputs_file_holds_only_key_equals_value(self, shards):
        root, work = shards
        outputs = root / "outputs"
        estimate(work, outputs, str(GAMES))
        for line in outputs.read_text().splitlines():
            assert re.fullmatch(r"[a-z]+=.*", line), line

    def test_it_is_executable_in_git(self):
        staged = subprocess.run(
            ["git", "ls-files", "--stage", "--", "bin/estimate.sh"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        if not staged:
            pytest.skip("estimate.sh is not in the index yet")
        assert staged.startswith("100755"), staged


def metadata():
    return ACTION.read_text(encoding="utf-8")


def block(text, key):
    """The keys directly under a top-level mapping."""
    lines = text.splitlines()
    start = lines.index(f"{key}:")
    found = []
    for line in lines[start + 1 :]:
        if line and not line.startswith(" "):
            break
        if match := re.fullmatch(r"  ([a-z0-9_]+):.*", line):
            found.append(match.group(1))
    return found


class TestTheMetadata:
    def test_it_is_at_the_root_where_the_marketplace_looks(self):
        assert ACTION.exists()
        assert not (ROOT / "action.yaml").exists()

    def test_it_names_itself_as_mache(self):
        name = re.search(r"^name: (.+)$", metadata(), re.MULTILINE).group(1)
        assert "mache" in name

    def test_the_description_fits_the_marketplace(self):
        # the listing takes 125 characters
        found = re.search(
            r"^description: >\n((?:  .*\n)+)", metadata(), re.MULTILINE
        ).group(1)
        description = " ".join(line.strip() for line in found.splitlines())
        assert len(description) <= 125, len(description)

    def test_the_badge_is_one_the_marketplace_draws(self):
        text = metadata()
        colour = re.search(r"^  color: (\S+)$", text, re.MULTILINE).group(1)
        assert colour in COLOURS
        assert re.search(r"^  icon: (\S+)$", text, re.MULTILINE)

    def test_every_input_reaches_the_script(self):
        text = metadata()
        for name in block(text, "inputs"):
            assert f"${{{{ inputs.{name} }}}}" in text, f"{name} is taken and unused"

    def test_every_output_is_one_the_script_writes(self, tmp_path):
        outputs = tmp_path / "outputs"
        work = tmp_path / "work"
        work.mkdir()
        estimate(work, outputs, str(GAMES))
        written = set(outputs_of(outputs))
        for name in block(metadata(), "outputs"):
            assert name in written, f"{name} is declared and never written"

    def test_it_runs_the_package_from_its_own_checkout(self):
        # so the version a caller names is the version that reads the games,
        # with no pin inside to fall behind it
        text = metadata()
        assert "aywrite/mache/" not in text
        assert 'PYTHONPATH="${GITHUB_ACTION_PATH}' in text
