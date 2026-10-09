from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import manual


@pytest.fixture(scope="module")
def source() -> str:
    return manual.SOURCE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def rendered(source: str) -> str:
    return manual.to_html(source)


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        ("## Signing in", '<h2 id="signing-in">Signing in</h2>'),
        ("### The kinds, and why they matter",
         '<h3 id="the-kinds-and-why-they-matter">The kinds, and why they matter</h3>'),
        ("---", "<hr>"),
        ("Plain words.", "<p>Plain words.</p>"),
        ("A **bold** word.", "<p>A <b>bold</b> word.</p>"),
        ("Some `code` inline.", "<p>Some <code>code</code> inline.</p>"),
        ("- one\n- two", "<ul><li>one</li><li>two</li></ul>"),
        ("1. first\n2. second", "<ol><li>first</li><li>second</li></ol>"),
        ("```\nLeft: purse 6.8, account 61240\n```", "<pre><code>Left: purse 6.8, account 61240</code></pre>"),
        ("[The idea](#the-idea)", '<p><a href="#the-idea">The idea</a></p>'),
    ],
)
def test_the_renderer_handles_what_the_guide_is_written_in(
    markdown: str, expected: str
) -> None:
    assert manual.to_html(markdown) == expected


def test_a_table_becomes_a_table() -> None:
    out = manual.to_html("| What | It means |\n| --- | --- |\n| `11.01` | a date |")
    assert "<thead><tr><th>What</th><th>It means</th></tr></thead>" in out
    assert "<td><code>11.01</code></td><td>a date</td>" in out


def test_html_in_the_source_is_escaped_not_executed() -> None:
    assert manual.to_html("A <script>alert(1)</script> line") == (
        "<p>A &lt;script&gt;alert(1)&lt;/script&gt; line</p>"
    )
    assert "&lt;id token&gt;" in manual.to_html("`Bearer <id token>`")


def test_a_star_inside_a_word_is_not_italics() -> None:
    assert manual.to_html("320 mints*3 snacks") == "<p>320 mints*3 snacks</p>"


def test_every_construct_the_guide_uses_is_one_of_those(source: str) -> None:
    unknown = []
    fenced = False
    for line in source.splitlines():
        if line.startswith("```"):
            fenced = not fenced
            continue
        if fenced or not line.strip():
            continue
        if re.match(r"^(#{1,4} |[-*] |\d+\. |\||>)", line) or line.strip() in ("---",):
            continue
        if line.startswith(("  ", "\t")):
            continue
        if line.lstrip().startswith(("![", ">")):
            unknown.append(line)
            continue
        if re.match(r"^\S", line):
            continue
        unknown.append(line)
    assert not unknown, "constructs the renderer does not cover:\n" + "\n".join(unknown)


def test_every_link_in_the_contents_reaches_a_heading(source: str, rendered: str) -> None:
    ids = set(re.findall(r'<h[1-4] id="([^"]+)"', rendered))
    anchors = set(re.findall(r'\]\(#([a-z0-9-]+)\)', source))
    assert anchors, "the guide lost its contents list"
    assert anchors <= ids, f"anchors with no heading: {sorted(anchors - ids)}"


def test_the_whole_guide_renders_to_one_self_contained_page(rendered: str) -> None:
    page = manual.page(rendered)
    assert page.startswith("<!doctype html>")
    assert "<style>" in page and "</style>" in page
    assert not re.search(r'<(link|script|img|iframe)\b', page)
    assert 'url(' not in page
    assert "<h1" in page and page.count("<h2") > 10


def test_the_committed_page_is_what_the_guide_renders_to_today(rendered: str) -> None:
    assert manual.OUT.is_file(), f"{manual.OUT} is missing - run scripts/manual.py"
    assert manual.OUT.read_text(encoding="utf-8") == manual.page(rendered), (
        "web/guide.html is out of step with docs/GUIDE.md - run scripts/manual.py"
    )


def test_the_page_links_to_the_guide() -> None:
    page = (manual.ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert page.count('href="guide.html"') == 2, "the header and the empty-state banner"
    assert 'rel="noopener"' in page


def test_the_dark_theme_is_the_same_page_on_a_different_ground(rendered: str) -> None:
    light, dark = manual.page(rendered), manual.page(rendered, "dark")
    assert light != dark
    assert "#1b1c18" in dark and "#1b1c18" not in light
    strip = lambda s: re.sub(r"<style>.*?</style>", "", s, flags=re.S)
    assert strip(light) == strip(dark)
