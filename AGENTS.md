# Working on mache

The tools are short enough to read. This file is for what reading them will not
tell you.

## The tests and the lints

```
python3 -m pip install -e '.[test]'
python3 -m pytest tests
pre-commit run --all-files
```

The quotes are for the shell, which would otherwise read the brackets as a
pattern to match files with. The package needs nothing outside the standard
library, so the install is for the tests and for the command names.

`pre-commit` runs ruff, shellcheck, check-yaml, check-toml and the whitespace
hooks. Both the tests and the lints are gated in ci, on Python 3.10 and 3.12.
The 3.10 leg is what holds the floor `requires-python` declares.

The command line is what a caller runs, so the tests run it rather than calling
`main` themselves: `python3 -m mache.<tool>` with the repository root on
`PYTHONPATH`, which is what the composite action arranges for a job.

## Commits

Conventional commits with a scope from `package`, `action`, `ci`, `docs`,
`deps`. A hook checks it, so a guess at a scope is rejected rather than quietly
accepted. Pull requests are reviewed before they merge.

## Releasing

The version lives in `mache/__init__.py` and nowhere else. A release is a
version bump, a merge, and an annotated `vX.Y.Z` tag on the commit that carries
it. The release workflow refuses a tag that does not match `__version__`, then
builds the sdist and the wheel, publishes them and makes the GitHub release.

There is no moving `v0` tag. A consumer pins the commit a release is tagged at,
and a tag that moved would leave two releases answering to one name.

The `--json` shape is a contract from `0.1.0` on. `JSON_FORMAT` says which
shape, fields are added and not removed, and a change that cannot be made that
way raises the number.

## What stays out of this repository

Planning documents, unless one has been asked for. Keep them in a scratch
directory.

Some of the planning for this work is kept privately, outside this repository.
Its name, its URL and its path stay out of everything committed here: commit
messages, pull request bodies, code comments, documentation and workflow
comments. `AGENTS.local.md` is gitignored, so a pointer to it can exist on one
machine and never in the tree.

## Writing

Anything a reader sees (commit messages, pull request bodies, documentation,
comments) is written plainly. Short declarative sentences. Parentheses rather
than em dashes. Say what changed and why.

Some things read as generated and are avoided: three-part parallel
constructions, hype words (robust, comprehensive, powerful, seamless), clever
closing lines, and the same idiom twice in one file.
