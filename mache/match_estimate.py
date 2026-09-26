# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

"""Pool the shards of a match into one estimate.

A match of any size is more games than one job can play inside its timeout, so
the games are played by several jobs at once, each with a slice of the opening
book of its own, and this reads them back as one match. Every shard is a pgn,
and no two shards share an opening, so the games pool as if one match had
played them.

fastchess prints an estimate of its own, but only over the games the one
process played. It cannot see the other shards, so the pooled figure is worked
out here from the games themselves.

The error bar is measured over pairs and not over games. With `-repeat` the two
games of a round are the same opening with the colours reversed, so they are
one draw and not two, and treating them as two would understate the spread. The
pair is also what a shard that ran out of clock can leave half of, so the games
it left over are counted and said, and kept out of the pair statistics.

With `--elo0` and `--elo1` the same pairs are read a second way, as a
sequential test. One run of the workflow is a batch: its shards play slices
chosen in advance and nothing is looked at until they are all in. The pairs of
the batch are added to the pairs the earlier batches of the same test played,
and the log likelihood ratio over all of them is judged against Wald's bounds.
Looking only at batch boundaries is what leaves the bounds meaning what they
say.

The report goes to stdout for the run summary. `--line` prints the one line the
release notes carry and `--trailer` the trailer a commit does. `--json` prints
the whole of it as data, for a reader that is not a person; its format says
which shape that is. Anything worth an alert goes to stderr, so
the workflow can raise it from there rather than parsing it back out of the
report.
"""

import argparse
import json
import math
import re
import sys
from collections import Counter
from itertools import pairwise
from pathlib import Path

from . import JSON_FORMAT, __version__, match_terminations, rating_estimate, tool

# The game split and the tag parse the rest of this tooling reads a fastchess
# pgn with. Round is wanted here and by nothing else: fastchess writes it on
# every game, and with -repeat the two games of a round share an opening.
RECORD = rating_estimate.RECORD
TAG = rating_estimate.TAG

LN10 = math.log(10)
# Normalized elo is the score's distance from a half in standard deviations of
# one game, times this. The scale is chosen so that where no game is drawn and
# the two games of a pair are unrelated, a small difference reads the same in
# normalized elo as in logistic elo. It is the constant fastchess and fishtest
# use, so the figure here is the one they print for the same pairs.
NELO = 800 / LN10
# the 95% interval, in standard errors, defined beside the other ± this tooling
# prints so that the two cannot drift apart under one symbol
CONFIDENCE = rating_estimate.CONFIDENCE
# A match that went one way throughout bounds the difference from one side
# only. This is as far out as it is worth reading, and is where the rating
# estimate stops its own extrapolation.
MAX_ELO = rating_estimate.MAX_IMPLIED

# what a result tag is worth to the player of the white pieces
RESULTS = {"1-0": 1.0, "1/2-1/2": 0.5, "0-1": 0.0}

# the shard index, as the artifact names carry it
SHARD = re.compile(r"shard-(\d+)")

# the five scores a pair can end on, from the candidate's point of view
PENTANOMIAL = (0.0, 0.5, 1.0, 1.5, 2.0)
# the same five as a fraction of the two points a pair is worth, which is what
# the sequential test weighs
PAIR = tuple(score / 2 for score in PENTANOMIAL)

# The error rates the sprt verdicts are accepted at: a wrong "passed" one run
# in twenty, a wrong "failed" the same. They are what the verdicts mean, so
# they are fixed here rather than asked for.
ALPHA = BETA = 0.05
# Wald's bounds on the log likelihood ratio at those rates, -2.94 and +2.94
LOWER = math.log(BETA / (1 - ALPHA))
UPPER = math.log((1 - BETA) / ALPHA)
# a count of nought has no logarithm, so it is nudged off nought first, which
# is what fastchess does with the same counts
REGULARISED = 1e-3
# As many pairs in one bin as a carried test is allowed to claim, which is the
# eight digits the workflow's box takes. Past about a hundred million million
# the fit's bisection reaches the end of its interval and divides by nought,
# and no match has played a millionth of that.
MAX_PRIOR = 99_999_999
# As far out as a hypothesis is worth asking about. Past a thousand elo the
# expected score rounds to nought or one, which leaves the distribution nothing
# to fit and the bisection no interval to run in.
MAX_HYPOTHESIS = 1000
# The same for a hypothesis in normalized elo. Past it the fit has to put
# nearly all of the distribution on scores the pairs almost never reached,
# and the arithmetic cannot meet the condition to the precision it is held
# to. Tests are run at a few normalized elo, so this is nowhere near a bound
# anyone asks for.
MAX_NORMALIZED = 100

# The two ways a sequential test can state its hypotheses. Logistic reads them
# as the elo the score implies, normalized as the difference in normalized elo.
MODELS = ("logistic", "normalized")
# How finely each interval of possible spreads is first scanned when the
# normalized fit looks for its maximum, before the scan is refined. See
# likeliest_normalized.
SPREADS = 40
# How closely a fitted distribution has to meet the conditions it was fitted
# to, and how many Newton steps it is given to get there. A fit that does not
# is refused rather than used.
CONDITIONS = 1e-12
MAX_STEPS = 200


def read_games(text: str, candidate: str) -> tuple[dict[str, list[float]], int]:
    """The candidate's score in each finished game of one shard, by round.

    The colours are read from the tags rather than assumed, since `-repeat`
    plays the second game of every round the other way round. A game with no
    result is one the match was stopped in the middle of; it is counted and
    left out."""
    rounds: dict[str, list[float]] = {}
    unfinished = 0
    for record in RECORD.split(text)[1:]:
        tags = dict(TAG.findall(record))
        white, black, result = tags.get("White"), tags.get("Black"), tags.get("Result")
        if not (white and black) or candidate not in (white, black):
            continue
        if result not in RESULTS:
            unfinished += 1
            continue
        score = RESULTS[result] if white == candidate else 1 - RESULTS[result]
        rounds.setdefault(tags.get("Round", ""), []).append(score)
    return rounds, unfinished


