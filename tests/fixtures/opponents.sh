#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

# An opponent table of one engine, written to the contract in
# actions/plan-ladder/README.md and used by the test that plays a match. It is
# the shortest table that honours the contract, and it is the worked example
# that contract otherwise lacks.
#
#     opponents.sh list                          the engines it can build
#     opponents.sh repository <engine>           where it is cloned from
#     opponents.sh build <engine> <pin> <binary> clone at the pin, build, put it there
#
# Stash rather than an engine written for this. A test needs an engine that
# answers uci and plays legal moves, which is most of a chess engine, and there
# is no reason to write one when a table of real engines is what this contract
# is for in the first place. It is here because it is the cheapest of them: one
# make, no toolchain beyond a c compiler, and about a second on a runner.
set -euo pipefail

ENGINE=stash
REPOSITORY=https://github.com/mhouppin/stash-bot.git

named() {
    if [ "${1:-}" != "$ENGINE" ]; then
        echo "opponents.sh: no engine named ${1:-}, this table has ${ENGINE}" >&2
        exit 1
    fi
}

build() {
    named "$1"
    local pin=$2 binary=$3 directory=.
    # thrown away however this ends, which set -e makes a trap rather than a
    # last line
    WORK=$(mktemp -d)
    trap 'rm -rf "$WORK"' EXIT
    # A pin that is not a whole sha is asked for as a tag. A bare name would
    # fetch a branch of that name just as happily, and a branch moves under
    # whatever the match said about the version it played.
    local ref="refs/tags/${pin}"
    if [ "${#pin}" = 40 ] && [ -z "${pin//[0-9a-f]/}" ]; then
        ref=$pin
    fi
    (
        cd "$WORK"
        git init -q .
        git remote add origin "$REPOSITORY"
        git fetch -q --depth 1 origin "$ref" \
            || { echo "opponents.sh: ${ENGINE} has no ${ref}" >&2; exit 1; }
        git checkout -q FETCH_HEAD
        # its makefile moved into src/ after v12, so the directory is looked
        # for rather than named
        if [ -f src/Makefile ]; then
            directory=src
        fi
        make -C "$directory" -j"$(nproc)" > /dev/null
        [ -f "${directory}/stash-bot" ] \
            || { echo "opponents.sh: the ${ENGINE} build left no binary" >&2; exit 1; }
        mv "${directory}/stash-bot" built
    )
    mkdir -p "$(dirname "$binary")"
    cp "${WORK}/built" "$binary"
}

case "${1:-}" in
    list) echo "$ENGINE" ;;
    repository) named "${2:-}"; echo "$REPOSITORY" ;;
    build)
        build "${2:?usage: opponents.sh build <engine> <pin> <binary>}" \
              "${3:?usage: opponents.sh build <engine> <pin> <binary>}" \
              "${4:?usage: opponents.sh build <engine> <pin> <binary>}" ;;
    *) echo "usage: opponents.sh list|repository|build" >&2; exit 1 ;;
esac
