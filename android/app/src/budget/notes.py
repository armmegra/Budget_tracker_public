"""Parses raw notes into periods, days and entries: dates, amounts, income, a
refund written inline, the closing line, and the marker that ends a month.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from decimal import Decimal

from budget import grammar
from budget.rules import RULES

__all__ = ["Entry", "Block", "Balances", "Day", "Period", "parse", "reassign_deferred",
           "arrived", "without"]

GRAMMAR = grammar.build(RULES.get("notes", {}))


_PERIOD_BREAK = re.compile(r"^#{3,}\s*$")

_DIVIDER = re.compile(r"^-{3,}\s*$")

_DATE = re.compile(r"^(\d{2})\.(\d{2})\s*$")

_ENTRY = re.compile(
    r"^(?P<income>\+\s*)?"
    r"(?P<digits>\d{1,3}(?:\s+\d{3})+|\d+)"
    r"\s*(?P<text>.*?)\s*$"
)

_GROUPING = re.compile("[    ]")

_BALANCE = GRAMMAR.balance

_DEFERRED = GRAMMAR.deferred

_REFERS_TO = GRAMMAR.refers_to

MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December")


def month_of(period: Period) -> str:
    if not period.dates:
        return "undated"
    tally: dict[str, int] = {}
    for date in period.dates:
        month = date.split(".")[1]
        tally[month] = tally.get(month, 0) + 1
    dominant = max(tally, key=lambda m: (tally[m], -int(m)))
    try:
        return MONTH_NAMES[int(dominant) - 1]
    except (ValueError, IndexError):
        return dominant

_MARKER = GRAMMAR.marker

_INSTANT_REFUND = GRAMMAR.instant_refund

_INLINE_DEDUCTION = re.compile(r"^-\s*(\d+)\s+")

_ANNOTATION = re.compile(r"^[^\d+]")

_COMMA_DECIMAL = re.compile(r"(?<=\d),(?=\d)")

_ASIDE = re.compile(r"\([^)]*\)")

_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)


def _int(text: str) -> int | None:
    match = re.search(r"-?\s*\d[\d ]*", text)
    return int(match.group().replace(" ", "")) if match else None


def _decimal(text: str) -> Decimal | None:
    match = re.search(r"-?\s*\d+(?:\.\d+)?", text)
    return Decimal(match.group().replace(" ", "")) if match else None


_NUMBER = re.compile(r"-?\s*\d[\d ]*(?:\.\d+)?")


def _figure(text: str) -> Decimal | None:
    match = _NUMBER.search(text)
    return Decimal(match.group().replace(" ", "")) if match else None


@dataclass(frozen=True)
class Entry:
    raw: str
    amount: int
    text: str
    income: bool
    deferred: bool

    @property
    def signed(self) -> int:
        return -self.amount if self.income else self.amount

    @property
    def refers_to(self) -> str | None:
        found = _REFERS_TO.search(self.text)
        return GRAMMAR.month_of(found.group(1), MONTH_NAMES) if found else None

    @property
    def bare(self) -> bool:
        return not self.text

    @classmethod
    def read(cls, line: str) -> Entry | None:
        match = _ENTRY.match(line)
        if not match:
            return None
        text = match.group("text")
        refunded = _INSTANT_REFUND.search(text)
        deducted = _INLINE_DEDUCTION.match(text)
        if deducted:
            text = text[deducted.end() :]
        if text and not _LETTER.search(text):
            return None
        return cls(
            raw=line,
            amount=int(_GROUPING.sub("", match.group("digits")))
            - (int(refunded.group(1)) if refunded else 0)
            - (int(deducted.group(1)) if deducted else 0),
            text=text,
            income=match.group("income") is not None,
            deferred=bool(_DEFERRED.search(text)),
        )


@dataclass(frozen=True)
class Block:
    entries: tuple[Entry, ...]

    def __iter__(self):
        return iter(self.entries)

    def __len__(self) -> int:
        return len(self.entries)


@dataclass(frozen=True)
class Balances:
    values: tuple[Decimal | None, ...]
    raw: str
    fields: tuple[str, ...] = ()

    @classmethod
    def read(cls, body: str, raw: str) -> Balances | None:
        fields = tuple(_COMMA_DECIMAL.sub(".", _ASIDE.sub("", body)).split(","))
        values = tuple(_figure(f) for f in fields)
        if len(fields) < 5 and not (len(fields) >= 2 and all(v is not None for v in values)):
            return None
        if len(fields) >= 5 and any(v is None for v in values[:5]):
            return None
        return cls(values=values, raw=raw, fields=fields)


@dataclass
class Day:
    date: str | None = None
    blocks: list[Block] = field(default_factory=list)
    balances: Balances | None = None
    unparsed: list[str] = field(default_factory=list)

    @property
    def entries(self) -> list[Entry]:
        return [entry for block in self.blocks for entry in block.entries]


@dataclass
class Period:
    days: list[Day] = field(default_factory=list)

    @property
    def entries(self) -> list[Entry]:
        return [entry for day in self.days for entry in day.entries]

    @property
    def blocks(self) -> list[Block]:
        return [block for day in self.days for block in day.blocks]

    @property
    def dates(self) -> list[str]:
        return [day.date for day in self.days if day.date]

    @property
    def unparsed(self) -> list[str]:
        return [line for day in self.days for line in day.unparsed]

    @property
    def deferred(self) -> list[Entry]:
        return [entry for entry in self.entries if entry.deferred]


def arrived(entry: Entry) -> Entry:
    return replace(entry, text=_MARKER.sub("", entry.text).strip(), deferred=False)


def without(period: Period, gone: list[Entry]) -> Period:
    days = []
    for day in period.days:
        blocks = []
        for block in day.blocks:
            staying = tuple(e for e in block.entries if not any(e is g for g in gone))
            if staying:
                blocks.append(Block(staying))
        days.append(Day(day.date, blocks, day.balances, list(day.unparsed)))
    return Period(days)


def reassign_deferred(periods: list[Period]) -> list[Period]:
    rebuilt: list[Period] = []
    incoming: list[list[Entry]] = [[] for _ in periods]
    by_month = {month_of(p): i for i, p in enumerate(periods)}

    def destination(entry: Entry, index: int) -> int | None:
        named = entry.refers_to
        if named is not None:
            target = by_month.get(named)
            return target if target is not None and target != index else None
        return index - 1 if index > 0 else None

    for index, period in enumerate(periods):
        days = []
        for day in period.days:
            blocks = []
            for block in day.blocks:
                movers = [
                    entry for entry in block.entries
                    if entry.deferred and destination(entry, index) is not None
                ]
                if not movers:
                    blocks.append(block)
                    continue
                staying = tuple(e for e in block.entries if e not in movers)
                for entry in movers:
                    incoming[destination(entry, index)].append(arrived(entry))
                if staying:
                    blocks.append(Block(staying))
            days.append(Day(day.date, blocks, day.balances, list(day.unparsed)))
        rebuilt.append(Period(days))

    for index, entries in enumerate(incoming):
        if not entries or not rebuilt[index].days:
            continue
        rebuilt[index].days[-1].blocks.extend(Block((entry,)) for entry in entries)

    return rebuilt


def parse(text: str) -> list[Period]:
    periods: list[Period] = []
    current = Period()
    day: Day | None = None
    pending: list[Entry] = []
    seen: str | None = None

    def flush_block() -> None:
        nonlocal pending
        if day is not None and pending:
            day.blocks.append(Block(tuple(pending)))
        pending = []

    def close_day() -> None:
        nonlocal day
        flush_block()
        if day is None:
            return
        if day.date is not None:
            for index, existing in enumerate(current.days):
                if existing.date == day.date:
                    if len(day.entries) >= len(existing.entries):
                        current.days[index] = day
                    day = None
                    return
        current.days.append(day)
        day = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            flush_block()
            continue
        prior_line, seen = seen, line

        if _PERIOD_BREAK.match(line):
            close_day()
            if current.days:
                periods.append(current)
            current = Period()
            continue

        if _DIVIDER.match(line):
            continue

        if _DATE.match(line):
            close_day()
            day = Day(date=line)
            continue

        if day is None:
            day = Day()

        balance_match = _BALANCE.match(line)
        if balance_match:
            flush_block()
            day.balances = Balances.read(balance_match.group("body"), line)
            if day.balances is None:
                day.unparsed.append(line)
            continue

        if _ANNOTATION.match(line):
            continue

        entry = Entry.read(line)
        if entry is None:
            day.unparsed.append(line)
            continue
        if entry.bare and day.unparsed and day.unparsed[-1] == prior_line:
            day.unparsed.append(line)
            continue
        pending.append(entry)

    close_day()
    if current.days:
        periods.append(current)
    return periods
