# The statistics

## Logistic and normalized elo

The headline figure is logistic elo, read off the score with
`-400 log10(1/p - 1)`. How far a given improvement moves the score depends on
how often the games are drawn. The same change reads as fewer elo on a balanced
book than on an unbalanced one, and fewer at a long time control than a short
one, so two runs that differ in either are not comparable in it.

The report also gives the difference in normalized elo, which is what fastchess
prints as nElo. It is the score's distance from a half divided by the spread of
the pairs, scaled so that a small difference in a match with no draws reads
about the same in both. Because it measures how clearly the games separate the
two sides, it compares across books and time controls better than logistic elo
does, and its margin depends on the number of pairs alone. For the same pairs
the figure here is the one fastchess prints. `--json` carries it as `nelo` and
`nelo_margin`.

The sequential test takes its bounds in either. `--model normalized` reads
`--elo0` and `--elo1` as normalized elo, and the default, `--model logistic`,
reads them as logistic elo as before. Under the normalized model the number of
games a test needs to settle depends on the bounds, and much less than under
the logistic model on the book or the time control, so the same bounds cost
roughly the same whichever is played. A normalized test names itself as
`SPRT [0, 5] nElo` in the report, the line and the trailer, and `--json`
carries the model in its `sprt` object.

Every batch of one test is judged under the model it started with. The pair
counts carried between batches are the same under either, so nothing stops a
caller changing it part way, but the error rates only hold for a test that did
not. `strength.yml` and `actions/summarise-match` take it as `sprt_model`.

The ratio under the normalized model fits, for each hypothesis, the
distribution over the five pair scores that is likeliest to have produced the
pairs while being that many of its own standard deviations from a half. It
does that as a convex fit at each spread and a search over the spread, rather
than by the fixed point iteration fastchess uses, which does not converge from
every set of counts. Where both converge they agree. Hypotheses are limited to
100 normalized elo either side of nought, which is wider than the bounds a test
normally uses.

## Reading a rating estimate

`rating-estimate` holds every opponent at its published figure and fits the one
free parameter, so the figure is the rating at which the expected score equals
the score actually made.

The `±` is a 95% interval and it describes the games and nothing else. Whether
one rating can describe the results at all is asked separately: when the
opponents disagree with each other by more than chance allows, a note says so,
and the interval is an understatement rather than an estimate.

**A placement against a published list carries a systematic error no number of
games reduces.** The opponents earned their ratings on other hardware at
slower time controls. Treat the figure as a placement worth about a hundred
points either way, not as a rating.