# Every move fastchess writes carries a comment, a played one holding what the
# engine reported and a book one holding the word `book`. So the comments are
# the moves in order, and which side made one is its place in that order.
COMMENT = re.compile(r"\{([^}]*)\}")
# the seconds the move took, which fastchess puts straight after the eval
SPENT = re.compile(r"^\S+ (\d+(?:\.\d+)?)s")
# what the clock had left after it, and what the search visited
LEFT = re.compile(r"\btl=(\d+(?:\.\d+)?)s")
VISITED = re.compile(r"\bn=(\d+)")

# How far apart the node counts may be for the rate to read as a speed. Two
# sides that prune differently do not search the same tree, and a node is not
# the same unit on each, so past this the rate compares trees.
LIKE_FOR_LIKE = (0.9, 1.1)


class Instruments:
    """What one side's clock and search did, added up over its moves.

    This is the third thing a suspicious result is read against, beside the
    score and the terminations: a difference that is really one side being
    given more time, or searching more nodes for it, shows here and nowhere
    else. It is counted from the games rather than from a result block so
    that it pools across shards the way the estimate does."""

    def __init__(self) -> None:
        self.moves = 0
        self.nodes = 0
        self.seconds = 0.0
        # the tightest the clock ever got, which is where a loss on time
        # would have come from
        self.least_left: float | None = None

    def add(self, comment: str) -> None:
        visited, spent = VISITED.search(comment), SPENT.match(comment)
        if not visited:
            # a book move, which the engine did not think about
            return
        self.moves += 1
        self.nodes += int(visited.group(1))
        if spent:
            self.seconds += float(spent.group(1))
        if left := LEFT.search(comment):
            remaining = float(left.group(1))
            if self.least_left is None or remaining < self.least_left:
                self.least_left = remaining

    def pool(self, other: "Instruments") -> None:
        self.moves += other.moves
        self.nodes += other.nodes
        self.seconds += other.seconds
        if other.least_left is not None and (
            self.least_left is None or other.least_left < self.least_left
        ):
            self.least_left = other.least_left

    @property
    def nps(self) -> float:
        return self.nodes / self.seconds if self.seconds else 0.0


def read_instruments(text: str, candidate: str) -> dict[str, Instruments]:
    """Each side's clock and search over one shard's games, by name.

    The side is read from the tags and the order of the moves rather than
    assumed: `-repeat` plays the second game of every round the other way
    round, so a side is an engine and not a colour."""
    found: dict[str, Instruments] = {}
    for record in RECORD.split(text)[1:]:
        tags = dict(TAG.findall(record))
        white, black = tags.get("White"), tags.get("Black")
        if not (white and black) or candidate not in (white, black):
            continue
        # The moves, which start after the blank line that ends the tags.
        # The last `]` is simpler and is what this read before, but a comment
        # holding one cuts the game short there and hands every move after it
        # to the other side, since the side is the position in the order.
        split = re.split(r"\n[ \t]*\n", record, maxsplit=1)
        moves = split[1] if len(split) == 2 else ""
        for number, comment in enumerate(COMMENT.findall(moves)):
            side = white if number % 2 == 0 else black
            found.setdefault(side, Instruments()).add(comment)
    return found


def pair_up(rounds: dict[str, list[float]]) -> tuple[list[float], int]:
    """The pair scores of one shard, out of two, and the games left over.

    A round holds the two games of one opening, so a round with both of them
    is a pair. A shard stopped by the clock in the middle of a round leaves
    one game, which counts in the score and in nothing the pair is the unit
    of."""
    scores, unpaired = [], 0
    for _, games in sorted(rounds.items()):
        for index in range(0, len(games) - 1, 2):
            scores.append(games[index] + games[index + 1])
        if len(games) % 2:
            unpaired += 1
    return scores, unpaired


class Shard:
    """One shard's games, and how they ended."""

    def __init__(self, name: str, text: str, candidate: str):
        self.name = name
        # the name fastchess played it under, so the report can order the
        # sides the same way round whatever they are called
        self.candidate = candidate
        found = SHARD.search(name)
        self.index = int(found.group(1)) if found else None
        rounds, self.unfinished = read_games(text, candidate)
        self.games = [score for scores in rounds.values() for score in scores]
        self.pairs, self.unpaired = pair_up(rounds)
        totals, _ = match_terminations.count(text)
        self.faults = sum(totals[ending] for ending in match_terminations.FAULTS)
        self.instruments = read_instruments(text, candidate)

    @property
    def points(self) -> float:
        return sum(self.games)

    @property
    def percent(self) -> float:
        return 100 * self.points / len(self.games) if self.games else 0.0


