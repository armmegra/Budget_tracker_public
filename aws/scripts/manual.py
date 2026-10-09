"""Render docs/GUIDE.md as one self-contained HTML page, ready to print.

    python scripts/manual.py                 -> web/guide.html
    python scripts/manual.py --dark          -> the same, on a dark ground

Then, for a PDF (Chrome is already here for the browser tests):

    chrome --headless=new --disable-gpu --no-pdf-header-footer
           --print-to-pdf=docs/GUIDE.pdf web/guide.html

It lands in `web/` because the app serves it: the page's `?` links to
`guide.html` beside it, and the frontend module uploads it to the bucket next
to index.html. One rendered copy, so there is nothing to drift -
`tests/test_manual.py` fails if the committed file is not what GUIDE.md
renders to today.

Not a Markdown library. It handles the constructs GUIDE.md actually uses -
headings, paragraphs, bullets, numbered lists, fenced code, tables, rules, bold,
italic, inline code and links - and nothing else, on purpose. A construct it
does not cover renders as the text it was, which for a manual is the right
failure and for a repository with no dependencies is the right trade.
`tests/test_manual.py` is the list, and fails if the guide grows a construct
this does not know.

The heading ids are slugs of the heading text, matching the anchors the guide's
own contents list already uses. `tests/test_manual.py` checks every one of them
resolves - a contents list whose links go nowhere is worse than none.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "GUIDE.md"
OUT = ROOT / "web" / "guide.html"

# Light by default: a manual is read at length and printed, and twenty pages of
# dark ground is a lot of toner. --dark is for reading on a screen.
THEME = {
    "light": {
        "bg": "#ffffff", "ink": "#1c1c1e", "dim": "#5c5c62", "rule": "#e0e0e4",
        "panel": "#f6f6f4", "accent": "#2f6f4e", "code": "#8a3b2f",
    },
    "dark": {
        "bg": "#1b1c18", "ink": "#f2f2ee", "dim": "#9a9b90", "rule": "#3b3d31",
        "panel": "#232418", "accent": "#a6e22e", "code": "#e6db74",
    },
}


def slug(words: str) -> str:
    """The anchor a heading gets - the same rule GitHub uses, which is what the
    guide's own contents list was written against."""
    return re.sub(r"[^a-z0-9 -]", "", words.lower()).replace(" ", "-")


def inline(text: str) -> str:
    """Escape first, then the span-level marks. Order matters: code spans are
    taken before bold, so a `**` inside backticks stays literal."""
    out = html.escape(text, quote=False)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?!\w)", r"<i>\1</i>", out)
    out = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', out)
    return out


def _table(rows: list[str]) -> str:
    """A pipe table. Row two is the dashes, and says nothing this needs."""
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    head, body = cells[0], cells[2:]
    out = ["<table><thead><tr>"]
    out += [f"<th>{inline(c)}</th>" for c in head]
    out.append("</tr></thead><tbody>")
    for row in body:
        out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def to_html(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]

        if line.startswith("```"):
            block = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(html.escape(lines[i], quote=False))
                i += 1
            i += 1
            out.append("<pre><code>" + "\n".join(block) + "</code></pre>")
            continue

        if re.match(r"^#{1,4} ", line):
            level = len(line) - len(line.lstrip("#"))
            words = line[level:].strip()
            out.append(f'<h{level} id="{slug(words)}">{inline(words)}</h{level}>')
            i += 1
            continue

        if line.strip() in ("---", "***", "___"):
            out.append("<hr>")
            i += 1
            continue

        if line.lstrip().startswith("|"):
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(lines[i])
                i += 1
            out.append(_table(rows) if len(rows) > 2 else "<p>" + inline(" ".join(rows)) + "</p>")
            continue

        bullet = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if bullet:
            ordered = bullet.group(2)[0].isdigit()
            tag = "ol" if ordered else "ul"
            items: list[str] = []
            while i < len(lines):
                m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", lines[i])
                if m:
                    items.append(m.group(3))
                    i += 1
                elif lines[i].startswith(("  ", "\t")) and lines[i].strip() and items:
                    items[-1] += " " + lines[i].strip()   # a wrapped item
                    i += 1
                else:
                    break
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
            continue

        if not line.strip():
            i += 1
            continue

        para = []
        while i < len(lines) and lines[i].strip() and not re.match(
            r"^(#{1,4} |```|\||\s*([-*]|\d+\.)\s)", lines[i]
        ) and lines[i].strip() not in ("---", "***", "___"):
            para.append(lines[i].strip())
            i += 1
        out.append("<p>" + inline(" ".join(para)) + "</p>")
    return "\n".join(out)


def page(body: str, theme: str = "light") -> str:
    c = THEME[theme]
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Budget tracker — the guide</title>
<style>
  @page {{ size: A4; margin: 18mm 16mm; }}
  * {{ box-sizing: border-box; }}
  html {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  body {{
    margin: 0 auto; max-width: 42em; padding: 24px 20px 60px;
    background: {c['bg']}; color: {c['ink']};
    font: 11pt/1.62 "Segoe UI", -apple-system, system-ui, sans-serif;
  }}
  h1 {{ font-size: 22pt; margin: 0 0 4px; letter-spacing: -.01em; }}
  h2 {{
    font-size: 14pt; margin: 30px 0 10px; padding-bottom: 5px;
    border-bottom: 1px solid {c['rule']}; break-after: avoid;
  }}
  h3 {{ font-size: 11.5pt; margin: 20px 0 6px; break-after: avoid; }}
  p, li {{ margin: 0 0 9px; }}
  ul, ol {{ margin: 0 0 12px; padding-left: 22px; }}
  li {{ margin-bottom: 5px; }}
  a {{ color: {c['accent']}; text-decoration: none; border-bottom: 1px solid {c['rule']}; }}
  b {{ color: {c['ink']}; }}
  code {{
    font-family: "Cascadia Mono", Consolas, monospace; font-size: .88em;
    color: {c['code']}; background: {c['panel']}; padding: 1px 4px; border-radius: 3px;
  }}
  pre {{
    background: {c['panel']}; border: 1px solid {c['rule']}; border-radius: 5px;
    padding: 11px 13px; overflow-x: auto; break-inside: avoid; margin: 0 0 14px;
  }}
  pre code {{ background: none; padding: 0; color: {c['ink']}; font-size: .84em; line-height: 1.5; }}
  hr {{ border: 0; border-top: 1px solid {c['rule']}; margin: 26px 0; }}
  table {{
    border-collapse: collapse; width: 100%; margin: 0 0 14px;
    font-size: .92em; break-inside: avoid;
  }}
  th, td {{ text-align: left; vertical-align: top; padding: 6px 10px 6px 0; border-bottom: 1px solid {c['rule']}; }}
  th {{ color: {c['dim']}; font-weight: 600; }}
</style>
{body}
"""


if __name__ == "__main__":
    theme = "dark" if "--dark" in sys.argv else "light"
    OUT.write_text(page(to_html(SOURCE.read_text(encoding="utf-8")), theme), encoding="utf-8")
    print(f"{OUT}  ({OUT.stat().st_size / 1024:.0f} KB, {theme})")
