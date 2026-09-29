# Examples

Files to copy into your engine's repository. [The quickstart](../docs/QUICKSTART.md)
walks through them.

| file | copy to | what it is |
| --- | --- | --- |
| `build_at.sh` | `scripts/build_at.sh` | builds the engine at a commit (written for cargo) |
| `strength.yml` | `.github/workflows/strength.yml` | a match you run by hand |
| `sprt.yml` | `.github/workflows/sprt.yml` | a sequential test you run by hand, carried across runs |

They live here until there's an example repository for them. Nothing in this
repository runs them, but `tests/test_examples.py` checks they call the current
release with inputs it takes.
