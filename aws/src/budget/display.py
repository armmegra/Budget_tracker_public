"""Turns classified entries into what a person reads: the minor-group rows, the
bars, the two Totals, the closing Left line and the side-by-side comparison.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from budget import grammar, speech
from budget.classify import Classification, classify_period
from budget.groups import BASE, MAJORS, Taxonomy, Tier, major_for
from budget.left import DEFAULT_SLOTS, Slot, assemble, cells as left_cells, format_value
from budget.rules import RULES
from budget.money import to_thousands
from budget.notes import Period
from budget.totals import majors as major_totals, second_total, tier_totals

_ROLES = RULES["groups"]["roles"]
_UNLISTED = {_ROLES["rent_lump"], _ROLES["savings"], _ROLES["elsewhere"]}
_HIDDEN = _UNLISTED | {_ROLES["salary"]}

GRAMMAR = grammar.build(RULES.get("notes", {}))

__all__ = ["render", "compare", "pending", "minor_amounts", "minor_rows"]


def minor_amounts(results: list[Classification]) -> dict[str, list[int]]:
    amounts: dict[str, list[int]] = defaultdict(list)
    for c in results:
        if c.minor is not None:
            amounts[c.minor].append(c.entry.signed)
    return dict(amounts)


_PER_VISIT_WHOLE = set(RULES["display"]["per_visit_whole"])
_PER_VISIT_SERVICE = set(RULES["display"]["per_visit_service"])
_OUTING_RULES = {"occasional outing", "gift outing"}
_FARE_TEXT = GRAMMAR.fare_word


def _display_rows(
    results: list[Classification], tax: Taxonomy = BASE
) -> dict[str, list[dict]]:
    seen: dict[str, int] = {}
    occurrence = []
    for c in results:
        n = seen.get(c.entry.raw, 0)
        seen[c.entry.raw] = n + 1
        occurrence.append(n)

    def kind(c) -> str:
        if c.rule == "answered by the user":
            return "answered"
        if c.rule == "moved by the user":
            return "moved"
        return "rule"

    def source(pairs) -> list[dict] | None:
        marks = [
            {
                "raw": c.entry.raw,
                "occurrence": occurrence[i],
                "candidates": [tax.minor_label(n) for n in c.candidates],
                "kind": kind(c),
                "date": c.date,
            }
            for i, c in pairs
        ]
        return marks or None

    per: dict[str, list] = defaultdict(list)
    for i, c in enumerate(results):
        if c.minor is not None:
            per[c.minor].append((i, c))

    styled: dict[str, str] = {name: "service" for name in _PER_VISIT_SERVICE}
    styled.update({name: "whole" for name in _PER_VISIT_WHOLE})
    for c in results:
        if c.minor and c.rule in _OUTING_RULES and c.minor not in styled:
            styled[c.minor] = "whole"

    out: dict[str, list[dict]] = {}
    for name, items in per.items():
        style = styled.get(name)
        rows: list[dict] = []
        if style is None:
            for i, c in items:
                rows.append({"v": c.entry.signed, "src": source([(i, c)])})
        else:
            for block in dict.fromkeys(c.block for _, c in items):
                visit = [(i, c) for i, c in items if c.block == block]
                if style == "whole":
                    rows.append(
                        {"v": sum(c.entry.signed for _, c in visit), "src": source(visit)}
                    )
                    continue
                fares = [
                    (i, c)
                    for i, c in visit
                    if c.entry.bare or _FARE_TEXT.search(c.entry.text)
                ]
                for i, c in visit:
                    if (i, c) not in fares:
                        rows.append({"v": c.entry.signed, "src": source([(i, c)])})
                if fares:
                    rows.append(
                        {"v": sum(c.entry.signed for _, c in fares), "src": source(fares)}
                    )
        out[name] = rows
    return out


def minor_rows(results: list[Classification], tax: Taxonomy = BASE) -> list[dict]:
    display = _display_rows(results, tax)
    rows = []
    seen: set[str] = set()

    def entry(name: str, label: str | None = None) -> dict:
        cells = display.get(name, [])
        return {
            "name": label or tax.minor_label(name),
            "amounts": [c["v"] for c in cells],
            "marks": [c["src"] for c in cells],
            "total": sum(c["v"] for c in cells),
        }

    for name in tax.minor_order:
        if name in tax.nested:
            subs = []
            for label, key in tax.nested[name]:
                seen.add(key)
                subs.append(entry(key, label))
            rows.append(
                {
                    "name": tax.major_label(name),
                    "subgroups": subs,
                    "total": sum(s["total"] for s in subs),
                }
            )
        else:
            seen.add(name)
            rows.append(entry(name))

    for name in sorted(set(display) - seen):
        if name in _UNLISTED:
            continue
        rows.append(entry(name))
    return rows


def _shown(values: list[int]) -> str:
    return ", ".join(f"+{-v}" if v < 0 else str(v) for v in values) if values else "—"


def _minor_lines(results: list[Classification], tax: Taxonomy = BASE) -> list[str]:
    lines = []
    for row in minor_rows(results, tax):
        if "subgroups" in row:
            lines.append(f"{row['name']}:")
            for sub in row["subgroups"]:
                lines.append(f"    {sub['name']}: {_shown(sub['amounts'])}    : {sub['total']}")
        else:
            lines.append(f"{row['name']}: {_shown(row['amounts'])}    : {row['total']}")
    return lines


def _signed(value: Decimal) -> str:
    return f"+{-value}" if value < 0 else f"{value}"


def _major_lines(
    results: list[Classification],
    fixed: dict[str, int] | None = None,
    tax: Taxonomy = BASE,
    omitted: set[str] | None = None,
    lang: str = "en",
) -> tuple[list[str], Decimal, list[tuple[str, Decimal]]]:
    totals = major_totals(results, fixed, tax)
    known = {m.name: m for m in tax.majors}
    ordered = [m.name for m in tax.majors if m.tier is not Tier.EXCLUDED]
    ordered += [n for n in totals if n not in known]
    lines, tier1, occasional = [], Decimal("0"), []
    for name in ordered:
        if name in _HIDDEN:
            continue
        if name in known and known[name].tier is Tier.EXCLUDED:
            continue
        value = totals.get(name, Decimal(0))
        major = known.get(name)
        shown = tax.major_label(name)
        if value == 0 and name not in totals:
            lines.append(f"{shown}: —")
        elif major and major.tier is Tier.NECESSARY:
            limit = ""
            if major.limit:
                excess = value - major.limit
                verdict = (
                    speech.say("over_by", lang, f"over by {excess}", x=excess)
                    if excess > 0
                    else speech.say("under_by", lang, f"{-excess} left", x=-excess)
                )
                limit = f" / {major.limit}  ({verdict})"
            lines.append(f"{shown}: {_signed(value)}{limit}")
            tier1 += value
        else:
            lines.append(f"{shown}: {_signed(value)}")
            if not (omitted and name in omitted):
                occasional.append((shown, value))
    return lines, tier1, occasional


def render(
    span: str,
    period: Period,
    results: list[Classification],
    year: int | None = None,
    fixed: dict[str, int] | None = None,
    tax: Taxonomy = BASE,
    omitted: set[str] | None = None,
    *,
    slots: tuple[Slot, ...] = DEFAULT_SLOTS,
) -> str:
    if year is None:
        import datetime

        year = datetime.date.today().year
    out = [f"=== {span} ===", "", "-- minor groups --", *_minor_lines(results, tax)]
    major_lines, tier1, occasional = _major_lines(results, fixed, tax, omitted)
    out += ["", "-- major groups (thousands) --", *major_lines]
    out += ["", f"Total: {tier1}"]
    if occasional:
        tail = " + ".join(f"{name} {value}" for name, value in occasional)
        out.append(f"Total: {tier1} + {tail}: {tier1 + sum(v for _, v in occasional)}")
    left = closing_left(period, year, slots)
    if left:
        line = left["computed"]["text"] if "computed" in left else left["raw"]
        note = (
            f"  (recounted: {left['date']}'s Left + {left['days_after']} newer days)"
            if "computed" in left
            else ""
        )
        out += ["", line + note]
    open_questions = pending(results)
    out += ["", f"unanswered questions: {len(open_questions)}  (see: questions)"]
    return "\n".join(out)


def compare(
    columns: list[tuple[str, list[Classification]]],
    tax: Taxonomy = BASE,
    average: bool = False,
    lang: str = "en",
) -> str:
    return "\n".join(compare_pages(columns, tax, average, lang=lang))


def compare_pages(
    columns: list[tuple[str, list[Classification]]],
    tax: Taxonomy = BASE,
    average: bool = False,
    per_page: int | None = None,
    lang: str = "en",
) -> list[str]:
    fixes = [c[2] if len(c) > 2 else None for c in columns]
    taxes = [c[3] if len(c) > 3 else tax for c in columns]
    marks = [c[4] if len(c) > 4 else ((), {}) for c in columns]
    per_period = [
        (c[0], major_totals(c[1], f, t)) for c, f, t in zip(columns, fixes, taxes)
    ]
    tiers_per_period = [
        tier_totals(c[1], f, t) for c, f, t in zip(columns, fixes, taxes)
    ]
    ends = [
        (t.necessary, second_total(t, x, m[0], m[1], _HIDDEN))
        for t, x, m in zip(tiers_per_period, taxes, marks)
    ]
    names: list[str] = []
    for _, totals in per_period:
        names += [n for n in totals if n not in names and n not in _HIDDEN]
    tiers = {m.name: m.tier for m in tax.majors}
    names.sort(
        key=lambda n: (
            tiers.get(n, Tier.OCCASIONAL) is not Tier.NECESSARY,
            tiers.get(n, Tier.OCCASIONAL) is Tier.EXCLUDED,
            -max(abs(t.get(n, Decimal(0))) for _, t in per_period),
        )
    )

    width = max(len(tax.major_label(n)) for n in names) + 2
    total_rows = (
        (speech.say("total", lang, "Total"), 0),
        (speech.say("total_occasional", lang, "Total + occasional"), 1),
    )
    if lang != "en":
        width = max([width] + [len(label) + 2 for label, _ in total_rows])
    cols = [max(14, len(label) + 2) for label, _ in per_period]

    if per_page is None:
        chunks = [list(range(len(per_period)))]
    else:
        chunks, room = [], []
        for i, w in enumerate(cols):
            if room and width + sum(cols[j] for j in room) + w > per_page:
                chunks.append(room)
                room = []
            room.append(i)
        chunks.append(room)

    deltas = len(per_period) == 2 and len(chunks) == 1

    pages = []
    for chunk in chunks:
        out = [
            f"{'':<{width}}"
            + "".join(f"{per_period[i][0]:>{cols[i]}}" for i in chunk)
            + (f"{speech.say('delta', lang, 'delta'):>10}" if deltas else "")
        ]
        for name in names:
            cells = ""
            for i in chunk:
                value = per_period[i][1].get(name)
                cells += f"{value if value is not None else '-':>{cols[i]}}"
            row = f"{tax.major_label(name):<{width}}{cells}"
            if deltas:
                a, b = (t.get(name) for _, t in per_period)
                if a is not None and b is not None:
                    row += f"{b - a:>+10.1f}"
            out.append(row)

        out.append("")
        for label, at in total_rows:
            cells = "".join(f"{ends[i][at]:>{cols[i]}}" for i in chunk)
            row = f"{label:<{width}}{cells}"
            if deltas:
                a, b = (e[at] for e in ends)
                row += f"{b - a:>+10.1f}"
            out.append(row)
        pages.append(out)

    if average and ends:
        n = len(ends)
        tails = {label.rsplit(" ", 1)[-1] for label, _ in per_period}
        named, year = "", None
        if len(tails) == 1:
            tail = next(iter(tails))
            if tail.isdigit():
                named, year = f" of {tail}", tail
        out = pages[-1]
        out.append("")
        out.append(speech.say(
            "average_of_year" if named else "average_of", lang,
            f"Average of {n} month{'' if n == 1 else 's'}{named}", n=n, year=year,
        ))
        for label, at in total_rows:
            mean = sum((e[at] for e in ends), Decimal(0)) / n
            cell = str(mean.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
            out.append(f"{label:<{width}}{cell:>{cols[chunks[-1][0]]}}")
    return ["\n".join(page) for page in pages]


def pending(results: list[Classification]) -> list[tuple[int, Classification]]:
    return [(i, c) for i, c in enumerate(results) if not c.confident]


def day_windows(period, wanted: list[Classification]) -> list[dict]:
    days = []
    owner: dict[int, int] = {}
    counter = 0
    for at, day in enumerate(period.days):
        days.append(day)
        for _ in day.blocks:
            owner[counter] = at
            counter += 1
    marked: dict[int, set[int]] = {}
    by_words: dict[int, list[str]] = {}
    for c in wanted:
        at = owner.get(c.block)
        if at is None:
            at = next((i for i, day in enumerate(days)
                       if any(e is c.entry for e in day.entries)), None)
        if at is None:
            continue
        if any(e is c.entry for e in days[at].entries):
            marked.setdefault(at, set()).add(id(c.entry))
        else:
            by_words.setdefault(at, []).append(c.entry.raw)
    windows = []
    for at in sorted(set(marked) | set(by_words)):
        day = days[at]
        ids, words = marked.get(at, set()), list(by_words.get(at, []))
        lines = []
        for number, block in enumerate(day.blocks):
            if number:
                lines.append({"text": "", "this": False})
            for entry in block.entries:
                this = id(entry) in ids
                if not this and entry.raw in words:
                    words.remove(entry.raw)
                    this = True
                lines.append({"text": entry.raw, "this": this})
        lines += [{"text": text, "this": False} for text in day.unparsed]
        if day.balances is not None:
            lines.append({"text": day.balances.raw, "this": False})
        windows.append({"date": day.date, "lines": lines})
    return windows


def closing_left(period, year: int, slots: tuple[Slot, ...] = DEFAULT_SLOTS):
    last = None
    for day in period.days:
        if day.balances is not None:
            last = day
    if last is None:
        return None
    index = [d.date for d in period.days].index(last.date)
    after = [d for d in period.days[index + 1 :] if d.entries]
    b = last.balances
    out = {
        "raw": b.raw,
        "text": assemble(b.values, slots, b.fields),
        "cells": left_cells(b.values, slots, b.fields),
        "extra": max(0, len(b.values) - len(slots)),
        "date": last.date,
        "days_after": len(after),
    }
    if after:
        out["computed"] = _replay(b, after, year, slots)
    return out


def count_on(period, year: int, slots: tuple[Slot, ...], base) -> dict | None:
    if base is None or all(v is None for v in base):
        return None
    from decimal import Decimal

    from budget.notes import Balances

    days = [d for d in period.days if d.entries]
    b = Balances(values=tuple(None if v is None else Decimal(str(v)) for v in base),
                 raw="", fields=())
    shown = _replay(b, days, year, slots)
    return {"raw": "", "text": shown["text"], "cells": shown["cells"], "extra": 0,
            "date": None, "days_after": len(days), "counted_on": True}


def with_set(left: dict | None, slots: tuple[Slot, ...], set_here: dict) -> dict | None:
    if not set_here:
        return left
    if left is None:
        left = {"raw": "", "text": assemble([], slots), "cells": left_cells([], slots),
                "extra": 0, "date": None, "days_after": 0}
    shown = left["computed"] if "computed" in left else left
    by_id = {s.id: s for s in slots}
    for cell in shown["cells"]:
        slot = by_id.get(cell.get("id"))
        if slot is None or cell["id"] not in set_here:
            continue
        value = set_here[cell["id"]]
        cell["noted"] = cell["figure"]
        cell["set"] = True
        cell["value"] = float(value)
        cell["figure"] = format_value(slot, value)
        cell["text"] = (
            f"{cell['figure']}{slot.join}{slot.label}" if slot.place == "after" and slot.label
            else f"{slot.label}{slot.join}{cell['figure']}" if slot.label
            else cell["figure"]
        )
    shown["text"] = assemble([c.get("value") for c in shown["cells"]], slots)
    return left


def _replay(b, days, year: int, slots: tuple[Slot, ...] = DEFAULT_SLOTS):
    import datetime

    values = [None if v is None else float(v) for v in b.values]

    def find(kind):
        return next((i for i, s in enumerate(slots) if s.kind == kind), None)

    card_i, cash_i = find("card"), find("cash")
    purses = [
        (i, s) for i, s in enumerate(slots)
        if s.kind == "purse" and i < len(values) and values[i] is not None
    ]

    def move(index, delta):
        if index is not None and index < len(values) and values[index] is not None:
            values[index] += delta

    for day in days:
        d, m = (int(x) for x in day.date.split("."))
        for i, slot in purses:
            reset = slot.reset or {}
            try:
                weekday = datetime.date(year, m, d).weekday()
            except ValueError:
                continue
            if weekday == int(reset.get("weekday", 0)):
                amount = float(reset.get("amount", 0))
                values[i] = (
                    amount + min(values[i], 0.0)
                    if reset.get("carry_deficit", True)
                    else amount
                )
        for c in classify_period(Period(days=[day])):
            amount = c.entry.signed
            minor = c.minor or ""
            major = major_for(minor)
            name = major.name if major else minor
            for i, slot in purses:
                if minor in slot.minors:
                    values[i] -= amount / 1000
            if minor in (_ROLES["salary"], _ROLES["reimbursements"]) or name == _ROLES["savings"]:
                move(card_i, -amount)
            elif name == _ROLES["withdrawal"]:
                move(card_i, -amount)
                move(cash_i, amount / 1000)
            elif GRAMMAR.on_card(c.entry.text):
                move(card_i, -amount)
            else:
                move(cash_i, -amount / 1000)

    for i, slot in enumerate(slots):
        if i < len(values) and values[i] is not None and slot.decimals:
            values[i] = round(values[i], slot.decimals)

    out = {
        "cells": left_cells(values, slots, b.fields),
        "text": assemble(values, slots, b.fields),
    }
    out["raw"] = out["text"]
    return out
