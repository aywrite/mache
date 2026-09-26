# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

"""Tests for the pooled match estimate.

The input is a pgn per shard, so the fixtures are shaped the way the pinned
fastchess writes one: a Round tag on every game, the two games of a round
playing the same opening with the colours reversed, and the ending in the
Termination tag with the reason at the end of the last comment. What this
guards against is a pooled estimate that pairs games from different shards,
that reads a colour it assumed rather than one the tags gave, or that states
an interval the games do not support.
"""

import json
import math
import os
import subprocess

import pytest
from conftest import command

import mache
from mache import match_estimate

# the command line a caller runs, which is what the action's PYTHONPATH makes work
COMMAND = command("match_estimate")

CANDIDATE = "new"
BASELINE = "old"
# What the workflow tells the estimate it played against, which is not the
# name fastchess played it under: the trailer has to still resolve months
# later, so a baseline that is not a release tag goes in as its sha.
BASE = "ce8b662"

# the comment fastchess puts on the last move, with the reason its tail
PLAYED = (
    "{+0.15/5 0.010s, tl=2.054s, latency=0.000s, n=83485, sd=20, nps=8348500,"
    ' hashfull=0, pv="e1g1 e8g8 c3e2"'
)


def game(
    round_id=1, result="1-0", swap=False, termination="normal", reason="White mates"
):
    """One game, shaped the way fastchess writes them. The candidate has white
    unless the sides are swapped, which is what the second game of a round
    does."""
    white, black = (BASELINE, CANDIDATE) if swap else (CANDIDATE, BASELINE)
    return (
        f'[Event "Fastchess Tournament"]\n'
        f'[Site "?"]\n'
        f'[Round "{round_id}"]\n'
        f'[White "{white}"]\n'
        f'[Black "{black}"]\n'
        f'[Result "{result}"]\n'
        f'[Termination "{termination}"]\n'
        f"\n1. e4 {{book}} e5 {{book}} 2. Nf3 {PLAYED}, {reason}}} {result}\n\n"
    )


def pair(round_id, first="1-0", second="0-1"):
    """A round as `-repeat` plays it: one opening, then the same one with the
    colours reversed. The results are as the pgn states them, so a candidate
    that won both of its games is 1-0 followed by 0-1."""
    return game(round_id, first) + game(round_id, second, swap=True)


def drawn(round_id):
    return pair(round_id, "1/2-1/2", "1/2-1/2")


# The pentanomial counts and the log likelihood ratio the pinned fastchess
# printed for a real match: 60 games of the engine against itself at 1+0.01
# under `-sprt elo0=0 elo1=10 alpha=0.05 beta=0.05 model=logistic` with
# `-report penta=true`, which ended `Ptnml(0-2): [2, 3, 14, 3, 8]` and
# `LLR: 0.44 (14.8%) (-2.94, 2.94) [0.00, 10.00]`.
MATCH = [2, 3, 14, 3, 8]
MATCH_LLR = 0.44

# the two games of a pair, by what the candidate scored over them. It has
# white in the first and black in the second, so the results below are as the
# pgn states them rather than as the candidate reads them
PAIRS = {
    0.0: ("0-1", "1-0"),
    0.5: ("0-1", "1/2-1/2"),
    1.0: ("1/2-1/2", "1/2-1/2"),
    1.5: ("1-0", "1/2-1/2"),
    2.0: ("1-0", "0-1"),
}


def batch(counts):
    """A shard whose pairs scored what `counts` says, in PENTANOMIAL order."""
    played = []
    for score, count in zip(match_estimate.PENTANOMIAL, counts):
        for _ in range(count):
            played.append(pair(len(played) + 1, *PAIRS[score]))
    return "".join(played)


def shard(tmp_path, name, text):
    """A shard as download-artifact leaves it: one directory per artifact,
    named after the artifact, with the shard's games inside."""
    directory = tmp_path / name
    directory.mkdir(parents=True, exist_ok=True)
    pgn = directory / "games.pgn"
    pgn.write_text(text)
    return pgn


def pooled(tmp_path, texts):
    """The shards, read and pooled the way the command line does."""
    paths = [
        shard(tmp_path, f"strength-1-1-shard-{index}", text)
        for index, text in enumerate(texts)
    ]
    shards, whole = match_estimate.read_shards(paths, CANDIDATE)
    games = [score for one in shards for score in one.games]
    pairs = [score for one in shards for score in one.pairs]
    estimate = match_estimate.Estimate(sum(games), len(games), pairs)
    return shards, estimate, whole


class TestPairing:
    def test_a_round_holds_the_two_games_of_one_opening(self):
        read, _ = match_estimate.read_games(pair(1) + pair(2), CANDIDATE)
        assert sorted(read) == ["1", "2"]
        scores, unpaired = match_estimate.pair_up(read)
        assert scores == [2.0, 2.0]
        assert unpaired == 0

    def test_two_shards_are_not_pooled_into_one_round(self, tmp_path):
        # every shard numbers its rounds from one, so pairing on the round
        # alone would put a game with one from another slice of the book
        shards, estimate, _ = pooled(tmp_path, [pair(1), pair(1)])
        assert [len(one.pairs) for one in shards] == [1, 1]
        assert estimate.pairs == 2
        assert estimate.games == 4

    def test_the_colour_is_read_from_the_tags_not_assumed(self):
        # the candidate has black in the second game of every round, so a
        # reader that assumed white would score its losses as wins
        read, _ = match_estimate.read_games(pair(1, "0-1", "1-0"), CANDIDATE)
        assert read["1"] == [0.0, 0.0]

    def test_an_odd_game_counts_in_the_score_and_not_in_the_pairs(self):
        # a shard the clock stopped in the middle of a round leaves one game
        read, _ = match_estimate.read_games(pair(1) + game(2, "1-0"), CANDIDATE)
        scores, unpaired = match_estimate.pair_up(read)
        assert scores == [2.0]
        assert unpaired == 1
        estimate = match_estimate.Estimate(3.0, 3, scores)
        assert estimate.games == 3
        assert estimate.pairs == 1

    def test_a_game_with_no_result_is_left_out_and_counted(self):
        read, unfinished = match_estimate.read_games(pair(1) + game(2, "*"), CANDIDATE)
        assert unfinished == 1
        assert sum(len(games) for games in read.values()) == 2

    def test_a_game_the_candidate_did_not_play_is_not_its_game(self):
        other = game(1).replace(f'[White "{CANDIDATE}"]', '[White "someone"]')
        read, _ = match_estimate.read_games(other, CANDIDATE)
        assert read == {}


