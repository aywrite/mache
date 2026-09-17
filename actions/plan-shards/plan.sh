#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

# Work out how a match is split across shards, and check the inputs a shard
# would otherwise discover too late:
#
#     plan.sh <games> <shards> <sprt> <elo0> <elo1> <prior-pairs>
#
# Prints `key=value` lines for the caller to hand to GITHUB_OUTPUT, and its
# remarks on stderr, one to a line.
#
# The sprt inputs are checked here rather than by the summary, because the
# summary is otherwise the first thing to read them and by then the batch has
# been played. A workflow_dispatch box takes free text whatever its type says.
set -euo pipefail

usage="usage: plan.sh <games> <shards> <sprt> <elo0> <elo1> <prior-pairs>"
games=${1:?$usage}
shards=${2:?$usage}
sprt=${3:?$usage}
elo0=${4?$usage}
elo1=${5?$usage}
prior_pairs=${6?$usage}

if [ "$shards" -lt 1 ]; then
    echo "plan.sh: shards must be at least one, got ${shards}" >&2
    exit 1
fi

if [ "$sprt" = "true" ]; then
    number='^-?[0-9]+(\.[0-9]+)?$'
    for value in "$elo0" "$elo1"; do
        if ! [[ "$value" =~ $number ]]; then
            echo "plan.sh: elo0 and elo1 must be numbers, got ${elo0} and ${elo1}" >&2
            exit 1
        fi
    done
    # A count for each of the five scores a pair can end on, as the last
    # batch's summary printed them. A ratio is the old shape of this box and
    # is refused. Pasted spaces are dropped, as the summary drops them, and
    # the digits are capped at eight, where the summary caps them.
    prior_pairs="${prior_pairs//[[:space:]]/}"
    if [ -n "$prior_pairs" ] \
       && ! [[ "$prior_pairs" =~ ^[0-9]{1,8}(,[0-9]{1,8}){4}$ ]]; then
        echo "plan.sh: prior_pairs is a count for each of the five pair scores, got ${prior_pairs}" >&2
        exit 1
    fi
    if ! awk -v null="$elo0" -v alternative="$elo1" \
         'BEGIN { exit !(null < alternative) }'; then
        echo "plan.sh: elo0 must be below elo1, got ${elo0} and ${elo1}" >&2
        exit 1
    fi
fi

# whole pairs a shard, so the run plays a little under what was asked for
pairs=$((games / shards / 2))
if [ "$pairs" -lt 1 ]; then
    echo "plan.sh: ${games} games across ${shards} shards is under a pair each" >&2
    exit 1
fi

batch=""
if [ "$sprt" = "true" ]; then
    batch=", one batch of the sprt"
fi
if [ "$shards" = "1" ]; then
    echo "one shard of $((pairs * 2)) games${batch}" >&2
else
    echo "$((pairs * 2)) games in each of ${shards} shards, $((pairs * 2 * shards)) in all${batch}" >&2
fi

echo "pairs=${pairs}"
# a matrix is a list, not a number
echo "shards=[$(seq -s, 0 $((shards - 1)))]"
echo "count=${shards}"
