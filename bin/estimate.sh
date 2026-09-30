#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

# Pool fastchess pgns into one estimate, for the action at the root of this
# repository:
#
#     estimate.sh <outputs-file> <pattern>...
#
# Each pattern is a path or a glob, and every file they match is read as one
# shard. The caller sets CANDIDATE and BASELINE, and may set TIME_CONTROL,
# SPRT, ELO0, ELO1, PRIOR_PAIRS, SPRT_MODEL, SPRT_ALPHA and SPRT_BETA. An unset
# model is the logistic one and an unset rate is five percent, as they are for
# match-estimate itself.
#
# The report goes to stdout, and to the step summary when there is one. The
# `key=value` lines the caller wants go to <outputs-file>, and the remarks to
# stderr, one to a line. Nothing is written in the working directory, which is
# the caller's.
set -euo pipefail

usage="usage: estimate.sh <outputs-file> <pattern>..."
outputs=${1:?$usage}
shift
[ "$#" -gt 0 ] || { echo "$usage" >&2; exit 1; }

# globstar so that `**/*.pgn` reaches into directories, and nullglob so that a
# pattern matching nothing expands to nothing rather than to itself
shopt -s nullglob globstar
games=()
for pattern in "$@"; do
    # unquoted on purpose: the glob is what is being expanded
    # shellcheck disable=SC2206
    matched=($pattern)
    if [ "${#matched[@]}" -eq 0 ]; then
        echo "estimate.sh: nothing matches ${pattern}" >&2
        exit 1
    fi
    games+=("${matched[@]}")
done

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

estimate=(python3 -m mache.match_estimate "${games[@]}"
          --candidate "${CANDIDATE:?estimate.sh: CANDIDATE is the engine to measure}"
          --baseline "${BASELINE:?estimate.sh: BASELINE is what it played}"
          --tc "${TIME_CONTROL-}")
if [ "${SPRT-false}" = "true" ]; then
    estimate+=(--elo0 "${ELO0:-0}" --elo1 "${ELO1:-10}"
               --prior-pairs "${PRIOR_PAIRS-}"
               --model "${SPRT_MODEL:-logistic}"
               --alpha "${SPRT_ALPHA:-0.05}" --beta "${SPRT_BETA:-0.05}")
fi

"${estimate[@]}" > "${work}/report.md" 2> "${work}/remarks.txt" \
    || { echo "estimate.sh: the games could not be read" >&2
         cat "${work}/remarks.txt" >&2
         exit 1; }

cat "${work}/report.md"

# the same estimate asked the other ways. Their stderr is the same remarks
# again, and the run above is the one that reports them
trailer=$("${estimate[@]}" --trailer 2> /dev/null)
line=$("${estimate[@]}" --line 2> /dev/null)
# read out of the json rather than parsed back out of the report, so the two
# cannot disagree. Both are empty when this was not a sequential test
"${estimate[@]}" --json 2> /dev/null | python3 -c '
import json
import sys

sequential = json.load(sys.stdin)["sprt"] or {}
for key in ("verdict", "carried"):
    print("%s=%s" % (key, sequential.get(key, "")))
' > "${work}/decided.txt"

if [ -n "${GITHUB_STEP_SUMMARY-}" ]; then
    {
        echo "${CANDIDATE} against ${BASELINE}, over ${#games[@]} pgn files${TIME_CONTROL:+ at ${TIME_CONTROL}}."
        echo
        cat "${work}/report.md"
        echo
        echo "As the trailer for the commit that made the difference:"
        echo
        echo '```'
        echo "$trailer"
        echo '```'
    } >> "$GITHUB_STEP_SUMMARY"
fi

cat "${work}/remarks.txt" >&2

{
    echo "line=${line}"
    echo "trailer=${trailer}"
    cat "${work}/decided.txt"
} > "$outputs"
