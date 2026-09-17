#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

# A book table of one book, written to the contract in actions/setup/README.md
# and used by the smoke test that runs the action. It is the shortest table that
# honours the contract, and it is deliberately not a copy of the one the engine
# that consumes this repository has: what is being tested is that the action
# asks for what the contract says and nothing else.
#
#     books.sh list                  the books it knows
#     books.sh pin                   the commit they are fetched at
#     books.sh file <book>           the file it plays as
#     books.sh format <book>         what fastchess reads that file as
#     books.sh count <book> <path>   how many openings that file holds
#     books.sh fetch <book> <dir>    download it at the pin, unzip it, check it
#     books.sh verify <book> <dir>   check one already there
set -euo pipefail

PIN=65815ccdbc7727cd4f6aee252ba8f67fb740e92f
BOOK=8moves_v3
FILE=8moves_v3.pgn
FORMAT=pgn
SHA256=5835239f88cc2c7511b177c32392a69f3ede21819cf0616f80a7f907cd21d17e

named() {
    if [ "${1:-}" != "$BOOK" ]; then
        echo "books.sh: no book named ${1:-}, this table has ${BOOK}" >&2
        exit 1
    fi
}

checked() {
    local arrived
    arrived=$(sha256sum "$1" | cut -d' ' -f1)
    if [ "$arrived" != "$SHA256" ]; then
        echo "books.sh: ${FILE} is ${arrived}, not the ${SHA256} this table names" >&2
        exit 1
    fi
}

verify() {
    named "$1"
    if [ ! -r "${2}/${FILE}" ]; then
        echo "books.sh: ${2}/${FILE} is not there to check" >&2
        exit 1
    fi
    checked "${2}/${FILE}"
}

fetch() {
    named "$1"
    # thrown away however this ends, which set -e makes a trap rather than a
    # last line
    WORK=$(mktemp -d)
    trap 'rm -rf "$WORK"' EXIT
    curl -sSLf -o "${WORK}/book.zip" \
        "https://raw.githubusercontent.com/official-stockfish/books/${PIN}/${FILE}.zip"
    unzip -qo "${WORK}/book.zip" "$FILE" -d "$WORK"
    # checked before it is moved, so a run that fetched something else has
    # nothing to play rather than something to play
    checked "${WORK}/${FILE}"
    mkdir -p "$2"
    mv "${WORK}/${FILE}" "${2}/${FILE}"
}

case "${1:-}" in
    list) echo "$BOOK" ;;
    pin) echo "$PIN" ;;
    file) named "${2:-}"; echo "$FILE" ;;
    format) named "${2:-}"; echo "$FORMAT" ;;
    # a pgn holds a game per opening, which is why counting belongs beside the
    # format rather than in whatever is asking
    count) named "${2:-}"; grep -c '^\[Event ' "${3:?usage: books.sh count <book> <path>}" ;;
    fetch) fetch "${2:?usage: books.sh fetch <book> <dir>}" "${3:?usage: books.sh fetch <book> <dir>}" ;;
    verify) verify "${2:?usage: books.sh verify <book> <dir>}" "${3:?usage: books.sh verify <book> <dir>}" ;;
    *) echo "usage: books.sh list|pin|file|format|count|fetch|verify" >&2; exit 1 ;;
esac
