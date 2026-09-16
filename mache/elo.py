# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

"""The logistic model both estimators price a score with, and the two figures
they agree on.

The rating fit and the pooled match estimate each turn a score into elo and
print an interval on it. They read one model and one confidence factor so that
a ± means the same thing under either tool, and they stop extrapolating at the
same distance so that a match or a gauntlet swept one way says the same bound
whichever read it.
"""

import math

LN10 = math.log(10)

# The 95% interval, in standard errors. Both tools print ±, so both read this
# rather than keeping a copy that could drift to a different scale under the
# same symbol.
CONFIDENCE = 1.96

# A result that went one way throughout puts no bound on the winner from the
# other side, so an implied rating, a fitted one and a pooled difference all
# stop this far out rather than running off to wherever a bracket ends.
MAX_ELO = 1200.0


def expected(difference: float) -> float:
    """The score the model expects of the stronger side of an elo difference."""
    return 1.0 / (1.0 + 10 ** (-difference / 400))


def difference(score: float) -> float:
    """The elo difference a score between nought and one points at, which is
    the model the other way round. A score of nought or of one has no
    difference: the model runs off to infinity there, so a caller says which
    side it ran off rather than asking."""
    return -400 * math.log10(1 / score - 1)