class TestEstimate:
    def test_a_match_of_draws_is_no_difference_at_all(self, tmp_path):
        _, estimate, _ = pooled(tmp_path, [drawn(1) + drawn(2), drawn(1)])
        assert estimate.score == 0.5
        assert estimate.elo == 0.0

    def test_a_seventy_five_percent_score_is_a_hundred_and_ninety_one_elo(self):
        # the logistic model, -400 log10(1/p - 1), which is what the rest of
        # this tooling reads a score with
        estimate = match_estimate.Estimate(3.0, 4, [2.0, 1.0])
        assert round(estimate.elo) == 191

    def test_every_pair_shared_falls_back_to_the_spread_the_model_expects(
        self, tmp_path
    ):
        # each round was won one way and lost the other, so every pair scored
        # one out of two and the variance over the pairs is nought. That is
        # no measurement of the spread rather than a measurement of none, so
        # the interval falls back to the one unrelated games would have
        halves = pair(1, "1-0", "1-0") + pair(2, "0-1", "0-1")
        _, estimate, _ = pooled(tmp_path, [halves])
        assert estimate.score == 0.5
        assert round(estimate.margin) == 340
        assert estimate.los == 0.5

    def test_the_figure_and_the_interval_read_the_same_pairs(self):
        # a drawn pair and one won game the pairing left over. Reading the
        # figure off every game and the spread off the pairs alone made that
        # +120 elo with no interval either side of it and superiority certain
        estimate = match_estimate.Estimate(2.0, 3, [1.0])
        assert estimate.score == 2 / 3
        assert estimate.paired == 0.5
        assert estimate.elo == 0.0
        assert estimate.margin > 0
        assert estimate.los == 0.5

    def test_one_pair_on_its_own_states_the_spread_it_cannot_measure(self):
        estimate = match_estimate.Estimate(1.5, 2, [1.5])
        assert round(estimate.elo) == 191
        assert round(estimate.margin) == 556
        assert 0.5 < estimate.los < 1.0

    def test_a_modelled_spread_says_it_is_one(self, tmp_path):
        # a measured ±340 and a modelled one are not the same claim, so the
        # paragraph the interval goes in says which it is
        halves = pair(1, "1-0", "1-0") + pair(2, "0-1", "0-1")
        shards, estimate, text = pooled(tmp_path, [halves])
        assert estimate.modelled
        assert "rather than from one these games showed" in match_estimate.report(
            shards, estimate, text
        )
        _, measured, _ = pooled(tmp_path / "measured", [drawn(1) + pair(2)])
        assert not measured.modelled

    def test_the_interval_narrows_as_the_pairs_pile_up(self, tmp_path):
        # the standard error goes with the square root of the number of pairs,
        # so four times the games at the same score halves the margin
        _, small, _ = pooled(tmp_path / "small", [pair(1) + drawn(2)])
        _, large, _ = pooled(tmp_path / "large", [(pair(1) + drawn(2)) * 4])
        assert small.elo == large.elo
        assert math.isclose(large.margin, small.margin / 2)

    def test_a_sweep_is_bounded_rather_than_infinite(self, tmp_path):
        # the model has no elo for a score of one, and dividing by 1 - p there
        # would be a crash rather than an answer
        _, estimate, _ = pooled(tmp_path, [pair(1) + pair(2)])
        assert estimate.bounded == "above +1200"
        assert estimate.los == 1.0
        assert str(estimate) == "above +1200 Elo (4 games)"

    def test_a_match_swept_the_other_way_is_bounded_below(self, tmp_path):
        swept = pair(1, "0-1", "1-0") + pair(2, "0-1", "1-0")
        _, estimate, _ = pooled(tmp_path, [swept])
        assert estimate.bounded == "below -1200"
        assert estimate.los == 0.0

    def test_a_match_with_no_complete_pair_states_no_interval(self, tmp_path):
        _, estimate, _ = pooled(tmp_path, [game(1, "1-0")])
        assert estimate.bounded == "not measured"
        assert estimate.margin is None
        assert str(estimate) == "100.0% score (1 games)"


class TestReport:
    def test_a_row_for_every_shard_and_one_for_the_pool(self, tmp_path):
        shards, estimate, text = pooled(
            tmp_path, [drawn(1) + drawn(2), drawn(1) + pair(2)]
        )
        printed = match_estimate.report(shards, estimate, text)
        assert "| strength-1-1-shard-0 | 4 | 50.0% | 0 |" in printed
        assert "| strength-1-1-shard-1 | 4 | 75.0% | 0 |" in printed
        assert "| pooled | 8 | 62.5% | 0 |" in printed

    def test_a_shard_that_lost_games_to_a_fault_shows_in_its_row(self, tmp_path):
        forfeit = game(
            2,
            "0-1",
            termination="time forfeit",
            reason="White loses on time (102ms overrun)",
        )
        shards, estimate, text = pooled(
            tmp_path, [drawn(1) + forfeit, drawn(1) + drawn(2)]
        )
        printed = match_estimate.report(shards, estimate, text)
        assert "| strength-1-1-shard-0 | 3 | 33.3% | 1 |" in printed
        assert "| pooled | 7 | 42.9% | 1 |" in printed

    def test_the_pairs_are_counted_by_what_they_scored(self, tmp_path):
        shards, estimate, text = pooled(
            tmp_path, [drawn(1) + pair(2) + pair(3, "0-1", "1-0")]
        )
        printed = match_estimate.report(shards, estimate, text)
        assert "| pair score | 0 | 0.5 | 1 | 1.5 | 2 |" in printed
        assert "| pairs | 1 | 0 | 1 | 0 | 1 |" in printed

    def test_the_terminations_are_counted_and_not_reimplemented(self, tmp_path):
        forfeit = game(
            2,
            "0-1",
            termination="time forfeit",
            reason="White loses on time (102ms overrun)",
        )
        shards, estimate, text = pooled(tmp_path, [drawn(1) + forfeit])
        printed = match_estimate.report(shards, estimate, text)
        assert "How the games ended:" in printed
        assert "games: 3" in printed
        assert "time forfeit: 1 (new 1)" in printed

    def test_the_headline_is_the_estimate_and_the_paragraph_the_interval(
        self, tmp_path
    ):
        shards, estimate, text = pooled(tmp_path, [drawn(1) + pair(2)])
        printed = match_estimate.report(shards, estimate, text)
        assert printed.splitlines()[0] == "+191 ±321 Elo (4 games)"
        assert "The 95% interval is -130 to +512 elo" in printed
        assert "likelihood of superiority is 92.1%" in printed

    def test_the_games_left_over_are_said_and_the_unfinished_ones_too(self, tmp_path):
        shards, estimate, text = pooled(
            tmp_path, [drawn(1) + game(2, "1-0") + game(3, "*")]
        )
        printed = match_estimate.report(shards, estimate, text)
        assert "1 of the games had no partner" in printed
        assert "1 games had no result and are left out" in printed

    def test_the_report_names_the_version_that_priced_the_games(self, tmp_path):
        shards, estimate, text = pooled(tmp_path, [drawn(1) + pair(2)])
        printed = match_estimate.report(shards, estimate, text)
        assert printed.splitlines()[-1] == f"Read by mache {mache.__version__}."


