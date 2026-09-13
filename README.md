# mache

Measure A CHess Engine.

A collection of tools for measuring and benchmarking chess engines. From mache
(μάχη), Greek for battle.

## Why this exists

[OpenBench](https://github.com/AndyGrant/OpenBench) is how engine testing is
normally done: an instance hands out tests and client machines attach to it and
play the games. In almost every case using OpenBench is a far better choice.

This tool exists for two reasons.

The first is that it was not planned. It grew as I wrote
[arche](https://github.com/aywrite/arche), my first chess engine, starting as a
basic CI job that got out of hand.

The second is that OpenBench needs machines. There is a shared instance a good
many engines develop against, and a dozen or more projects run their own. mache
is for the case where you have neither. It has no instance and no clients, and
it runs on the hosted CI runners a repository already gets, as part of the pull
requests and releases it already runs, so testing an engine costs no machine you
have to own, administer or ask anyone to lend you. Both play their games with
fastchess underneath.

Hosted runners are the point of mache and also what make it awkward. They are
slow, they are noisy, they are shared, and a job is killed at a time limit often
long before a match worth reading has finished. So a match is split across jobs
that run at once and pooled afterwards, which is most of what the tools below
are for, and why they take the care described further down.

## What is here

`mache`, a Python package with four tools:

| Tool | What it answers |
| --- | --- |
| `match-estimate` | How much stronger, over the pooled games of every shard. Or, with bounds, whether |
| `rating-estimate` | Where an engine sits on a published rating scale, from a gauntlet |
| `match-terminations` | How the games actually ended |
| `book-slice` | Which openings a shard plays, so that no two shards share one |

`actions/setup`, a composite action that builds
[fastchess](https://github.com/Disservin/fastchess) at a pinned commit,
fetches an opening book and checks it against a recorded hash, and puts the
package on `PYTHONPATH`. Nothing is installed at match time.

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

## Install

```
pip install mache
```

The engine side needs no install. The action puts the package on the path.

## Status

Alpha. mache is used by [arche](https://github.com/aywrite/arche), which is
where it was written, and it has not yet been used by an engine that is not
arche. Until it has, expect the rough edges of a tool with one user.

mache is written with heavy AI assistance.

## Licence

MIT. See [LICENSE](LICENSE).

The generalized log likelihood ratio follows Van den Bergh's note on the
pentanomial model, written from the note and checked against fastchess: for
the same pairs the number here is the number it prints. Two test cases are
fastchess's own, attributed where they are used. fastchess is MIT.
