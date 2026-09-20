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
| `match-estimate` | How much stronger, over the pooled games of every shard. Or, with bounds, whether it is stronger at all, as a sequential test |
| `rating-estimate` | Where an engine sits on a published rating scale, from a gauntlet |
| `match-terminations` | How the games actually ended |
| `book-slice` | Which openings a shard plays, so that no two shards share one |

Six composite actions, which are the parts of a match workflow that are not
about any one engine. A caller keeps its own jobs, its own matrix and its own
toolchain cache, and calls these for the work inside them.

| Action | What it does |
| --- | --- |
| `actions/setup` | Builds [fastchess](https://github.com/Disservin/fastchess) at a pinned commit, fetches an opening book and checks it against a recorded hash, and puts the package on `PYTHONPATH`. Nothing is installed at match time |
| `actions/resolve-ref` | Turns a branch, tag, commit or pull request number into a commit, and refuses under a trigger where the ref was not the caller's to choose |
| `actions/plan-shards` | Works out the shard list and the pairs each shard plays, and checks the sequential test's bounds before anything is built |
| `actions/plan-ladder` | Reads a gauntlet's ladder into the rungs a matrix plays and the spec the fit reads |
| `actions/play-shard` | Works out which openings a shard plays, and plays them |
| `actions/summarise-match` | Pools every shard and estimates the difference, and judges the sequential test where there is one |
| `actions/summarise-gauntlet` | Pools every rung and fits a rating against the ladder |

Each has a `README.md` beside it. Two things they deliberately do not do:
build an engine, and write the manifest a run keeps about itself. A build
belongs to the engine, and arrives as steps of the caller's own rather than as
a command in a string. A manifest is the calling repository's record of its own
run, and its shape is that repository's business.

Two reusable workflows, `.github/workflows/strength.yml` and
`calibrate.yml`, which are a whole match as one call. A repository that wants a
match rather than a job graph writes about ten lines and gives up three things:
its own cache action, its own build as steps, and the shape of its own manifest.
`uses:` is not an expression, so a reusable workflow cannot be handed a step by
anybody. [`.github/workflows/README.md`](.github/workflows/README.md) has the
call, the build contract and the trade in full.

`bin/` holds the shell tools a caller can run directly, which `actions/setup`
puts on `PATH`. There is no build script among them, and
`docs/BUILDING-A-REF.md` says why, along with the one trap a build step written
for this has to avoid.

## Using the tools

`pip install mache` gives the four command names used below. Under the
composite action nothing is installed, and the same tools are
`python3 -m mache.<tool>` with underscores where the command name has hyphens.

Each tool prints its report on stdout. Anything worth an alert goes to stderr
instead, a fault or an unfinished game, so a workflow can raise it from there
rather than reading it back out of the report.

### `match-estimate`

A shard is one pgn, written by one job of the run. fastchess plays it with
`-repeat`, so a round is two games on one opening with the colours reversed,
and `--candidate` and `--baseline` name the engines as fastchess named them.

```
match-estimate strength-1-1-shard-*/games.pgn \
  --candidate new --baseline ce8b662 --tc 10+0.1
```

```
+56 ±37 Elo (150 games)

75 pairs from 150 games. The 95% interval is +19 to +93 elo, and the likelihood of superiority is 99.9%.

| pair score | 0 | 0.5 | 1 | 1.5 | 2 |
| --- | --- | --- | --- | --- | --- |
| pairs | 2 | 9 | 36 | 19 | 9 |

| shard | games | score | faults |
| --- | --- | --- | --- |
| strength-1-1-shard-0 | 50 | 57.0% | 0 |
| strength-1-1-shard-1 | 50 | 59.0% | 1 |
| strength-1-1-shard-2 | 50 | 58.0% | 0 |
| pooled | 150 | 58.0% | 1 |
```

The block `match-terminations` prints follows that, and the last line of the
report names the version that read the games. `--tc` and `--baseline` are
recorded rather than read, so a baseline that is not a release tag can go in as
its sha.

`--elo0` and `--elo1` read the same pairs a second way, as a sequential test:

```
match-estimate strength-1-1-shard-*/games.pgn \
  --candidate new --baseline ce8b662 --tc 10+0.1 --elo0 0 --elo1 10
```

which puts this paragraph in the report:

```
SPRT [0, 10] inconclusive. The log likelihood ratio over the 75 pairs of the test (75 from this batch and 0 from the batches before it) is 1.32 against bounds of (-2.94, 2.94). The games so far settle it neither way. Launch another batch with prior_pairs set to 2,9,36,19,9.
```

The counts at the end of it are what the next batch carries in, so that the
runs accumulate into one test:

```
match-estimate strength-1-1-shard-*/games.pgn \
  --candidate new --baseline ce8b662 --tc 10+0.1 \
  --elo0 0 --elo1 10 --prior-pairs 2,9,36,19,9
```

```
SPRT [0, 10] inconclusive. The log likelihood ratio over the 150 pairs of the test (75 from this batch and 75 from the batches before it) is 2.64 against bounds of (-2.94, 2.94). Over all of them the difference is +56 ±26 elo, which is the figure the trailer carries. The games so far settle it neither way. Launch another batch with prior_pairs set to 4,18,72,38,18.
```

Three flags each replace the whole report. `--line` prints what release notes
carry:

```
+56 ±37 Elo (150 games), SPRT [0, 10] inconclusive, LLR 1.32 (-2.94, 2.94)
```

`--trailer` prints what a commit carries:

```
Elo: +56 ±37 (sprt [0, 10] inconclusive, 150 games, 10+0.1, vs ce8b662)
```

`--json` prints all of it as data, for a reader that is not a person:

```
{
  "format": 1,
  "tool": {
    "name": "mache",
    "version": "0.1.0",
    "command": "match_estimate"
  },
  "candidate": "new",
  "baseline": "ce8b662",
  "tc": "10+0.1",
  "games": 150,
  "pairs": 75,
```

`format` is which shape the object is in, and shape 1 is a contract from
`0.1.0` on. Fields are added to it. None is removed and none is given a new
meaning under the name it has, and a change that cannot be made that way
raises the number. The rest of the object holds the pentanomial counts, the
sequential test, a row per shard, the terminations, and the `line` and
`trailer` strings above.

### `rating-estimate`

The ladder is one argument, `name:rating` per opponent separated by commas,
with the names as the pgn spells them:

```
rating-estimate gauntlet.pgn arche-0.5 \
  'stash-v33:1876,cheng-4.39:1932,supernova-2.1:1801,winter-0.7:1978'
```

```
| opponent | ccrl | w-d-l | score | implies |
| --- | --- | --- | --- | --- |
| stash-v33 | 1876 | 12-6-12 | 50.0% | 1876 |
| cheng-4.39 | 1932 | 9-7-14 | 41.7% | 1874 |
| supernova-2.1 | 1801 | 16-5-9 | 61.7% | 1884 |
| winter-0.7 | 1978 | 7-6-17 | 33.3% | 1858 |

1873 ±56 (95%) on the ccrl blitz scale (120 games)

Read by mache 0.1.0.
```

`--line` prints the estimate and nothing else. `--json` prints the fit, the
ladder it was given and a record per opponent, in the same format 1.

### `match-terminations`

```
match-terminations strength-1-1-shard-1/games.pgn
```

```
games: 50
normal: 49
adjudication: 0
time forfeit: 1 (new 1)
disconnect: 0
stall: 0
abandoned: 0
illegal move: 0
unterminated: 0
```

Every ending is printed, zero included. The line about the one that ended by a
fault goes to stderr beside the block. `--json` prints the same counts, with
the engines an ending fell on as a mapping rather than as the sentence.

### `book-slice`

```
book-slice --openings 34700 --pairs 250 --shards 5 --shard 3 --seed 7
```

```
758
```

That number is one based, which is what fastchess's `start=` takes. Every
shard of a run asks with the same `--openings`, `--pairs`, `--shards` and
`--seed`, and its own `--shard`, so the slices are worked out from the run's
own numbers and no two of them hold an opening in common.

A sequential test pools its batches the same way it pools its shards, so the
rule holds across them too, and `--batches` with `--batch` is how a caller
says so. What is then reserved is the whole test rather than one batch of it,
and a batch takes the slice after the batch before it. This matters where the
batches are chained inside one run, because they share a seed: each reserving
its own games alone would start every batch where the first one started, and
the pooled estimate would count those positions twice with nothing failing.
A caller that passes neither plays what an unbatched run plays.

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
