# What hosted runners can measure

A run of `strength.yml` with its defaults plays 500 games over five shards,
which is 250 pairs. A sequential test given `batches: 4` plays up to four such
batches in one run, 1,000 pairs. It stops early if a batch settles the test,
and otherwise hands back the counts for the next run to carry on from.

For an estimate on its own, the 95% margin in normalized elo, as mache works
it out, depends only on the number of pairs:

| pairs | margin |
| ---: | ---: |
| 250 | ±30 |
| 1,000 | ±15 |
| 4,000 | ±8 |

The margin in logistic elo also depends on how the pairs scored, and so on
how many games were drawn.

A sequential test runs until the pairs settle it, and the closer its bounds,
the longer that takes. In the simulation below, halving the gap between the
bounds took between three and four times the pairs. It ran 300 tests a row of
the normalized test with mache's own code, at the default error rates of five
percent each, judged every 250 pairs as with the workflow's default batch. The pair scores were drawn from a distribution in
which three pairs in five score one point, shifted to each true difference:

| bounds (normalized elo) | true difference at a bound | true difference halfway between |
| --- | ---: | ---: |
| [0, 10] | about 4,000 pairs | about 7,000 pairs |
| [0, 5] | about 13,000 to 14,000 pairs | about 26,000 pairs |

Those are averages, and the spread around them is wide: about one test in ten
ran to nearly twice the average or longer. At 1,000 pairs a run, the averages
come to about four to seven runs for [0, 10] and about thirteen to twenty-six
for [0, 5]. The normalized model is what `match-estimate --model normalized`
uses, and what `strength.yml` and `actions/summarise-match` use when given
`sprt_model: normalized`. Both default to logistic elo, so `strength.yml`'s
default bounds of [0, 10] are not the first row above, and how long a logistic
test runs depends on the draw rate as well as the bounds.

How long a batch takes depends on the time control, the engines and the
runner, so it is worth timing one before planning a test around it. A shard
is stopped at `max_match_minutes`, 150 by default, and reports the games it
finished by then.

Both engines of a shard share one runner, so a slow runner slows both. An
engine whose strength changes a lot with the time it is given loses more to a
slow runner than one whose strength does not.

GitHub does not charge for its standard hosted runners on public repositories.
A private repository uses the Actions minutes its plan includes. GitHub's
billing documentation has the current terms.
