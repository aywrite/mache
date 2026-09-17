# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

"""What the scripts put on each stream, which is what the actions around them
depend on.

Both of these are here because both were got wrong. A script that writes its
report and its `key=value` lines to one stream leaves the action no way to tell
them apart, and `$GITHUB_OUTPUT` refuses a line that is not `key=value` after
the games have already been played. A script that writes its captures to the
file its caller is redirecting its stderr into ends up reading and writing one
file, which fails, and silently loses whatever it captured first.

Neither is visible from the outside: the exit status is fine, the report is
right, and the run fails or goes quiet at the step after. So they are pinned
from the streams rather than from the result.

The tools these call are stubbed. What is under test is the plumbing.
"""

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLAY = ROOT / "actions" / "play-shard" / "play.sh"
SUMMARISE = ROOT / "actions" / "summarise-match" / "summarise.sh"

TRANSCRIPT = [
    "Started game 1 of 4 (new vs old)",
    "Score of new vs old: 2 - 1 - 1  [0.625] 4",
]


def executable(path, body):
    path.write_text("#!/usr/bin/env bash\n" + textwrap.dedent(body))
    path.chmod(0o755)
    return path


@pytest.fixture
def match(tmp_path):
    """A directory laid out as a shard plays from: the harness, the two
    engines and somewhere to write."""
    tools = tmp_path / "tools"
    tools.mkdir()
    executable(
        tools / "fastchess",
        """
        printf '%s\\n' "Started game 1 of 4 (new vs old)" \\
            "Score of new vs old: 2 - 1 - 1  [0.625] 4"
    """,
    )
    for side in ("new", "old"):
        executable(tools / side, "exit 0")
    return tools


def play(tools, outputs):
    return subprocess.run(
        [str(PLAY), str(outputs)],
        cwd=tools,
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "CANDIDATE": "new",
            "CANDIDATE_BINARY": "./new",
            "OPPONENT": "old",
            "OPPONENT_BINARY": "./old",
            "BOOK_FILE": "b.pgn",
            "BOOK_FORMAT": "pgn",
            "START": "1",
            "PAIRS": "2",
            "TIME_CONTROL": "10+0.1",
            "HASH": "256",
            "CONCURRENCY": "2",
            "STARTUP_MS": "20000",
            "MAX_MATCH_MINUTES": "150",
        },
    )


class TestPlayingAShard:
    def test_the_harness_output_goes_to_the_log(self, match, tmp_path):
        # what a reader opens the job for. It used to reach the log through
        # the step's own stdout, and has to still
        result = play(match, tmp_path / "outputs")
        assert result.returncode == 0, result.stderr
        for line in TRANSCRIPT:
            assert line in result.stdout

    def test_the_outputs_file_holds_only_key_equals_value(self, match, tmp_path):
        # $GITHUB_OUTPUT refuses a line that is neither `key=value` nor a
        # heredoc, and it refuses it after the games have been played
        outputs = tmp_path / "outputs"
        play(match, outputs)
        lines = outputs.read_text().splitlines()
        assert lines, "nothing was reported"
        for line in lines:
            assert "=" in line, f"{line!r} would be refused by the output file"
        assert not any(line in outputs.read_text() for line in TRANSCRIPT)

    def test_a_shard_that_finished_says_so(self, match, tmp_path):
        # the caller reads this to decide whether to warn about the cap, so a
        # shard that reached its game count has to be distinguishable
        outputs = tmp_path / "outputs"
        play(match, outputs)
        assert outputs.read_text().startswith("stopped_by=fastchess")

    def test_the_result_file_is_kept_beside_the_games(self, match, tmp_path):
        play(match, tmp_path / "outputs")
        assert (match / "result.txt").read_text().splitlines() == TRANSCRIPT

    def test_a_harness_that_died_fails_the_shard(self, match, tmp_path):
        # without pipefail the tee hides it, and a composite action's step
        # does not take the caller's defaults
        executable(match / "fastchess", "echo 'some output'; exit 3")
        assert play(match, tmp_path / "outputs").returncode == 3


@pytest.fixture
def games(tmp_path):
    """One shard's pgn, and an estimator that reports a remark the way the
    real one does when a game ended by a fault rather than by play."""
    shard = tmp_path / "shards" / "shard-0"
    shard.mkdir(parents=True)
    (shard / "games.pgn").write_text(
        '[Event "?"]\n[Result "1-0"]\n\n1. e4 *\n\n', encoding="utf-8"
    )
    stub = tmp_path / "bin"
    stub.mkdir()
    executable(
        stub / "python3",
        """
        if [ "$1" = "-m" ] && [ "$2" = "mache.match_estimate" ]; then
            echo "4 of 5 shards reported" >&2
            echo "+3 ±2 Elo (200 games)"
            exit 0
        fi
        exec /usr/bin/python3 "$@"
    """,
    )
    return tmp_path, stub


def summarise(root, stub, outputs):
    return subprocess.run(
        [str(SUMMARISE), "shards", str(outputs)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}",
            "CANDIDATE": "candidate",
            "CANDIDATE_SHA": "a" * 40,
            "BASELINE": "v1.2.3",
            "BASELINE_SHA": "b" * 40,
            "SHARDS": "1",
            "TIME_CONTROL": "10+0.1",
            "SPRT": "false",
            "ELO0": "0",
            "ELO1": "5",
            "PRIOR_PAIRS": "",
            "PROVENANCE": "",
            "GITHUB_STEP_SUMMARY": str(root / "step_summary"),
            "GITHUB_RUN_ATTEMPT": "1",
        },
    )


class TestSummarisingAMatch:
    def test_an_estimate_with_a_remark_still_reports_its_line(self, games, tmp_path):
        # A remark is the ordinary case, not the exceptional one: the
        # estimator makes one whenever a game ended by a crash, the clock or
        # an illegal move. The release note line has to survive it.
        root, stub = games
        outputs = root / "outputs"
        result = summarise(root, stub, outputs)
        assert result.returncode == 0, result.stderr
        assert outputs.read_text().startswith("line=Performance compared to v1.2.3")

    def test_the_remark_reaches_stderr_once(self, games):
        # the caller turns each line of stderr into one warning, so a remark
        # repeated here is a warning repeated in the run
        root, stub = games
        result = summarise(root, stub, root / "outputs")
        assert result.stderr.count("4 of 5 shards reported") == 1

    def test_the_report_goes_to_the_log(self, games):
        root, stub = games
        result = summarise(root, stub, root / "outputs")
        assert "+3 ±2 Elo (200 games)" in result.stdout

    def test_the_script_does_not_write_the_file_its_caller_redirects_onto(self, games):
        # the caller runs this as `summarise.sh ... 2> remarks.txt`. Naming
        # its own capture the same thing made it cat a file onto itself, which
        # fails, and lost what it had captured first
        root, stub = games
        summarise(root, stub, root / "outputs")
        assert not (root / "remarks.txt").exists()

    def test_no_shard_uploaded_any_games_is_an_error(self, games):
        root, stub = games
        (root / "shards" / "shard-0" / "games.pgn").unlink()
        result = summarise(root, stub, root / "outputs")
        assert result.returncode != 0
        assert "rerun all of them" in result.stderr
