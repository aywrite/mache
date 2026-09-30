# Running a match without CI

None of the four tools needs GitHub Actions. They read pgn files, or in
`book-slice`'s case a few numbers, so they work on games played anywhere: on
one machine, or on a few machines that each play part of a match.
`pip install mache` gives the command names. fastchess and an opening book are
yours to provide. In a clone of this repository,
`bin/book_table.sh fetch 8moves_v3 .` downloads one of the two books the
actions use and checks it against its recorded hash.

Each machine plays a shard. `book-slice` says which opening a shard starts at,
so that no two shards play the same one. Every shard asks with the same
numbers and its own `--shard`:

```
openings=$(grep -c '^\[Event ' 8moves_v3.pgn)
start=$(book-slice --openings "$openings" --pairs 100 --shards 2 --shard 0 --seed 7)
```

Then fastchess plays the shard. `-repeat` pairs the games as `match-estimate`
expects. `-rounds` is the number of pairs and has to match `--pairs` above.
`nodes=true` is what the report's table of clocks and nodes counts moves by,
and `timeleft=true` gives its last column. Without them the table reads as
zeros.

```
fastchess -engine name=new cmd=./new -engine name=old cmd=./old \
  -each proto=uci tc=10+0.1 \
  -openings file=8moves_v3.pgn format=pgn order=sequential start="$start" \
  -rounds 100 -repeat -concurrency 2 \
  -pgnout file=games.pgn nodes=true timeleft=true
```

fastchess adds to a `games.pgn` that is already there, so start each shard in
an empty directory. A shard played twice into one file would be counted twice.

With each shard's games in a directory of its own, one command pools them. The
directory names become the rows of the shard table:

```
match-estimate shard-0/games.pgn shard-1/games.pgn \
  --candidate new --baseline old --tc 10+0.1
```

`--elo0`, `--elo1`, `--prior-pairs` and `--model` run the sequential test here
the same way they do in a workflow. A test played in several batches passes
`--batches` and `--batch` to `book-slice` as well, so that a later batch does
not replay an earlier one's openings.
