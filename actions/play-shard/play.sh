#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

# Play one shard of a match, from the directory the engines and the book are
# in:
#
#     play.sh <outputs-file>
#
# Everything else is an environment variable, because there are fourteen of
# them and a positional list that long is a bug waiting for someone to add the
# fifteenth in the wrong place. The caller sets:
#
#     CANDIDATE, CANDIDATE_BINARY   one side, by name and by file
#     OPPONENT, OPPONENT_BINARY     the other
#     BOOK_FILE, BOOK_FORMAT        what fastchess reads, and as what
#     START                         the opening this shard starts at
#     PAIRS                         how many rounds it plays
#     TIME_CONTROL, HASH, CONCURRENCY, STARTUP_MS
#     MAX_MATCH_MINUTES             the wall clock cap
#
# stdout is fastchess's own, so the progress and the result block reach the
# job's log the way they always have. The one `key=value` line this has to
# report, `stopped_by`, goes to <outputs-file> instead: a shard stopped by the
# cap played fewer games and the summary says so.
set -euo pipefail

outputs=${1:?usage: play.sh <outputs-file>}

# fastchess appends to a pgn it is given, and a rerun on the same runner can
# find the last attempt's here.
rm -f games.pgn result.txt config.json

# No -sprt, sharded or not. A shard that stopped itself when its own games
# settled the question would be one look per shard at a bound meant for one
# look, and its games a slice chosen by what they said. The summary runs the
# test over all the shards at once.
#
# tbhits is left off the pgn: no tablebases here.
#
# INT asks fastchess to stop, report the games so far and exit, and 124 is how
# timeout says it sent it.
status=0
timeout -k 60 -s INT "${MAX_MATCH_MINUTES}m" ./fastchess \
    -engine "name=$CANDIDATE" "cmd=$CANDIDATE_BINARY" \
    -engine "name=$OPPONENT" "cmd=$OPPONENT_BINARY" \
    -each proto=uci "tc=$TIME_CONTROL" "option.Hash=$HASH" \
    -startup-ms "$STARTUP_MS" \
    -openings "file=$BOOK_FILE" "format=$BOOK_FORMAT" order=sequential "start=$START" \
    -rounds "$PAIRS" -repeat -concurrency "$CONCURRENCY" -recover \
    -pgnout file=games.pgn nodes=true seldepth=true nps=true \
      hashfull=true timeleft=true latency=true pv=true \
    | tee result.txt || status=$?

if [ "$status" = "124" ]; then
    echo "stopped_by=the ${MAX_MATCH_MINUTES} minute wall clock cap" > "$outputs"
elif [ "$status" != "0" ]; then
    exit "$status"
else
    echo "stopped_by=fastchess, at the game count" > "$outputs"
fi
