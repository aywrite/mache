# Quickstart

Setting up a strength match in your engine's own repository.

When you're done you'll have a workflow you run from the Actions tab. It builds
two versions of your engine, plays them against each other on GitHub's hosted
runners and puts the result in the run summary.

## Requirements

- your engine speaks UCI and builds on the hosted Ubuntu runner (x86-64 Linux)
- it's in a GitHub repository with Actions turned on, and you can push to it
- if the repository belongs to an organisation, its Actions settings have to
  allow actions and reusable workflows from other repositories

So far mache has only been run from public repositories. In a private one,
stick to tags, commits and the branch you run from for now:
[actions/resolve-ref](https://github.com/aywrite/mache/blob/main/actions/resolve-ref/README.md#in-a-private-repository)
has why.

## 1. Build script

mache doesn't build your engine. It calls a script in your repository to do
it, once for each side of the match:

```
scripts/build_at.sh <commit> <binary>
```

The script builds the engine as it was at `<commit>` and leaves a runnable
file at `<binary>`. It's run from the root of your repository's checkout.

Copy [`examples/build_at.sh`](https://github.com/aywrite/mache/blob/main/examples/build_at.sh) to
`scripts/build_at.sh`. It's written for a Rust engine built with cargo, so
you'll probably need to change the two lines at the bottom (the build command,
and where the binary ends up). For make they might look like:

```bash
make -C "$src"
cp "${src}/engine" "$binary"
```

and for cmake:

```bash
cmake -S "$src" -B "${src}/build" -DCMAKE_BUILD_TYPE=Release
cmake --build "${src}/build" -j
cp "${src}/build/engine" "$binary"
```

Leave the `git archive` line above them alone, including the `-m` on `tar`.
[BUILDING-A-REF.md](BUILDING-A-REF.md) explains why. `git archive` also leaves
out submodules, and Git LFS files come out as pointers, so if your engine needs
either (e.g. a network file kept in LFS) fetch them in the script.

The runner image already has cargo, make, cmake, gcc and clang. The versions
move when GitHub updates the image, so if you need a particular one, install or
pin it in the script.

Make the script executable, on disk and in git:

```
chmod +x scripts/build_at.sh
git add --chmod=+x scripts/build_at.sh
```

Then try it. This builds your last commit, not anything uncommitted:

```
scripts/build_at.sh HEAD /tmp/engine
printf 'uci\nquit\n' | /tmp/engine | grep uciok
```

## 2. Workflow

Copy [`examples/strength.yml`](https://github.com/aywrite/mache/blob/main/examples/strength.yml) to
`.github/workflows/strength.yml`:

```yaml
name: Strength

on:
  workflow_dispatch:
    inputs:
      candidate:
        description: Branch, tag, commit or pull request number to test
        type: string
      baseline:
        description: What to measure it against. The last release if empty
        type: string
      games:
        type: number
        default: 500

# strength.yml asks for no more than this itself. It keeps anything you add
# to this file read-only too.
permissions:
  contents: read

jobs:
  match:
    uses: aywrite/mache/.github/workflows/strength.yml@v0.8.0
    with:
      build: scripts/build_at.sh
      candidate: ${{ inputs.candidate }}
      baseline: ${{ inputs.baseline }}
      games: ${{ inputs.games }}
```

`@v0.8.0` is the version of mache you're running. Pin a release rather than
`main`, so your results don't change under you. You can pin the commit the
release is tagged at instead (`@<sha> # v0.8.0`), but the actions it calls are
pinned by tag either way.

Commit both files and push them to your default branch. GitHub only shows the
Run workflow button for a workflow that's on the default branch.

## 3. First run

1. open the Actions tab and pick Strength
2. press Run workflow, fill in the form and run it

`candidate` is what to test: a branch, tag, commit or pull request number.
Leave it empty to test the branch you ran the workflow from.

`baseline` is what to test it against. Empty means your latest release, which
is the highest `v[0-9]*` tag with no `-` in it (so `v1.2.0-rc1` is passed
over). If you haven't tagged one yet the match is skipped with this notice:

```
No previous release to compare against, skipping
```

Until you have a release, put a branch or a commit in `baseline`.

`games` defaults to 500. Try 100 for the first run. It's enough to show the
build works and the engines play.

The run starts with a short job that works out the two commits, then five shard
jobs that each build both engines and play a fifth of the games, then one job
that pools them. The report is on the run's page, under the job graph. After a
line naming the two commits it looks something like this (from a 150 game
run):

```
+56 ±37 Elo (150 games)
```

and then the pair counts, a row per shard, how the games ended and each
engine's clock and node counts. [Using the tools](tools.md#match-estimate) goes
through each part. Each shard also uploads its games, fastchess's own output
and a manifest as an artifact called `strength-<run>-<attempt>-shard-<n>`.

Don't expect much from 500 games. The margin is about ±30 normalized elo, which
is enough to see a big change and not a lot else. (The headline figure is
logistic elo, so the two aren't directly comparable.)
[What hosted runners can measure](limits.md)
has numbers for bigger matches. Time your first run too, since how long a match
takes depends on your engine, the time control and the runner.

## SPRT

For smaller changes you'll want a sequential test (SPRT) instead. It keeps
playing until it can say whether the change is at least a given amount better.
[`examples/sprt.yml`](https://github.com/aywrite/mache/blob/main/examples/sprt.yml) turns it on:

```yaml
    with:
      build: scripts/build_at.sh
      candidate: ${{ inputs.candidate }}
      baseline: ${{ inputs.baseline }}
      sprt: true
      elo0: 0
      elo1: 10
      games: 500
      batches: 4
      prior_pairs: ${{ inputs.prior_pairs }}
```

- `elo0` and `elo1` are the bounds, in logistic elo
- `games` is the size of one batch
- `batches: 4` lets one run play up to four batches, and it stops as soon as the
  test passes or fails

If four batches aren't enough the verdict is inconclusive, and it ends with
something like:

```
Launch another batch with prior_pairs set to 4,18,72,38,18.
```

Run the workflow again with those numbers in `prior_pairs` to carry on the same
test. mache doesn't store anything between runs, so if you lose the numbers
you have to start over.

Keep the candidate, baseline and bounds the same from one run to the next, and
give both sides as commits rather than branch names. A branch can move between
runs, and so can an empty baseline when you tag a new release.

With more than one batch the artifacts are called
`strength-<run>-<attempt>-batch-<b>-shard-<n>`.

## Testing a pull request

Put the pull request number in `candidate`. An empty baseline still means your
latest release, not the branch the pull request is against, so set `baseline`
to `main` (or whatever it targets) if that's the comparison you want.

This builds and runs the pull request's code. If it comes from a fork, read it
first, more so if you've set `cache_paths`, since a cache saved by that run can
be restored by later ones.

A `pull_request` workflow can't pass a candidate or a baseline. mache won't
resolve a ref you name unless the workflow was started by `workflow_dispatch`,
`push`, `schedule` or `release`, where whoever picked the ref can already push
to the repository.
[actions/resolve-ref](https://github.com/aywrite/mache/blob/main/actions/resolve-ref/README.md#the-refusal-and-what-it-does-not-cover)
has the details.

## When it goes wrong

- no Run workflow button: the workflow isn't on the default branch yet
- `No previous release to compare against, skipping`: see `baseline` above
- `cannot resolve candidate ...` (or `baseline`): the ref doesn't exist, or the
  workflow was started by a trigger other than the four above
- the build step fails with your script's own output: run it locally as in step
  1
- `scripts/build_at.sh left no runnable tools/new`: the script finished without
  leaving an executable file where it was told to

## Options

The ones you're most likely to want. The rest are described in
[strength.yml](https://github.com/aywrite/mache/blob/main/.github/workflows/strength.yml).

| input | default | what it does |
| --- | --- | --- |
| `games` | 500 | games per run (per batch in an SPRT), split between the shards |
| `shards` | 5 | how many jobs to split them across |
| `time_control` | 10+0.1 | passed to fastchess as `tc` |
| `book` | `8moves_v3` | the opening book; `UHO_4060_v2` is the other one mache knows |
| `book_table` | empty | your own book table, for any other book (the contract is in [actions/setup](https://github.com/aywrite/mache/blob/main/actions/setup/README.md#the-book-table-contract)) |
| `cache_paths`, `cache_key` | empty | paths kept between runs with `actions/cache`; with the example script that's `~/.cargo/registry` and `~/.cargo/git`, since it builds in a fresh directory each time |
| `hash_mb` | 256 | the hash size each engine is asked for |
| `concurrency` | 2 | games a shard plays at once |

## Next

- [calibrate.yml](https://github.com/aywrite/mache/blob/main/.github/workflows/README.md#the-other-two-contracts) places
  your engine on a rating list by playing a gauntlet against rated opponents. It
  needs a table of opponents as well as the build script.
- if you want your own cache action, build steps or manifest, call the composite
  actions from your own workflow instead.
  [.github/workflows/README.md](https://github.com/aywrite/mache/blob/main/.github/workflows/README.md#what-you-give-up-by-calling-these)
  has the trade-off.
