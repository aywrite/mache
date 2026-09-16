# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

"""How a fastchess pgn is picked apart, written down once.

The three tools that read a pgn read it the same way: split into games, and
each game's tags read from that game alone. A game truncated by an interrupted
match ends without a result and without a last move, and reading the file as a
whole would let it borrow the next game's tags. Reading a game at a time is
what stops that, and this module is where that is decided, so the tools agree
on what a game is without one of them owning the answer for the others.
"""

import re
from collections.abc import Iterator

# fastchess starts every game with its Event tag, so that is where one game
# ends and the next begins
RECORD = re.compile(r"^\[Event ", re.MULTILINE)
# a tag pair on a line of its own, as the pgn standard lays them out
TAG = re.compile(r'^\[([A-Za-z0-9_]+) "([^"]*)"\]', re.MULTILINE)
COMMENT = re.compile(r"\{([^{}]*)\}")


def games(text: str) -> Iterator[tuple[dict[str, str], str]]:
    """Each game of the pgn, as its tags and the text they were read from.

    A record with no players is not a game, so it is left out: the header a
    file starts with, or a record the match was interrupted before it wrote
    the players of, has nothing in it to count."""
    for record in RECORD.split(text)[1:]:
        tags = dict(TAG.findall(record))
        if tags.get("White") and tags.get("Black"):
            yield tags, record


def reason(record: str) -> str:
    """Why a game ended, as fastchess writes it: at the end of the comment on
    the last move. A game with no comment at all has no reason."""
    comments = COMMENT.findall(record)
    return comments[-1] if comments else ""
