# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

"""The tools a match is read with: the pooled estimate, the ccrl fit, the
terminations count and the book slice.

They are one package because they read one thing. What the tools share sits
beside them rather than inside one of them: `pgn` is how a fastchess pgn is
split into games, `elo` is the logistic model both estimators price a score
with, and the `--json` header every tool prints is built below. The pooled
estimate reads the terminations count as well, for the faults column of its
table, and that is the one tool that reads another.
"""

import json

__version__ = "0.1.0"

# The version of the --json shape, and the one thing every --json object says
# about itself. It is 1 because the shape is released: a tagged version is what
# another repository can pin, and a shape nobody can pin is not a contract.
# Fields are added from here on. None is removed, and none is given a new
# meaning under the name it already has. A change that cannot be made that way
# raises this number, and a reader that finds a number it does not know should
# say so rather than read the object anyway.
JSON_FORMAT = 1


def tool(command: str) -> dict[str, str]:
    """What produced a --json object, so a figure can be read back against the
    version of the tooling that produced it."""
    return {"name": "mache", "version": __version__, "command": command}


def document(command: str, fields: dict) -> dict:
    """A --json object: the format and what produced it first, then what the
    command has to say. Every tool builds its object here, so the two fields
    the contract rests on are written once and sit in the same place in each."""
    return {"format": JSON_FORMAT, "tool": tool(command), **fields}


def print_json(obj: dict) -> None:
    """The object as the --json modes print it. allow_nan=False rather than
    the default, so a figure that is not a number fails here rather than being
    written as NaN or Infinity, which no parser is required to read back."""
    print(json.dumps(obj, indent=2, allow_nan=False))