class Estimate:
    """What the games say the difference is, and how far out that could be.

    The figure and the interval are both read off the pairs, so that the two
    describe the same games. A shard the clock stopped can leave a game with no
    partner, and such a game is in the score the table prints and in nothing
    else: taking the figure from every game and the interval from the pairs
    alone would let one won game with no partner move the estimate while
    leaving the spread untouched, which reads as a difference measured exactly.

    The pair score, as a fraction of the two points a pair is worth, is turned
    into elo with the logistic model the rest of this tooling uses,
    `elo = -400 log10(1/p - 1)`. The variance of the pair scores divided by the
    number of pairs is the variance of that fraction, and its square root is
    the standard error. The derivative of the model at the score,
    `400 / (ln 10 p (1 - p))`, carries that into elo, and 1.96 of them is the
    95% interval.

    A score of nought or of one has no elo: the model runs off to infinity
    there, so the estimate is bounded on one side and says so instead. A match
    with no complete pair has no interval either, which is the same answer as
    not having measured. An interval that fell back to a modelled spread is
    marked, since it is a different claim from a measured one.

    Beside it is the difference in normalized elo. Logistic elo reads a score,
    and how far a given improvement moves the score depends on how often the
    games are drawn, so the same change reads as fewer elo on a drawish book or
    at a long time control. Normalized elo divides the distance from a half by
    the spread of the pairs instead, which makes it a measure of how clearly
    the games tell the two sides apart. Two runs on different books or at
    different time controls can be compared in it, and the games a test needs
    to settle on it barely depend on the draw rate.

    The spread of one game is taken as the spread of a pair times the square
    root of two, `(p - 1/2) / sqrt(2 var) * 800 / ln 10`. Its margin comes
    from the same interval on the score, which with the spread held where it
    was measured is `1.96 * 800 / ln 10 / sqrt(2 pairs)`: it depends on the
    number of pairs and on nothing else."""

    def __init__(self, points: float, games: int, pair_scores: list[float]):
        self.games = games
        self.pairs = len(pair_scores)
        # over every game, including any the pairing left over, which is what
        # the shard table and the score line report
        self.score = points / games if games else 0.0
        # over the pairs, which is what the estimate is read from
        self.paired = 0.0
        self.elo = 0.0
        self.margin: float | None = None
        self.low, self.high = -math.inf, math.inf
        self.los = 0.5
        self.bounded = ""
        # set when the pairs showed no spread and the interval falls back to
        # a modelled one, which is a different claim from a measured interval
        self.modelled = False
        # the difference in normalized elo, where there is a spread to
        # normalize by
        self.nelo: float | None = None
        self.nelo_margin: float | None = None

        if not games or not pair_scores:
            self.bounded = "not measured"
            return

        self.paired = sum(pair_scores) / (2 * self.pairs)

        if self.paired <= 0.0 or self.paired >= 1.0:
            above = self.paired >= 1.0
            self.elo = MAX_ELO if above else -MAX_ELO
            self.bounded = f"above +{MAX_ELO:.0f}" if above else f"below -{MAX_ELO:.0f}"
            self.low = self.elo if above else -math.inf
            self.high = math.inf if above else self.elo
            self.los = 1.0 if above else 0.0
            return

        variance = (
            sum((score / 2 - self.paired) ** 2 for score in pair_scores) / self.pairs
        )
        # Every pair scoring the same leaves no wobble to measure, which is not
        # the same as there being none, so fall back to the wobble the score
        # would have if the two games of a pair were unrelated, as the rating
        # estimate falls back to a modelled spread for the same reason. A
        # single pair is that case too: one of anything has no spread.
        if variance == 0.0:
            variance = self.paired * (1 - self.paired) / 2
            self.modelled = True
        error = math.sqrt(variance / self.pairs)

        self.elo = -400 * math.log10(1 / self.paired - 1)
        slope = 400 / (LN10 * self.paired * (1 - self.paired))
        self.margin = CONFIDENCE * error * slope
        self.low, self.high = self.elo - self.margin, self.elo + self.margin
        self.los = 0.5 * (1 + math.erf((self.paired - 0.5) / (error * math.sqrt(2))))
        self.nelo = (self.paired - 0.5) / math.sqrt(2 * variance) * NELO
        self.nelo_margin = CONFIDENCE * NELO / math.sqrt(2 * self.pairs)

    def __str__(self) -> str:
        if self.bounded == "not measured":
            return f"{100 * self.score:.1f}% score ({self.games} games)"
        if self.margin is None:
            return f"{self.bounded} Elo ({self.games} games)"
        return f"{round(self.elo):+d} ±{round(self.margin)} Elo ({self.games} games)"


def expected_score(elo: float) -> float:
    """The score the logistic model expects from an elo difference."""
    return 1 / (1 + 10 ** (-elo / 400))


def likeliest(observed: list[float], mean: float) -> list[float]:
    """The distribution over the five pair scores that is likeliest to have
    produced `observed` while averaging `mean`.

    Proposition 1.1 of Van den Bergh's note on the generalized likelihood
    ratio, which is what fastchess solves for the same purpose: there is one
    theta in (-1/(1 - s), 1/s) with
    `sum_i phat_i (a_i - s) / (1 + theta (a_i - s)) = 0`, and
    `p_i = phat_i / (1 + theta (a_i - s))` is the distribution. That sum falls
    from plus infinity to minus infinity across the interval, so a bisection
    finds the root. fastchess stops at 1e-3 and this runs to the last bit,
    which changes nothing either way: the sum being solved is the derivative
    of the ratio in theta, so the ratio is flat where the root is."""
    low, high = -1 / (PAIR[-1] - mean), -1 / (PAIR[0] - mean)
    while True:
        theta = (low + high) / 2
        if theta <= low or theta >= high:
            break
        slope = sum(
            p * (a - mean) / (1 + theta * (a - mean)) for a, p in zip(PAIR, observed)
        )
        if slope > 0:
            low = theta
        else:
            high = theta
    return [p / (1 + theta * (a - mean)) for a, p in zip(PAIR, observed)]


