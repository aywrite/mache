# How it works

## The part that is not obvious

A sharded match is not a long match cut up. Three things have to hold or the
number it produces is wrong.

**The estimate is over the pool.** fastchess prints one, but only for the
games its own process played. With five shards that is a fifth of the
evidence, and averaging five such figures is a different calculation.
`match-estimate` reads the games themselves.

**The error bar is over pairs, not games.** Under `-repeat` the two games of a
round are one opening with the colours reversed, so they are one observation.
Counting them as two understates the spread.

**A sequential test looks only at batch boundaries.** A per-shard SPRT that
stopped when its own games settled the question would be one look per shard at
a bound priced for one, on a sample chosen by what it said. Here the shards
play their slices out with nothing watching and the test is judged once over
all of them. A run is one batch, and `--prior-pairs` carries its pairs into
the next, so repeated runs accumulate into one test rather than several.

Openings follow from a seed rather than a shuffle, so a schedule can be played
again from what the run recorded.

## The clocks and the search are in the report

A match report carries what each side's clock and search did: moves thought
about, nodes, time, nodes a second, and the tightest its clock ever got. The
figures are per engine rather than per colour, since `-repeat` plays every
opening both ways, and they pool across shards the way the estimate does.

They are there because an elo figure does not say why. A result that is really
one side being handed more time, or more nodes for the time, shows as a ratio
away from one here and nowhere else in the report. A registration that says a
surprising number is re-read against the clocks and the node counts is
answered from this table.

**It is in the report, and the report goes to the log and to the run's
summary.** That is the point of putting it there rather than leaving it in the
games: a later session reading back a run can reach a log, and may not be able
to reach the artifacts. Book moves are left out of the counts, since the engine
did not think about them, and still hold their place so the moves after them
are attributed to the side that made them.

## The test keeps no state

mache stores nothing between runs. The pairs the earlier batches of a
sequential test played are an argument: a run prints them at the end of its
verdict and the next run is handed them back with `--prior-pairs`. That is a
decision and not an omission.

Carrying five numbers is the price. A caller that loses them has lost the test
and has to start it again. `actions/summarise-match` hands them back as
`carried`, beside the `verdict` that says whether another batch is wanted at
all, so a caller writing its own job graph passes them on rather than a person
retyping them between runs. What it buys is that a run says on its face
what it was judged over, so a reader checks the count against the batches that
were played rather than trusting a file nobody looked at. Stored state would
also have to be one thing per test, and a tool that cannot see which test a run
belongs to would be guessing at that.

An accumulator that keeps the counts in an artifact is a later addition if
anyone wants one. It is not missing by accident.

## The version is in the output

A change to the estimator can price the same games differently. So a report
names the version that read them, `--json` carries it in its `tool` object, and
the composite action hands the version on the path back as an output, for a
caller to write into whatever it records about a run. A figure kept without it
cannot be checked against the code that produced it.

`--line` and `--trailer` are one line each and carry no version. They are
quoted beside a report or a manifest that does.
