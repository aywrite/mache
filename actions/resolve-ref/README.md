# `actions/resolve-ref`

Turns what a workflow was asked to play into a commit. A number is a pull
request, whose head a checkout does not fetch. Anything else is a branch, a tag
or a commit, which a full clone may already have and otherwise has to be asked
for by name.

```yaml
- uses: aywrite/mache/actions/resolve-ref@<sha> # v0.1.0
  id: candidate
  with:
    ref: ${{ inputs.candidate }}
    when_empty: head
```

## Inputs

| input | default | what it is |
| --- | --- | --- |
| `ref` | `""` | what to resolve; may be empty |
| `when_empty` | `fail` | `head`, `last-release` or `fail` |
| `release_glob` | `v[0-9]*` | the tag pattern `last-release` looks through |

## Outputs

| output | what it is |
| --- | --- |
| `name` | what to call this side in a report |
| `sha` | the commit |

The name is what a report calls the side, and it is the ref that was asked for
rather than the commit it resolved to today. A reader can look up a tag or a
branch; nobody can look up the sha a moving ref stood for on the day. Where a
figure has to name the same build months later, quote the sha instead: a
release tag is stable and everything else is not.

## What an empty ref means

`head` is the commit the workflow is running on. A gauntlet with no candidate
named measures what it is running on, which is what a reader expects.

`last-release` is the newest tag matching `release_glob` that is neither a
pre-release nor the tag being released. A strength match with no baseline named
compares against the last thing a user could have been running, which is why
pre-releases are skipped: their tags carry a `-`. The tag on the commit being
released is skipped too, because a release match runs from its own tag and
would otherwise play itself and report zero.

Both outputs are empty when `last-release` finds nothing, which is the first
release of a repository. The caller skips the match rather than failing: there
is nothing wrong, there is just nothing to compare against.

`fail` is for a caller that has no default and would rather say so than guess.

## The refusal, and what it does not cover

The caller builds and runs whatever this prints, and a pull request head is
anybody's to write. Under `pull_request_target`, `workflow_run` or a comment
event, a job also holds the repository's secrets and a token that can write to
it, and the two together hand a fork the repository. So this refuses unless the
trigger is one where the ref was chosen by somebody who can already push:
`workflow_dispatch`, `push`, `schedule` or `release`. It also runs when
`GITHUB_EVENT_NAME` is unset, which means it is not on a runner at all.

`pull_request` is deliberately not on the list. A fork's `pull_request` run gets
a read-only token and no secrets, so it is arguably safe, but allowing it would
break the rule the refusal states and nothing needs it.

**It is not a check on permissions or on secrets.** Neither is readable from
inside a job. The `permissions:` block is exposed to nothing running there, and
a secret is in the environment only when a step above passes it, so its absence
proves nothing about what else the job could be handed. A script that tested for
`GITHUB_TOKEN` and called that a permission check would be describing its own
environment and naming it something it is not.

What is readable is the trigger, and the trigger is the part that carries the
risk. The runner sets `GITHUB_EVENT_NAME` on every job, an `env:` block cannot
override a `GITHUB_` name, and a workflow entered through `workflow_call` sees
its caller's event, so a call through a reusable workflow is covered too.

So this does not say the job is unprivileged. A `workflow_dispatch` workflow
that granted `contents: write` and passed a secret would pass it. That part is
the workflow's to declare, and a caller should write `permissions: contents:
read` at the top of any workflow that builds a ref.