def with_moments(
    observed: list[float], mean: float, spread: float, start: tuple[float, float]
) -> tuple[float, list[float], tuple[float, float]] | None:
    """The distribution over the five pair scores that is likeliest to have
    produced `observed` while having this mean and this standard deviation, as
    (its log likelihood per pair, the distribution, the multipliers that gave
    it). None where no distribution with every score possible has them.

    Both conditions are linear in the distribution once the mean is fixed, so
    this is empirical likelihood with two moment conditions: the likelihood is
    concave and the conditions cut a flat slice through the simplex, so there
    is one maximum and nothing else to find. With `g_i = (a_i - m,
    (a_i - m)^2 - s^2)` it is `p_i = phat_i / (1 + lambda . g_i)`, where lambda
    minimises the convex `-sum_i phat_i log(1 + lambda . g_i)`. Newton's method
    finds it, halving any step that would leave the region where every
    `1 + lambda . g_i` is positive or that would not go downhill.

    Such a distribution exists exactly when nought is inside the convex hull
    of the five g_i. They lie on a parabola, so that is the spread lying above
    the chord through the two scores either side of the mean and below the
    chord through the two ends, which is what the first lines check."""
    if not 0 < mean < 1:
        return None
    below = max(a for a in PAIR if a <= mean)
    above = min(a for a in PAIR if a >= mean)
    if not (mean - below) * (above - mean) < spread**2 < mean * (1 - mean):
        return None
    moments = [(a - mean, (a - mean) ** 2 - spread**2) for a in PAIR]

    def dual(first: float, second: float) -> float:
        total = 0.0
        for p, (x, y) in zip(observed, moments):
            inside = 1 + first * x + second * y
            if inside <= 0:
                return math.inf
            total -= p * math.log(inside)
        return total

    first, second = start
    if dual(first, second) == math.inf:
        first = second = 0.0
    value = dual(first, second)
    # Stopped on the conditions themselves rather than on the likelihood,
    # which a score seen almost never barely moves while the fit is still
    # wrong about it. At the minimum the fitted distribution sums to one and
    # has the mean and the spread asked for.
    for _ in range(MAX_STEPS):
        fitted = [
            p / (1 + first * x + second * y) for p, (x, y) in zip(observed, moments)
        ]
        g1 = -sum(q * x for q, (x, _) in zip(fitted, moments))
        g2 = -sum(q * y for q, (_, y) in zip(fitted, moments))
        if abs(sum(fitted) - 1) < CONDITIONS and max(abs(g1), abs(g2)) < CONDITIONS:
            return (
                sum(p * math.log(q) for p, q in zip(observed, fitted)),
                fitted,
                (first, second),
            )
        h11 = h12 = h22 = 0.0
        for p, q, (x, y) in zip(observed, fitted, moments):
            h11 += q * q / p * x * x
            h12 += q * q / p * x * y
            h22 += q * q / p * y * y
        determinant = h11 * h22 - h12 * h12
        if not determinant > 0:
            break
        step1 = -(h22 * g1 - h12 * g2) / determinant
        step2 = -(h11 * g2 - h12 * g1) / determinant
        # Halved while it would leave the region or climb. Near the minimum
        # the dual is flat to within its own rounding, so a step that climbs
        # by no more than that is taken: refusing it would stop the fit short
        # of conditions a full step meets.
        scale = 1.0
        while scale > 1e-20:
            trial = dual(first + scale * step1, second + scale * step2)
            if trial <= value + 1e-14 * (1 + abs(value)):
                break
            scale /= 2
        else:
            break
        first, second, value = first + scale * step1, second + scale * step2, trial
    return None


def feasible_spreads(t: float) -> list[tuple[float, float]]:
    """The spreads a distribution over the five pair scores can have while its
    mean is `1/2 + t s`, as open intervals.

    with_moments can meet a mean m and a spread s exactly when s squared lies
    below `m (1 - m)` and above `(m - a_k)(a_(k+1) - m)`, where a_k and
    a_(k+1) are the scores either side of m. With `m = 1/2 + t s` the first is
    `s < 1 / (2 sqrt(1 + t^2))`, and each of the second turns over where a
    quadratic in s has a root. Those roots, and the spreads at which the mean
    crosses a score, cut the range into pieces on which the answer does not
    change, so each piece is tried once at its middle."""
    top = 0.5 / math.sqrt(1 + t * t)
    cuts = {0.0, top}
    for below, above in pairwise(PAIR):
        # s^2 (1 + t^2) + t s (1 - a_k - a_(k+1)) + (1/2 - a_k)(1/2 - a_(k+1))
        a, b, c = 1 + t * t, t * (1 - below - above), (0.5 - below) * (0.5 - above)
        discriminant = b * b - 4 * a * c
        if discriminant >= 0:
            for sign in (-1, 1):
                cuts.add((-b + sign * math.sqrt(discriminant)) / (2 * a))
    if t:
        cuts.update((score - 0.5) / t for score in PAIR)
    cuts = sorted(cut for cut in cuts if 0 <= cut <= top)
    pieces = []
    for low, high in pairwise(cuts):
        middle = (low + high) / 2
        mean = 0.5 + t * middle
        below = max(a for a in PAIR if a <= mean)
        above = min(a for a in PAIR if a >= mean)
        if high > low and (mean - below) * (above - mean) < middle**2 < mean * (
            1 - mean
        ):
            pieces.append((low, high))
    return pieces


def likeliest_normalized(observed: list[float], t: float) -> tuple[float, list[float]]:
    """The distribution over the five pair scores that is likeliest to have
    produced `observed` while being `t` of its own standard deviations above a
    half, as (its log likelihood per pair, the distribution).

    The condition `mean - 1/2 = t sd` is not linear in the distribution, so
    the fit is split in two. For a given spread s the mean is `1/2 + t s`,
    both conditions are linear, and with_moments finds the one maximum there.
    What is left is one number, the spread. feasible_spreads says which
    spreads a distribution can have, and within each such interval the best
    is found by a scan refined by golden section. The likelihood falls away to
    nothing at the ends of every interval, where the fit has to empty a score
    the counts say happens, so the maximum is inside one of them.

    Van den Bergh's note on normalized elo, and fastchess after it, solve the
    same maximum by a fixed point iteration instead. That agrees with this
    where it converges, and it does not always converge: from some counts it
    reaches a step with no root to take, or cycles. Split this way, the part
    that has to be solved exactly is convex and the rest is a search along a
    line, so each half can be checked on its own."""
    tried: dict[float, tuple[float, list[float]] | None] = {}
    multipliers = (0.0, 0.0)

    def fit(spread: float) -> float:
        nonlocal multipliers
        if spread not in tried:
            found = with_moments(observed, 0.5 + t * spread, spread, multipliers)
            if found is not None:
                multipliers = found[2]
                tried[spread] = found[:2]
            else:
                tried[spread] = None
        found = tried[spread]
        return -math.inf if found is None else found[0]

    ratio = (math.sqrt(5) - 1) / 2
    for low, high in feasible_spreads(t):
        multipliers = (0.0, 0.0)
        scan = [low + (high - low) * (step + 0.5) / SPREADS for step in range(SPREADS)]
        values = [fit(spread) for spread in scan]
        best = max(range(SPREADS), key=values.__getitem__)
        if values[best] == -math.inf:
            continue
        left_end = scan[best - 1] if best else low
        right_end = scan[best + 1] if best + 1 < SPREADS else high
        left = right_end - ratio * (right_end - left_end)
        right = left_end + ratio * (right_end - left_end)
        for _ in range(100):
            if fit(left) > fit(right):
                right_end, right = right, left
                left = right_end - ratio * (right_end - left_end)
            else:
                left_end, left = left, right
                right = left_end + ratio * (right_end - left_end)
    found = [spread for spread in tried if tried[spread] is not None]
    if not found:
        raise ArithmeticError(f"no distribution is {t} of its spread above a half")
    return tried[max(found, key=lambda spread: tried[spread][0])]


