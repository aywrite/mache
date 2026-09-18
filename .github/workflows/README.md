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

Both workflows read a **book table** in your repository, described in
[`actions/setup/README.md`](../../actions/setup/README.md). `calibrate.yml` also
reads an **opponent table**, described in
[`actions/plan-ladder/README.md`](../../actions/plan-ladder/README.md).
`tests/fixtures/books.sh` is a worked example of the first.

## Pinning, and the lag in it

Call these at a tag.

Inside them, the actions they use are pinned at a tag too, and **that tag is
normally the release before the one you are calling**. A workflow at `v0.3.0`
runs the actions of `v0.2.0`.

Moving the pins does not change a release that is already out. A tag is fixed,
so they move on `main` and reach the release after them. Bumping them to
`v0.3.0` is what keeps `v0.4.0` one release behind rather than two.

That is not where it started. The release was going to move the pins itself,
which is tidier and does not work: a release commit is pushed by
`GITHUB_TOKEN`, and GitHub refuses to let that token create or update a file
under `.github/workflows/` at all. There is no permission that grants it; the
refusal is the point of it. So the pins move in an ordinary pull request, like
any other dependency bump, whenever the newer actions are wanted.

What this costs is the lag. A fix to an action is in the actions at the release
that carries it, and in the reusable workflows one release later. If you call
the actions directly you do not have this problem, and if you call these and
need a fix sooner, pin to the commit that carries it rather than to the tag.

## Not included

No release note is written and no pull request is commented on. Both workflows
hand back a `line` output and the caller decides what to do with it. That is
deliberate: writing to a release needs `contents: write`, and a workflow that
plays games should not be asking for it.

`strength.yml` also hands back `baseline_sha`, which is empty when there was no
release to compare against. The match is skipped in that case rather than
failed, because a first release has nothing to measure against and that is not
an error.
