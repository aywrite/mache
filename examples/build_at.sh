#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

# Build the engine as it was at a commit, to the contract the reusable
# workflows call:
#
#     build_at.sh <ref> <binary>
#
# Written for a Rust engine built with cargo. Change the two lines marked below
# for another build (docs/QUICKSTART.md has them for make and cmake).
set -euo pipefail

ref=${1:?usage: build_at.sh <ref> <binary>}
binary=${2:?usage: build_at.sh <ref> <binary>}

# Export the commit rather than check it out, so the working tree is left
# alone. `tar -m` stamps the files with the time they're extracted rather than
# the commit's. It doesn't matter while every build starts in a fresh
# directory, but it does once a target directory is shared between builds
# (CARGO_TARGET_DIR, or a cache): cargo would take the sources for older than
# its last build, hand back the binary it already had, and both sides of the
# match would be the same program.
src=$(mktemp -d)
trap 'rm -rf "$src"' EXIT
git archive "$ref" | tar -xm -C "$src"
# git archive leaves out submodules, and Git LFS files come out as pointers.
# If the engine needs either, fetch them into "$src" here.

mkdir -p "$(dirname "$binary")"
# change these two lines for another build
(cd "$src" && cargo build --release)
cp "${src}/target/release/my-engine" "$binary"
