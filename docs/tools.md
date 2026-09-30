# Using the tools

`pip install mache` gives the four command names used below. Under the
composite action nothing is installed, and the same tools are
`python3 -m mache.<tool>` with underscores where the command name has hyphens.

Each tool prints its report on stdout. Anything worth an alert goes to stderr
instead, a fault or an unfinished game, so a workflow can raise it from there
rather than reading it back out of the report.

## `match-estimate`

A shard is one pgn, written by one job of the run. fastchess plays it with
`-repeat`, so a round is two games on one opening with the colours reversed,
and `--candidate` and `--baseline` name the engines as fastchess named them.

```
match-estimate strength-1-1-shard-*/games.pgn \
  --candidate new --baseline ce8b662 --tc 10+0.1
```

```
+56 ±37 Elo (150 games)

75 pairs from 150 games. The 95% interval is +19 to +93 elo, and the likelihood of superiority is 99.9%. In normalized elo the difference is +85 ±56, which is the figure to compare across books and time controls.

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

`--alpha` and `--beta` are the chances of a wrong pass and a wrong fail the test
accepts, five percent each unless given. They set Wald's bounds, which are
(-2.94, 2.94) at the defaults and (-4.60, 4.60) at one percent each, so
stricter rates take more pairs to settle a test. A verdict reached at other
rates names them wherever it is quoted, as in
`SPRT [0, 10] alpha=0.01 beta=0.01 passed`. Give every batch of one test the
same rates, since they are what the bounds were drawn at.
`actions/summarise-match` takes them as `alpha` and `beta`.

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

## `rating-estimate`

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

The figure is on the scale of the list the ratings were read off, and the
line names it. That is `ccrl blitz` unless `--scale` says otherwise, so a
ladder read off the 40/15 list is fitted with `--scale 'ccrl 40/15'`. The
`summarise-gauntlet` action takes the same thing as its `scale` input.

## `match-terminations`

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

## `book-slice`

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