class TestCommandLine:
    def run(self, tmp_path, texts, *arguments):
        paths = [
            shard(tmp_path, f"strength-1-1-shard-{index}", text)
            for index, text in enumerate(texts)
        ]
        return subprocess.run(
            [
                *COMMAND,
                *[str(path) for path in paths],
                "--candidate",
                CANDIDATE,
                "--baseline",
                BASE,
                "--tc",
                "30+0.3",
                *arguments,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_a_pgn_outside_ascii_is_read_whatever_the_locale_says(self, tmp_path):
        """The pgn is read as utf-8 and not as whatever the locale asks for.

        fastchess writes utf-8, and an engine name or a comment can carry a
        character outside ascii. A runner or a shell left on a C locale makes
        Python's default encoding ascii, and reading the pgn with that default
        raised UnicodeDecodeError before the encoding was stated. --json is
        what is read back here because it escapes to ascii, which stdout can
        carry under the same locale.
        """
        pgn = tmp_path / "games.pgn"
        pgn.write_text(
            (drawn(1) + pair(2)).replace(f'"{BASELINE}"', '"Br\u00e9ton"'),
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                *COMMAND,
                str(pgn),
                "--candidate",
                CANDIDATE,
                "--baseline",
                BASE,
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                # no utf-8 mode and no coercion of the C locale, so the
                # encoding the interpreter falls back to is ascii
                "PYTHONUTF8": "0",
                "PYTHONCOERCECLOCALE": "0",
                "LC_ALL": "C",
                "LANG": "C",
            },
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["games"] == 4

    def test_the_report_goes_to_stdout_and_nothing_else_does(self, tmp_path):
        result = self.run(tmp_path, [drawn(1) + drawn(2), drawn(1) + drawn(2)])
        assert result.returncode == 0
        assert result.stdout.startswith("+0 ±241 Elo (8 games)")
        assert result.stderr == ""

    def test_the_line_is_the_one_the_release_notes_carry(self, tmp_path):
        result = self.run(tmp_path, [drawn(1) + drawn(2)], "--line")
        assert result.stdout == "+0 ±340 Elo (4 games)\n"

    def test_the_trailer_is_the_line_a_commit_carries(self, tmp_path):
        # Written out rather than matched loosely, because the hook that
        # accepts it is in the repository that consumes this one and neither
        # side can import the other. This is what that side holds as a line it
        # must accept, so a change to the shape fails here as well as there.
        line = self.run(tmp_path, [drawn(1) + pair(2)], "--trailer").stdout
        assert line == "Elo: +191 ±321 (4 games, 30+0.3, vs ce8b662)\n"

    def test_the_line_carries_the_sprt_reading_after_the_estimate(self, tmp_path):
        result = self.run(
            tmp_path, [drawn(1) + pair(2)], "--line", "--elo0", "0", "--elo1", "10"
        )
        assert result.stdout == (
            "+191 ±321 Elo (4 games), SPRT [0, 10] inconclusive,"
            " LLR 0.06 (-2.94, 2.94)\n"
        )

    def test_the_sprt_trailer_names_the_verdict(self, tmp_path):
        line = self.run(
            tmp_path,
            [drawn(1) + pair(2)],
            "--trailer",
            "--elo0",
            "0",
            "--elo1",
            "10",
            "--prior-pairs",
            "0,0,100,0,5",
        ).stdout
        # the 105 pairs carried in and the 2 this batch played. The figure,
        # the interval and the count are all the test's: the batch on its own
        # reads +191 ±321 over 4 games, which is no claim about 214 of them
        assert line == (
            "Elo: +20 ±15 (sprt [0, 10] passed, 214 games, 30+0.3, vs ce8b662)\n"
        )

    def test_a_first_batch_is_the_whole_test_it_has(self, tmp_path):
        line = self.run(
            tmp_path, [drawn(1) + pair(2)], "--trailer", "--elo0", "0", "--elo1", "10"
        ).stdout
        assert line == (
            "Elo: +191 ±321 (sprt [0, 10] inconclusive, 4 games, 30+0.3, vs ce8b662)\n"
        )

    def test_the_trailer_counts_the_paired_games_of_a_cut_off_shard(self, tmp_path):
        # three games, so one round is a pair and the other is half of one.
        # The odd game is out of the counts the ratio is read from, so it is
        # out of the games the trailer states
        line = self.run(
            tmp_path,
            [drawn(1) + game(2, "1-0")],
            "--trailer",
            "--elo0",
            "0",
            "--elo1",
            "10",
        ).stdout
        assert line.endswith(
            "(sprt [0, 10] inconclusive, 2 games, 30+0.3, vs ce8b662)\n"
        )

    def test_one_hypothesis_without_the_other_is_not_a_test(self, tmp_path):
        result = self.run(tmp_path, [drawn(1)], "--elo0", "0")
        assert result.returncode != 0
        assert "both or neither" in result.stderr

    def test_a_settled_test_keeps_its_verdict_with_no_estimate_to_state(self, tmp_path):
        # every pair of the test went the same way, so the model has no elo
        # for the score. The verdict is what the batches were run for and
        # survives without one
        line = self.run(
            tmp_path,
            [pair(1) + pair(2)],
            "--trailer",
            "--elo0",
            "0",
            "--elo1",
            "10",
            "--prior-pairs",
            "0,0,0,0,110",
        ).stdout
        assert line == (
            "Elo: not measured (sprt [0, 10] passed, 224 games, 30+0.3, vs ce8b662)\n"
        )

    def test_a_hypothesis_the_model_has_no_score_for_is_refused(self, tmp_path):
        # not a number bisects forever, and past a thousand elo the expected
        # score rounds to nought or one and there is no interval left to run in
        for elo0, elo1 in (("nan", "10"), ("0", "6400"), ("0", "inf")):
            result = self.run(tmp_path, [drawn(1)], "--elo0", elo0, "--elo1", elo1)
            assert result.returncode != 0
            assert "is an elo difference" in result.stderr

    def test_a_normalized_hypothesis_past_its_cap_is_refused(self, tmp_path):
        cap = match_estimate.MAX_NORMALIZED
        result = self.run(
            tmp_path,
            [drawn(1)],
            "--elo0",
            "0",
            "--elo1",
            str(cap + 1),
            "--model",
            "normalized",
        )
        assert result.returncode != 0
        assert f"between -{cap} and {cap}" in result.stderr

    def test_counts_no_fit_can_meet_are_said_plainly(self, tmp_path):
        # a hundred million pairs in one score and none in the rest, which no
        # match plays, is past what the fit's arithmetic can meet
        result = self.run(
            tmp_path,
            [drawn(1)],
            "--elo0",
            "-3",
            "--elo1",
            "3",
            "--model",
            "normalized",
            "--prior-pairs",
            "0,0,0,0,99999999",
        )
        assert result.returncode != 0
        assert "cannot be fitted to these pairs" in result.stderr
        assert "Traceback" not in result.stderr

    def test_a_model_with_no_test_to_apply_it_to_is_refused(self, tmp_path):
        result = self.run(tmp_path, [drawn(1)], "--model", "normalized")
        assert result.returncode != 0
        assert "wants --elo0" in result.stderr

    def test_a_normalized_test_runs_from_the_command_line(self, tmp_path):
        result = self.run(
            tmp_path,
            [drawn(1) + pair(2)],
            "--elo0",
            "0",
            "--elo1",
            "5",
            "--model",
            "normalized",
            "--line",
        )
        assert result.returncode == 0, result.stderr
        assert ", SPRT [0, 5] nElo inconclusive, LLR " in result.stdout

    def test_pairs_carried_in_that_are_not_five_counts_are_refused(self, tmp_path):
        # the counts are one per pair score, so a ratio typed into the box a
        # ratio used to go in is caught rather than read as a count
        for spec in ("1.06", "1,2,3", "1,2,3,4,5,6", "1,-2,3,4,5", "1e9,0,0,0,0"):
            result = self.run(
                tmp_path,
                [drawn(1)],
                "--elo0",
                "0",
                "--elo1",
                "10",
                "--prior-pairs",
                spec,
            )
            assert result.returncode != 0
            assert "--prior-pairs is a count for each pair score" in result.stderr

    def test_pairs_carried_in_with_no_test_to_carry_them_are_refused(self, tmp_path):
        result = self.run(tmp_path, [drawn(1)], "--prior-pairs", "1,2,3,4,5")
        assert result.returncode != 0
        assert "wants --elo0 and --elo1" in result.stderr

    def test_hypotheses_the_wrong_way_round_are_refused(self, tmp_path):
        # the ratio of a test whose ends meet is nought whatever the games
        # did, so every batch of it would ask for another one
        result = self.run(tmp_path, [drawn(1)], "--elo0", "10", "--elo1", "0")
        assert result.returncode != 0
        assert "--elo0 10 is not below --elo1 0" in result.stderr

    def test_a_match_with_no_estimate_states_none_in_the_trailer(self, tmp_path):
        line = self.run(tmp_path, [game(1, "1-0")], "--trailer").stdout
        assert line == "Elo: not measured\n"

    def test_a_fault_is_reported_on_stderr_for_the_workflow_to_raise(self, tmp_path):
        crashed = game(1, "0-1", termination="abandoned", reason="White disconnects")
        result = self.run(tmp_path, [drawn(1) + game(2, "1-0"), crashed])
        # counted and not an error: the games stay in the estimate either way
        assert result.returncode == 0
        assert "ended by a fault" in result.stderr

    def test_a_shard_with_no_games_of_its_own_does_not_stop_the_pool(self, tmp_path):
        result = self.run(tmp_path, [drawn(1), ""])
        assert result.returncode == 0
        assert "| strength-1-1-shard-1 | 0 | 0.0% | 0 |" in result.stdout

    def test_no_games_anywhere_is_an_error(self, tmp_path):
        result = self.run(tmp_path, ["", ""])
        assert result.returncode != 0
        assert "no games for new" in result.stderr


class TestSequential:
    """The sprt reading, pinned against the numbers fastchess itself prints.

    The two cases below the first are fastchess's own, from
    `app/tests/sprt_test.cpp` at the pinned tag. Its `Stats` holds the counts
    as (LL, LD, WL, DD, WD, WW) and its test merges WL with DD into the middle
    bin, which is the bin a shared pair and a doubly drawn one share here. It
    runs them at alpha and beta of 0.05, the same as ours, though the bounds
    do not enter the ratio."""

    def test_a_real_match_reads_as_the_ratio_fastchess_printed(self):
        llr = match_estimate.log_likelihood_ratio(MATCH, 0, 10)
        assert abs(llr - MATCH_LLR) < 0.01

    def test_the_pairs_of_that_match_read_back_out_of_a_pgn(self, tmp_path):
        # the same counts through the pairing, so a reader that put a pair in
        # the wrong bin would fail here rather than in the arithmetic
        shards, _, _ = pooled(tmp_path, [batch(MATCH)])
        pairs = [score for one in shards for score in one.pairs]
        sprt = match_estimate.Sprt(pairs, 0, 10)
        assert sprt.counts == MATCH
        assert abs(sprt.llr - MATCH_LLR) < 0.01

    def test_fastchess_own_logistic_cases(self):
        for counts, elo0, elo1, expected in (
            ([223, 9863, 21279, 10037, 246], 0.5, 2.5, -3.07),
            ([871, 26175, 55983, 26678, 821], 0, 2, -4.98),
        ):
            llr = match_estimate.log_likelihood_ratio(counts, elo0, elo1)
            assert abs(llr - expected) < 0.01, counts

    def test_the_ratio_flips_when_the_match_and_the_question_both_do(self):
        # swapping the wins for the losses is the same match from the other
        # side, and negating and swapping the hypotheses is the same question
        # asked of that side, so the evidence has to read the other way round
        counts = [3, 11, 42, 17, 7]
        assert math.isclose(
            match_estimate.log_likelihood_ratio(counts, 0, 10),
            -match_estimate.log_likelihood_ratio(list(reversed(counts)), -10, 0),
        )

    def test_a_score_no_pair_reached_is_not_divided_by(self):
        # a short batch can easily have none of a score, and a count of nought
        # has no logarithm, so it is nudged off nought as fastchess does
        assert match_estimate.log_likelihood_ratio([0, 0, 4, 0, 0], 0, 10) < 0
        assert match_estimate.log_likelihood_ratio([0, 0, 0, 0, 4], 0, 10) > 0
        assert match_estimate.Sprt([], 0, 10).llr == 0.0

    def test_a_batch_carries_the_pairs_it_played_to_the_next_one(self):
        before = [2, 3, 14, 3, 8]
        carried = match_estimate.Sprt([2.0, 1.0], 0, 10, before)
        assert carried.batch == [0, 0, 1, 0, 1]
        assert carried.counts == [2, 3, 15, 3, 9]
        assert carried.carried == "2,3,15,3,9"
        assert math.isclose(
            carried.llr, match_estimate.log_likelihood_ratio(carried.counts, 0, 10)
        )

    def test_the_ratio_is_worked_out_over_the_test_and_not_added_up(self):
        # the fit is to the pairs the ratio is read against, so each batch
        # fitting its own distribution and the ratios then being added is a
        # different statistic from the one the pairs together give. Two
        # batches that disagree with each other show how far apart: a fifth
        # of the pairs shared and the rest split evenly between a sweep each
        # way reads as -0.03 pooled and -0.59 added
        first, second = [10, 0, 0, 0, 10], [0, 0, 20, 0, 0]
        together = [one + other for one, other in zip(first, second)]
        added = sum(
            match_estimate.log_likelihood_ratio(counts, 0, 10)
            for counts in (first, second)
        )
        sprt = match_estimate.Sprt([], 0, 10, together)
        assert math.isclose(
            sprt.llr, match_estimate.log_likelihood_ratio(together, 0, 10)
        )
        assert abs(sprt.llr - added) > 0.5

    def test_a_prior_that_is_not_one_count_per_score_is_refused(self):
        # every caller reaching Sprt has five counts, and a shorter list would
        # otherwise be zipped down to its own length and silently drop a bin
        with pytest.raises(ValueError):
            match_estimate.Sprt([2.0], 0, 10, [1, 2, 3])

    def test_more_pairs_than_a_match_plays_are_refused(self):
        # the fit bisects between two bounds set by the counts, and counts
        # this far apart put the root on a bound and the division by nought
        with pytest.raises(ValueError):
            match_estimate.read_prior("100000000,0,0,0,0")
        assert match_estimate.read_prior("99999999,0,0,0,0")[0] == 99999999

    def test_the_bounds_are_where_the_verdict_turns_over(self):
        # the pairs of the whole test are what the ratio is read from, so the
        # verdict turns over on the pair that carries the ratio past a bound
        def verdict(counts):
            return match_estimate.Sprt([], 0, 10, counts).verdict

        assert verdict([0, 0, 100, 0, 5]) == "inconclusive"
        assert verdict([0, 0, 100, 0, 6]) == "passed"
        assert verdict([0, 0, 100, 0, 0]) == "inconclusive"
        assert verdict([1, 0, 100, 0, 0]) == "failed"

    def test_the_report_states_the_ratio_the_pairs_of_the_test_give(self, tmp_path):
        shards, estimate, text = pooled(tmp_path, [drawn(1) + pair(2)])
        pairs = [score for one in shards for score in one.pairs]
        sprt = match_estimate.Sprt(pairs, 0, 10, [1, 0, 1, 0, 0])
        printed = match_estimate.report(shards, estimate, text, sprt)
        assert "SPRT [0, 10] inconclusive." in printed
        assert (
            "over the 4 pairs of the test (2 from this batch and 2 from the"
            " batches before it) is -0.00 against bounds of (-2.94, 2.94)" in printed
        )
        assert "Launch another batch with prior_pairs set to 1,0,2,0,1." in printed

    def test_a_test_that_settled_says_what_it_settled(self, tmp_path):
        shards, estimate, text = pooled(tmp_path, [drawn(1) + pair(2)])
        pairs = [score for one in shards for score in one.pairs]
        printed = match_estimate.report(
            shards, estimate, text, match_estimate.Sprt(pairs, 0, 10, [0, 0, 100, 0, 5])
        )
        assert "SPRT [0, 10] passed." in printed
        assert (
            "The pairs favour a difference of about 10 elo over one of about 0"
            in printed
        )
        # a pass prefers the larger hypothesis, it does not put a floor under
        # the difference, and the old wording claimed it did
        assert "or more" not in printed
        assert "not a floor under the difference" in printed

    def test_a_test_that_failed_says_what_that_does_not_show(self, tmp_path):
        # a fail favours elo0 over elo1. It is not a finding that the
        # candidate is weaker, and the report says so rather than implying it
        shards, estimate, text = pooled(tmp_path, [drawn(1) + pair(2)])
        pairs = [score for one in shards for score in one.pairs]
        printed = match_estimate.report(
            shards,
            estimate,
            text,
            match_estimate.Sprt(pairs, 0, 10, [20, 0, 100, 0, 0]),
        )
        assert "SPRT [0, 10] failed." in printed
        assert (
            "The pairs favour a difference of about 0 elo over one of about 10"
            in printed
        )
        assert "That does not show the candidate is weaker" in printed


class TestNormalized:
    """The difference in normalized elo, pinned against what the pinned
    fastchess works out for the same pairs.

    The figures were printed by fastchess's own EloPentanomial, compiled at the
    pinned tag and given each count as a `Stats`, which is the same object
    whose nElo it prints under a match. The first counts are the real match
    above, the next two are fastchess's own sprt cases and the last is the
    example the README shows."""

    CASES = (
        (MATCH, 83.855453, 87.911717),
        ([223, 9863, 21279, 10037, 246], 1.794764, 2.359447),
        ([871, 26175, 55983, 26678, 821], 1.219646, 1.448342),
        ([2, 9, 36, 19, 9], 84.892025, 55.600252),
    )

    @staticmethod
    def estimate(counts):
        scores = [
            score
            for score, count in zip(match_estimate.PENTANOMIAL, counts)
            for _ in range(count)
        ]
        return match_estimate.Estimate(sum(scores), 2 * len(scores), scores)

    @pytest.mark.parametrize("counts,nelo,margin", CASES)
    def test_the_figure_is_the_one_fastchess_prints(self, counts, nelo, margin):
        estimate = self.estimate(counts)
        # fastchess puts its interval at 1.959964 standard errors and this
        # tooling at 1.96, which moves the margin in the fifth figure
        assert math.isclose(estimate.nelo, nelo, abs_tol=1e-4)
        assert math.isclose(estimate.nelo_margin, margin, rel_tol=1e-4)

    def test_the_draw_rate_moves_the_logistic_figure_and_not_the_normalized_one(
        self,
    ):
        # The same evidence, once as decisive pairs and once as a drawish
        # match. The drawish one is 1.5 against 0.5 where the other is 2
        # against 0, so its score sits nearer a half and its logistic elo is
        # smaller, while the pairs are spread in the same proportion about
        # that score and the normalized figure does not move.
        decisive = self.estimate([30, 0, 0, 0, 70])
        drawish = self.estimate([0, 30, 0, 70, 0])
        assert drawish.elo < decisive.elo / 2
        assert math.isclose(drawish.nelo, decisive.nelo)

    def test_the_margin_depends_on_the_number_of_pairs_alone(self):
        decisive = self.estimate([30, 0, 0, 0, 70])
        drawish = self.estimate([0, 10, 80, 10, 0])
        assert math.isclose(decisive.nelo_margin, drawish.nelo_margin)

    def test_the_report_states_it_beside_the_interval(self, tmp_path):
        shards, estimate, text = pooled(tmp_path, [batch([2, 9, 36, 19, 9])])
        printed = match_estimate.report(shards, estimate, text)
        assert "In normalized elo the difference is +85 ±56," in printed

    def test_every_pair_scoring_the_same_has_no_normalized_figure(self, tmp_path):
        # the spread is modelled there, and a normalized figure read off a
        # modelled spread would be a function of the score alone
        estimate = self.estimate([0, 0, 0, 10, 0])
        assert estimate.modelled
        assert estimate.nelo is None
        assert estimate.nelo_margin is None
        shards, pooled_estimate, text = pooled(tmp_path, [batch([0, 0, 0, 10, 0])])
        printed = match_estimate.report(shards, pooled_estimate, text)
        assert "In normalized elo" not in printed

    def test_a_sweep_has_no_normalized_figure(self):
        # every pair went the same way, so there is no spread to divide by
        estimate = self.estimate([0, 0, 0, 0, 5])
        assert estimate.nelo is None
        assert estimate.nelo_margin is None


class TestNormalizedSprt:
    """The sequential test with its hypotheses in normalized elo.

    Most of what is pinned here is what has to hold whoever else prints a
    number: the fit meets its condition, nothing on the condition fits the
    pairs better, the ratio has the symmetries it should, it reduces to the
    logistic fit where the two models ask the same question, and it tracks
    the normal approximation where that is good. Agreement with fastchess is
    the last test rather than the first, since the fit here was written to be
    checked on its own and fastchess solves it another way."""

    @staticmethod
    def observed(counts):
        counted = [count or match_estimate.REGULARISED for count in counts]
        return [count / sum(counted) for count in counted]

    @staticmethod
    def moments(p):
        mean = sum(a * q for a, q in zip(match_estimate.PAIR, p))
        spread = math.sqrt(
            sum(q * (a - mean) ** 2 for a, q in zip(match_estimate.PAIR, p))
        )
        return mean, spread

    @staticmethod
    def likelihood(observed, p):
        return sum(o * math.log(q) for o, q in zip(observed, p))

    @pytest.mark.parametrize(
        "counts", [MATCH, [2, 9, 36, 19, 9], [0, 0, 50, 0, 3], [40, 0, 0, 0, 1]]
    )
    @pytest.mark.parametrize("nelo", [-50, -5, 0, 2, 10, 50])
    def test_the_fit_meets_the_condition_it_was_asked_for(self, counts, nelo):
        t = match_estimate.normalized_t(nelo)
        _, fitted = match_estimate.likeliest_normalized(self.observed(counts), t)
        mean, spread = self.moments(fitted)
        assert math.isclose(sum(fitted), 1, abs_tol=1e-12)
        assert math.isclose(mean - 0.5, t * spread, abs_tol=1e-10)

    @pytest.mark.parametrize("counts", [MATCH, [5, 1, 60, 2, 9], [0, 3, 10, 30, 0]])
    @pytest.mark.parametrize("nelo", [-20, 0, 5, 40])
    def test_nothing_on_the_condition_fits_the_pairs_better(self, counts, nelo):
        # Distributions drawn at random and each tilted, `q_i e^(k a_i)`,
        # until it meets the condition, which puts every one of them on it.
        # None may be likelier than the fit. The tilt moves the mean far more
        # than the spread, so a bisection on k finds the one that fits.
        import random

        observed = self.observed(counts)
        t = match_estimate.normalized_t(nelo)
        best, _ = match_estimate.likeliest_normalized(observed, t)
        draw = random.Random(7)

        def tilted(q, k):
            w = [x * math.exp(k * a) for x, a in zip(q, match_estimate.PAIR)]
            return [x / sum(w) for x in w]

        def gap(q, k):
            mean, spread = self.moments(tilted(q, k))
            return mean - 0.5 - t * spread

        checked = 0
        for _ in range(300):
            q = [draw.expovariate(1) for _ in range(5)]
            low, high = -60.0, 60.0
            if not gap(q, low) < 0 < gap(q, high):
                continue
            for _ in range(200):
                middle = (low + high) / 2
                low, high = (middle, high) if gap(q, middle) < 0 else (low, middle)
            assert self.likelihood(observed, tilted(q, low)) <= best + 1e-9
            checked += 1
        assert checked > 200

    @pytest.mark.parametrize(
        "counts,elo0,elo1,exact",
        [
            # the ratio at fifty digits, from the same fit written with
            # mpmath. These are the counts a fit refused before its tolerance
            # allowed for what the arithmetic can reach: every pair in one or
            # two scores, so the fit has to give weight to scores the pairs
            # never reached
            ([0, 0, 0, 1000, 0], 0, 5, 14.1839693109359),
            ([0, 0, 0, 0, 30000], 0, 5, 604.311066589889),
            ([0, 0, 0, 30000, 1000], 0, 5, 446.864225024732),
            ([30000, 1000, 0, 0, 0], -5, 0, -619.359770540342),
        ],
    )
    def test_a_one_sided_match_is_read_rather_than_refused(
        self, counts, elo0, elo1, exact
    ):
        llr = match_estimate.log_likelihood_ratio(counts, elo0, elo1, "normalized")
        assert math.isclose(llr, exact, abs_tol=1e-8)

    def test_a_lopsided_fit_reaches_the_maximum_an_optimiser_finds(self):
        # A case from the statistical review, where a multi-start optimiser
        # put the maximum at -1.7823 per pair. The review quoted the counts
        # rounded, and a fit that refused spreads it could not meet to 1e-12
        # got -1.9691 at its exact counts; at these rounded ones both get it
        observed = [0.607, 0.357, 0.0358, 6.8e-6, 1e-6]
        observed = [share / sum(observed) for share in observed]
        value, _ = match_estimate.likeliest_normalized(observed, 0.4055)
        assert math.isclose(value, -1.7822953064, abs_tol=1e-8)

    @pytest.mark.parametrize(
        "counts",
        [[0, 0, 3, 40, 900], [900, 40, 3, 0, 0], [5, 0, 0, 0, 5], [0, 20, 0, 0, 1]],
    )
    @pytest.mark.parametrize("nelo", [-100, -5, 0, 5, 100])
    def test_nothing_drawn_at_random_beats_it_on_lopsided_counts(self, counts, nelo):
        # Distributions drawn from the whole simplex, from near its corners
        # to near its middle, each moved onto the condition along two
        # different families of tilt, one weighting the scores and one their
        # squares. Lopsided counts are where a fit that stops short shows
        import random

        observed = self.observed(counts)
        t = match_estimate.normalized_t(nelo)
        best, _ = match_estimate.likeliest_normalized(observed, t)
        draw = random.Random(11)

        def tilted(q, k, power):
            w = [x * math.exp(k * a**power) for x, a in zip(q, match_estimate.PAIR)]
            return [x / sum(w) for x in w]

        def gap(q, k, power):
            mean, spread = self.moments(tilted(q, k, power))
            return mean - 0.5 - t * spread

        checked = 0
        for concentration in (0.05, 0.3, 1.0, 5.0):
            for _ in range(150):
                q = [draw.gammavariate(concentration, 1) + 1e-300 for _ in range(5)]
                for power in (1, 2):
                    low, high = -200.0, 200.0
                    if not gap(q, low, power) < 0 < gap(q, high, power):
                        continue
                    for _ in range(200):
                        middle = (low + high) / 2
                        if gap(q, middle, power) < 0:
                            low = middle
                        else:
                            high = middle
                    candidate = tilted(q, low, power)
                    if min(candidate) <= 0:
                        continue
                    assert self.likelihood(observed, candidate) <= best + 1e-9
                    checked += 1
        assert checked > 300

    def test_the_spreads_that_can_be_reached_at_t_one(self):
        # Worked by hand. The mean is 1/2 + s. Below s = 1/8 it sits between
        # the scores 1/2 and 3/4 closer than s squared allows, since
        # (m - 1/2)(3/4 - m) = s (1/4 - s) exceeds s^2 there. At s = 1/4 it
        # crosses 3/4, past which the gap's condition always holds, and the
        # top is 1 / (2 sqrt 2), where s^2 reaches m (1 - m)
        pieces = match_estimate.feasible_spreads(1.0)
        assert len(pieces) == 2
        assert math.isclose(pieces[0][0], 0.125)
        assert math.isclose(pieces[0][1], 0.25)
        assert math.isclose(pieces[1][0], 0.25)
        assert math.isclose(pieces[1][1], 0.5 / math.sqrt(2))

    def test_at_nought_every_spread_to_a_half_can_be_reached(self):
        # the mean is a half, on a score, so no gap between scores applies
        assert match_estimate.feasible_spreads(0.0) == [(0.0, 0.5)]

    @pytest.mark.parametrize("t", [-1.5, -0.3, 0.02, 0.7, 2.0])
    def test_inside_a_reachable_spread_a_fit_meets_it(self, t):
        for low, high in match_estimate.feasible_spreads(t):
            for share in (0.1, 0.5, 0.9):
                spread = low + share * (high - low)
                found = match_estimate.with_moments(
                    self.observed([5, 10, 20, 10, 5]), 0.5 + t * spread, spread, (0, 0)
                )
                assert found is not None, (t, spread)
                mean, measured = self.moments(found[1])
                assert math.isclose(mean, 0.5 + t * spread, abs_tol=1e-9)
                assert math.isclose(measured, spread, abs_tol=1e-9)

    @pytest.mark.parametrize(
        "elo0,elo1",
        [(-match_estimate.MAX_NORMALIZED, 0), (0, match_estimate.MAX_NORMALIZED)],
    )
    def test_the_cap_itself_can_be_asked_for(self, elo0, elo1):
        for counts in (MATCH, [0, 0, 0, 1000, 0], [30000, 1, 20, 1000, 0]):
            llr = match_estimate.log_likelihood_ratio(counts, elo0, elo1, "normalized")
            assert math.isfinite(llr)

    def test_at_nought_it_is_the_logistic_fit_at_nought(self):
        # normalized elo of nought and logistic elo of nought both say the
        # mean is a half and nothing else, so the two fits are one fit
        observed = self.observed(MATCH)
        value, _ = match_estimate.likeliest_normalized(observed, 0.0)
        logistic = match_estimate.likeliest(observed, 0.5)
        assert math.isclose(value, self.likelihood(observed, logistic), abs_tol=1e-12)

    def test_the_ratio_flips_when_the_match_and_the_question_both_do(self):
        forward = match_estimate.log_likelihood_ratio(MATCH, -2, 7, "normalized")
        backward = match_estimate.log_likelihood_ratio(MATCH[::-1], -7, 2, "normalized")
        assert math.isclose(forward, -backward, rel_tol=1e-9)

    def test_it_tracks_the_normal_approximation_on_a_long_match(self):
        # With many pairs and small hypotheses the ratio is close to
        # `n/2 ((that - t0)^2 - (that - t1)^2)`, t-hat being the pairs' own
        # distance from a half in their own spread
        counts = [900, 3600, 16000, 3900, 1000]
        observed = [count / sum(counts) for count in counts]
        mean, spread = self.moments(observed)
        seen = (mean - 0.5) / spread
        t0, t1 = match_estimate.normalized_t(0), match_estimate.normalized_t(5)
        approximate = sum(counts) / 2 * ((seen - t0) ** 2 - (seen - t1) ** 2)
        exact = match_estimate.log_likelihood_ratio(counts, 0, 5, "normalized")
        assert math.isclose(exact, approximate, rel_tol=0.02)

    def test_the_same_separation_is_the_same_evidence_on_any_book(self):
        # Two matches that separate the sides equally clearly, one decisive
        # and one drawish: the drawish one is the decisive one with every
        # pair pulled halfway to a draw. Under normalized hypotheses they are
        # the same evidence, to within the nudge an empty score is given,
        # which lands on different scores in the two. Under logistic ones the
        # same bounds weigh them very differently
        decisive = [300, 0, 0, 0, 700]
        drawish = [0, 300, 0, 700, 0]
        normalized = [
            match_estimate.log_likelihood_ratio(counts, 0, 5, "normalized")
            for counts in (decisive, drawish)
        ]
        assert math.isclose(normalized[0], normalized[1], rel_tol=1e-4)
        logistic = [
            match_estimate.log_likelihood_ratio(counts, 0, 10)
            for counts in (decisive, drawish)
        ]
        assert logistic[1] > 1.5 * logistic[0]

    @pytest.mark.parametrize(
        "counts,elo0,elo1,printed",
        [
            (MATCH, 0, 5, 0.194344971),
            ([223, 9863, 21279, 10037, 246], 0, 2, 1.096834254),
            ([871, 26175, 55983, 26678, 821], 0, 2, 0.804451473),
            ([2, 9, 36, 19, 9], -1, 3, 0.391779344),
            ([100, 400, 1000, 450, 120], 0, 5, 1.574910820),
        ],
    )
    def test_it_agrees_with_fastchess(self, counts, elo0, elo1, printed):
        # fastchess's own normalized ratio at the pinned tag, compiled and
        # given each count as its `Stats`. It solves the fit by the fixed
        # point iteration of Van den Bergh's note, capped at ten steps, so
        # this is agreement between two methods rather than a copy of one
        llr = match_estimate.log_likelihood_ratio(counts, elo0, elo1, "normalized")
        assert math.isclose(llr, printed, abs_tol=1e-6)

    def test_the_report_names_the_model(self, tmp_path):
        shards, estimate, text = pooled(tmp_path, [batch([2, 9, 36, 19, 9])])
        pairs = [score for one in shards for score in one.pairs]
        sprt = match_estimate.Sprt(
            pairs, 0, 5, [20, 90, 360, 190, 90], model="normalized"
        )
        assert sprt.verdict == "passed"
        printed = match_estimate.report(shards, estimate, text, sprt)
        assert str(sprt).startswith("SPRT [0, 5] nElo passed, LLR ")
        assert "SPRT [0, 5] nElo passed." in printed
        assert "a difference of about 5 normalized elo over one of about 0" in printed
        trailer = match_estimate.trailer(estimate, "10+0.1", BASE, sprt)
        assert "(sprt [0, 5] nElo passed, " in trailer

    def test_the_logistic_forms_are_unchanged(self, tmp_path):
        shards, _, _ = pooled(tmp_path, [batch(MATCH)])
        pairs = [score for one in shards for score in one.pairs]
        assert str(match_estimate.Sprt(pairs, 0, 10)).startswith("SPRT [0, 10] ")

    def test_an_inconclusive_normalized_test_says_to_keep_the_model(self, tmp_path):
        shards, estimate, text = pooled(tmp_path, [drawn(1) + pair(2)])
        pairs = [score for one in shards for score in one.pairs]
        sprt = match_estimate.Sprt(pairs, 0, 5, model="normalized")
        printed = match_estimate.report(shards, estimate, text, sprt)
        assert "and the normalized model again." in printed

    def test_a_model_it_does_not_know_is_refused(self):
        with pytest.raises(ValueError):
            match_estimate.Sprt([1.0], 0, 5, model="bayesian")


class TestJson:
    """The --json mode, which is the same result the report states, as data.

    The shape is provisional while the format is 0, so what is pinned here is
    that it parses, that the figures in it are the ones the other modes print,
    and that a bound the model puts at infinity is not written as a word no
    parser has to read."""

    def run(self, tmp_path, texts, *arguments):
        return TestCommandLine().run(tmp_path, texts, *arguments)

    def loaded(self, tmp_path, texts, *arguments):
        result = self.run(tmp_path, texts, "--json", *arguments)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    def test_the_figures_are_the_ones_the_report_states(self, tmp_path):
        texts = [batch(MATCH), drawn(1) + drawn(2)]
        written = self.loaded(tmp_path, texts)
        assert written["format"] == 1
        assert written["tool"] == {
            "name": "mache",
            "version": mache.__version__,
            "command": "match_estimate",
        }
        assert written["candidate"] == CANDIDATE
        assert written["baseline"] == BASE
        assert written["tc"] == "30+0.3"
        assert written["games"] == 64
        assert written["pairs"] == 32
        assert written["pentanomial"] == [2, 3, 16, 3, 8]
        assert written["sprt"] is None
        assert [one["name"] for one in written["shards"]] == [
            "strength-1-1-shard-0",
            "strength-1-1-shard-1",
        ]
        assert written["terminations"]["games"] == 64
        assert written["terminations"]["endings"]["normal"]["count"] == 64
        assert written["remarks"] == []
        assert written["line"] == self.run(tmp_path, texts, "--line").stdout.strip()
        assert (
            written["trailer"] == self.run(tmp_path, texts, "--trailer").stdout.strip()
        )
        # the figures are unrounded, and the line is what rounds them
        assert round(written["elo"]) == 66
        assert written["line"].startswith("+66 ")
        assert written["low"] < written["elo"] < written["high"]
        # normalized elo beside it, unrounded like the rest
        expected = TestNormalized.estimate(written["pentanomial"])
        assert written["nelo"] == pytest.approx(expected.nelo)
        assert written["nelo_margin"] == pytest.approx(expected.nelo_margin)

    def test_a_bounded_estimate_is_null_and_not_an_infinity(self, tmp_path):
        # every pair went the same way, so the model has no elo for the score
        # and the interval is open on one side. json.dumps writes that side as
        # -Infinity, which no parser is required to read back
        result = self.run(tmp_path, [pair(1) + pair(2)], "--json")
        assert "Infinity" not in result.stdout
        written = json.loads(result.stdout)
        assert written["bounded"] == "above +1200"
        assert written["elo"] == match_estimate.MAX_ELO
        assert written["margin"] is None
        assert written["low"] == match_estimate.MAX_ELO
        assert written["high"] is None

    def test_a_match_with_no_complete_pair_states_no_figure(self, tmp_path):
        written = self.loaded(tmp_path, [game(1, "1-0")])
        assert written["bounded"] == "not measured"
        assert written["unpaired"] == 1
        assert written["score"] == 1.0
        for key in (
            "paired_score",
            "elo",
            "margin",
            "low",
            "high",
            "los",
            "nelo",
            "nelo_margin",
        ):
            assert written[key] is None, key

    def test_the_sprt_names_its_model(self, tmp_path):
        arguments = ("--elo0", "0", "--elo1", "5")
        logistic = self.loaded(tmp_path / "a", [drawn(1) + pair(2)], *arguments)
        assert logistic["sprt"]["model"] == "logistic"
        normalized = self.loaded(
            tmp_path / "b", [drawn(1) + pair(2)], *arguments, "--model", "normalized"
        )
        assert normalized["sprt"]["model"] == "normalized"

    def test_the_sprt_carries_the_whole_test_and_this_batch(self, tmp_path):
        written = self.loaded(
            tmp_path,
            [drawn(1) + pair(2)],
            "--elo0",
            "0",
            "--elo1",
            "10",
            "--prior-pairs",
            "0,0,100,0,5",
        )
        sprt = written["sprt"]
        assert sprt["elo0"] == 0.0
        assert sprt["elo1"] == 10.0
        assert sprt["verdict"] == "passed"
        assert sprt["batch"] == [0, 0, 1, 0, 1]
        assert sprt["prior"] == [0, 0, 100, 0, 5]
        assert sprt["counts"] == [0, 0, 101, 0, 6]
        assert sprt["carried"] == "0,0,101,0,6"
        # the batch played 4 games and the test 214, and the trailer states
        # the test
        assert written["games"] == 4
        assert sprt["estimate"]["games"] == 214
        assert "214 games" in written["trailer"]

    def test_the_remarks_are_in_it_as_well_as_on_stderr(self, tmp_path):
        text = drawn(1) + game(
            2, "1-0", termination="time forfeit", reason="White loses on time"
        )
        result = self.run(tmp_path, [text], "--json")
        written = json.loads(result.stdout)
        assert written["remarks"] == [result.stderr.strip()]
        assert "ended by a fault" in written["remarks"][0]
        assert written["terminations"]["endings"]["time forfeit"] == {
            "count": 1,
            "blamed": {CANDIDATE: 1},
        }

    def test_the_json_and_the_line_are_not_both_asked_for(self, tmp_path):
        result = self.run(tmp_path, [drawn(1)], "--json", "--line")
        assert result.returncode != 0
        assert "not allowed with argument" in result.stderr


class TestInstruments:
    """The clocks and the node counts, which a suspicious result is read
    against. They live in the move comments, which nothing read before, and
    the registration that asks for them is answered from the run's own log
    rather than from artifacts a later session may not reach."""

    @staticmethod
    def thought(seconds, left, nodes):
        return (
            f"{{+0.15/5 {seconds}s, tl={left}s, latency=0.000s, n={nodes},"
            ' sd=20, nps=8348500, hashfull=0, pv="e1g1"}'
        )

    def played(self, white, black, moves):
        """A game whose moves carry the comments given, in order."""
        text = ""
        for number, comment in enumerate(moves):
            if number % 2 == 0:
                text += f"{number // 2 + 1}. e4 {comment} "
            else:
                text += f"e5 {comment} "
        return (
            f'[Event "Fastchess Tournament"]\n[Site "?"]\n[Round "1"]\n'
            f'[White "{white}"]\n[Black "{black}"]\n[Result "1-0"]\n'
            f'[Termination "normal"]\n\n{text}1-0\n\n'
        )

    def test_a_side_is_an_engine_and_not_a_colour(self):
        # -repeat plays the second game of a round the other way round, so
        # counting by colour would add the two engines together
        from mache.match_estimate import read_instruments

        first = self.played(
            "new",
            "old",
            [self.thought("0.1", "2.0", 1000), self.thought("0.2", "2.0", 9000)],
        )
        second = self.played(
            "old",
            "new",
            [self.thought("0.1", "2.0", 9000), self.thought("0.2", "2.0", 1000)],
        )
        found = read_instruments(first + second, "new")
        assert found["new"].nodes == 2000
        assert found["old"].nodes == 18000

    def test_a_book_move_is_not_counted_but_keeps_its_place(self):
        # the engine did not think about it, so it is not its search; the move
        # was still made, so dropping it would hand the rest to the wrong side
        from mache.match_estimate import read_instruments

        text = self.played(
            "new",
            "old",
            ["{book}", "{book}", self.thought("0.3", "1.9", 7000)],
        )
        found = read_instruments(text, "new")
        assert found["new"].moves == 1
        assert found["new"].nodes == 7000
        assert "old" not in found or found["old"].moves == 0

    def test_a_bracket_in_a_comment_does_not_move_a_side_s_nodes(self):
        """The side is the move's place in the order, so anything that drops a
        move hands every move after it to the other engine.

        The movetext used to start after the last `]`, which is the last tag
        until a comment holds one. fastchess writes none today, so this is
        about the parse not resting on that."""
        from mache.match_estimate import read_instruments

        bracketed = self.thought("0.1", "2.0", 1).replace('pv="e1g1"', 'pv="e1g1" [1]')
        text = self.played(
            "new",
            "old",
            [
                bracketed,
                self.thought("0.1", "2.0", 2),
                self.thought("0.1", "2.0", 4),
                self.thought("0.1", "2.0", 8),
            ],
        )
        found = read_instruments(text, "new")
        # white played the first and the third, black the second and fourth.
        # Reading from the last `]` loses the first move and turns the rest
        # around, which gives new 10 and old 4
        assert found["new"].nodes == 1 + 4
        assert found["old"].nodes == 2 + 8

    def test_the_rate_is_not_offered_as_a_speed_when_the_trees_differ(self):
        """Nodes a second compares two engines' speed only where a node means
        the same thing on both sides. A side that prunes harder visits fewer
        nodes and dearer ones, so its rate falls while it reaches depth
        sooner, and the figure invites the opposite reading."""
        from mache.match_estimate import Instruments, instruments

        def side(nodes):
            found = Instruments()
            found.moves, found.nodes, found.seconds = 10, nodes, 1.0
            return found

        apart = "\n".join(instruments({"new": side(580), "old": side(1000)}, "new"))
        assert "0.580 times the rate" in apart
        assert "not a speed comparison" in apart

        # the ordinary case, one engine against a near neighbour of itself
        alike = "\n".join(instruments({"new": side(1000), "old": side(1010)}, "new"))
        assert "times the rate" in alike
        assert "not a speed comparison" not in alike

    def test_the_least_time_left_is_the_tightest_the_clock_got(self):
        from mache.match_estimate import read_instruments

        text = self.played(
            "new",
            "old",
            [
                self.thought("0.1", "2.000", 10),
                self.thought("0.1", "9.000", 10),
                self.thought("0.1", "0.312", 10),
                self.thought("0.1", "8.000", 10),
            ],
        )
        found = read_instruments(text, "new")
        assert found["new"].least_left == 0.312
        assert found["old"].least_left == 8.0

    def test_the_report_carries_them_so_a_log_is_enough(self, tmp_path):
        # the point of the whole thing: readable off the run page, with no
        # artifact to download
        shards, estimate, text = pooled(tmp_path, [pair(1)])
        printed = match_estimate.report(shards, estimate, text)
        assert "The clocks and the search" in printed
        assert "nodes a second" in printed
        # and the candidate first, whatever the sides are called, so two runs
        # read the same way round
        section = printed[printed.index("The clocks and the search") :]
        rows = [line for line in section.splitlines() if line.startswith("| ")]
        assert rows[2].split("|")[1].strip() == CANDIDATE
