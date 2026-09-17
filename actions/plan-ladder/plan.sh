#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

# Read a gauntlet's ladder into the rungs a matrix plays and the spec the fit
# reads:
#
#     plan.sh <games> <ladder> <opponent-table>
#
# A ladder is a comma separated list of `engine:tag:rating`. Every name in it
# is checked against the table before a runner builds anything, so an engine
# the table has no block for costs a job that does nothing.
#
# Prints `key=value` lines for the caller to hand to GITHUB_OUTPUT, and its
# remarks on stderr, one to a line.
set -euo pipefail

usage="usage: plan.sh <games> <ladder> <opponent-table>"
games=${1:?$usage}
ladder=${2?$usage}
table=${3:?$usage}

# whole pairs, an opening from each side, so rounded down to even
pairs=$((games / 2))
if [ "$pairs" -lt 1 ]; then
    echo "plan.sh: ${games} games against an opponent is under a pair" >&2
    exit 1
fi

known=$("$table" list | tr '\n' ' ')
rungs=""
spec=""
named=" "
index=0
# Split on the commas alone: splitting on whitespace would let a * in the
# ladder glob the checkout. Newlines are joined first, since read stops at one
# and would silently drop the rungs after it.
IFS=, read -r -a entries <<< "${ladder//$'\n'/,}"
for rung in "${entries[@]}"; do
    # spaces after the commas and a trailing comma are not faults
    rung=${rung// /}
    [ -n "$rung" ] || continue
    IFS=: read -r engine tag rating extra <<< "$rung"
    if [ -z "$engine" ] || [ -z "$tag" ] || [ -z "$rating" ] || [ -n "$extra" ]; then
        echo "plan.sh: ladder entry ${rung} is not engine:tag:rating" >&2
        exit 1
    fi
    case " ${known} " in
        *" ${engine} "*) ;;
        *) echo "plan.sh: ladder entry ${rung} names ${engine}, which is not one of ${known}" >&2
           exit 1 ;;
    esac
    # the tag is part of a file name, an artifact name and the name the engine
    # plays under
    case "$tag" in
        *[!A-Za-z0-9._-]*)
            echo "plan.sh: ladder entry ${rung} has a tag that is not a name" >&2
            exit 1 ;;
    esac
    case "$rating" in
        *[!0-9.]*|*.*.*|.)
            echo "plan.sh: ${rung} has no rating on it" >&2
            exit 1 ;;
    esac
    # a repeated engine and pin would upload twice under one artifact name and
    # be counted once
    case "$named" in
        *" ${engine}-${tag} "*)
            echo "plan.sh: ${engine}-${tag} is in the ladder twice" >&2
            exit 1 ;;
    esac
    named="${named}${engine}-${tag} "
    rungs="${rungs}${rungs:+,}"
    rungs="${rungs}{\"engine\":\"${engine}\",\"tag\":\"${tag}\""
    rungs="${rungs},\"rating\":\"${rating}\",\"index\":${index}}"
    # the fit's ladder has to carry the names the games do
    spec="${spec}${spec:+,}${engine}-${tag}:${rating}"
    index=$((index + 1))
done

if [ "$index" -eq 0 ]; then
    echo "plan.sh: the ladder is empty" >&2
    exit 1
fi

if [ "$index" = "1" ]; then
    echo "one rung of $((pairs * 2)) games: ${ladder}" >&2
else
    echo "${index} rungs of $((pairs * 2)) games each: ${ladder}" >&2
fi

echo "rungs=[${rungs}]"
echo "count=${index}"
echo "pairs=${pairs}"
echo "spec=${spec}"
