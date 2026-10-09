"""The closing "Left" line: its figures, their kinds (card, cash, weekly purse,
carried over) and the recount of a month still being written.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from budget import grammar, speech
from budget.rules import RULES, RulesError

__all__ = [
    "Slot", "DEFAULT_SLOTS", "KINDS", "left_slots", "cells", "assemble",
    "format_value", "MAX_SLOTS",
]

GRAMMAR = grammar.build(RULES.get("notes", {}))

MAX_SLOTS = 8

KINDS = ("card", "cash", "purse", "carry")


@dataclass(frozen=True)
class Slot:
    id: str
    label: str = ""
    place: str = "before"
    join: str = " "
    kind: str = "carry"
    unit: str = "thousands"
    decimals: int = 1
    spaced: bool = False
    reset: dict | None = None
    minors: tuple[str, ...] = ()


def _slots(raw) -> tuple[Slot, ...]:
    if not isinstance(raw, list) or not raw:
        raise speech.Said("the Left line needs at least one figure", code="left_needs_figure")
    if len(raw) > MAX_SLOTS:
        raise speech.Said(f"the Left line takes at most {MAX_SLOTS} figures",
                          code="most_figures", n=MAX_SLOTS)
    slots = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict) or not item.get("id"):
            raise speech.Said("every figure needs an id", code="left_no_id")
        if item["id"] in seen:
            raise speech.Said(f"two figures share the id {item['id']!r}",
                              code="left_same_id", id=repr(item["id"]))
        seen.add(item["id"])
        kind = item.get("kind", "carry")
        if kind not in KINDS:
            raise speech.Said(f"kind must be one of {list(KINDS)}",
                              code="left_kind", kinds=list(KINDS))
        label = str(item.get("label", ""))
        if "," in label or "\n" in label:
            raise speech.Said("a label cannot contain a comma", code="left_comma")
        slots.append(
            Slot(
                id=str(item["id"]),
                label=label,
                place="after" if item.get("place") == "after" else "before",
                join=str(item.get("join", " ")),
                kind=kind,
                unit="thousands" if item.get("unit", "thousands") == "thousands" else "whole",
                decimals=int(item.get("decimals", 1)),
                spaced=bool(item.get("spaced")),
                reset=item.get("reset"),
                minors=tuple(item.get("minors", ())),
            )
        )
    if sum(1 for s in slots if s.kind == "card") > 1:
        raise speech.Said("only one figure can be the card balance", code="left_one_card")
    if sum(1 for s in slots if s.kind == "cash") > 1:
        raise speech.Said("only one figure can be the cash balance", code="left_one_cash")
    for slot in slots:
        if slot.kind != "purse":
            continue
        reset = slot.reset or {}
        if not 0 <= int(reset.get("weekday", 0)) <= 6:
            raise speech.Said("a purse resets on a weekday 0 (Monday) to 6",
                              code="purse_weekday")
        if Decimal(str(reset.get("amount", 0))) <= 0:
            raise speech.Said("a purse needs an amount above zero", code="purse_amount")
    return tuple(slots)


try:
    DEFAULT_SLOTS: tuple[Slot, ...] = _slots(RULES["left"]["slots"])
except ValueError as err:
    raise RulesError(f"rules.toml: left.slots: {err}") from None


def left_slots(config: dict | None) -> tuple[Slot, ...]:
    if not config or not config.get("left"):
        return DEFAULT_SLOTS
    return _slots(config["left"].get("slots"))


def as_json(slots: tuple[Slot, ...]) -> list[dict]:
    out = []
    for s in slots:
        item = {
            "id": s.id, "label": s.label, "place": s.place, "join": s.join,
            "kind": s.kind, "unit": s.unit, "decimals": s.decimals,
        }
        if s.spaced:
            item["spaced"] = True
        if s.reset:
            item["reset"] = s.reset
        if s.minors:
            item["minors"] = list(s.minors)
        out.append(item)
    return out


def _spaced(value: int) -> str:
    sign = "-" if value < 0 else ""
    digits = str(abs(value))
    groups = []
    while len(digits) > 3:
        groups.insert(0, digits[-3:])
        digits = digits[:-3]
    groups.insert(0, digits)
    return sign + " ".join(groups)


def format_value(slot: Slot, value) -> str:
    if value is None:
        return "—"
    number = Decimal(str(value))
    if slot.decimals == 0:
        rounded = int(number.to_integral_value())
        return _spaced(rounded) if slot.spaced else str(rounded)
    quantised = round(float(number), slot.decimals)
    text = f"{quantised:g}"
    if GRAMMAR.decimal != ".":
        text = text.replace(".", GRAMMAR.decimal)
    return _spaced(int(quantised)) if slot.spaced and quantised == int(quantised) else text


def cells(values, slots: tuple[Slot, ...], fields=()) -> list[dict]:
    out = []
    for i, slot in enumerate(slots):
        value = values[i] if i < len(values) else None
        if value is None and i < len(fields) and str(fields[i]).strip():
            figure = str(fields[i]).strip()
        else:
            figure = format_value(slot, value)
        text = (
            f"{figure}{slot.join}{slot.label}"
            if slot.place == "after" and slot.label
            else f"{slot.label}{slot.join}{figure}" if slot.label
            else figure
        )
        out.append({
            "id": slot.id, "label": slot.label, "place": slot.place,
            "join": slot.join, "figure": figure, "text": text,
            "value": None if value is None else float(value),
        })
    return out


def assemble(values, slots: tuple[Slot, ...], fields=()) -> str:
    return f"{GRAMMAR.left_word}: " + ", ".join(c["text"] for c in cells(values, slots, fields))


def relabel(slots: tuple[Slot, ...], slot_id: str, **fields) -> tuple[Slot, ...]:
    return tuple(replace(s, **fields) if s.id == slot_id else s for s in slots)
