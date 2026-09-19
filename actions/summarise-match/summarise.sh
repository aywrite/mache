#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

# Pool the shards of a strength match and say what they came to:
#
#     summarise.sh <games-dir> <outputs-file>
#
# The caller sets CANDIDATE, CANDIDATE_SHA, BASELINE, BASELINE_SHA, SHARDS,
# TIME_CONTROL, SPRT, ELO0, ELO1, PRIOR_PAIRS and PROVENANCE.
#
# Writes report.md, and writes the `key=value` lines the caller wants into
# <outputs-file>. The report goes to stdout, so it is in the job's log as well
# as in the summary: the summary is read from the run's web page and nowhere
# else, the pair counts the next batch needs are in it, and the artifacts
# expire. The step summary goes to GITHUB_STEP_SUMMARY and the remarks to
# stderr, one to a line.
#
# The estimate is counted from every shard's games, not from a result block
# that saw one shard. Games lost to a crash or the clock stay in it, because
# choosing what to count after seeing it is not a measurement; the termination
# counts sit beside it.
set -euo pipefail

usage="usage: summarise.sh <games-dir> <outputs-file>"
dir=${1:?$usage}
outputs=${2:?$usage}

mapfile -t games < <(find "$dir" -name games.pgn 2>/dev/null | sort)
if [ "${#games[@]}" -eq 0 ]; then
    echo "summarise.sh: no shard of attempt ${GITHUB_RUN_ATTEMPT} uploaded any games. Rerunning the failed jobs alone leaves the shards on the attempt that played them, so rerun all of them." >&2
    exit 1
fi

# The trailer's base has to name the same build when it is read back months
# later. A release tag does; anything else is a ref that moves, so the sha it
# resolved to today goes in instead.
case "$BASELINE" in
    v[0-9]*.[0-9]*.[0-9]*) base="$BASELINE" ;;
    *) base="${BASELINE_SHA:0:8}" ;;
esac

estimate=(python3 -m mache.match_estimate "${games[@]}"
          --candidate "$CANDIDATE" --baseline "$base"
          --tc "$TIME_CONTROL")
if [ "$SPRT" = "true" ]; then
    estimate+=(--elo0 "$ELO0" --elo1 "$ELO1" --prior-pairs "$PRIOR_PAIRS")
fi

# Named for what writes it. The caller redirects this script's own stderr into
# a file of its own, and a shared name would have been cat reading and writing
# one file, which fails, and two later invocations overwriting the remarks
# this one captured.
"${estimate[@]}" > report.md 2> estimate-remarks.txt \
    || { echo "summarise.sh: the games could not be read" >&2
         cat estimate-remarks.txt >&2
         exit 1; }

cat report.md

# The same estimate asked three more ways. Their stderr is dropped rather than
# captured: it is the same remarks again, and the run above is the one that
# reports them.
trailer=$("${estimate[@]}" --trailer 2> /dev/null)
line="Performance compared to ${BASELINE} | $("${estimate[@]}" --line 2> /dev/null)"

# What the test decided, and the counts a batch after this one carries. Read
# out of the json rather than parsed back out of the report, so the two cannot
# disagree. Both are empty when this was not a sequential test, which is the
# `sprt` key being null: a caller chaining batches reads an empty verdict as
# nothing to chain rather than as a test that failed. The pipeline is not
# redirected into a variable, so pipefail sees an estimate that died here.
"${estimate[@]}" --json 2> /dev/null | python3 -c '
import json
import sys

sequential = json.load(sys.stdin)["sprt"] or {}
for key in ("verdict", "carried"):
    print("%s=%s" % (key, sequential.get(key, "")))
' > decided.txt

{
    echo "${CANDIDATE} (\`${CANDIDATE_SHA:0:8}\`) against ${BASELINE} (\`${BASELINE_SHA:0:8}\`),"
    echo "over ${#games[@]} of ${SHARDS} shards at ${TIME_CONTROL}."
    echo
    cat report.md
    echo
    echo "As the trailer for the commit that made the difference:"
    echo
    echo '```'
    echo "$trailer"
    echo '```'
    if [ -n "${PROVENANCE-}" ]; then
        echo
        echo "$PROVENANCE"
    fi
    echo
    echo "Both sides played on shared runners, whose clocks are not the same"
    echo "from one job to the next. That is noise in the figure above and not"
    echo "bias, because the two sides played every game against each other."
} >> "$GITHUB_STEP_SUMMARY"

cat estimate-remarks.txt >&2

{
    echo "line=${line}"
    cat decided.txt
} > "$outputs"
