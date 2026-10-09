"""What is kept: the months as written, the answers, moves, ticks and set figures,
and the configuration edits with the month each starts from. Also backup and
restore. Figures are never stored - every total is worked out from the notes.
"""

from __future__ import annotations

import calendar
import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from budget.classify import TAUGHT, Classification, ruled_group, taught_group
from budget.groups import compose, effective, words_of
from budget.notes import (MONTH_NAMES, Block, Day, Period, arrived, month_of, parse,
                          reassign_deferred, without)
from budget.rules import RULES
from budget.speech import Month, Said

__all__ = ["Store", "answer_key", "apply_answers", "apply_taught", "month_of"]

_MARKER = re.compile(r"^#{3,}\s*$", re.MULTILINE)

STATE_FIELDS: tuple[str, ...] = (
    "periods",
    "answers",
    "years",
    "config",
    "config_versions",
    "omitted",
    "adjusted",
    "moves",
    "left_set",
    "left_start",
)

_MONTHS = {
    m.lower(): i
    for i, m in enumerate(
        ["January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"],
        1,
    )
}


def answer_key(identity: str, c: Classification, occurrence: int) -> str:
    return f"{identity}|{c.entry.raw}|{occurrence}"


def apply_taught(
    results: list[Classification],
    words: list[tuple[str, str]],
    resolve=None,
) -> list[Classification]:
    out = []
    for c in results:
        found = None if c.entry.deferred else taught_group(c.entry.text, words)
        if found is not None:
            group, word = found
            group = ruled_group(c.entry, group)
            if resolve is not None:
                group = resolve(group, c.entry) or group
            c = replace(c, minor=group, rule=TAUGHT + word, review=None, candidates=())
        out.append(c)
    return out


def apply_answers(
    results: list[Classification],
    answers: dict[str, str],
    identity: str,
    resolve=None,
    moves: dict[str, str] | None = None,
) -> list[Classification]:
    seen: dict[str, int] = {}
    out = []
    for c in results:
        n = seen.get(c.entry.raw, 0)
        seen[c.entry.raw] = n + 1
        key = answer_key(identity, c, n)
        ruled = answers.get(key)
        if ruled is not None:
            if resolve is not None:
                ruled = resolve(ruled, c.entry) or ruled
            c = replace(c, minor=ruled, rule="answered by the user", review=None)
        moved = (moves or {}).get(key)
        if moved is not None:
            if resolve is not None:
                moved = resolve(moved, c.entry) or moved
            c = replace(c, minor=moved, rule="moved by the user", review=None)
        out.append(c)
    return out


MOVED = "moved:"


def is_moved(identity: str) -> bool:
    return identity.startswith(MOVED)


def _month_before(name: str) -> str | None:
    if name not in MONTH_NAMES:
        return None
    return MONTH_NAMES[MONTH_NAMES.index(name) - 1]


def _span(period: Period) -> str:
    dates = period.dates
    return f"{dates[0]}..{dates[-1]}" if dates else "undated"


_MONTH_NAMES = MONTH_NAMES

_SALARY_FLOOR: int = RULES["classify"]["thresholds"]["salary_floor"]


def _identity(period: Period) -> str:
    for entry in period.entries:
        if entry.income and entry.bare and entry.amount >= _SALARY_FLOOR:
            return f"salary:{entry.amount}"
    return _span(period)


def _fullness(period: Period, text: str) -> tuple[int, int, int]:
    return len(period.days), len(period.entries), len(text)


def _opening_month(period: Period) -> int:
    return int(period.dates[0].split(".")[1])


def _year_for(period: Period, base: int, first_month: int | None) -> int:
    opening = _opening_month(period)
    year = base + 1 if first_month is not None and opening < first_month else base
    named = _MONTHS.get(month_of(period).lower())
    return year + 1 if named is not None and named < opening else year


def _key(version: dict) -> int:
    at = version.get("from", {})
    return int(at.get("year", 0)) * 12 + int(at.get("month", 0))


def _day_of_year(text: str) -> int:
    first = parse(text)[0].dates[0]
    day, month = first.split(".")
    return int(month) * 31 + int(day)


