#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

# The book table the actions use when a caller does not name one of its own.
# It is written to the contract in actions/setup/README.md like any other, so
# a repository that wants different openings writes its own table and passes
# its path as `book_table`. Nothing else changes when it does.
#
#     book_table.sh list                  the books it knows
#     book_table.sh pin                   the commit they are fetched at
#     book_table.sh file <book>           the file it plays as
#     book_table.sh format <book>         what fastchess reads that file as
#     book_table.sh count <book> <path>   how many openings that file holds
#     book_table.sh fetch <book> <dir>    download it at the pin, unzip it, check it
#     book_table.sh verify <book> <dir>   check one already there
#
# Both books are from official-stockfish/books, which is where most engine
# testing takes its openings. 8moves_v3 is balanced, and UHO_4060_v2 is
# unbalanced on purpose so that fewer games are drawn and a difference shows
# sooner. The files are the two the setup action caches.
set -euo pipefail

PIN=65815ccdbc7727cd4f6aee252ba8f67fb740e92f

# name, file, format, sha256 of the unzipped file
BOOKS="\
8moves_v3 8moves_v3.pgn pgn 5835239f88cc2c7511b177c32392a69f3ede21819cf0616f80a7f907cd21d17e
UHO_4060_v2 UHO_4060_v2.epd epd 36f2ec751ab78def6be1307430cbe2cd2ba65ade8d2aaae8f10e3df7d0ea83e1"

# Sets FILE, FORMAT and SHA256 for the book named, or refuses it.
named() {
    local name file format sha256
    while read -r name file format sha256; do
        if [ "$name" = "${1:-}" ]; then
            FILE=$file FORMAT=$format SHA256=$sha256
            return
        fi
    done <<< "$BOOKS"
    echo "book_table.sh: no book named ${1:-}, this table has $(cut -d' ' -f1 <<< "$BOOKS" | tr '\n' ' ')" >&2
    exit 1
}

checked() {
    local arrived
    arrived=$(sha256sum "$1" | cut -d' ' -f1)
    if [ "$arrived" != "$SHA256" ]; then
        echo "book_table.sh: ${FILE} is ${arrived}, not the ${SHA256} this table names" >&2
        exit 1
    fi
}

verify() {
    named "$1"
    if [ ! -r "${2}/${FILE}" ]; then
        echo "book_table.sh: ${2}/${FILE} is not there to check" >&2
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

# A pgn holds a game per opening and an epd a position a line, which is why
# counting belongs beside the format rather than in whatever is asking.
count() {
    named "$1"
    case "$FORMAT" in
        pgn) grep -c '^\[Event ' "$2" ;;
        epd) grep -c . "$2" ;;
    esac
}

case "${1:-}" in
    list) cut -d' ' -f1 <<< "$BOOKS" ;;
    pin) echo "$PIN" ;;
    file) named "${2:-}"; echo "$FILE" ;;
    format) named "${2:-}"; echo "$FORMAT" ;;
    count) count "${2:-}" "${3:?usage: book_table.sh count <book> <path>}" ;;
    fetch) fetch "${2:?usage: book_table.sh fetch <book> <dir>}" "${3:?usage: book_table.sh fetch <book> <dir>}" ;;
    verify) verify "${2:?usage: book_table.sh verify <book> <dir>}" "${3:?usage: book_table.sh verify <book> <dir>}" ;;
    *) echo "usage: book_table.sh list|pin|file|format|count|fetch|verify" >&2; exit 1 ;;
esac
