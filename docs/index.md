# mache

Chess engine testing on GitHub Actions, with no server to run.

mache runs a match between two versions of an engine on the GitHub-hosted
runners a repository already has. The match is split across jobs that run at
the same time, and the games are pooled afterwards into one elo estimate or
one sequential test (SPRT). fastchess plays the games, and the result goes in
the run's summary.

It suits an engine whose changes are still large enough to show within a few
thousand games. [What hosted runners can measure](limits.md) says how many a
smaller change needs.

## Where to start

- [Quickstart](QUICKSTART.md), a match in your engine's repository from the
  build script to a first run
- [Using the tools](tools.md), what each command prints
- [Running a match without CI](without-ci.md), on pgn files fastchess wrote
  anywhere
- [How it works](how-it-works.md), and why a sharded match is pooled the way it
  is
- [The statistics](statistics.md), logistic and normalized elo and reading a
  rating estimate
- [Building an engine at a commit](BUILDING-A-REF.md), and the one mistake that
  is silent

The code, the composite actions and the reusable workflows are in
[the repository](https://github.com/aywrite/mache), and
`pip install mache` gives the command-line tools.
