#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

# Check that a book table knows the book a run asked for:
#
#     check_book.sh <table> <book>
#
# Checked before a runner has built anything, so a name with a typo in it
# costs a job that does nothing rather than one that has already built two
# engines. The table's `list` is the authority; see actions/setup/README.md
# for the contract a table answers to.
set -euo pipefail

usage="usage: check_book.sh <table> <book>"
table=${1:?$usage}
book=${2?$usage}

# Held rather than piped into grep, so a grep that leaves early cannot fail
# the caller under pipefail. -F and -x, so a box holding a metacharacter or
# nothing is an unknown name rather than a pattern.
known=$("$table" list)
if ! grep -Fxq -- "$book" <<< "$known"; then
    echo "check_book.sh: ${book} is not one of $(tr '\n' ' ' <<< "$known")" >&2
    exit 1
fi
