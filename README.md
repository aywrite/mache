# mache: chess engine testing on GitHub Actions

[![Tests](https://github.com/aywrite/mache/actions/workflows/tests.yml/badge.svg)](https://github.com/aywrite/mache/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/mache)](https://pypi.org/project/mache/)

Sharded fastchess matches pooled into one elo estimate or SPRT, with no server
to run.

mache runs a match between two versions of an engine on the GitHub-hosted
runners a repository already has. The match is split across jobs that run at
the same time, and the games are pooled afterwards into one elo estimate or
one sequential test (SPRT). A repository calls it from a workflow of its own,
on its pull requests or by hand, and the result goes in the run's summary.
fastchess plays the games.

To set one up in your engine's repository, start with
[the quickstart](https://aywrite.github.io/mache/quickstart/).

It suits an engine whose changes are still large enough to show within a few
thousand games. A small change can take many runs to settle, and
[What hosted runners can measure](https://aywrite.github.io/mache/limits/)
says how many.

The tools that read the games also work without GitHub Actions, on pgn files
fastchess wrote anywhere.
[Running a match without CI](https://aywrite.github.io/mache/without-ci/)
shows how.

The name is from mache (μάχη), Greek for battle, and reads as Measure A CHess
Engine.

## Why this exists

[OpenBench](https://github.com/AndyGrant/OpenBench) is how engine testing is
normally done: an instance hands out tests and client machines attach to it and
play the games. In almost every case using OpenBench is a far better choice.

This tool exists for two reasons.

The first is that it was not planned. It grew as I wrote
[arche](https://github.com/aywrite/arche), my first chess engine, starting as a
basic CI job that got out of hand.

The second is that OpenBench needs machines. Some engines develop against a
shared instance and some projects run their own. mache is for the case where
you have neither. It has no instance and no clients, and it runs on the hosted
CI runners a repository already gets, as part of the pull requests and releases
it already runs, so testing an engine needs no machine of your own. Both play
their games with fastchess underneath.

Hosted runners are the point of mache and also what make it awkward. Their
timing varies from one job to the next, and a job is stopped at a time limit,
often long before a match worth reading has finished. So a match is split
across jobs that run at once and pooled afterwards, which is most of what the
tools below are for, and why they take the care
[How it works](https://aywrite.github.io/mache/how-it-works/) describes.

## What is here

`mache`, a Python package with four tools:

| Tool | What it answers |
| --- | --- |
| `match-estimate` | How much stronger, over the pooled games of every shard. Or, with bounds, whether it is stronger at all, as a sequential test |
| `rating-estimate` | Where an engine sits on a published rating scale, from a gauntlet |
| `match-terminations` | How the games actually ended |
| `book-slice` | Which openings a shard plays, so that no two shards share one |

Seven composite actions, which are the parts of a match workflow that are not
about any one engine. A caller keeps its own jobs, its own matrix and its own
toolchain cache, and calls these for the work inside them.

| Action | What it does |
| --- | --- |
| `actions/setup` | Builds [fastchess](https://github.com/Disservin/fastchess) at a pinned commit, fetches the opening books and checks them against recorded hashes, and puts the package on `PYTHONPATH`. Nothing is installed at match time |
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
puts on `PATH`. One of them is `book_table.sh`, the default book table: two
standard books from official-stockfish/books, used whenever a caller does not
pass a table of its own. There is no build script among them, and
`docs/BUILDING-A-REF.md` says why, along with the one trap a build step written
for this has to avoid.

## As one step

The action at the root of this repository reads games that are already on the
runner. It suits a repository that plays its own matches and only wants them
pooled:

```yaml
- uses: aywrite/mache@v0.7.0
  with:
    pgn: shards/**/games.pgn
    candidate: new
    baseline: old
    sprt: true
```

Every file the pattern matches is one shard. The report goes in the job
summary, and `line`, `trailer`, `verdict` and `carried` come back as outputs.
It needs `python3` 3.10 or newer, which GitHub's hosted Ubuntu runners have,
and installs nothing. [`action.yml`](https://github.com/aywrite/mache/blob/main/action.yml)
describes each input.

## Documentation

The documentation is at [aywrite.github.io/mache](https://aywrite.github.io/mache/):

- [Quickstart](https://aywrite.github.io/mache/quickstart/), a match in your engine's
  repository from the build script to a first run
- [Using the tools](https://aywrite.github.io/mache/tools/), what each command prints
- [Running a match without CI](https://aywrite.github.io/mache/without-ci/)
- [What hosted runners can measure](https://aywrite.github.io/mache/limits/)
- [How it works](https://aywrite.github.io/mache/how-it-works/), and why a sharded match is
  pooled the way it is
- [The statistics](https://aywrite.github.io/mache/statistics/), logistic and normalized elo
  and reading a rating estimate
- [Building an engine at a commit](https://aywrite.github.io/mache/building-a-ref/)

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
