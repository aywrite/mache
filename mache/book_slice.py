# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

"""Print the opening a shard of a match starts at.

The shards of a match play at the same time and are pooled afterwards, so no
two of them may play the same opening: a position played twice would be counted
twice and the games would not be the independent sample the estimate reads them
as. The book is taken in order rather than drawn, and each shard is given a
slice of its own, which is where its games begin.

The run's first shard starts at a remainder of the seed, so two runs of the same
size play different regions of a book far larger than either of them uses, and
each shard after it starts a slice further along. The starts are worked out from
the seed and the counts alone, so the manifest is enough to play the schedule
again, without depending on how fastchess draws its own openings.

A sequential test pools its batches the same way it pools its shards, so the
same rule holds across them. What is reserved is the whole test rather than one
batch of it: a batch is told how many there are and which it is, and takes the
slice after the batch before it. This matters because batches chained inside
one run share a run id and so a seed, and each reserving only its own games
would start every batch where the first one started.

The index printed is one based, which is what fastchess's `start=` takes.
"""

import argparse
import sys


def first_opening(openings: int, wanted: int, seed: int) -> int:
    """Where the first shard begins. The offset leaves room for every shard, so
    the last one still ends inside the book."""
    room = openings - wanted
    if room < 1:
        return 1
    return 1 + seed % room


def start(
    openings: int,
    pairs: int,
    shards: int,
    shard: int,
    seed: int,
    batch: int = 0,
    batches: int = 1,
) -> int:
    """The opening this shard of this batch begins at, one based.

    The slices run batch by batch and shard by shard, so every (batch, shard)
    of one test gets its own. Defaulting to batch 0 of 1 is what an unbatched
    run plays, which is the formula this had before batches existed."""
    room = first_opening(openings, pairs * shards * batches, seed)
    return room + (batch * shards + shard) * pairs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openings", type=int, required=True, help="what the book has")
    parser.add_argument("--pairs", type=int, required=True, help="openings per shard")
    parser.add_argument("--shards", type=int, required=True, help="shards in the run")
    parser.add_argument("--shard", type=int, required=True, help="which one, from zero")
    parser.add_argument("--seed", type=int, required=True, help="the run's seed")
    parser.add_argument(
        "--batches", type=int, default=1, help="batches in the test, one if unbatched"
    )
    parser.add_argument("--batch", type=int, default=0, help="which one, from zero")
    args = parser.parse_args()

    if min(args.openings, args.pairs, args.shards, args.batches) < 1 or args.seed < 0:
        sys.exit("the counts are all at least one and the seed is not negative")
    if not 0 <= args.shard < args.shards:
        sys.exit(f"shard {args.shard} is not one of {args.shards}")
    if not 0 <= args.batch < args.batches:
        sys.exit(f"batch {args.batch} is not one of {args.batches}")

    # the whole test, not this batch of it: it is the test that has to fit,
    # since its batches are pooled and may not repeat each other's openings
    wanted = args.pairs * args.shards * args.batches
    if args.openings - wanted < 1:
        # fastchess reads on around the end of the book, so the match still
        # plays. It is the shards no longer being disjoint that is worth saying
        print(
            f"the book holds {args.openings} openings and the run wants {wanted},"
            " so the shards repeat each other",
            file=sys.stderr,
        )
    print(
        start(
            args.openings,
            args.pairs,
            args.shards,
            args.shard,
            args.seed,
            args.batch,
            args.batches,
        )
    )


if __name__ == "__main__":
    main()
