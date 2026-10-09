"""Renders the user guide (Markdown) into the page the app serves."""

from __future__ import annotations

import html
import re
from pathlib import Path

__all__ = ["DOCS", "render", "picture"]

HERE = Path(__file__).resolve().parent
PICTURES = HERE / "guide"

DOCS = {
    "guide": {"en": "GUIDE.md", "ru": "GUIDE.ru.md"},
    "readme": {"en": "README.md", "ru": "README.ru.md"},
    "third-party": {"en": "THIRD-PARTY.md", "ru": "THIRD-PARTY.ru.md"},
}
_CROSS = {name: f"/{url}" for url, files in DOCS.items() for name in files.values()}

LANGS = ("en", "ru")
NAMES = {"en": "English", "ru": "Русский"}
_NAV = {
    "en": ("Back to the app", "Guide", "Running it", "What is bundled"),
    "ru": ("Вернуться в приложение", "Справка", "Как запустить", "Сторонние программы"),
}

_SHELL = """<!doctype html>
<html lang="{lang}"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ --ink: #1c1c1e; --dim: #6b6b70; --rule: #d3d3d8; --bg: #fbfbfa;
           --card: #ffffff; --accent: #3f9d5a; --code: #f1f1ee; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --ink: #ececf0; --dim: #9a9aa2; --rule: #34343a; --bg: #161618;
             --card: #1e1e21; --accent: #4fbf88; --code: #26262a; }} }}
  body {{ margin: 0; background: var(--bg); color: var(--ink);
          font: 15.5px/1.6 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
  main {{ max-width: 46rem; margin: 0 auto; padding: 32px 22px 80px; }}
  h1 {{ font-size: 28px; margin: 0 0 12px; }}
  h2 {{ font-size: 21px; margin: 36px 0 10px; padding-top: 8px; border-top: 1px solid var(--rule); }}
  h3 {{ font-size: 16.5px; margin: 24px 0 6px; }}
  h4 {{ font-size: 15.5px; margin: 18px 0 6px; }}
  p, li {{ margin: 0 0 10px; }}
  ul {{ padding-left: 22px; }}
  hr {{ border: 0; border-top: 1px solid var(--rule); margin: 22px 0; }}
  a {{ color: var(--accent); }}
  code {{ font: 13.5px/1.5 Consolas, "Cascadia Mono", Menlo, monospace;
          background: var(--code); padding: 1px 5px; border-radius: 4px; }}
  pre {{ background: var(--code); padding: 12px 14px; border-radius: 8px;
         overflow-x: auto; margin: 0 0 14px; }}
  pre code {{ background: none; padding: 0; }}
  img {{ max-width: 100%; height: auto; border: 1px solid var(--rule);
         border-radius: 8px; margin: 6px 0 16px; display: block; }}
  table {{ border-collapse: collapse; margin: 0 0 16px; width: 100%; }}
  th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--rule);
            vertical-align: top; }}
  th {{ color: var(--dim); font-weight: 500; font-size: 13.5px; }}
  .top {{ font-size: 13px; color: var(--dim); margin-bottom: 18px; }}
</style>
</head><body><main>
<p class="top"><a href="/">{back}</a> ·
  <a href="/guide">{guide}</a> · <a href="/readme">{readme}</a> ·
  <a href="/third-party">{bundled}</a>{others}</p>
{body}
</main></body></html>
"""

_HEADING = re.compile(r"^(#{1,4}) (.+?)\s*$")
_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<![*\w])\*([^*\n]+?)\*(?![*\w])")
_CODE = re.compile(r"`([^`]+)`")


def render(name: str, lang: str = "en") -> str | None:
    files = DOCS.get(name)
    if files is None:
        return None
    lang = lang if lang in LANGS else "en"
    file, text_lang = files.get(lang), lang
    if file is None or not (HERE / file).is_file():
        file, text_lang = files["en"], "en"
        if not (HERE / file).is_file():
            return None
    text = (HERE / file).read_text(encoding="utf-8")
    title = next((m.group(2) for line in text.splitlines()
                  if (m := _HEADING.match(line)) and m.group(1) == "#"), file)
    body = _blocks(text)
    if text_lang != lang:
        body = f'<div lang="{text_lang}">\n{body}\n</div>'
    back, guide, readme, bundled = _NAV[lang]
    others = "".join(
        f' · <a href="?lang={code}" lang="{code}" hreflang="{code}">{NAMES[code]}</a>'
        for code in LANGS if code != lang)
    return _SHELL.format(lang=lang, title=html.escape(title), back=back, guide=guide,
                         readme=readme, bundled=bundled, others=others, body=body)


def picture(name: str) -> Path | None:
    if "/" in name or "\\" in name or not name.lower().endswith(".png"):
        return None
    target = (PICTURES / name).resolve()
    if target.parent != PICTURES.resolve() or not target.is_file():
        return None
    return target


def _blocks(text: str) -> str:
    out: list[str] = []
    lines = text.splitlines()
    i = 0
    para: list[str] = []

    def flush() -> None:
        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>")
            para.clear()

    while i < len(lines):
        line = lines[i]

        if line.startswith("```"):
            flush()
            i += 1
            code = []
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i])
                i += 1
            out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
            i += 1
            continue

        if line.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(lines[i])
                i += 1
            out.append(_table(rows))
            continue

        if line.startswith("- "):
            flush()
            items: list[str] = []
            while i < len(lines) and (lines[i].startswith("- ") or lines[i].startswith("  ")):
                if lines[i].startswith("- "):
                    items.append(lines[i][2:])
                elif items:
                    items[-1] += " " + lines[i].strip()
                i += 1
            out.append("<ul>" + "".join(f"<li>{_inline(item)}</li>" for item in items) + "</ul>")
            continue

        heading = _HEADING.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            words = heading.group(2)
            out.append(f'<h{level} id="{_slug(words)}">{_inline(words)}</h{level}>')
            i += 1
            continue

        if re.match(r"^-{3,}\s*$", line):
            flush()
            out.append("<hr>")
            i += 1
            continue

        if not line.strip():
            flush()
            i += 1
            continue

        para.append(line.strip())
        i += 1

    flush()
    return "\n".join(out)


def _table(rows: list[str]) -> str:
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    body = [r for k, r in enumerate(cells) if not (k == 1 and all(set(c) <= set("-: ") for c in r))]
    if not body:
        return ""
    head, rest = body[0], body[1:]
    thead = "" if not any(head) else (
        "<thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in head) + "</tr></thead>")
    if not any(head):
        rest = body[1:] if len(body) > 1 else []
    trs = "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in rest)
    return f"<table>{thead}<tbody>{trs}</tbody></table>"


def _slug(words: str) -> str:
    plain = re.sub(r"[^\w\s-]", "", words.lower())
    return re.sub(r"\s+", "-", plain.strip())


def _inline(text: str) -> str:
    held: list[str] = []

    def keep(m: re.Match) -> str:
        held.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00{len(held) - 1}\x00"

    text = _CODE.sub(keep, text)
    text = html.escape(text, quote=False)
    text = _IMAGE.sub(lambda m: f'<img alt="{m.group(1)}" src="{m.group(2)}">', text)
    text = _LINK.sub(lambda m: f'<a href="{_href(m.group(2))}">{m.group(1)}</a>', text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: held[int(m.group(1))], text)


def _href(target: str) -> str:
    base, _, fragment = target.partition("#")
    if base in _CROSS:
        return _CROSS[base] + ("#" + fragment if fragment else "")
    return target
