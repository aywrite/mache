#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

# What a match was asked to play, as a name and a commit:
#
#     resolve.sh <ref> <when-empty> <release-glob>
#
# <ref> is what the caller was given, and may be empty. <when-empty> says what
# an empty one means: `head` is the commit the workflow is running on,
# `last-release` is the newest release tag that is not a pre-release and is not
# the tag being released, and `fail` says a caller that left it empty made a
# mistake.
#
# `last-release` is what a strength match compares against when nobody names a
# baseline. It skips pre-releases, because a release is measured against the
# last thing a user could have been running, and it skips the tag on HEAD,
# because a release match run from its own tag would otherwise play itself.
#
# Prints two lines, the name and the sha. The name is what a report calls the
# side: a tag or a branch a reader can look up, rather than the sha it resolved
# to today. Both are empty when there is nothing to resolve and <when-empty> is
# `last-release`, which is the first release of a repository.
set -euo pipefail

usage="usage: resolve.sh <ref> <when-empty> <release-glob>"
ref=${1?$usage}
when_empty=${2:?$usage}
glob=${3:?$usage}

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

if [ -n "$ref" ]; then
    sha=$("${here}/../../bin/resolve_ref.sh" "$ref")
    printf '%s\n%s\n' "$ref" "$sha"
    exit 0
fi

case "$when_empty" in
    head)
        printf '%s\n%s\n' "${GITHUB_REF_NAME-}" "${GITHUB_SHA-}"
        ;;
    last-release)
        # --sort so the newest is first, and grep -v -- '-' drops the
        # pre-releases, whose tags carry one. The tag being released is
        # dropped by name rather than by sha: a release match runs on its own
        # tag, and comparing that against itself would report zero.
        # git and the greps are separated so that only the greps are allowed
        # to come back empty. A git that failed (a shallow clone with no tags
        # fetched, a broken repository) would otherwise read as a repository
        # with no release yet, and the caller would skip the match and go
        # green with a notice.
        tags=$(git tag --list "$glob" --sort=-v:refname) \
            || { echo "resolve.sh: cannot read the tags" >&2; exit 1; }
        tag=$(grep -v -- '-' <<< "$tags" \
              | grep -v -x "${GITHUB_REF_NAME-}" \
              | head -1) || true
        if [ -z "$tag" ]; then
            printf '\n\n'
            exit 0
        fi
        printf '%s\n%s\n' "$tag" "$(git rev-parse "${tag}^{commit}")"
        ;;
    fail)
        echo "resolve.sh: nothing to resolve, and this caller has no default" >&2
        exit 1
        ;;
    *)
        echo "resolve.sh: ${when_empty} is not head, last-release or fail" >&2
        exit 1
        ;;
esac
