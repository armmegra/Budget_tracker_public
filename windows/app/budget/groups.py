"""Major and minor groups, tiers and limits: the taxonomy read from the rules file,
and the user's own edits - renames, reroutes, limits, taught words - layered
over it, each optionally from a given month on.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum

from budget import grammar
from budget.rules import RULES

__all__ = [
    "MAX_MAJORS", "MAX_MINORS", "MAX_LIMITS", "MAX_WORDS", "words_of",
    "Tier", "Major", "MAJORS", "major_for", "minor_names", "LIMIT_TOTAL",
    "MINOR_ORDER", "NESTED", "LIMIT_ORDER", "minor_sort_key",
    "Taxonomy", "BASE", "effective", "merge_config", "compose",
]

GRAMMAR = grammar.build(RULES.get("notes", {}))

MAX_MAJORS = 200
MAX_MINORS = 500
MAX_LIMITS = 200
MAX_WORDS = 500


class Tier(Enum):
    NECESSARY = 1
    FREQUENT = 2
    OCCASIONAL = 3
    EXCLUDED = 0


@dataclass(frozen=True)
class Major:
    name: str
    tier: Tier
    minors: tuple[str, ...]
    limit: int | None = None
    limit_label: str | None = None
    fixed: int | None = None
    income: bool = False

    @property
    def is_income(self) -> bool:
        return self.income


def _majors(spec: list[dict]) -> tuple[Major, ...]:
    return tuple(
        Major(
            major["name"],
            Tier[major["tier"]],
            tuple(major.get("minors", ())),
            limit=major.get("limit"),
            limit_label=major.get("limit_label"),
            fixed=major.get("fixed"),
            income=bool(major.get("income", False)),
        )
        for major in spec
    )


_GROUPS = RULES["groups"]

MAJORS: tuple[Major, ...] = _majors(_GROUPS["majors"])

LIMIT_TOTAL: int = _GROUPS["limit_total"]

LIMIT_ORDER: tuple[str, ...] = tuple(_GROUPS["limit_order"])

MINOR_ORDER: tuple[str, ...] = tuple(_GROUPS["minor_order"])

NESTED: dict[str, tuple[tuple[str, str], ...]] = {
    header: tuple((label, minor) for label, minor in subs)
    for header, subs in _GROUPS.get("nested", {}).items()
}


def minor_sort_key(name: str) -> tuple[int, str]:
    try:
        return (MINOR_ORDER.index(name), "")
    except ValueError:
        return (len(MINOR_ORDER), name)

_BY_MINOR: dict[str, Major] = {
    minor: major for major in MAJORS for minor in major.minors
}


def major_for(minor: str) -> Major | None:
    return _BY_MINOR.get(minor)


def minor_names() -> tuple[str, ...]:
    return tuple(_BY_MINOR)


def merge_config(base: dict, patch: dict) -> dict:
    import copy

    out = copy.deepcopy(base)
    for section in ("majors", "minors", "words"):
        if section in patch:
            dest = out.setdefault(section, {})
            for name, fields in patch[section].items():
                dest.setdefault(name, {}).update(copy.deepcopy(fields))
    if "left" in patch:
        out["left"] = copy.deepcopy(patch["left"])
    if "limit_order" in patch:
        out["limit_order"] = copy.deepcopy(patch["limit_order"])
    return out


def compose(layers: list[dict]) -> dict:
    out: dict = {}
    for layer in layers:
        if layer:
            out = merge_config(out, layer)
    return out


def words_of(config: dict | None) -> list[tuple[str, str]]:
    return [
        (patch.get("shown") or word, patch["group"])
        for word, patch in (config or {}).get("words", {}).items()
        if not patch.get("removed") and patch.get("group")
    ]


@dataclass(frozen=True)
class Taxonomy:
    majors: tuple[Major, ...]
    limit_order: tuple[str, ...]
    minor_order: tuple[str, ...]
    nested: dict[str, tuple[tuple[str, str], ...]]
    major_labels: dict[str, str]
    minor_labels: dict[str, str]
    merged: dict[str, str] = field(default_factory=dict)
    dropped: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        by_minor = {minor: major for major in self.majors for minor in major.minors}
        object.__setattr__(self, "_by_minor", by_minor)

    def settled(self, minor: str | None) -> str | None:
        return self.merged.get(minor, minor) if minor else minor

    def major_for(self, minor: str) -> Major | None:
        return self._by_minor.get(self.settled(minor))

    def minor_names(self) -> tuple[str, ...]:
        return tuple(self._by_minor)

    def major(self, name: str) -> Major | None:
        return next((m for m in self.majors if m.name == name), None)

    def major_label(self, name: str) -> str:
        return self.major_labels.get(name, name)

    def minor_label(self, name: str) -> str:
        settled = self.settled(name)
        return self.minor_labels.get(settled, settled)

    def canonical_minor(self, shown: str) -> str:
        for canonical, label in self.minor_labels.items():
            if label == shown:
                return canonical
        return shown

    def canonical_major(self, shown: str) -> str:
        for canonical, label in self.major_labels.items():
            if label == shown:
                return canonical
        return shown

    def resolve_group(self, typed: str, text: str = "") -> tuple[str | None, list[str]]:
        wanted = " ".join(typed.split()).casefold()
        if not wanted:
            return None, []

        for minor in self._by_minor:
            if minor.casefold() == wanted:
                return minor, []
        for canonical, label in self.minor_labels.items():
            if label.casefold() == wanted and canonical in self._by_minor:
                return canonical, []
        for gone, into in self.merged.items():
            if wanted in (gone.casefold(), self.minor_labels.get(gone, gone).casefold()):
                return into, []

        major = next(
            (
                m for m in self.majors
                if m.name.casefold() == wanted
                or self.major_label(m.name).casefold() == wanted
            ),
            None,
        )
        if major is None:
            return None, []
        if len(major.minors) == 1:
            return major.minors[0], []
        if not major.minors:
            return None, []

        if major.name in self.nested:
            def sub(suffix: str) -> str | None:
                name = f"{major.name} {suffix}"
                return name if name in major.minors else None

            if GRAMMAR.fare_word.search(text):
                if sub(GRAMMAR.nested_taxi):
                    return sub(GRAMMAR.nested_taxi), []
            if GRAMMAR.paid_by_card.search(text):
                if sub(GRAMMAR.nested_card):
                    return sub(GRAMMAR.nested_card), []
            if sub(GRAMMAR.nested_cash):
                return sub(GRAMMAR.nested_cash), []
        return None, [self.minor_label(m) for m in major.minors]

    def all_names(self) -> set[str]:
        names = {m.name for m in self.majors} | set(self._by_minor)
        names |= set(self.major_labels.values()) | set(self.minor_labels.values())
        return names


BASE = Taxonomy(MAJORS, LIMIT_ORDER, MINOR_ORDER, NESTED, {}, {})


def effective(config: dict | None) -> Taxonomy:
    if not config or not any(
        config.get(key) for key in ("majors", "minors", "limit_order")
    ):
        return BASE
    minors_cfg: dict = config.get("minors", {})
    majors_cfg: dict = config.get("majors", {})

    routed: dict[str, str] = {}
    for major in MAJORS:
        for minor in major.minors:
            routed[minor] = major.name
    for minor, patch in minors_cfg.items():
        if patch.get("removed"):
            routed.pop(minor, None)
        elif "major" in patch:
            routed[minor] = patch["major"]

    base_minor_order = [m for maj in MAJORS for m in maj.minors]
    minor_seq = base_minor_order + [m for m in minors_cfg if m not in base_minor_order]

    def minors_of(name: str) -> tuple[str, ...]:
        return tuple(m for m in minor_seq if routed.get(m) == name)

    majors: list[Major] = []
    for major in MAJORS:
        patch = majors_cfg.get(major.name, {})
        if patch.get("removed"):
            continue
        fields = {
            key: patch[key]
            for key in ("limit", "limit_label", "fixed", "income")
            if key in patch
        }
        if "tier" in patch:
            fields["tier"] = Tier[patch["tier"]]
        majors.append(replace(major, minors=minors_of(major.name), **fields))
    base_names = {major.name for major in MAJORS}
    for name, patch in majors_cfg.items():
        if not patch.get("added") or patch.get("removed") or name in base_names:
            continue
        majors.append(
            Major(
                name,
                Tier[patch.get("tier", "NECESSARY")],
                minors_of(name),
                limit=patch.get("limit"),
                limit_label=patch.get("limit_label"),
                fixed=patch.get("fixed"),
                income=bool(patch.get("income")),
            )
        )

    major_labels = {
        name: patch["renamed"]
        for name, patch in majors_cfg.items()
        if patch.get("renamed")
    }
    minor_labels = {
        name: patch["renamed"]
        for name, patch in minors_cfg.items()
        if patch.get("renamed")
    }

    by_name = {m.name: m for m in majors}
    if "limit_order" in config:
        limit_order = tuple(
            n for n in config["limit_order"]
            if n in by_name and by_name[n].limit is not None
        )
        limit_order += tuple(
            m.name for m in majors if m.limit is not None and m.name not in limit_order
        )
    else:
        limit_order = tuple(
            n for n in LIMIT_ORDER if n in by_name and by_name[n].limit is not None
        ) + tuple(
            m.name for m in majors
            if m.limit is not None and m.name not in LIMIT_ORDER
        )

    roster = MINOR_ORDER + tuple(
        m for m in minors_cfg
        if minors_cfg[m].get("added") and m not in MINOR_ORDER
    )
    rows: list[str] = []
    for m in roster:
        if m in NESTED and m not in by_name:
            rows += [key for _, key in NESTED[m] if key in routed and key not in roster]
        elif m in routed or (m in by_name and not minors_cfg.get(m, {}).get("removed")):
            rows.append(m)
    minor_order = tuple(rows)
    nested = {
        header: tuple((label, key) for label, key in subs if routed.get(key) == header)
        for header, subs in NESTED.items()
        if header in by_name
    }
    merged: dict[str, str] = {}
    for gone, patch in minors_cfg.items():
        if not patch.get("removed") or not patch.get("into"):
            continue
        seen = {gone}
        into = patch["into"]
        while into not in routed and into in minors_cfg and into not in seen:
            seen.add(into)
            into = minors_cfg[into].get("into")
            if not into:
                break
        if into in routed:
            merged[gone] = into
    dropped = frozenset(gone for gone, patch in minors_cfg.items()
                        if patch.get("removed") and gone not in merged)

    return Taxonomy(tuple(majors), limit_order, minor_order, nested,
                    major_labels, minor_labels, merged, dropped)