def normalized_t(nelo: float) -> float:
    """A difference in normalized elo as the distance from a half, in standard
    deviations of a pair's score, that the fit is asked for. A pair's spread
    is a game's divided by the square root of two, which is where that factor
    comes from."""
    return math.sqrt(2) * nelo / NELO


def log_likelihood_ratio(
    counts: list[int], elo0: float, elo1: float, model: str = "logistic"
) -> float:
    """How much likelier the pairs are under elo1 than under elo0.

    The generalized log likelihood ratio of Van den Bergh's note under the
    logistic model, written from the note and checked against fastchess: for
    the same pairs the number here is the number it prints. The counts are the
    pairs by what the candidate scored in them, in PENTANOMIAL order, so the
    shared pairs and the doubly drawn ones are one bin already, which is the
    bin fastchess merges them into.

    Under the normalized model the hypotheses are differences in normalized
    elo, and each is fitted by likeliest_normalized rather than by a mean. The
    ratio is the difference between the two fitted log likelihoods, which is
    the same quantity the logistic model works out term by term."""
    counted = [count or REGULARISED for count in counts]
    total = sum(counted)
    observed = [count / total for count in counted]
    if model == "normalized":
        under0, _ = likeliest_normalized(observed, normalized_t(elo0))
        under1, _ = likeliest_normalized(observed, normalized_t(elo1))
        return total * (under1 - under0)
    under0 = likeliest(observed, expected_score(elo0))
    under1 = likeliest(observed, expected_score(elo1))
    return total * sum(
        phat * (math.log(one) - math.log(zero))
        for phat, zero, one in zip(observed, under0, under1)
    )


def read_prior(spec: str) -> list[int]:
    """The pairs the earlier batches of a test played, by what the candidate
    scored in them, as the summary of the last one printed them. An empty spec
    is a first batch, which has none behind it."""
    if not spec.strip():
        return [0] * len(PENTANOMIAL)
    counts = []
    for field in spec.split(","):
        field = field.strip()
        if not field.isdecimal():
            raise ValueError(f"{spec!r} is not {len(PENTANOMIAL)} whole numbers")
        counts.append(int(field))
    if len(counts) != len(PENTANOMIAL):
        raise ValueError(f"{spec!r} is not {len(PENTANOMIAL)} whole numbers")
    if max(counts) > MAX_PRIOR:
        raise ValueError(f"{max(counts)} pairs in one score is more than a match plays")
    return counts


def number(value: float) -> str:
    """A hypothesis or a bound, carrying the decimals only when it has any."""
    return str(round(value)) if float(value).is_integer() else f"{value:.2f}"


class Sprt:
    """The sequential test over the pooled pairs, and the verdict it reaches.

    A batch is one run of the match: the shards play slices settled in
    advance, and the games are read once they are all in rather than as they
    arrive. The pairs of this batch are added to the pairs the earlier batches
    of the same test played, and the ratio over all of them is what the bounds
    are read against, so every look is at a batch boundary and the error rates
    the bounds stand for are the ones the verdict carries.

    What a batch carries forward is its pairs and not its ratio. The ratio is a
    generalized one: the distribution over the five pair scores is fitted to
    the pairs it is read against, under each hypothesis in turn, so a ratio
    worked out per batch fits a distribution per batch and the sum of those is
    not the ratio of the pairs together. Simulated over the default [0, 10]
    with a true difference between the two, eight batches of 250 pairs reach
    different verdicts the two ways about one test in twenty. The counts add
    exactly, so the counts are what is carried.

    The pair is the unit, as it is for the estimate, so a game a shard left
    without a partner is out of this too.

    The model says what the hypotheses are differences in: logistic elo, or
    normalized elo. The counts are the same under either, so a test could be
    carried on under the other model, but the error rates hold only for a
    test judged under the one it started with."""

    def __init__(
        self,
        pairs: list[float],
        elo0: float,
        elo1: float,
        prior: list[int] | None = None,
        model: str = "logistic",
    ):
        if model not in MODELS:
            raise ValueError(f"the model is one of {', '.join(MODELS)}, not {model}")
        self.elo0, self.elo1, self.model = elo0, elo1, model
        counted = Counter(pairs)
        self.batch = [counted[score] for score in PENTANOMIAL]
        self.prior = list(prior) if prior else [0] * len(PENTANOMIAL)
        if len(self.prior) != len(PENTANOMIAL):
            raise ValueError(f"the prior is {len(PENTANOMIAL)} counts, one per score")
        self.counts = [
            played + before for played, before in zip(self.batch, self.prior)
        ]
        self.llr = (
            log_likelihood_ratio(self.counts, elo0, elo1, model)
            if sum(self.counts)
            else 0.0
        )
        if self.llr >= UPPER:
            self.verdict = "passed"
        elif self.llr <= LOWER:
            self.verdict = "failed"
        else:
            self.verdict = "inconclusive"

    @property
    def hypotheses(self) -> str:
        # The logistic form is the one every line and trailer carried before
        # there was a choice, so it stays as it was and the normalized one
        # names itself
        unit = " nElo" if self.model == "normalized" else ""
        return f"[{number(self.elo0)}, {number(self.elo1)}]{unit}"

    @property
    def unit(self) -> str:
        """What the hypotheses are differences in, as a sentence says it."""
        return "normalized elo" if self.model == "normalized" else "elo"

    @property
    def bounds(self) -> str:
        return f"({number(LOWER)}, {number(UPPER)})"

    @property
    def estimate(self) -> Estimate:
        """What the pairs of the whole test say the difference is.

        The report states the batch's own estimate, since the batch is the
        match that was just played, and the trailer states this one, so that
        its figure, its interval and its game count are all read from the
        pairs the verdict rests on. On a first batch the two are the same
        measurement."""
        scores = [
            score
            for score, count in zip(PENTANOMIAL, self.counts)
            for _ in range(count)
        ]
        return Estimate(sum(scores), 2 * len(scores), scores)

    @property
    def carried(self) -> str:
        """The pairs of the test so far, in the shape the next batch takes
        them in."""
        return ",".join(str(count) for count in self.counts)

    def __str__(self) -> str:
        return (
            f"SPRT {self.hypotheses} {self.verdict}, LLR {self.llr:.2f} {self.bounds}"
        )


