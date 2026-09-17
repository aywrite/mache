# Building an engine at a commit

`play-shard` takes two binaries and does not build them. This says how to write
the step that does, and names the one mistake that is silent.

## Why there is no build action

A build belongs to the engine. It is a toolchain, a cache, a set of feature
flags and sometimes two commands, and none of that fits through an action input
without becoming a string that the action has to split or evaluate. A caller
that writes its own build step keeps its own cache action in front of it, keeps
its flags where a reader of the workflow can see them, and does not have to ask
for a new input every time the build changes.

It also keeps this repository out of a job it would do badly. A build script
here would have to be right for cargo, for make, for cmake and for whatever the
next engine uses, and the version that was right for all four would be a shell
wrapper around a string again.

## The trap

**Export the commit with `git archive` and let the files be stamped with the
time they were extracted, not the commit's.**

A build system decides a target is fresh by comparing its sources against the
last build. Cargo does, make does, and so does anything else worth using. If
the export is stamped with the commit's own time, its sources look older than
the last build and the build system hands back the binary it already had.

In a strength match that means both sides are the same binary. The match runs
for an hour, every game is between two copies of one program, and the report
says zero elo with no interval wide enough to look wrong. Nothing fails. There
is no log line. The only sign is a result that is suspiciously close to nothing.

`git archive` stamps at extraction time by default, and `tar -xm` keeps that
behaviour on the way out, so the plain form is the right one:

```bash
git archive "$sha" | tar -xm -C "$export"
```

What to avoid is anything that restores the commit's timestamps onto the export.

## The rest of it

**Build in a directory of its own.** Two commits built into one target
directory look to the build system like one crate that keeps changing, and it
will rebuild more than it needs to or, worse, less. Give the export its own
target directory and keep it across calls, so the dependencies stay warm and
only the engine is rebuilt.

**Do not check the commit out.** A checkout moves the branch, the index and
anything half written in the working tree. An export reads the commit and
leaves the tree alone, which matters because the job may be doing something
else with it.

**Do not pin the lock file.** A baseline old enough that its lock file predates
a registry change will refuse to build under a flag that demands the lock be
honoured, and the pull request's own tree is already held to its lock by
whatever gates the repository.

**Know which configuration the export is built under.** A build system that
finds its configuration by walking up from where it runs will find the working
tree's configuration if the export sits inside the tree, and the commit's own if
it sits outside. Neither is wrong, and they answer different questions: a
comparison spanning a change to that configuration reads about zero from inside
the tree and reads the change from outside it.

## A worked example

The engine this was written for builds two sides like this, with its own cache
action in the step before:

```yaml
- uses: Swatinem/rust-cache@<sha> # v2.9.2

- name: Build both versions
  run: |
    # a pull request head is not fetched by default
    for sha in "$CANDIDATE_SHA" "$BASELINE_SHA"; do
      git cat-file -e "${sha}^{commit}" 2>/dev/null || git fetch -q origin "$sha"
    done
    scripts/build_at.sh "$CANDIDATE_SHA" tools/new
    scripts/build_at.sh "$BASELINE_SHA" tools/old

- uses: aywrite/mache/actions/play-shard@<sha>
  with:
    candidate_binary: ./new
    opponent_binary: ./old
    # and the rest
```

`scripts/build_at.sh` is forty lines and lives in that repository, not this
one. Write your own; it is shorter than reading an action's inputs, and it is
yours to change when your build changes.
