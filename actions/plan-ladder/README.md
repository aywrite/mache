# `actions/plan-ladder`

Reads a gauntlet's ladder into the rungs a matrix plays and the spec the rating
fit reads, and refuses a ladder no runner could play before a runner tries.

```yaml
- uses: aywrite/mache/actions/plan-ladder@<sha> # v0.1.0
  id: plan
  with:
    games: 50
    ladder: stash:v36:2713,alexandria:v7.1.0:2651
    book: 8moves_v3
    max_match_minutes: 150
```

## Inputs

| input | default | what it is |
| --- | --- | --- |
| `games` | required | games against each opponent |
| `ladder` | required | the opponents, as `engine:tag:rating` separated by commas |
| `opponent_table` | `scripts/opponent.sh` | the opponent table in the calling repository's checkout |
| `book` | required | the book name the run asked for |
| `book_table` | empty | the book table, as `actions/setup/README.md` describes it; empty is the shipped one |
| `max_match_minutes` | required | the wall clock cap a rung plays under |

## Outputs

| output | what it is |
| --- | --- |
| `rungs` | the rungs as json, for a matrix to read with `fromJSON` |
| `count` | how many there are |
| `pairs` | pairs against each opponent, which is `games` rounded down to even |
| `spec` | the ladder the fit reads, as `name:rating` |
| `book` | the book name, once the table has been asked whether it knows it |
| `play_timeout` | minutes to give a play job, for `timeout-minutes` to read with `fromJSON` |

`play_timeout` is half an hour over the cap, for the builds and the upload. It
is worked out here because a job timeout takes an expression and expressions
have no arithmetic.

## What it refuses, and why here

Everything below costs a job that does nothing, rather than one that has
already cloned and built an opponent.

- An engine the table has no block for.
- A rung that is not `engine:tag:rating`.
- A tag that is not a name. It becomes part of a file name, an artifact name
  and the name the engine plays under.
- A rating that is not a number.
- The same engine at the same pin twice. Two rungs would upload under one
  artifact name and be counted once.
- An empty ladder.

The ladder is split on commas alone. Splitting on whitespace would let a `*` in
it glob the checkout. Newlines are joined to commas first, because `read` stops
at one and would silently drop every rung below the first line.

## The opponent table contract

The table is a program in the calling repository, named by `opponent_table`.
This action calls it one way; the caller calls it the other two itself, in a
step of its own, for the same reason it builds its own engine.

| call | prints | exit status |
| --- | --- | --- |
| `<table> list` | every engine it can build, one name a line | non-zero if it cannot say |
| `<table> repository <engine>` | where that engine is cloned from | non-zero if it has no such engine |
| `<table> build <engine> <pin> <binary>` | nothing | non-zero if the clone or the build failed |

`build` clones the engine at `<pin>` and leaves a runnable binary at
`<binary>`.

A pin should be a tag or a whole commit, and a table should refuse a branch. A
rating on a published list belongs to the exact version it names, and a branch
would move under it. A tag can still be moved by whoever owns the repository,
which nothing here can see.

`repository` is for the manifest a run writes about itself: an opponent named
by a version string alone cannot be found again.
