# The reusable workflows

`strength.yml` and `calibrate.yml` are whole matches as one call. They are for a
repository that wants a match rather than a job graph.

```yaml
name: Strength
on:
  workflow_dispatch:
    inputs:
      candidate:
        type: string
      baseline:
        type: string
      games:
        type: number
        default: 500
permissions:
  contents: read
jobs:
  match:
    uses: aywrite/mache/.github/workflows/strength.yml@v0.3.0
    with:
      build: scripts/build_at.sh
      candidate: ${{ inputs.candidate }}
      baseline: ${{ inputs.baseline }}
      games: ${{ inputs.games }}
```

Twenty one lines. Ten of them are the three dispatch boxes, which are yours to
choose and nothing to do with this workflow; drop them and the call is ten lines
with one required input. Decision 1 estimated twenty for the common case, and
that is about where it landed.

The other route is not twenty lines. After the engine that was written for this
moved its orchestration into the actions, its strength workflow was still 270
lines of jobs, of which 54 were its manifest and about 15 its build. Roughly 200
lines are what you write for yourself if you call the actions rather than this.

## What you give up by calling these

`uses:` is not an expression. Nothing can be passed into a reusable workflow
that decides which action runs, so these cannot take your cache action or your
build as steps. Both arrive as data instead, and both are worse than the step
would have been:

- **The build** is a path to a program in your repository, called
  `<build> <ref> <binary>`. One process, no environment, no second command.
- **The toolchain cache** is a generic `actions/cache` driven by `cache_paths`
  and `cache_key`. A cache action that understands your toolchain will do
  better, and you cannot use one here.
- **The manifest** is the shape these workflows write. If something in your
  repository reads a manifest back, it has to read this shape or you have to
  write your own.

If any of those matters, call the six actions and write the job graph. It is the
right trade when you need a step rather than a string, and the engine this was
written for pays it for all three reasons above.

## The build contract

The one thing you must provide.

```
<build> <ref> <binary>
```

Build the engine as it was at `<ref>` and leave a runnable file at `<binary>`.
The workflow checks that the file is there and executable, and fails the shard
if it is not.

`<ref>` is a commit, already resolved. `<binary>` is a path under the
workspace. The workflow calls this twice for a strength match, once per side,
and once for a gauntlet.

Nothing is said about how you build. `docs/BUILDING-A-REF.md` says what to
watch out for, and names the one mistake that is silent: an export stamped with
the commit's own time looks older than the last build, so the build system hands
back the binary it already had, both sides of the match are the same program,
and the match reports zero elo with nothing failing.

## The other two contracts

Both workflows read a **book table**, described in
[`actions/setup/README.md`](../../actions/setup/README.md). Leave `book_table`
out and they use the one this repository ships, which knows `8moves_v3` and
`UHO_4060_v2`; name a table in your repository to play anything else. `calibrate.yml` also
reads an **opponent table**, described in
[`actions/plan-ladder/README.md`](../../actions/plan-ladder/README.md).
`tests/fixtures/books.sh` is a worked example of the first.

## Early stopping, and what a batch is

A sequential test is judged at batch boundaries, so a batch that settles it is
where the games should stop. `batches` is how many `strength.yml` may play
before it reports inconclusive:

```yaml
      sprt: true
      games: 500
      batches: 4
```

`games` is the size of one batch either way, so this plays up to 2,000 and
stops as soon as the pooled pairs cross a bound. The default is `1`, which is
one batch and exactly what a caller played before this existed.

Four is as deep as the ladder goes. Actions has no loop and `uses:` is not an
expression, so the stages are written out in `strength.yml` and their number is
the ceiling; asking for more is refused rather than quietly truncated. A test
that wants more carries on in a second run, the way every batch did before:
take the `carried` output and hand it to the next run as `prior_pairs`.

Three outputs come back rather than one. `verdict` is `passed`, `failed` or
`inconclusive`, and is empty when the run was not a sequential test. `carried`
is the pair counts of the whole test. `line` is the last batch that played.

Two things follow from the batches sharing a run.

**They share a seed**, and the book is reserved for the test rather than for
each batch, so no two of them play the same opening. This is not a detail: the
batches are pooled, and a position played twice would be counted twice. A
caller writing its own job graph out of the actions has to pass `batch` and
`batches` to `play-shard` itself, or every batch starts where the first one
did and nothing says so.

**They share a run id and an attempt**, so the artifacts carry the batch as
well: `<prefix>-<run>-<attempt>-batch-<n>-shard-<i>`. A run of one batch keeps
the name it had, without the batch in it.

## Pinning

Call these at a tag.

Inside them, the actions they use are pinned at a tag too, and **it is the
same one**. A workflow at `v0.5.0` runs the actions of `v0.5.0`.

That is not automatic, and it cannot be. A release commit is pushed by
`GITHUB_TOKEN`, and GitHub refuses to let that token create or update a file
under `.github/workflows/` at all. There is no permission that grants it; the
refusal is the point of it. So the pins are moved by hand, in a commit that
sits beside the version bump on the release branch.

What holds them there is a test rather than a habit. The pins have to name the
version in `mache/__init__.py`, so a release branch carrying only the bump is
red until the pin commit is on it.

The pins used to name the release before instead, which cost a lag: a fix to an
action reached the reusable workflows one release later. `v0.5.0` is why that
stopped. It went out serving `v0.4.0`'s actions, so a caller who asked for the
release that put the clocks and the node counts in a match report got a report
with neither, and nothing said so.

None of that applies to `batch.yml` itself, which `strength.yml` reaches by a
relative path rather than a pin, so you get the one from the release you
called. That works because a relative reference from a workflow to a workflow
is resolved in the repository that holds it, at that repository's own commit,
and not in yours: run 35444376094 of the engine this was written for called a
workflow here that reached a second one beside it, and the log named it at
this repository's sha.

**The same syntax does not work for an action**, which is worth saying because
the two look identical. Run 35489144466 asked, and a workflow here reaching
`./actions/probe-only` while called from that repository failed with `Can't
find action.yml under /home/runner/work/arche/arche/actions/probe-only`: the
caller's workspace, with and without a checkout alike. So the actions are
named by ref and there is nothing to fall back on.

The lag had one case it could not carry at all, and `v0.4.0` is where it came
up: an action input added in the same release as the workflow that passes it.
The release before the first one to hold a ladder had no action that took a
batch, so a tag pin would have run the first stage, skipped the rest and said
nothing, a missing output reading as empty rather than failing. That release
pinned its actions at its own commit to get round it. With the pins naming
this release there is nothing left for a commit to reach.

Four tests hold the shape: a pin is a release tag; all of them name the same
one; that one is the version this tree is; and every input the workflows hand
an action and every output they read off one is declared by the version they
pinned. The last is the one that matters, because it is what a wrong pin gets
wrong silently.

## Not included

No release note is written and no pull request is commented on. Both workflows
hand back a `line` output and the caller decides what to do with it. That is
deliberate: writing to a release needs `contents: write`, and a workflow that
plays games should not be asking for it.

`strength.yml` also hands back `baseline_sha`, which is empty when there was no
release to compare against. The match is skipped in that case rather than
failed, because a first release has nothing to measure against and that is not
an error.
