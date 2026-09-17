#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

# Which openings this shard plays:
#
#     slice.sh <table> <book> <workdir> <pairs> <shards> <shard> <seed>
#
# The book is counted rather than written down, so a book that changed size
# cannot move every shard but the first onto its neighbour's openings. The
# table is asked rather than grepped, because what an opening is depends on
# the format: a pgn holds a game per opening and an epd a position a line.
#
# Prints `key=value` lines for the caller: the file and the format fastchess
# is given, how many openings the file holds, and the one this shard starts
# at. Remarks from the slice go to stderr, one to a line.
set -euo pipefail

usage="usage: slice.sh <table> <book> <workdir> <pairs> <shards> <shard> <seed>"
table=${1:?$usage}
book=${2?$usage}
workdir=${3:?$usage}
pairs=${4:?$usage}
shards=${5:?$usage}
shard=${6?$usage}
seed=${7:?$usage}

book_file=$("$table" file "$book")
book_format=$("$table" format "$book")
openings=$("$table" count "$book" "${workdir}/${book_file}") \
    || { echo "slice.sh: no openings in the book" >&2; exit 1; }

start=$(python3 -m mache.book_slice --openings "$openings" \
    --pairs "$pairs" --shards "$shards" --shard "$shard" --seed "$seed")

echo "book_file=${book_file}"
echo "book_format=${book_format}"
echo "openings=${openings}"
echo "start=${start}"
