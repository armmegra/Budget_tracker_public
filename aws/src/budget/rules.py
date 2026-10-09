"""Loads and validates the household's rules file (TOML): groups, limits, the words
that send a line to a group, the closing line. A file that does not make sense
is refused by name at start-up.
"""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path

from budget import grammar

__all__ = ["RULES", "RulesError", "DEFAULT_PATH", "load", "path_in_use", "validate",
           "resolve_pattern"]

DEFAULT_PATH = Path(__file__).with_name("rules.toml")


def path_in_use() -> Path:
    return Path(os.environ.get("BUDGET_RULES") or DEFAULT_PATH)

TIERS = ("NECESSARY", "FREQUENT", "OCCASIONAL", "EXCLUDED")

ROLES = ("salary", "reimbursements", "withdrawal", "savings", "rent_lump", "rent", "elsewhere")


def resolve_pattern(classify: dict, value: str) -> str:
    if value.startswith("@"):
        return classify["patterns"][value[1:]]
    return value


class RulesError(ValueError):
    pass


def load(path: str | os.PathLike | None = None) -> dict:
    where = Path(path) if path else path_in_use()
    try:
        with open(where, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        raise RulesError(f"no rules file at {where}") from None
    except tomllib.TOMLDecodeError as err:
        raise RulesError(f"{where}: {err}") from None
    return validate(data, where.name)


def _fail(where: str, key: str, why: str) -> RulesError:
    return RulesError(f"{where}: {key}: {why}")


def _table(where: str, parent: dict, key: str) -> dict:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise _fail(where, key, "must be a table")
    return value


def _strings(where: str, parent: dict, key: str, *, allow_empty: bool = False) -> list[str]:
    value = parent.get(key)
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise _fail(where, key, "must be a list of strings")
    if not value and not allow_empty:
        raise _fail(where, key, "must not be empty")
    return value


def _int(where: str, parent: dict, key: str, *, optional: bool = False) -> int | None:
    value = parent.get(key)
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail(where, key, "must be a whole number")
    return value


def _pattern(where: str, key: str, value) -> str:
    if not isinstance(value, str) or not value:
        raise _fail(where, key, "must be a regular expression")
    try:
        re.compile(value, re.IGNORECASE)
    except re.error as err:
        raise _fail(where, key, f"bad regular expression {value!r}: {err}") from None
    return value


def _resolved(where: str, classify: dict, key: str, value) -> str:
    if not isinstance(value, str):
        raise _fail(where, key, "must be a regular expression or an @name")
    if value.startswith("@") and value[1:] not in classify.get("patterns", {}):
        raise _fail(where, key, f"no [classify.patterns] entry named {value[1:]!r}")
    return _pattern(where, key, resolve_pattern(classify, value))


def _pair(where: str, key: str, value) -> tuple[str, str]:
    if not (isinstance(value, list) and len(value) == 2 and all(isinstance(v, str) for v in value)):
        raise _fail(where, key, "must be [pattern, group]")
    return value[0], value[1]


def _minor(where: str, key: str, value, minors: dict[str, str]) -> str:
    if not isinstance(value, str) or value not in minors:
        raise _fail(where, key, "must name a minor group from [[groups.majors]]")
    return value


def _groups(where: str, data: dict) -> tuple[set[str], dict[str, str], set[str]]:
    groups = _table(where, data, "groups")
    _int(where, groups, "limit_total")

    majors = groups.get("majors")
    if not isinstance(majors, list) or not majors:
        raise _fail(where, "groups.majors", "must be a non-empty list of [[groups.majors]] tables")
    names: set[str] = set()
    owner: dict[str, str] = {}
    for i, major in enumerate(majors):
        key = f"groups.majors[{i}]"
        if not isinstance(major, dict):
            raise _fail(where, key, "must be a table")
        name = major.get("name")
        if not isinstance(name, str) or not name.strip():
            raise _fail(where, key, "needs a name")
        if name in names:
            raise _fail(where, key, f"a second major named {name!r}")
        names.add(name)
        key = f"groups.majors[{name}]"
        if major.get("tier") not in TIERS:
            raise _fail(where, key + ".tier", f"must be one of {list(TIERS)}")
        for minor in _strings(where, major, "minors", allow_empty=True):
            if minor in owner:
                raise _fail(where, key + ".minors", f"{minor!r} already rolls into {owner[minor]!r}")
            owner[minor] = name
        _int(where, major, "limit", optional=True)
        _int(where, major, "fixed", optional=True)
        if "limit_label" in major and not isinstance(major["limit_label"], str):
            raise _fail(where, key + ".limit_label", "must be a string")
        if "income" in major and not isinstance(major["income"], bool):
            raise _fail(where, key + ".income", "must be true or false")
        unknown = set(major) - {"name", "tier", "minors", "limit", "limit_label", "fixed", "income"}
        if unknown:
            raise _fail(where, key, f"unknown field(s) {sorted(unknown)}")

    for name in _strings(where, groups, "limit_order"):
        if name not in names:
            raise _fail(where, "groups.limit_order", f"{name!r} is not a major group")
    for name in _strings(where, groups, "minor_order"):
        if name not in names and name not in owner:
            raise _fail(where, "groups.minor_order", f"{name!r} is neither a major nor a minor group")

    nested = groups.get("nested", {})
    if not isinstance(nested, dict):
        raise _fail(where, "groups.nested", "must be a table of header = [[label, minor], ...]")
    for header, subs in nested.items():
        key = f"groups.nested.{header}"
        if header not in names:
            raise _fail(where, key, "is not a major group")
        if not isinstance(subs, list) or not all(
            isinstance(s, list) and len(s) == 2 and all(isinstance(x, str) for x in s) for s in subs
        ):
            raise _fail(where, key, "must be a list of [label, minor] pairs")
        for _label, minor in subs:
            if owner.get(minor) != header:
                raise _fail(where, key, f"{minor!r} does not roll into {header!r}")

    income = {m["name"] for m in majors if m.get("income")}
    return names, owner, income


def _roles(where: str, data: dict, names: set[str], owner: dict[str, str], income: set[str]) -> None:
    roles = _table(where, data["groups"], "roles")
    for role in ROLES:
        key = f"groups.roles.{role}"
        if role == "rent":
            if roles.get(role) not in names:
                raise _fail(where, key, "must name a major group")
            continue
        name = _minor(where, key, roles.get(role), owner)
        if role == "reimbursements" and owner[name] not in income:
            raise _fail(where, key, f"{name!r} must roll into an income group")
    unknown = set(roles) - set(ROLES)
    if unknown:
        raise _fail(where, "groups.roles", f"unknown role(s) {sorted(unknown)}")


def _classify(where: str, data: dict, owner: dict[str, str]) -> None:
    cfg = _table(where, data, "classify")
    _strings(where, cfg, "platforms")
    _pattern(where, "classify.platform_words", cfg.get("platform_words"))

    patterns = _table(where, cfg, "patterns")
    for name, value in list(patterns.items()):
        key = f"classify.patterns.{name}"
        if isinstance(value, list):
            if not value or not all(isinstance(v, str) and v for v in value):
                raise _fail(where, key, "must be a list of regular expressions")
            value = "|".join(value)
            patterns[name] = value
        _pattern(where, key, value)
    for name in ("food_words", "pubs", "named_restaurants", "groceries", "meals"):
        if name not in patterns:
            raise _fail(where, f"classify.patterns.{name}", "is required")

    contexts = cfg.get("contexts")
    if not isinstance(contexts, list):
        raise _fail(where, "classify.contexts", "must be a list of [pattern, group]")
    for i, item in enumerate(contexts):
        pattern, _group = _pair(where, f"classify.contexts[{i}]", item)
        _resolved(where, cfg, f"classify.contexts[{i}]", pattern)
    pattern, _group = _pair(where, "classify.appointment", cfg.get("appointment"))
    _resolved(where, cfg, "classify.appointment", pattern)

    rules = cfg.get("rules")
    if not isinstance(rules, list) or not rules:
        raise _fail(where, "classify.rules", "must be a non-empty list of [pattern, group]")
    for i, item in enumerate(rules):
        pattern, _group = _pair(where, f"classify.rules[{i}]", item)
        _resolved(where, cfg, f"classify.rules[{i}]", pattern)

    questions = cfg.get("context_questions", {})
    if not isinstance(questions, dict):
        raise _fail(where, "classify.context_questions", "must be a table")
    for group, item in questions.items():
        key = f"classify.context_questions.{group}"
        if not (
            isinstance(item, list) and len(item) == 2 and isinstance(item[0], str)
            and isinstance(item[1], list) and all(isinstance(c, str) for c in item[1])
        ):
            raise _fail(where, key, "must be [question, [groups offered]]")

    food = _table(where, cfg, "food")
    for part in ("cash", "card", "taxi"):
        _minor(where, f"classify.food.{part}", food.get(part), owner)

    trip = _table(where, cfg, "trip")
    for part in ("road", "taxi", "restaurants"):
        _minor(where, f"classify.trip.{part}", trip.get(part), owner)
    _int(where, trip, "fare")
    legs = trip.get("legs")
    if not isinstance(legs, list) or not all(
        isinstance(leg, list) and len(leg) == 2
        and all(isinstance(x, int) and not isinstance(x, bool) for x in leg)
        for leg in legs
    ):
        raise _fail(where, "classify.trip.legs", "must be a list of [first fare, second fare]")

    tickets = _table(where, cfg, "fares").get("tickets")
    if not isinstance(tickets, list) or not all(
        isinstance(t, int) and not isinstance(t, bool) for t in tickets
    ):
        raise _fail(where, "classify.fares.tickets", "must be a list of whole amounts")

    alcohol = _table(where, cfg, "alcohol")
    _pattern(where, "classify.alcohol.words", alcohol.get("words"))
    if not isinstance(alcohol.get("celebration"), str) or not alcohol["celebration"]:
        raise _fail(where, "classify.alcohol.celebration", "must name a group")

    settlements = _table(where, cfg, "settlements")
    for key in ("partner", "group"):
        if not isinstance(settlements.get(key), str) or not settlements[key]:
            raise _fail(where, f"classify.settlements.{key}", "must be a name")
    for key in ("settlement", "named"):
        _pattern(where, f"classify.settlements.{key}", settlements.get(key))

    _pattern(where, "classify.reimbursements.named", _table(where, cfg, "reimbursements").get("named"))

    thresholds = _table(where, cfg, "thresholds")
    _int(where, thresholds, "salary_floor")
    _int(where, thresholds, "flower_ceiling")

    rent = cfg.get("rent", {})
    if not isinstance(rent, dict) or rent.get("months", 1) not in (1, 2):
        raise _fail(where, "classify.rent.months",
                    "must be 1 (paid every month) or 2 (every second month)")


def _display(where: str, data: dict) -> None:
    display = _table(where, data, "display")
    for key in ("per_visit_whole", "per_visit_service"):
        _strings(where, display, key, allow_empty=True)


def _left(where: str, data: dict) -> None:
    left = _table(where, data, "left")
    slots = left.get("slots")
    if not isinstance(slots, list) or not slots:
        raise _fail(where, "left.slots", "must be a non-empty list of [[left.slots]] tables")
    for i, slot in enumerate(slots):
        if not isinstance(slot, dict) or not isinstance(slot.get("id"), str):
            raise _fail(where, f"left.slots[{i}]", "needs an id")


def _notes(where: str, data: dict) -> None:
    if "notes" not in data:
        return
    try:
        grammar.build(data["notes"])
    except grammar.GrammarError as err:
        raise _fail(where, f"notes.{err.key}" if err.key else "notes", err.why) from None


def validate(data: dict, where: str = "rules") -> dict:
    if not isinstance(data, dict):
        raise _fail(where, "(file)", "must be a TOML document")
    if data.get("version") != 1:
        raise _fail(where, "version", "must be 1")
    names, owner, income = _groups(where, data)
    _roles(where, data, names, owner, income)
    _classify(where, data, owner)
    _display(where, data)
    _left(where, data)
    _notes(where, data)
    return data


RULES: dict = load()