def sequential(sprt: Sprt) -> str:
    """The sprt reading for the report, and what its verdict means."""
    means = {
        "passed": (
            f"The pairs favour a difference of about {number(sprt.elo1)}"
            f" {sprt.unit} over one of about {number(sprt.elo0)}, at a five"
            " percent error rate each way. That is the hypothesis the test prefers and not a"
            " floor under the difference: the estimate above is what the games"
            " measured."
        ),
        "failed": (
            f"The pairs favour a difference of about {number(sprt.elo0)}"
            f" {sprt.unit} over one of about {number(sprt.elo1)}, at a five"
            " percent error rate each way. That does not show the candidate is weaker, only"
            " that the games did not favour the larger difference."
        ),
        "inconclusive": (
            "The games so far settle it neither way. Launch another batch with"
            f" prior_pairs set to {sprt.carried}"
            + (
                " and the normalized model again."
                if sprt.model == "normalized"
                else "."
            )
        ),
    }
    # the table above is this batch, so a test carrying earlier batches has a
    # second figure, and the trailer states that one rather than the table's
    pooled = sprt.estimate
    carried = (
        ""
        if not sum(sprt.prior)
        else (
            f" Over all of them the difference is"
            f" {round(pooled.elo):+d} ±{round(pooled.margin)} elo,"
            " which is the figure the trailer carries."
            if pooled.margin is not None
            else " The pairs of the test together leave no interval to state."
        )
    )
    return (
        f"SPRT {sprt.hypotheses} {sprt.verdict}. The log likelihood ratio over"
        f" the {sum(sprt.counts)} pairs of the test ({sum(sprt.batch)} from this"
        f" batch and {sum(sprt.prior)} from the batches before it) is"
        f" {sprt.llr:.2f} against bounds of {sprt.bounds}.{carried}"
        f" {means[sprt.verdict]}"
    )


def trailer(
    estimate: Estimate, tc: str, baseline: str, sprt: Sprt | None = None
) -> str:
    """The result as the Elo trailer a commit carries, in the shape the
    commit-msg hook accepts. A match with no estimate to state says so rather
    than quoting a number it does not have, though it still names the sprt
    verdict when there was one. An sprt names its verdict beside the estimate,
    since +58 with the test failed and +58 with it passed are not the same
    claim.

    An sprt states the whole test and not the batch that ended it, because a
    line quoting the spread of one batch beside the game count of several
    would claim a precision its own numbers deny."""
    if sprt:
        test = f"sprt {sprt.hypotheses} {sprt.verdict}, "
        estimate = sprt.estimate
    else:
        test = ""
    played = f"({test}{estimate.games} games, {tc}, vs {baseline})"
    if estimate.margin is None:
        # the estimate is what is missing, not the verdict: a test that
        # settled says something a score of nought or of one does not
        return f"Elo: not measured {played}" if sprt else "Elo: not measured"
    return f"Elo: {round(estimate.elo):+d} ±{round(estimate.margin)} {played}"


def interval(estimate: Estimate) -> str:
    if estimate.bounded == "not measured":
        return "There were no complete pairs, so there is no interval to report."
    if estimate.bounded:
        return (
            "Every pair went the same way, so the games bound the difference"
            f" from one side only, at {estimate.bounded} elo."
        )
    modelled = (
        " Every pair scored the same, so that interval is drawn from the spread"
        " unrelated games would have rather than from one these games showed."
        if estimate.modelled
        else ""
    )
    return (
        f"The 95% interval is {round(estimate.low):+d} to"
        f" {round(estimate.high):+d} elo, and the likelihood of superiority is"
        f" {100 * estimate.los:.1f}%. In normalized elo the difference is"
        f" {round(estimate.nelo):+d} ±{round(estimate.nelo_margin)}, which is"
        f" the figure to compare across books and time controls.{modelled}"
    )


def pentanomial(pairs: list[float]) -> list[str]:
    """The pairs by what the candidate scored in them, which is what the
    interval is measured over."""
    counted = Counter(pairs)
    heads = " | ".join(f"{score:g}" for score in PENTANOMIAL)
    rule = " | ".join("---" for _ in PENTANOMIAL)
    counts = " | ".join(str(counted[score]) for score in PENTANOMIAL)
    return [f"| pair score | {heads} |", f"| --- | {rule} |", f"| pairs | {counts} |"]


def table(shards: list[Shard], estimate: Estimate) -> list[str]:
    """A row per shard, so a runner that played fewer games than the others, or
    lost some of them to a fault, shows rather than being averaged away."""
    rows = ["| shard | games | score | faults |", "| --- | --- | --- | --- |"]
    for shard in shards:
        rows.append(
            f"| {shard.name} | {len(shard.games)} |"
            f" {shard.percent:.1f}% | {shard.faults} |"
        )
    faults = sum(shard.faults for shard in shards)
    rows.append(
        f"| pooled | {estimate.games} | {100 * estimate.score:.1f}% | {faults} |"
    )
    return rows


