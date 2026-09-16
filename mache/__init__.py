# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

"""The tools a match is read with: the pooled estimate, the ccrl fit, the
terminations count and the book slice.

They are one package because they read one thing. How a fastchess pgn is split
into games is written down once, in `pgn`, and the three tools that read one
read it through there. The pooled estimate reads the terminations count as well,
for the faults column of its table.
"""

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
