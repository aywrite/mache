# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

"""The documentation site, which GitHub Pages builds from docs/.

The pages are read in two places: on the site, and as files in the repository.
A link that works in one can break in the other, and nothing fails when it
does. What is pinned here is what keeps both working: no link climbs out of
docs/, since the site has nothing above it; every link between pages names a
page and a heading that exist; every page has an address and a place in the
menu; and the links into the site from the README and from PyPI name
addresses the site has.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
CONFIG = DOCS / "_config.yml"
SITE = "https://aywrite.github.io/mache/"
PAGES = sorted(DOCS.glob("*.md"))

# a markdown link, and where it goes
LINK = re.compile(r"\]\(([^)\s]+)\)")


def slug(heading):
    """The anchor GitHub gives a heading. Kramdown, which builds the site,
    gives the same one for the headings these pages have."""
    text = re.sub(r"[`*_]", "", heading.strip().lower())
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(path):
    text = path.read_text(encoding="utf-8")
    # headings inside code blocks are not headings
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    return {
        slug(line.lstrip("#")) for line in text.splitlines() if line.startswith("#")
    }


def configured():
    """Each page the config places, with the permalink it gives it."""
    text = CONFIG.read_text(encoding="utf-8")
    found = {}
    for path, values in re.findall(r"path: ([^}]*)}\n\s+values: {([^}]*)}", text):
        if not path.strip().endswith(".md"):
            # the default every page takes, which is not a page
            continue
        permalink = re.search(r"permalink: (\S+?),", values)
        found[path.strip()] = (
            permalink.group(1) if permalink else "/",
            "nav_order" in values,
        )
    return found


def test_there_are_pages():
    assert len(PAGES) >= 8, [page.name for page in PAGES]


@pytest.mark.parametrize("page", PAGES, ids=lambda page: page.name)
def test_no_link_climbs_out_of_the_site(page):
    for target in LINK.findall(page.read_text(encoding="utf-8")):
        assert not target.startswith("../"), f"{page.name} links to {target}"


@pytest.mark.parametrize("page", PAGES, ids=lambda page: page.name)
def test_every_link_between_pages_finds_its_page_and_heading(page):
    for target in LINK.findall(page.read_text(encoding="utf-8")):
        if re.match(r"[a-z]+:", target):
            continue
        name, _, anchor = target.partition("#")
        linked = DOCS / name if name else page
        assert linked.exists(), f"{page.name} links to {target}, which is not a page"
        if anchor:
            assert anchor in anchors(linked), f"{page.name} links to {target}"


@pytest.mark.parametrize("page", PAGES, ids=lambda page: page.name)
def test_every_page_has_an_address_and_a_place_in_the_menu(page):
    placed = configured()
    assert page.name in placed, f"{page.name} is not in docs/_config.yml"
    assert placed[page.name][1], f"{page.name} has no nav_order"


def test_no_two_pages_share_an_address():
    permalinks = [permalink for permalink, _ in configured().values()]
    assert len(permalinks) == len(set(permalinks))


@pytest.mark.parametrize(
    "path", [ROOT / "README.md", ROOT / "pyproject.toml"], ids=lambda p: p.name
)
def test_links_into_the_site_name_pages_it_has(path):
    addresses = {SITE + permalink.lstrip("/") for permalink, _ in configured().values()}
    found = re.findall(re.escape(SITE) + r"[^)\s\"]*", path.read_text("utf-8"))
    assert found, f"{path.name} does not link to the site"
    for url in found:
        assert url.split("#")[0] in addresses, f"{path.name} links to {url}"


def test_the_readme_links_to_every_page():
    # the README is what GitHub and PyPI show, so it is the way in
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for permalink, _ in configured().values():
        assert SITE + permalink.lstrip("/") in readme, permalink
