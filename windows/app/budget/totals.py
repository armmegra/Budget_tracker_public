"""Sums classified entries into major groups by tier, spreads a rent lump over the
months it covers, and compares spending with limits.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Container, Iterable
from decimal import Decimal

from budget.classify import Classification
from budget.groups import BASE, MAJORS, Taxonomy, Tier
from budget.rules import RULES
from budget.money import to_thousands

__all__ = [
    "major_whole", "majors", "second_total", "tier_totals", "Totals", "rent_fixed",
]

_TIER_OF = {major.name: major.tier for major in MAJORS}

_ROLES = RULES["groups"]["roles"]
_RENT_MONTHS: int = RULES["classify"].get("rent", {}).get("months", 1)


def major_whole(
    results: list[Classification],
    fixed: dict[str, int] | None = None,
    tax: Taxonomy = BASE,
) -> dict[str, int]:
    whole: dict[str, int] = defaultdict(int)
    for result in results:
        if result.minor is None:
            continue
        major = tax.major_for(result.minor)
        whole[major.name if major else result.minor] += result.entry.signed
    configured = {m.name: m.fixed for m in tax.majors if m.fixed is not None}
    override = {k: v for k, v in (fixed or {}).items() if tax.major(k) is not None}
    whole.update(configured | override)
    return dict(whole)


def majors(
    results: list[Classification],
    fixed: dict[str, int] | None = None,
    tax: Taxonomy = BASE,
) -> dict[str, Decimal]:
    return {
        name: to_thousands(total)
        for name, total in major_whole(results, fixed, tax).items()
    }


def rent_fixed(store, identity: str) -> dict[str, int]:
    from budget.classify import classify_period
    from budget.notes import month_of

    _MONTH_NO = {
        m: i
        for i, m in enumerate(
            ["January", "February", "March", "April", "May", "June", "July",
             "August", "September", "October", "November", "December"],
            1,
        )
    }

    def lump(ident, period) -> int:
        results = classify_period(period, overlay=store.rulings(ident))
        total = sum(c.entry.signed for c in results if c.minor == _ROLES["rent_lump"])
        return total if total > 0 else 0

    ordered = store.assembled()
    for i, (ident, period) in enumerate(ordered):
        if ident != identity:
            continue
        own = lump(ident, period)
        if own:
            return {_ROLES["rent"]: own if _RENT_MONTHS == 1 else own - own // 2}
        if _RENT_MONTHS == 1:
            return {}
        if i + 1 < len(ordered):
            next_ident, next_period = ordered[i + 1]
            this_no = _MONTH_NO.get(month_of(period))
            next_no = _MONTH_NO.get(month_of(next_period))
            adjacent = (
                this_no is not None
                and next_no is not None
                and (next_no - this_no) % 12 == 1
            )
            this_year = store.years.get(ident)
            next_year = store.years.get(next_ident)
            if adjacent and this_year is not None and next_year is not None:
                adjacent = next_year - this_year == (1 if this_no == 12 else 0)
            if adjacent:
                theirs = lump(next_ident, next_period)
                if theirs:
                    return {_ROLES["rent"]: theirs // 2}
        return {}
    return {}


class Totals(dict):
    def __init__(
        self, rounded: dict[str, Decimal], tiers: dict[str, Tier] | None = None
    ) -> None:
        super().__init__(rounded)
        self._tiers = _TIER_OF if tiers is None else tiers

    def _sum(self, tier: Tier) -> Decimal:
        return sum(
            (value for name, value in self.items() if self._tiers.get(name) is tier),
            Decimal(0),
        )

    @property
    def necessary(self) -> Decimal:
        return self._sum(Tier.NECESSARY)

    @property
    def appended(self) -> Decimal:
        known = set(self._tiers)
        return sum(
            (
                value
                for name, value in self.items()
                if name not in known or self._tiers[name] is Tier.OCCASIONAL
                or self._tiers[name] is Tier.FREQUENT
            ),
            Decimal(0),
        )

    @property
    def grand(self) -> Decimal:
        return self.necessary + self.appended

    @property
    def excluded(self) -> dict[str, Decimal]:
        return {
            name: value
            for name, value in self.items()
            if self._tiers.get(name) is Tier.EXCLUDED
        }


def tier_totals(
    results: list[Classification],
    fixed: dict[str, int] | None = None,
    tax: Taxonomy = BASE,
) -> Totals:
    return Totals(
        majors(results, fixed, tax), {m.name: m.tier for m in tax.majors}
    )


def second_total(
    totals: Totals,
    tax: Taxonomy = BASE,
    omitted: "Iterable[str]" = (),
    adjusted: dict[str, float] | None = None,
    hidden: "Container[str]" = frozenset(),
) -> Decimal:
    known = {m.name: m for m in tax.majors}
    dropped = set(omitted)
    fixes = adjusted or {}
    out = totals.necessary
    for name, value in totals.items():
        if name in hidden or name in dropped:
            continue
        major = known.get(name)
        if major is not None and major.tier not in (Tier.FREQUENT, Tier.OCCASIONAL):
            continue
        out += Decimal(str(fixes[name])) if name in fixes else value
    return out
