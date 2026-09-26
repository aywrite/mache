#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

# Fit a rating from a gauntlet's games and say where the engine placed:
#
#     summarise.sh <games-dir> <outputs-file>
#
# The caller sets ENGINE_NAME, CANDIDATE_SHA, LADDER_SPEC, RUNGS,
# TIME_CONTROL, RATING_LIST, SCALE, RATING_TIME_CONTROL and PROVENANCE.
#
# The table goes to stdout, so it is in the job's log as well as in the
# summary: the summary is read from the run's web page and nowhere else, and
# the artifacts expire. The step summary goes to GITHUB_STEP_SUMMARY and the
# remarks to stderr, one to a line.
set -euo pipefail

usage="usage: summarise.sh <games-dir> <outputs-file>"
dir=${1:?$usage}
outputs=${2:?$usage}

mapfile -t games < <(find "$dir" -name games.pgn 2>/dev/null | sort)
if [ "${#games[@]}" -eq 0 ]; then
    echo "summarise.sh: no rung of attempt ${GITHUB_RUN_ATTEMPT} uploaded any games. Rerunning the failed jobs alone leaves the games on the attempt that played them, so rerun all of them." >&2
    exit 1
fi
cat "${games[@]}" > gauntlet.pgn

# How the games ended, counted from the games. Games lost to a crash or the
# clock stay in the fit, because choosing what to count after seeing it is not
# a measurement; the counts sit beside the estimate.
if python3 -m mache.match_terminations gauntlet.pgn \
        > terminations.txt 2> faults.txt; then
    cat faults.txt >&2
else
    echo "The games could not be counted, the block below is incomplete" >&2
    cat faults.txt >&2
fi

# the estimate's remarks (a rung that played no games, a fit the pairings
# disagree with) come back on stderr
python3 -m mache.rating_estimate --scale "$SCALE" \
    gauntlet.pgn "$ENGINE_NAME" "$LADDER_SPEC" > table.md 2> notes.txt \
    || { cat notes.txt >&2; exit 1; }
cat table.md

# asked for again rather than cut out of the table, so a change to the table's
# layout cannot quietly change what is published
line=$(python3 -m mache.rating_estimate --scale "$SCALE" \
    gauntlet.pgn "$ENGINE_NAME" "$LADDER_SPEC" --line 2> /dev/null)

{
    echo "### Rating estimate"
    echo
    echo "\`${CANDIDATE_SHA:0:8}\` at ${TIME_CONTROL} against engines with a"
    echo "rating on the ${RATING_LIST} list, ${#games[@]} of ${RUNGS} rungs played."
    echo
    cat table.md
    # one alert holding every remark: one alert each renders as the first
    # alert with the rest of the markup showing through as text
    if [ -s notes.txt ]; then
        echo
        echo "> [!WARNING]"
        sed 's/^/> /' notes.txt
    fi
    echo
    echo "How the games ended:"
    echo
    echo '```'
    cat terminations.txt
    echo '```'
    if [ -n "${PROVENANCE-}" ]; then
        echo
        echo "$PROVENANCE"
    fi
    echo
    echo "The opponents were rated${RATING_TIME_CONTROL:+ at ${RATING_TIME_CONTROL}} on other hardware, so the"
    echo "placement carries a systematic error the game count does not"
    echo "describe. It is worth about a hundred points, and no number of games"
    echo "reduces it."
} >> "$GITHUB_STEP_SUMMARY"

cat notes.txt >&2

echo "line=Estimated rating | ${line}" > "$outputs"