@dataclass
class Store:
    path: Path
    periods: dict[str, str] = field(default_factory=dict)
    answers: dict[str, str] = field(default_factory=dict)
    years: dict[str, int] = field(default_factory=dict)
    config: dict = field(default_factory=dict)
    config_versions: list[dict] = field(default_factory=list)
    omitted: dict[str, list[str]] = field(default_factory=dict)
    adjusted: dict[str, dict[str, float]] = field(default_factory=dict)
    left_set: dict[str, dict[str, float]] = field(default_factory=dict)
    left_start: dict[str, float] = field(default_factory=dict)
    moves: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> Store:
        store = cls(path)
        if path.exists():
            store.restore(json.loads(path.read_text(encoding="utf-8")))
        return store

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.state(), ensure_ascii=False, indent=1), encoding="utf-8"
        )


    def state(self) -> dict:
        state = {name: getattr(self, name) for name in STATE_FIELDS}
        state["years"] = {k: v for k, v in self.years.items() if not is_moved(k)}
        return state

    def restore(self, data: dict) -> None:
        if not isinstance(data, dict):
            raise Said("the backup is not a JSON object", code="backup_not_object")
        fresh: dict[str, object] = {}
        for name in STATE_FIELDS:
            got = data.get(name, [] if name == "config_versions" else {})
            want = list if name == "config_versions" else dict
            if not isinstance(got, want):
                raise Said(f"the backup's {name!r} is not a {want.__name__}",
                           code="backup_not_list" if want is list else "backup_not_dict",
                           name=name)
            fresh[name] = got
        for key, text in fresh["periods"].items():
            if not isinstance(key, str) or not isinstance(text, str):
                raise Said("the backup's 'periods' must be text keyed by identity",
                           code="backup_periods")
        try:
            fresh["years"] = {k: int(v) for k, v in fresh["years"].items()}
        except (TypeError, ValueError):
            raise Said("the backup's 'years' must be whole calendar years",
                       code="backup_years") from None
        for per in fresh["omitted"].values():
            if not isinstance(per, list) or any(not isinstance(g, str) for g in per):
                raise Said(
                    "the backup's 'omitted' must be lists of group names",
                    code="backup_omitted",
                )
        for key, group in fresh["moves"].items():
            if not isinstance(key, str) or not isinstance(group, str):
                raise Said(
                    "the backup's 'moves' must be group names keyed like answers",
                    code="backup_moves",
                )
        try:
            fresh["adjusted"] = {
                k: {g: float(v) for g, v in per.items()}
                for k, per in fresh["adjusted"].items()
            }
        except (AttributeError, TypeError, ValueError):
            raise Said("the backup's 'adjusted' must be figures per group",
                       code="backup_adjusted") from None
        try:
            fresh["left_set"] = {
                k: {s: float(v) for s, v in per.items()}
                for k, per in fresh["left_set"].items()
            }
            fresh["left_start"] = {s: float(v) for s, v in fresh["left_start"].items()}
        except (AttributeError, TypeError, ValueError):
            raise Said("the backup's Left figures must be numbers, per figure",
                       code="backup_left") from None
        for name, value in fresh.items():
            setattr(self, name, value)
        self.forget_taxonomy()


    def add_to(self, name: str, text: str) -> tuple[str, int, int, str]:
        found = self.period(name)
        if found is None:
            raise KeyError(name)
        identity, _, period = found

        segments = _MARKER.split(text)
        text, leftover = segments[0], "\n\n".join(
            seg.strip() for seg in segments[1:] if seg.strip()
        )

        lines = text.strip().splitlines()
        first_dated = next(
            (i for i, ln in enumerate(lines) if re.fullmatch(r"\d{2}\.\d{2}", ln.strip())),
            None,
        )
        if first_dated is None:
            raise Said(
                "the paste has no dated day (dd.mm) - for a month already "
                "stored, add days; the opening lines are there already",
                code="no_dated_day",
            )
        lines = lines[first_dated:]
        text = "\n".join(lines)

        before = len(period.dates)
        self.periods[identity] = grown = (
            self.periods[identity].rstrip() + "\n" + text.strip() + "\n"
        )
        after = len(parse(grown)[0].dates)
        return month_of(period), before, after, leftover

    def year_of(self, identity: str, period: Period) -> int | None:
        return self.years.get(identity)

    def import_text(
        self, text: str, replace: bool = False, year: int | None = None
    ) -> list[tuple[str, str]]:
        outcome = []
        first_dated = True
        first_month: int | None = None
        for segment in _MARKER.split(text):
            for period in parse(segment):
                if not period.dates:
                    outcome.append(("undated", "skipped: no dated days"))
                    continue
                force = replace and first_dated
                first_dated = False
                key = _identity(period)
                if not key.startswith("salary:"):
                    name = month_of(period)
                    if any(
                        month_of(other) == name and other_key != key
                        and not is_moved(other_key)
                        for other_key, other in self.assembled()
                    ):
                        raise Said(
                            f"these notes carry no salary line, so they cannot start "
                            f"a month of their own - and {name} is already stored. "
                            f"Choose {name} under 'Add to' instead.",
                            code="no_salary_line", name=Month(name),
                        )
                held = self.periods.get(key)
                this_year = None
                if year is not None:
                    this_year = _year_for(period, year, first_month)
                    first_month = first_month or _opening_month(period)
                incoming = segment.strip() + "\n"
                if (
                    held is not None
                    and not force
                    and _fullness(parse(held)[0], held) >= _fullness(period, incoming)
                ):
                    kept = (
                        "kept fuller copy (carry-over fragment)" if replace else "kept fuller copy"
                    )
                    outcome.append((_span(period), kept))
                    if this_year is not None and key not in self.years:
                        self.years[key] = this_year
                    continue
                outcome.append((_span(period), "replaced" if held else "imported"))
                self.periods[key] = incoming
                if this_year is not None:
                    self.years[key] = this_year
        return outcome

    def _ordered(self) -> list[tuple[str, str]]:
        items = sorted(self.periods.items(), key=lambda kv: _day_of_year(kv[1]))
        if len(items) < 2:
            return items
        days = [_day_of_year(text) for _, text in items]
        gaps = [
            (days[(i + 1) % len(days)] - days[i]) % 372 for i in range(len(days))
        ]
        seam = (gaps.index(max(gaps)) + 1) % len(items)
        return items[seam:] + items[:seam]

    def assembled(self) -> list[tuple[str, Period]]:
        key = tuple(sorted((k, len(v), hash(v), self.years.get(k))
                           for k, v in self.periods.items()))
        cached = getattr(self, "_assembled", None)
        if cached is not None and cached[0] == key:
            for identity, year in cached[2].items():
                self.years.setdefault(identity, year)
            return cached[1]
        ordered = self._ordered()
        periods = reassign_deferred(parse("\n#####\n".join(t for _, t in ordered)))
        result, years = self._with_moved_months(
            list(zip((identity for identity, _ in ordered), periods)))
        self._assembled = (key, result, years)
        return result

    def _with_moved_months(self, result: list[tuple[str, Period]]):
        groups: dict[tuple[str, int | None], list] = {}
        sources: dict[tuple[str, int | None], str] = {}
        out = []
        for identity, period in result:
            here = month_of(period)
            source_year = self.years.get(identity)
            moving = []
            for entry in period.entries:
                if not entry.deferred:
                    continue
                named = entry.refers_to or _month_before(here)
                if named is None or named == here or named not in MONTH_NAMES:
                    continue
                year = source_year
                if year is not None and here in MONTH_NAMES and (
                        MONTH_NAMES.index(named) > MONTH_NAMES.index(here)):
                    year -= 1
                moving.append(entry)
                groups.setdefault((named, year), []).append(entry)
                sources.setdefault((named, year), identity)
            out.append((identity, without(period, moving) if moving else period))
        years: dict[str, int] = {}
        for (named, year), entries in groups.items():
            month = MONTH_NAMES.index(named) + 1
            last = calendar.monthrange(year or 2001, month)[1]
            made = Period([Day(f"{last:02d}.{month:02d}",
                               [Block((arrived(entry),)) for entry in entries])])
            identity = f"{MOVED}{named} {year}" if year else f"{MOVED}{named}"

            def later(other: str, period: Period) -> bool:
                other_year = self.years.get(other, years.get(other))
                other_month = _MONTHS.get(month_of(period).lower())
                if year is not None and other_year is not None and other_month:
                    return (other_year, other_month) > (year, month)
                return other == sources[(named, year)]

            at = next((i for i, (other, period) in enumerate(out) if later(other, period)),
                      len(out))
            out.insert(at, (identity, made))
            if year is not None:
                years[identity] = year
                self.years.setdefault(identity, year)
        return out, years

    def settle_moved(self, before: set[str]) -> None:
        now = {identity for identity, _ in self.assembled()}
        for gone in before - now:
            if not is_moved(gone):
                continue
            found = self.period(gone)
            if found is None:
                continue
            home = found[0]
            for book in (self.answers, self.moves):
                for key in [k for k in book if k.startswith(f"{gone}|")]:
                    book.setdefault(home + key[len(gone):], book.pop(key))
            for book in (self.omitted, self.adjusted, self.left_set):
                if gone in book:
                    book.setdefault(home, book.pop(gone))
            self.years.pop(gone, None)

    def backfill_years(self, today_year: int, today_month: int) -> bool:
        ordered = self.assembled()
        if not ordered:
            return False
        months = [_MONTHS.get(month_of(period).lower()) for _, period in ordered]
        if any(m is None for m in months):
            return False

        years: list[int | None] = [self.years.get(identity) for identity, _ in ordered]
        anchor = next((i for i, y in enumerate(years) if y is not None), None)
        if anchor is None:
            anchor = len(ordered) - 1
            newest = months[anchor]
            years[anchor] = today_year if newest <= today_month else today_year - 1

        for i in range(anchor + 1, len(ordered)):
            if years[i] is None:
                years[i] = years[i - 1] + (1 if months[i] < months[i - 1] else 0)
        for i in range(anchor - 1, -1, -1):
            if years[i] is None:
                years[i] = years[i + 1] - (1 if months[i] > months[i + 1] else 0)

        changed = False
        for (identity, _), year in zip(ordered, years):
            if identity not in self.years and year is not None:
                self.years[identity] = year
                changed = True
        return changed


    def anchor_of(self, identity: str) -> tuple[int, int] | None:
        year = self.years.get(identity)
        if year is None:
            return None
        for ident, period in self.assembled():
            if ident == identity:
                month = _MONTHS.get(month_of(period).lower())
                return (year, month) if month else None
        return None

    def config_at(self, identity: str) -> dict:
        layers = [self.config]
        anchor = self.anchor_of(identity)
        if anchor is not None:
            here = anchor[0] * 12 + anchor[1]
            covering = [
                v for v in self.config_versions
                if (v.get("scope") == "month" and _key(v) == here)
                or (v.get("scope") == "onward" and _key(v) <= here)
            ]
        else:
            covering = [
                v for v in self.config_versions
                if v.get("from", {}).get("identity") == identity
            ]
        covering.sort(key=lambda v: (_key(v), v.get("id", 0)))
        for version in covering:
            layers = [version["config"]] if version.get("reset") else layers + [
                version["config"]
            ]
        return compose(layers)

    def taxonomy_at(self, identity: str | None):
        cache = getattr(self, "_tax_cache", None)
        if cache is None:
            cache = self._tax_cache = {}
        if identity not in cache:
            cache[identity] = effective(
                self.config if identity is None else self.config_at(identity)
            )
        return cache[identity]

    def forget_taxonomy(self) -> None:
        self._tax_cache = {}

    def rulings(self, identity: str):
        tax = self.taxonomy_at(identity)
        words = words_of(self.config_at(identity))

        def resolve(name: str, entry) -> str | None:
            return tax.resolve_group(ruled_group(entry, name), entry.text)[0]

        def overlay(results: list[Classification]) -> list[Classification]:
            if words:
                results = apply_taught(results, words, resolve=resolve)
            return apply_answers(
                results, self.answers, identity, resolve=resolve, moves=self.moves,
            )

        return overlay

    def next_version_id(self) -> int:
        return max((v.get("id", 0) for v in self.config_versions), default=0) + 1

    def period(self, name: str) -> tuple[str, str, Period] | None:
        wanted = _MONTHS.get(name.lower())
        if wanted is None and name.isdigit() and 1 <= int(name) <= 12:
            wanted = int(name)
        for identity, period in self.assembled():
            span = _span(period)
            month = month_of(period)
            if name in (span, identity) or name.lower() == month.lower():
                return identity, span, period
            if wanted is not None and month == _MONTH_NAMES[wanted - 1]:
                return identity, span, period
        if is_moved(name):
            month, _, year = name[len(MOVED):].partition(" ")
            for identity, period in self.assembled():
                if (not is_moved(identity) and month_of(period) == month
                        and (not year or str(self.years.get(identity)) == year)):
                    return identity, _span(period), period
        return None
