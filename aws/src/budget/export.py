"""The printouts: a month, a year or a comparison as RTF or plain text, laid out to
fit a page.
"""

from __future__ import annotations

from budget import speech
from budget.display import _major_lines, closing_left, compare_pages, minor_rows
from budget.groups import BASE, Taxonomy
from budget.left import DEFAULT_SLOTS, Slot
from budget.notes import Period, month_of

__all__ = ["compare_report", "month_report", "year_report", "PAGE_BREAK", "A4_COLUMNS"]

A4_COLUMNS = 100

PAGE_BREAK = "\f"

_UNDERLINE = "\u0332"


def _underline(text: str) -> str:
    return "".join(ch + _UNDERLINE for ch in text)


def _amount(value: int) -> str:
    return f"+{-value}" if value < 0 else str(value)


def _row(row: dict, mark) -> str:
    cells = []
    for value, src in zip(row["amounts"], row.get("marks") or [None] * len(row["amounts"])):
        shown = _amount(value)
        his = src and any(m.get("kind") in ("answered", "moved") for m in src)
        cells.append(mark(shown) if his else shown)
    return f"{row['name']}: {', '.join(cells) if cells else '—'}    : {row['total']}"


def _title(period: Period, span: str, year: int | None, lang: str = "en") -> str:
    name = speech.month_label(month_of(period), lang).capitalize()
    return f"{name} {year}" if year else name


def _pages(span: str, period: Period, results: list[dict], year: int | None,
           left_year: int, mark, fixed: dict[str, int] | None = None,
           tax: Taxonomy = BASE,
           omitted: set[str] | None = None,
           slots: tuple[Slot, ...] = DEFAULT_SLOTS,
           lang: str = "en") -> tuple[list[str], list[str]]:
    major_lines, tier1, occasional = _major_lines(results, fixed, tax, omitted, lang)
    head = _title(period, span, year, lang)

    first = [head, speech.month_label(span, lang), "",
             speech.say("major_groups_heading", lang, "MAJOR GROUPS (thousands)"), ""]
    first += major_lines
    first += ["", speech.say("total_line", lang, f"Total: {tier1}", x=tier1)]
    if occasional:
        tail = " + ".join(f"{name} {value}" for name, value in occasional)
        grand = tier1 + sum(v for _, v in occasional)
        first.append(speech.say("total_line_occasional", lang,
                                f"Total: {tier1} + {tail}: {grand}",
                                x=tier1, tail=tail, grand=grand))

    second = [speech.say("minor_groups_heading", lang, f"{head} - minor groups", title=head), ""]
    for row in minor_rows(results, tax):
        if "subgroups" in row:
            second.append(f"{row['name']}:")
            for sub in row["subgroups"]:
                second.append("    " + _row(sub, mark))
        else:
            second.append(_row(row, mark))

    left = closing_left(period, left_year, slots)
    if left:
        line = left["computed"]["text"] if "computed" in left else left["text"]
        second += ["", line]
    return first, second


def month_report(
    span: str,
    period: Period,
    results: list[dict],
    year: int | None,
    left_year: int,
    fmt: str = "txt",
    fixed: dict[str, int] | None = None,
    tax: Taxonomy = BASE,
    omitted: set[str] | None = None,
    *,
    slots: tuple[Slot, ...] = DEFAULT_SLOTS,
    lang: str = "en",
) -> str:
    first, second = _pages(span, period, results, year, left_year,
                           _rtf_underline if fmt == "rtf" else _underline, fixed, tax,
                           omitted, slots, lang)
    if fmt == "rtf":
        return _rtf_document([first, second])
    return "\n".join(first) + f"\n{PAGE_BREAK}" + "\n".join(second) + "\n"


def compare_report(
    columns: list[tuple],
    tax: Taxonomy = BASE,
    fmt: str = "txt",
    average: bool = False,
    title: str | None = None,
    lang: str = "en",
) -> str:
    if title is None:
        title = speech.say("comparison", lang, "Comparison")
    pages = compare_pages(columns, tax, average, per_page=A4_COLUMNS, lang=lang)
    laid: list[list[str]] = []
    for i, page in enumerate(pages, 1):
        head = title if len(pages) == 1 else speech.say(
            "page_of", lang, f"{title} - page {i} of {len(pages)}",
            title=title, i=i, n=len(pages),
        )
        laid.append([head, ""] + page.split("\n"))
    if fmt == "rtf":
        return _rtf_document(laid)
    return f"\n{PAGE_BREAK}".join("\n".join(p) for p in laid) + "\n"


def year_report(months: list[tuple], fmt: str = "txt",
                *, slots: tuple[Slot, ...] = DEFAULT_SLOTS, lang: str = "en") -> str:
    pages: list[list[str]] = []
    for span, period, results, year, left_year, fixed, omitted, tax, *own in months:
        first, second = _pages(span, period, results, year, left_year,
                               _rtf_underline if fmt == "rtf" else _underline, fixed, tax,
                               omitted, own[0] if own else slots, lang)
        pages += [first, second]
    if fmt == "rtf":
        return _rtf_document(pages)
    return f"\n{PAGE_BREAK}".join("\n".join(p) for p in pages) + "\n"


_RTF_HEAD = (
    r"{\rtf1\ansi\ansicpg1252\deff0"
    r"{\fonttbl{\f0\fmodern Consolas;}}"
    r"\paperw11906\paperh16838\margl851\margr851\margt851\margb851"
    "\n" r"\fs18" "\n"
)


def _rtf_escape(text: str) -> str:
    out = []
    for ch in text:
        if ch in "\\{}":
            out.append("\\" + ch)
        elif ord(ch) < 128:
            out.append(ch)
        else:
            code = ord(ch)
            out.append(f"\\u{code if code < 32768 else code - 65536}?")
    return "".join(out)


def _rtf_underline(text: str) -> str:
    return f"\x01{text}\x02"


def _rtf_document(pages: list[list[str]]) -> str:
    body = []
    for i, page in enumerate(pages):
        if i:
            body.append(r"\page")
        for line in page:
            escaped = _rtf_escape(line).replace("\x01", r"{\ul ").replace("\x02", "}")
            body.append(escaped + r"\par")
    return _RTF_HEAD + "\n".join(body) + "\n}"
