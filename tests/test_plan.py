# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

"""What the planning scripts refuse, and what they work out.

These run before a runner has built anything, which is the whole reason they
exist: a ladder naming an engine the table cannot build, or an sprt bound
typed into the wrong box, costs a job that does nothing rather than one that
has already built two engines and played for an hour. So most of what is
pinned here is a refusal.

The scripts are run as a caller runs them rather than read, because what they
promise is `key=value` on stdout and a remark on stderr, and only running them
says whether they keep to that.
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARDS = ROOT / "actions" / "plan-shards" / "plan.sh"
LADDER = ROOT / "actions" / "plan-ladder" / "plan.sh"
CHECK_BOOK = ROOT / "bin" / "check_book.sh"
BOOKS = ROOT / "tests" / "fixtures" / "books.sh"


def run(script, *arguments):
    return subprocess.run(
        [str(script), *[str(argument) for argument in arguments]],
        capture_output=True,
        text=True,
        check=False,
    )


def planned(result):
    """The `key=value` lines a plan printed, as a dict."""
    assert result.returncode == 0, result.stderr
    return dict(line.split("=", 1) for line in result.stdout.splitlines())


def shards(games, count, sprt="false", elo0="0", elo1="5", prior=""):
    return run(SHARDS, games, count, sprt, elo0, elo1, prior)


def ladder(games, entries, table=BOOKS):
    # the opponent table stands in for itself: what plan.sh asks of it is
    # `list`, and the book fixture's list is a name like any other
    return run(LADDER, games, entries, table)


class TestShards:
    def test_whole_pairs_a_shard(self):
        # 500 games over 4 shards is 62 pairs each, so 496 are played. A run
        # gets a little under what it asked for rather than a part pair
        plan = planned(shards(500, 4))
        assert plan["pairs"] == "62"
        assert plan["count"] == "4"

    def test_the_shard_list_is_json_for_a_matrix(self):
        # a matrix is a list, not a number, and fromJSON is what reads it
        assert planned(shards(100, 3))["shards"] == "[0,1,2]"
        assert planned(shards(100, 1))["shards"] == "[0]"

    def test_a_match_too_small_to_shard_is_refused(self):
        result = shards(4, 8)
        assert result.returncode != 0
        assert "under a pair each" in result.stderr

    def test_no_shards_is_refused(self):
        assert shards(100, 0).returncode != 0

    def test_the_sprt_bounds_have_to_be_numbers(self):
        # the dispatch box takes free text whatever its type says, and the
        # summary is otherwise the first thing to read these, after the batch
        # has been played
        result = shards(100, 1, sprt="true", elo0="nought")
        assert result.returncode != 0
        assert "must be numbers" in result.stderr

    def test_the_null_has_to_be_below_the_alternative(self):
        result = shards(100, 1, sprt="true", elo0="10", elo1="5")
        assert result.returncode != 0
        assert "elo0 must be below elo1" in result.stderr

    def test_the_bounds_are_not_read_when_there_is_no_sprt(self):
        # nobody clears the boxes to play a match that is not a test
        assert shards(100, 1, sprt="false", elo0="nought").returncode == 0

    def test_prior_pairs_is_five_counts(self):
        assert shards(100, 1, sprt="true", prior="1,2,3,4,5").returncode == 0
        # the old shape of this box was a ratio, and a ratio read as counts
        # would carry the wrong weight into the next batch
        assert shards(100, 1, sprt="true", prior="3/4").returncode != 0
        assert shards(100, 1, sprt="true", prior="1,2,3,4").returncode != 0

    def test_pasted_spaces_in_prior_pairs_are_not_a_fault(self):
        # the summary prints them with spaces, and they are pasted back
        assert shards(100, 1, sprt="true", prior="1, 2, 3, 4, 5").returncode == 0

    def test_an_empty_prior_is_the_first_batch(self):
        assert shards(100, 1, sprt="true", prior="").returncode == 0


class TestLadder:
    def test_a_rung_becomes_a_matrix_entry_and_a_fit_entry(self):
        plan = planned(ladder(50, "8moves_v3:v1:2500"))
        assert plan["count"] == "1"
        assert plan["pairs"] == "25"
        assert plan["spec"] == "8moves_v3-v1:2500"
        assert '"engine":"8moves_v3"' in plan["rungs"]
        assert '"index":0' in plan["rungs"]

    def test_the_rungs_are_indexed_in_the_order_they_were_given(self):
        plan = planned(ladder(50, "8moves_v3:a:2500,8moves_v3:b:2600"))
        assert plan["count"] == "2"
        assert plan["rungs"].index('"tag":"a"') < plan["rungs"].index('"tag":"b"')
        assert plan["spec"] == "8moves_v3-a:2500,8moves_v3-b:2600"

    def test_spaces_and_a_trailing_comma_are_not_faults(self):
        plan = planned(ladder(50, "8moves_v3:a:2500, 8moves_v3:b:2600,"))
        assert plan["count"] == "2"

    def test_newlines_do_not_swallow_the_rungs_after_them(self):
        # read stops at a newline, so a ladder pasted over two lines would
        # otherwise lose everything below the first
        plan = planned(ladder(50, "8moves_v3:a:2500,\n8moves_v3:b:2600"))
        assert plan["count"] == "2"

    def test_an_engine_the_table_cannot_build_is_refused(self):
        result = ladder(50, "nosuch:v1:2500")
        assert result.returncode != 0
        assert "not one of" in result.stderr

    def test_a_rung_that_is_not_engine_tag_rating_is_refused(self):
        assert ladder(50, "8moves_v3:v1").returncode != 0
        assert ladder(50, "8moves_v3:v1:2500:extra").returncode != 0

    def test_a_rating_that_is_not_a_number_is_refused(self):
        assert ladder(50, "8moves_v3:v1:strong").returncode != 0

    def test_a_tag_that_is_not_a_name_is_refused(self):
        # the tag is part of a file name, an artifact name and the name the
        # engine plays under
        assert ladder(50, "8moves_v3:v1/../x:2500").returncode != 0

    def test_a_glob_in_the_ladder_does_not_reach_the_checkout(self):
        # splitting on whitespace rather than on commas alone would let this
        # expand against the files in the working directory
        result = ladder(50, "8moves_v3:*:2500")
        assert result.returncode != 0
        assert "not a name" in result.stderr

    def test_the_same_engine_and_pin_twice_is_refused(self):
        # two rungs would upload under one artifact name and be counted once
        result = ladder(50, "8moves_v3:v1:2500,8moves_v3:v1:2500")
        assert result.returncode != 0
        assert "twice" in result.stderr

    def test_the_same_engine_at_two_pins_is_fine(self):
        assert ladder(50, "8moves_v3:v1:2500,8moves_v3:v2:2600").returncode == 0

    def test_an_empty_ladder_is_refused(self):
        assert ladder(50, "").returncode != 0
        assert ladder(50, " , ").returncode != 0

    def test_too_few_games_for_a_pair_is_refused(self):
        assert ladder(1, "8moves_v3:v1:2500").returncode != 0


class TestCheckBook:
    def test_a_book_the_table_knows_passes(self):
        assert run(CHECK_BOOK, BOOKS, "8moves_v3").returncode == 0

    def test_a_book_it_does_not_know_is_refused_with_the_list(self):
        result = run(CHECK_BOOK, BOOKS, "nosuch")
        assert result.returncode != 0
        assert "8moves_v3" in result.stderr

    def test_an_empty_name_is_an_unknown_name(self):
        assert run(CHECK_BOOK, BOOKS, "").returncode != 0

    def test_a_metacharacter_is_an_unknown_name_rather_than_a_pattern(self):
        # grep -F and -x, or `.*` would match every book in the table
        assert run(CHECK_BOOK, BOOKS, ".*").returncode != 0
