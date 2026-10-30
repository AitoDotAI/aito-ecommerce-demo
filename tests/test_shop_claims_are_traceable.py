"""A measurement quoted in the Shop's settings must say which result file and which release it comes from.

The Shop's ⚙ panel states what held-out sweeps measured. Those sweeps ran on one data release; the demo
now serves another. A sentence that cites a result file but not the release reads as a claim about the
data on screen, and nobody can tell it has gone stale. So each paragraph that cites a file must exist
on disk, and must name the release it was measured on, or say it has not been run.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "frontend" / "components" / "shop" / "ShopSettings.tsx"
CITATION = re.compile(r"<code>([\w-]+\.md)</code>")
RELEASE = re.compile(r"release \d\w*", re.IGNORECASE)
NOT_RUN = re.compile(r"not (yet )?(been )?run", re.IGNORECASE)


def paragraphs_citing_a_file(source: str) -> list[tuple[str, str]]:
    """(file, the paragraph around its citation), paragraphs being what `<br />` separates."""
    found = []
    for paragraph in re.split(r"<br\s*/>", source):
        for name in CITATION.findall(paragraph):
            found.append((name, re.sub(r"\s+", " ", paragraph)))
    return found


def test_every_file_the_shop_settings_cite_exists():
    cited = paragraphs_citing_a_file(SETTINGS.read_text(encoding="utf-8"))

    assert cited, "the settings cite no result file; if the claims were removed, so can this test be"
    missing = [name for name, _ in cited if not list((ROOT / "docs").rglob(name))]
    assert missing == []


def test_every_paragraph_that_cites_a_file_names_its_release_or_says_it_has_not_been_run():
    untraceable = [name for name, paragraph in paragraphs_citing_a_file(SETTINGS.read_text(encoding="utf-8"))
                   if not (RELEASE.search(paragraph) or NOT_RUN.search(paragraph))]

    assert untraceable == [], f"cited without a release: {untraceable}"


def test_a_paragraph_that_cites_a_file_without_a_release_is_caught():
    source = "<div>It lost (<code>last-basket-prereg.md</code>).<br />Other.</div>"

    (name, paragraph), = paragraphs_citing_a_file(source)

    assert name == "last-basket-prereg.md"
    assert not (RELEASE.search(paragraph) or NOT_RUN.search(paragraph))
