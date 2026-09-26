# `actions/setup`

Builds fastchess at a pinned commit, fetches the opening books a table names
and checks them against their recorded hashes, and puts the `mache` package on
`PYTHONPATH` for the rest of the job. Nothing is installed: the commit the job
pins this action at is the code that runs.

```yaml
- uses: actions/checkout@<sha> # v7.0.1
- uses: aywrite/mache/actions/setup@<sha> # v0.1.0
  id: tools
- run: python3 -m mache.book_slice --openings 34700 --pairs 250 --shards 5 --shard 0 --seed 7
```

## Inputs

| input | default | what it is |
| --- | --- | --- |
| `fastchess` | `v1.8.2-alpha` | the release to build, and the name a manifest records |
| `fastchess_sha` | `f618e345…` | the commit that tag points at; a tag that has moved fails the run |
| `book_table` | empty | the book table in the calling repository's checkout; empty is the shipped one |
| `estimator_only` | `false` | skip the cache, the build and the books, and put the package on the path alone |

## Outputs

| output | what it is |
| --- | --- |
| `fastchess` | the release that is in `tools/` |
| `version` | the version of the package that is on the path |

Record the `version` in whatever a run writes about itself. It is what lets a
figure be read back against the tooling that produced it.

## What fastchess is built as

`build=release`, which is fastchess's own baseline target: `-march=x86-64` and a
static link. The binary is cached, and a cache is shared by runners with
different processors, so a binary built for the one that filled the cache is one
the next runner may not be able to execute. fastchess orchestrates the games and
the engines do the searching, so nothing measurable is lost by building for the
baseline.

## What the books land as

`tools/fastchess`, and each book beside it under the file name its table gives.
The match is played from `tools/`, and the cache holds the binary and the books
and nothing else: a match writes its games and its results into the same
directory, and caching those would let a later run read an earlier run's games
as its own.

## The book table contract

The table is a program, named by `book_table`, and the actions in this
repository call it seven ways. A table is how a repository
says which openings it plays and how a file it downloaded is checked, which is
a decision that belongs to the repository rather than to an action.

| call | prints | exit status |
| --- | --- | --- |
| `<table> list` | every book it knows, one name a line | non-zero if it cannot say |
| `<table> pin` | the commit of the book source every book is fetched at | non-zero if it cannot say |
| `<table> file <book>` | the file that book plays as | non-zero if it has no such book |
| `<table> format <book>` | what fastchess reads that file as | non-zero if it has no such book |
| `<table> count <book> <path>` | how many openings the file at `<path>` holds | non-zero if it cannot count them |
| `<table> fetch <book> <dir>` | nothing | non-zero if the download failed or is not what the table says it should be |
| `<table> verify <book> <dir>` | nothing | non-zero if the file in `<dir>` is not what the table says it should be |

`setup` uses the first two and the last two. `plan-shards` and `plan-ladder`
use `list`. `play-shard` uses `file`, `format` and `count`.

`count` takes a path rather than answering from a number the table has written
down, because a book that changed size would otherwise move every shard but the
first onto its neighbour's openings with nothing failing. It belongs beside the
format because what an opening is depends on it: a pgn holds a game per opening
and an epd a position a line.

`fetch` leaves the book in `<dir>` under the file name the table gives it, and
leaves nothing there at all if what arrived was not what was asked for. It is
checked again by `verify`, because `fetch` is skipped on a cache hit and a
restored file is what most runs play.

`pin` is what the cache key is built from, so a table that changed its pin
cannot hand a run the file fetched at the old one under the new one's name.

`tests/fixtures/books.sh` in this repository is a table of one book, written to
this contract and used by the smoke test. It is the shortest example of one.

## The shipped table

A caller that leaves `book_table` empty gets `bin/book_table.sh`, which is a
table like any other and holds two books from
[official-stockfish/books](https://github.com/official-stockfish/books):

| book | file | what it is |
| --- | --- | --- |
| `8moves_v3` | `8moves_v3.pgn` | 34,700 balanced openings |
| `UHO_4060_v2` | `UHO_4060_v2.epd` | 242,201 positions that favour one side, so fewer games are drawn |

It is there so that a first match needs no table. To play other openings, or to
fetch from somewhere else, write a table to the contract above and pass its path
as `book_table` to every action that takes one (and to the reusable workflow, if
that is what you call). Copying `bin/book_table.sh` is the quickest start. The
actions read nothing from the shipped table that a table of your own does not
answer.

The table can also be run by hand. `setup` puts `bin/` on the path, so a later
step can ask `book_table.sh list`.

## Known limit

The cache names the two files of the shipped table. A repository whose table
names other files gets them fetched and checked on every run rather than
restored, which is correct and slower.