def pool_instruments(shards: list[Shard]) -> dict[str, Instruments]:
    """Every side's clock and search over the whole match."""
    pooled: dict[str, Instruments] = {}
    for shard in shards:
        for side, found in shard.instruments.items():
            pooled.setdefault(side, Instruments()).pool(found)
    return pooled


def instruments(pooled: dict[str, Instruments], candidate: str) -> list[str]:
    """What each side's clock and search did, as the report prints it.

    The candidate goes first whatever it is called, so two runs read the same
    way round. The ratios are what a reader is after: a score that is really
    one side being given more time, or more nodes for the time, shows as a
    ratio away from one here while the elo says nothing about why."""
    if not pooled:
        return []
    sides = sorted(pooled, key=lambda side: side != candidate)
    rows = [
        "| side | moves | nodes | time | nodes a second | least time left |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for side in sides:
        found = pooled[side]
        left = "-" if found.least_left is None else f"{found.least_left:.3f} s"
        rows.append(
            f"| {side} | {found.moves:,} | {found.nodes:,} |"
            f" {found.seconds:,.1f} s | {found.nps:,.0f} | {left} |"
        )
    remark = ""
    if len(sides) == 2:
        first, second = (pooled[side] for side in sides)
        if second.seconds and second.nodes and second.nps:
            nodes = first.nodes / second.nodes
            remark = (
                f"\n{sides[0]} had {first.seconds / second.seconds:.3f} times"
                f" the time and {nodes:.3f} times the"
                f" nodes of {sides[1]}, at"
                f" {first.nps / second.nps:.3f} times the rate."
            )
            if not LIKE_FOR_LIKE[0] <= nodes <= LIKE_FOR_LIKE[1]:
                remark += (
                    " The two sides searched very different trees, so the"
                    " rate is not a speed comparison. A side that prunes more"
                    " visits fewer nodes and dearer ones, and posts a lower"
                    " rate for it."
                )
    return [
        "The clocks and the search, over the moves the engines thought about:",
        "",
        *rows,
        *([remark] if remark else []),
    ]


def report(
    shards: list[Shard], estimate: Estimate, text: str, sprt: Sprt | None = None
) -> str:
    unpaired = sum(shard.unpaired for shard in shards)
    unfinished = sum(shard.unfinished for shard in shards)
    left_over = (
        f" {unpaired} of the games had no partner, so they are in the score and"
        " not in the estimate."
        if unpaired
        else ""
    )
    stopped = (
        f" {unfinished} games had no result and are left out altogether."
        if unfinished
        else ""
    )
    lines = [
        str(estimate),
        "",
        (
            f"{estimate.pairs} pairs from {estimate.games} games.{left_over}"
            f"{stopped} {interval(estimate)}"
        ),
        "",
        *pentanomial([score for shard in shards for score in shard.pairs]),
        "",
        *([sequential(sprt), ""] if sprt else []),
        *table(shards, estimate),
        "",
        "How the games ended:",
        "",
        "```",
        match_terminations.block(*match_terminations.count(text)),
        "```",
        "",
        *instruments(pool_instruments(shards), shards[0].candidate if shards else ""),
        "",
        # Which estimator priced these games. A later version can price the
        # same games differently, and a figure kept without its version cannot
        # be told apart from one the current version would print.
        f"Read by mache {__version__}.",
    ]
    return "\n".join(lines)


def finite(value: float | None) -> float | None:
    """A number json can carry, or nothing. A match that went one way
    throughout has a bound of infinity on the open side, and json.dumps writes
    that as -Infinity, which no parser is required to read back; the bounded
    string below is what says which side it ran off."""
    return value if value is not None and math.isfinite(value) else None


def figures(estimate: Estimate, left_over: dict[str, int] | None = None) -> dict:
    """One estimate as data, with what the pairing left over beside it where
    the caller counted any.

    The figures are unrounded, since rounding is what the report, the trailer
    and the line do with them. A match with no complete pair has no figure at
    all, so those are null rather than the zeroes the estimate starts at, and
    the bounded string is what it has instead."""
    measured = estimate.bounded != "not measured"
    return {
        "games": estimate.games,
        "pairs": estimate.pairs,
        **(left_over or {}),
        "score": estimate.score,
        "paired_score": estimate.paired if measured else None,
        "elo": estimate.elo if measured else None,
        "margin": estimate.margin,
        "low": finite(estimate.low),
        "high": finite(estimate.high),
        "los": estimate.los if measured else None,
        # normalized elo, null wherever the logistic interval is, since both
        # need a spread to read
        "nelo": estimate.nelo,
        "nelo_margin": estimate.nelo_margin,
        "bounded": estimate.bounded,
        "modelled": estimate.modelled,
    }


def as_json(
    shards: list[Shard],
    estimate: Estimate,
    text: str,
    candidate: str,
    baseline: str,
    tc: str,
    sprt: Sprt | None = None,
) -> dict:
    """The whole result as data, for a reader that is not a person.

    It is built from the objects the report is built from rather than from the
    report, so the two cannot say different things. It carries the shards, the
    pairs by score, how the games ended and both strings the other modes
    print, and the remarks that went to stderr are in it as well, so that
    reading stdout alone loses nothing.

    The shape is the one the format names, which JSON_FORMAT explains."""
    totals, blamed = match_terminations.count(text)
    counted = Counter(score for shard in shards for score in shard.pairs)
    fault = match_terminations.remark(totals, blamed)
    return {
        "format": JSON_FORMAT,
        "tool": tool("match_estimate"),
        "candidate": candidate,
        "baseline": baseline,
        "tc": tc,
        **figures(
            estimate,
            {
                "unpaired": sum(shard.unpaired for shard in shards),
                "unfinished": sum(shard.unfinished for shard in shards),
            },
        ),
        "pentanomial": [counted[score] for score in PENTANOMIAL],
        # the clocks and the search, so a reader that is not a person can
        # check the same thing the report's table is there for
        "instruments": {
            side: {
                "moves": found.moves,
                "nodes": found.nodes,
                "seconds": round(found.seconds, 3),
                "nps": round(found.nps, 1),
                "least_time_left": found.least_left,
            }
            for side, found in sorted(pool_instruments(shards).items())
        },
        "sprt": None
        if sprt is None
        else {
            "model": sprt.model,
            "elo0": sprt.elo0,
            "elo1": sprt.elo1,
            "llr": sprt.llr,
            "lower": LOWER,
            "upper": UPPER,
            "verdict": sprt.verdict,
            "batch": sprt.batch,
            "prior": sprt.prior,
            "counts": sprt.counts,
            "carried": sprt.carried,
            # the pairs of the whole test, which is what the trailer states
            "estimate": figures(sprt.estimate),
        },
        "shards": [
            {
                "name": shard.name,
                "index": shard.index,
                "games": len(shard.games),
                "points": shard.points,
                "score": shard.percent / 100,
                "pairs": len(shard.pairs),
                "unpaired": shard.unpaired,
                "unfinished": shard.unfinished,
                "faults": shard.faults,
            }
            for shard in shards
        ],
        "terminations": {
            "games": sum(totals.values()),
            "endings": match_terminations.endings(totals, blamed),
        },
        "remarks": [fault] if fault else [],
        "line": f"{estimate}, {sprt}" if sprt else str(estimate),
        "trailer": trailer(estimate, tc, baseline, sprt),
    }


def read_shards(paths: list[Path], candidate: str) -> tuple[list[Shard], str]:
    """One shard per pgn, named after the directory it arrived in, which is the
    artifact it was downloaded from. A single artifact is extracted without a
    directory of its own, so the name falls back to the file's."""
    shards, texts = [], []
    for path in paths:
        # fastchess writes utf-8, and an engine name or a comment can carry
        # a character outside ascii, so the encoding is stated rather than
        # taken from whatever locale the runner or the shell happens to set
        text = path.read_text(encoding="utf-8")
        texts.append(text)
        shards.append(Shard(path.parent.name or path.name, text, candidate))
    shards.sort(key=lambda shard: (shard.index is None, shard.index or 0, shard.name))
    return shards, "\n".join(texts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pgn", type=Path, nargs="+", help="a shard's games, one file")
    parser.add_argument("--candidate", required=True, help="the name it played under")
    parser.add_argument("--baseline", required=True, help="what it played against")
    parser.add_argument("--tc", default="", help="the time control played")
    parser.add_argument(
        "--elo0", type=float, help="the sprt null hypothesis in elo, with --elo1"
    )
    parser.add_argument(
        "--elo1", type=float, help="the sprt alternative in elo, with --elo0"
    )
    parser.add_argument(
        "--prior-pairs",
        default="",
        metavar="N,N,N,N,N",
        help="the pairs the earlier batches of this test played, by score,"
        " as the summary of the last one printed them",
    )
    parser.add_argument(
        "--model",
        choices=MODELS,
        default="logistic",
        help="what --elo0 and --elo1 are differences in: logistic elo, the"
        " default, or normalized elo",
    )
    printed = parser.add_mutually_exclusive_group()
    printed.add_argument(
        "--line",
        action="store_true",
        help="print the one line for the release notes instead of the report",
    )
    printed.add_argument(
        "--trailer",
        action="store_true",
        help="print the Elo trailer for a commit instead of the report",
    )
    printed.add_argument(
        "--json",
        action="store_true",
        help="print the whole result as json instead of the report, in the"
        " shape its format names",
    )
    args = parser.parse_args()
    if (args.elo0 is None) != (args.elo1 is None):
        parser.error(
            "--elo0 and --elo1 are the two ends of one test, so both or neither"
        )
    try:
        prior = read_prior(args.prior_pairs)
    except ValueError as bad:
        parser.error(f"--prior-pairs is a count for each pair score: {bad}")
    if args.elo0 is None and args.model != "logistic":
        parser.error("--model says what an sprt's bounds are in, so it wants --elo0")
    if args.elo0 is None and any(prior):
        parser.error("--prior-pairs carries a test on, so it wants --elo0 and --elo1")
    if args.elo0 is not None:
        cap = MAX_NORMALIZED if args.model == "normalized" else MAX_HYPOTHESIS
        for name, elo in (("--elo0", args.elo0), ("--elo1", args.elo1)):
            # a hypothesis off the end of the model, or not a number at all,
            # leaves the fit with nothing to solve for
            if not math.isfinite(elo) or abs(elo) > cap:
                parser.error(
                    f"{name} is an elo difference, so it is between -{cap} and {cap}"
                )
        # the null is the weaker of the two, and a test whose ends meet has no
        # evidence to weigh: its ratio is nought whatever the games did
        if args.elo0 >= args.elo1:
            parser.error(f"--elo0 {args.elo0:g} is not below --elo1 {args.elo1:g}")

    shards, text = read_shards(args.pgn, args.candidate)
    games = [score for shard in shards for score in shard.games]
    if not games:
        sys.exit(f"no games for {args.candidate} in {len(args.pgn)} shards")
    pairs = [score for shard in shards for score in shard.pairs]
    estimate = Estimate(sum(games), len(games), pairs)
    sprt = (
        Sprt(pairs, args.elo0, args.elo1, prior, args.model)
        if args.elo0 is not None
        else None
    )

    if args.trailer:
        print(trailer(estimate, args.tc, args.baseline, sprt))
    elif args.line:
        print(f"{estimate}, {sprt}" if sprt else str(estimate))
    elif args.json:
        # allow_nan=False rather than the default, so a figure that is not a
        # number fails here rather than being written as one no parser has to
        # read back
        print(
            json.dumps(
                as_json(
                    shards, estimate, text, args.candidate, args.baseline, args.tc, sprt
                ),
                indent=2,
                allow_nan=False,
            )
        )
    else:
        print(report(shards, estimate, text, sprt))
    if fault := match_terminations.remark(*match_terminations.count(text)):
        print(fault, file=sys.stderr)


if __name__ == "__main__":
    main()
