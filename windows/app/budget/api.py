"""The one entry point every front end calls.

`dispatch(store, event)` takes a JSON-shaped request - import, totals,
questions, answer, move, configure, compare, export, backup, restore - and
returns a JSON-shaped reply. A refusal is a sentence meant for the person, with
a code a page can act on.
"""

from __future__ import annotations

import copy
import re
from dataclasses import replace

from budget.classify import classify_period, counted_here, held
from budget.display import _HIDDEN as HIDDEN, closing_left, compare, count_on, day_windows, minor_rows, pending, render, with_set
from budget.export import compare_report, month_report, year_report
from budget.groups import MAX_LIMITS, MAX_MAJORS, MAX_MINORS, MAX_WORDS, words_of
from budget.groups import Tier, compose, effective
from budget.left import KINDS, MAX_SLOTS, as_json, assemble as assemble_left, cells as left_cells, left_slots
from budget.rules import RULES
from budget.notes import Period
from budget.store import Store, answer_key, is_moved, month_of, _span
from budget import speech
from decimal import Decimal

from budget.totals import rent_fixed, second_total, tier_totals

__all__ = ["dispatch"]


class _Refused(Exception):
    def __init__(self, text: str, code: str | None = None, **values) -> None:
        super().__init__(text)
        self.code = code
        self.values = values


def _passed(why: Exception) -> _Refused:
    code = getattr(why, "code", None)
    values = getattr(why, "values", None)
    return _Refused(
        str(why),
        code if isinstance(code, str) else None,
        **(values if isinstance(values, dict) else {}),
    )


def _lang(event: dict) -> str:
    return speech.pick(event.get("lang"))


def _labels(labels, lang: str) -> list[str]:
    return [speech.month_label(label, lang) for label in labels]


FREEZE_AFTER_MONTHS = 3

_STUB_DAYS = 2


def _today():
    import datetime

    return datetime.date.today()


def _tax(store: Store, identity: str | None = None):
    return store.taxonomy_at(identity)


def _month_label(store: Store, identity: str, period, lang: str = "en") -> str:
    year = store.years.get(identity)
    name = month_of(period)
    label = f"{name} {year}" if year else name
    return label if lang == "en" else speech.month_label(label, lang)


def _frozen_months(store: Store) -> dict[str, int]:
    today = _today()
    now = today.year * 12 + today.month
    out = {}
    for identity, _ in store.assembled():
        anchor = store.anchor_of(identity)
        if anchor is None:
            continue
        age = now - (anchor[0] * 12 + anchor[1])
        if age > FREEZE_AFTER_MONTHS:
            out[identity] = age
    return out


def _refuse_if_closed(store: Store, identity: str, period, event: dict) -> None:
    if event.get("override"):
        return
    age = _frozen_months(store).get(identity)
    if age is None:
        return
    label = _month_label(store, identity, period)
    raise _Refused(
        f"{label} is read-only - months close {FREEZE_AFTER_MONTHS} months on, "
        f"and this one closed {age - FREEZE_AFTER_MONTHS} month(s) ago - pass "
        f'"override": true to correct it anyway',
        code="closed", label=speech.Month(label), freeze=FREEZE_AFTER_MONTHS,
        age=age - FREEZE_AFTER_MONTHS,
    )


def _slots(store: Store, identity: str | None = None):
    return left_slots(store.config_at(identity) if identity else store.config)


def _classified(store: Store, name: str):
    found = store.period(name)
    if found is None:
        stored = [_span(p) for _, p in store.assembled()]
        spans = ", ".join(stored) or "(none imported yet)"
        raise _Refused(
            f"no period matches {name!r} - stored: {spans}",
            code="no_period_stored" if stored else "no_period_nothing_stored",
            name=name, spans=[speech.Month(s) for s in stored],
        )
    identity, span, period = found
    results = counted_here(classify_period(period, overlay=store.rulings(identity),
                                           dropped=_tax(store, identity).dropped))
    return identity, span, period, _named_in_line(store, identity, results)


def _named_in_line(store: Store, identity: str, results):
    tax = _tax(store, identity)
    names = [*tax.minor_names(),
             *(m.name for m in tax.majors if m.tier is not Tier.EXCLUDED),
             *store.answers.values(), *store.moves.values()]
    known: dict[str, str] = {}
    for name in names:
        if name and name not in tax.dropped:
            known.setdefault(name.lower(), name)
    out = []
    for c in results:
        if c.minor is None and c.review is not None:
            text = c.entry.text.lower()
            offered = [name for key, name in known.items()
                       if name not in c.candidates
                       and re.search(rf"(?<!\w){re.escape(key)}(?!\w)", text)]
            if offered:
                c = replace(c, candidates=tuple(offered) + tuple(c.candidates))
        out.append(c)
    return out


def _held(store: Store, identity: str, period) -> list[dict]:
    return [{"raw": c.entry.raw, "date": c.date, "amount": c.entry.signed,
             "month": c.entry.refers_to}
            for c in held(classify_period(period, overlay=store.rulings(identity)))]


def _do_periods(store: Store, event: dict):
    import datetime

    today = datetime.date.today()
    if store.backfill_years(_year(event) or today.year, today.month):
        store.save()
    return [
        {
            "identity": identity,
            "span": _span(period),
            "month": month_of(period),
            "year": store.years.get(identity),
            "days": len(period.dates),
            "moved": is_moved(identity),
        }
        for identity, period in store.assembled()
    ]


def _do_import(store: Store, event: dict):
    text = event.get("text")
    if not text or not text.strip():
        raise _Refused("import needs 'text': the raw notes")

    lang = _lang(event)
    target = event.get("period")
    moved_before = {identity for identity, _ in store.assembled() if is_moved(identity)}
    if target:
        found = store.period(target)
        if found is not None and is_moved(found[0]):
            try:
                outcome = store.import_text(text, year=_import_year(store, event, text))
            except ValueError as why:
                raise _passed(why)
            store.settle_moved(moved_before)
            store.save()
            return [_outcome(span, result, lang) for span, result in outcome]
        if found is not None:
            _refuse_if_closed(store, found[0], found[2], event)
        try:
            month, before, after, leftover = store.add_to(target, text)
        except KeyError:
            raise _Refused(f"no period matches {target!r} - call periods first",
                           code="no_period_refresh", target=target)
        except ValueError as why:
            raise _passed(why)
        reply = {"month": month, "days_before": before, "days_after": after}
        if leftover.strip():
            _refuse_closed_in_paste(store, leftover, event)
            carried = store.import_text(
                leftover, year=_import_year(store, event, leftover)
            )
            reply["carried"] = [
                _outcome(span, result, lang) for span, result in carried
            ]
        store.settle_moved(moved_before)
        store.save()
        return reply

    _refuse_closed_in_paste(store, text, event)

    try:
        outcome = [
            _outcome(span, result, lang)
            for span, result in store.import_text(
                text, replace=bool(event.get("replace")),
                year=_import_year(store, event, text),
            )
        ]
    except ValueError as why:
        raise _passed(why)
    if not outcome:
        raise _Refused(
            "no complete period found - the notes need a salary line, or name a "
            "month to add them to",
            code="no_complete_period",
        )
    store.settle_moved(moved_before)
    store.save()
    return outcome


_OUTCOMES = {
    "imported": "outcome.imported",
    "replaced": "outcome.replaced",
    "kept fuller copy": "outcome.kept",
    "kept fuller copy (carry-over fragment)": "outcome.kept_carry",
    "skipped: no dated days": "outcome.skipped",
}


def _outcome(span: str, result: str, lang: str) -> dict:
    item = {"span": span, "outcome": result}
    if lang != "en":
        item["said"] = speech.say(_OUTCOMES.get(result), lang, result)
        item["span_said"] = speech.month_label(span, lang)
    return item


def _refuse_closed_in_paste(store: Store, text: str, event: dict) -> None:
    if event.get("override"):
        return
    frozen = _frozen_months(store)
    if not frozen:
        return
    from budget.notes import parse, month_of
    from budget.store import _MARKER, _fullness, _identity

    opened = {
        str(name).strip().lower()
        for name in event.get("unlocked", [])
        if isinstance(name, str)
    }

    replace = bool(event.get("replace"))
    first_dated = True
    hit = []
    for segment in _MARKER.split(text):
        for period in parse(segment):
            if not period.dates:
                continue
            force = replace and first_dated
            first_dated = False
            identity = _identity(period)
            held = store.periods.get(identity)
            if held is None or identity not in frozen:
                continue
            if month_of(period).lower() in opened:
                continue
            incoming = segment.strip() + "\n"
            if not force and _fullness(parse(held)[0], held) >= _fullness(period, incoming):
                continue
            if len(parse(held)[0].days) <= _STUB_DAYS < len(period.days):
                continue
            label = speech.Month(_month_label(store, identity, period))
            if label not in hit:
                hit.append(label)
    if hit:
        raise _Refused(
            f"this paste would rewrite {', '.join(hit)}, which "
            f"{'is' if len(hit) == 1 else 'are'} read-only - unlock "
            f'{"it" if len(hit) == 1 else "them"} first, or pass '
            '"override": true',
            code="paste_closed", months=hit, n=len(hit),
        )


def _do_raw(store: Store, event: dict):
    found = store.period(_need(event, "period"))
    if found is None:
        raise _Refused(f"no period matches {event.get('period')!r}")
    identity, span, _ = found
    return {"identity": identity, "span": span, "text": store.periods[identity]}


def _do_show(store: Store, event: dict):
    identity, span, period, results = _classified(store, _need(event, "period"))
    return render(
        span, period, results, _year(event), rent_fixed(store, identity),
        _tax(store, identity),
        set(store.omitted.get(identity, ())), slots=_slots(store, identity),
    )


def _do_questions(store: Store, event: dict):
    identity, _, period, results = _classified(store, _need(event, "period"))
    tax = _tax(store, identity)
    lang = _lang(event)
    return [
        {
            "number": number,
            "raw": c.entry.raw,
            "review": speech.review(c.review, lang),
            "candidates": [tax.minor_label(n) for n in c.candidates],
            "occurrence": sum(1 for p in results[:number] if p.entry.raw == c.entry.raw),
            "date": c.date,
            "day": (day_windows(period, [c]) or [{"lines": []}])[0]["lines"],
        }
        for number, c in pending(results)
    ]


def _do_day(store: Store, event: dict):
    identity, span, period, results = _classified(store, _need(event, "period"))
    wanted = []
    for item in event.get("entries") or []:
        raw = item.get("raw") if isinstance(item, dict) else None
        occurrence = item.get("occurrence", 0) if isinstance(item, dict) else None
        found = [c for c in results if c.entry.raw == raw]
        if not isinstance(occurrence, int) or not 0 <= occurrence < len(found):
            raise _Refused(f"no entry {raw!r} (occurrence {occurrence}) in {span}",
                           code="no_entry", raw=raw, occurrence=occurrence,
                           span=speech.Month(span))
        wanted.append(found[occurrence])
    return day_windows(period, wanted)


def _do_answer(store: Store, event: dict):
    identity, span, period, results = _classified(store, _need(event, "period"))
    _refuse_if_closed(store, identity, period, event)
    number = event.get("number")
    group = event.get("group")
    if not isinstance(number, int) or not group:
        raise _Refused("answer needs 'number' (int, from questions) and 'group'")
    rows = dict(pending(results))
    if number not in rows:
        raise _Refused(f"no open question {number} - call questions first",
                       code="no_open_question", number=number)
    target = rows[number]

    tax = _tax(store, identity)
    resolved, choices = tax.resolve_group(group, target.entry.text)
    if choices:
        raise _Refused(
            f"{group!r} is written as several lines - say which: {choices}",
            code="several_lines", group=group, choices=choices,
        )
    group = resolved or tax.canonical_minor(group)
    known = set(tax.minor_names()) | {c.minor for c in results if c.minor}
    allow_new = bool(event.get("new"))
    if group in target.candidates:
        allow_new = True
    if group not in known and not allow_new:
        hint = speech.Said(
            f" - this question suggests {list(target.candidates)}",
            code="suggests", candidates=list(target.candidates),
        ) if target.candidates else ""
        raise _Refused(
            f"{group!r} is not an existing group{hint} - "
            'pass "new": true to start it',
            code="answer_new_group", group=group, hint=hint,
        )

    occurrence = sum(1 for c in results[:number] if c.entry.raw == target.entry.raw)
    store.answers[answer_key(identity, target, occurrence)] = group
    store.save()
    return f"answered ({span}): {target.entry.raw!r} -> {group}"


def _do_totals(store: Store, event: dict):
    identity, span, period, results = _classified(store, _need(event, "period"))
    out = _figures(store, identity, _tax(store, identity), results,
                   rent_fixed(store, identity), readings=not is_moved(identity))
    out.update({
        "span": span,
        "questions": len(pending(results)),
        "closed": identity in _frozen_months(store),
        "left": _left_line(store, identity, period, _year(event)),
        "held": _held(store, identity, period),
    })
    return out


def _left_line(store: Store, identity: str, period, year: int, depth: int = 0):
    slots = _slots(store, identity)
    left = closing_left(period, year, slots)
    if left is None and depth < 36:
        base, source = _left_base(store, identity, slots, year, depth)
        left = count_on(period, year, slots, base)
        if left is not None:
            left["counted_from"] = source
    left = with_set(left, slots, store.left_set.get(identity, {}))
    if left is None:
        left = {"raw": "", "text": assemble_left([], slots), "cells": left_cells([], slots),
                "extra": 0, "date": None, "days_after": 0, "blank": True}
    return left


def _left_base(store: Store, identity: str, slots, year: int, depth: int):
    order = store.assembled()
    ids = [ident for ident, _ in order]
    here = ids.index(identity) if identity in ids else -1
    if here > 0:
        before_id, before = order[here - 1]
        line = _left_line(store, before_id, before, store.years.get(before_id) or year,
                          depth + 1)
        if line is None:
            return None, None
        shown = line["computed"] if "computed" in line else line
        by_id = {c["id"]: c.get("value") for c in shown["cells"] if "id" in c}
        return [by_id.get(s.id) for s in slots], "before"
    if store.left_start:
        return [store.left_start.get(s.id) for s in slots], "start"
    return None, None


def _do_left_value(store: Store, event: dict):
    slot = _need(event, "slot")
    value = event.get("value")
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
        raise _Refused("left_value needs 'value': a number, or null to take it back")
    name = event.get("period")
    if name:
        identity, span, period, _ = _classified(store, name)
        _refuse_if_closed(store, identity, period, event)
        slots = _slots(store, identity)
    else:
        identity, span, slots = None, "", _slots(store)
    if slot not in {s.id for s in slots}:
        raise _Refused(f"no figure named {slot!r} in the Left line", code="no_slot",
                       wanted=slot)
    here = dict(store.left_set.get(identity, {})) if identity else dict(store.left_start)
    if value is None:
        here.pop(slot, None)
    else:
        here[slot] = float(value)
    if identity is None:
        store.left_start = here
    elif here:
        store.left_set[identity] = here
    else:
        store.left_set.pop(identity, None)
    store.save()
    return {"span": span, "slot": slot, "value": value, "start": identity is None}


def _do_empty(store: Store, event: dict):
    slots = _slots(store)
    out = _figures(store, None, _tax(store), [], {}, readings=False)
    out.update({
        "span": "",
        "empty": True,
        "questions": 0,
        "closed": False,
        "held": [],
        "left": with_set({"raw": "", "text": assemble_left([], slots),
                          "cells": left_cells([], slots), "extra": 0, "date": None,
                          "days_after": 0}, slots, store.left_start),
    })
    return out


def _figures(store: Store, identity: str | None, tax, results, fixed,
             readings: bool = True) -> dict:
    totals = tier_totals(results, fixed, tax)
    known = {major.name: major for major in tax.majors}
    omitted = set(store.omitted.get(identity, ())) if identity else set()
    adjusted = dict(store.adjusted.get(identity, {})) if identity else {}

    only_income: dict[str, bool] = {}
    for c in results:
        if c.minor is None:
            continue
        owner = tax.major_for(c.minor)
        group = owner.name if owner else c.minor
        only_income[group] = only_income.get(group, True) and c.entry.income

    ordered = [m.name for m in tax.majors if m.name not in HIDDEN]
    ordered += [name for name in totals if name not in known and name not in HIDDEN]
    def counted(name):
        if name in adjusted:
            return Decimal(str(adjusted[name]))
        return totals.get(name, Decimal(0))

    appended_total = (
        second_total(totals, tax, omitted, adjusted, HIDDEN) - totals.necessary
    )

    majors = []
    for name in ordered:
        major = known.get(name)
        value = totals.get(name, Decimal(0))
        excluded = bool(major and major.tier is Tier.EXCLUDED)
        majors.append(
            {
                "name": tax.major_label(name),
                "id": name,
                "value": float(value),
                "tier": major.tier.name if major else "OCCASIONAL",
                "limit": major.limit if major else None,
                "income": bool(major and major.is_income)
                or (name in only_income and only_income[name]),
                "chart": not excluded,
            }
        )

    def _limited():
        for name, major in known.items():
            if major.limit is not None and name not in HIDDEN:
                yield Decimal(major.limit), totals.get(name, Decimal(0))

    saved = sum((limit - spent for limit, spent in _limited() if spent < limit), Decimal(0))
    over = sum((spent - limit for limit, spent in _limited() if spent > limit), Decimal(0))
    if not readings:
        saved = over = Decimal(0)

    for label, value, flag in (
        ("Totally saved", saved, "saved"),
        ("Totally overspent", over, "overspent"),
    ):
        majors.append(
            {
                "name": label,
                "id": label,
                "value": float(value),
                "tier": "READING",
                "limit": None,
                "income": False,
                "chart": True,
                flag: True,
            }
        )

    return {
        "majors": majors,
        "minors": minor_rows(results, tax),
        "limits": [
            {
                "label": known[name].limit_label or tax.major_label(name),
                "group": name,
                "value": known[name].limit,
            }
            for name in tax.limit_order
            if known.get(name) and known[name].limit is not None
        ],
        "totals": {
            "necessary": float(totals.necessary),
            "appended": float(appended_total),
            "grand": float(totals.necessary + appended_total),
        },
        "appended": [
            {
                "name": tax.major_label(name),
                "id": name,
                "value": float(counted(name)),
                "actual": float(totals[name]),
                "adjusted": name in adjusted,
                "counted": name not in omitted,
            }
            for name in ordered
            if name in totals
            and (known.get(name) is None or known[name].tier in (Tier.FREQUENT, Tier.OCCASIONAL))
        ],
    }


def _import_year(store: Store, event: dict, text: str) -> int:
    given = event.get("year")
    if isinstance(given, int) and 1900 < given < 2200:
        return given
    import datetime

    today = datetime.date.today()
    now = _year(event)
    opening = re.search(r"^\s*\d{2}\.(\d{2})\s*$", text, re.MULTILINE)
    if opening and int(opening.group(1)) > today.month and now == today.year:
        return now - 1
    return now


def _do_setyear(store: Store, event: dict):
    identity, span, period, _ = _classified(store, _need(event, "period"))
    year = event.get("year")
    if not isinstance(year, int) or not 1900 < year < 2200:
        raise _Refused("setyear needs 'year': a four-digit calendar year")
    store.years[identity] = year
    store.save()
    return {"month": month_of(period), "span": span, "year": year}


def _do_export(store: Store, event: dict):
    fmt = event.get("format", "txt")
    if fmt not in ("txt", "rtf"):
        raise _Refused("export 'format' is 'txt' or 'rtf'")
    lang = _lang(event)

    if event.get("periods"):
        columns, labels = _compare_columns(store, event)
        body = compare_report(
            columns, _tax(store, None), fmt,
            average=bool(event.get("average")),
            title=_compare_title(labels, lang),
            lang=lang,
        )
        return {"name": f"budget-compare.{fmt}", "format": fmt, "body": body}

    wanted = event.get("year")
    if wanted is not None and not event.get("period"):
        if not isinstance(wanted, int):
            raise _Refused("export 'year' must be a four-digit calendar year")
        months = []
        for identity, period in store.assembled():
            if store.years.get(identity) != wanted:
                continue
            results = counted_here(classify_period(period, overlay=store.rulings(identity),
                                                   dropped=_tax(store, identity).dropped))
            months.append((
                _span(period), period, results, wanted, _year(event),
                rent_fixed(store, identity), set(store.omitted.get(identity, ())),
                _tax(store, identity), _slots(store, identity),
            ))
        if not months:
            raise _Refused(f"no stored month carries the year {wanted}",
                           code="no_year_stored", wanted=wanted)
        body = year_report(months, fmt, lang=lang)
        return {"name": f"budget-{wanted}.{fmt}", "format": fmt, "body": body}

    identity, span, period, results = _classified(store, _need(event, "period"))
    year = store.years.get(identity)
    body = month_report(
        span, period, results, year, _year(event), fmt,
        rent_fixed(store, identity), _tax(store, identity),
        set(store.omitted.get(identity, ())), slots=_slots(store, identity), lang=lang,
    )
    stamp = f"-{year}" if year else ""
    return {
        "name": f"budget-{month_of(period)}{stamp}.{fmt}",
        "format": fmt,
        "body": body,
    }


def _do_omit(store: Store, event: dict):
    identity, span, period, results = _classified(store, _need(event, "period"))
    _refuse_if_closed(store, identity, period, event)
    groups = event.get("groups", [])
    if not isinstance(groups, list) or any(not isinstance(g, str) for g in groups):
        raise _Refused("omit needs 'groups': a list of group names (empty counts everything)")
    tax = _tax(store, identity)
    known = {tax.major_label(m.name): m.name for m in tax.majors}
    known.update({m.name: m.name for m in tax.majors})
    for c in results:
        if c.minor and tax.major_for(c.minor) is None:
            known[c.minor] = c.minor
    unknown = [g for g in groups if g not in known]
    if unknown:
        raise _Refused(f"not groups in this month: {unknown}",
                       code="not_groups_here", unknown=unknown)
    canonical = sorted({known[g] for g in groups})
    was = set(store.omitted.get(identity, ()))
    if canonical:
        store.omitted[identity] = canonical
    else:
        store.omitted.pop(identity, None)

    fixes = store.adjusted.get(identity) or {}
    reset = sorted((was ^ set(canonical)) & set(fixes))
    for name in reset:
        del fixes[name]
    if not fixes:
        store.adjusted.pop(identity, None)

    store.save()
    return {"span": span, "omitted": canonical, "reset": reset}


def _do_adjust(store: Store, event: dict):
    identity, span, period, results = _classified(store, _need(event, "period"))
    _refuse_if_closed(store, identity, period, event)
    tax = _tax(store, identity)
    group = _need(event, "group")
    known = {tax.major_label(m.name): m.name for m in tax.majors}
    known.update({m.name: m.name for m in tax.majors})
    for c in results:
        if c.minor and tax.major_for(c.minor) is None:
            known[c.minor] = c.minor
    if group not in known:
        raise _Refused(f"{group!r} is not a group in this month",
                       code="not_group_here", group=group)
    canonical = known[group]

    value = event.get("value")
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, (int, float))
    ):
        raise _Refused("adjust needs 'value': a number in thousands, or null to undo")

    here = store.adjusted.get(identity, {})
    if value is None:
        here.pop(canonical, None)
    else:
        here[canonical] = float(value)
    if here:
        store.adjusted[identity] = here
    else:
        store.adjusted.pop(identity, None)
    store.save()
    return {"span": span, "group": canonical, "value": value}


def _purse_default() -> dict:
    from budget.left import DEFAULT_SLOTS

    for slot in DEFAULT_SLOTS:
        if slot.kind == "purse" and slot.reset:
            return dict(slot.reset)
    return {"weekday": 0, "amount": 1, "carry_deficit": True}


BACKUP_KIND = "budget-backup"
BACKUP_VERSION = 1


def _do_backup(store: Store, event: dict):
    import datetime

    from budget.rules import path_in_use

    document = {
        "kind": BACKUP_KIND,
        "version": BACKUP_VERSION,
        "saved": datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "months": len(store.periods),
        "answers": len(store.answers),
        "server": store.state(),
    }
    try:
        document["rules"] = path_in_use().read_text(encoding="utf-8")
    except OSError as why:
        raise _Refused(f"the rules file could not be read, so no backup was made: {why}",
                       code="backup_no_rules", why=why)
    return document


def _same_rules(theirs: object) -> str:
    from budget.rules import path_in_use

    if not isinstance(theirs, str):
        return "absent"
    try:
        ours = path_in_use().read_text(encoding="utf-8")
    except OSError:
        return "different"
    settle = lambda text: text.replace("\r\n", "\n").strip()
    return "same" if settle(theirs) == settle(ours) else "different"


def _do_restore(store: Store, event: dict):
    backup = event.get("backup")
    if not isinstance(backup, dict):
        raise _Refused("restore needs 'backup': the file you downloaded")
    if backup.get("kind") != BACKUP_KIND:
        raise _Refused(
            "that file is not a budget backup - it has no 'kind: budget-backup'"
        )
    version = backup.get("version")
    if not isinstance(version, int) or version > BACKUP_VERSION:
        raise _Refused(
            f"that backup was written by a newer version of the app "
            f"(version {version!r}, this one reads up to {BACKUP_VERSION})",
            code="backup_newer", version=version, max=BACKUP_VERSION,
        )
    if event.get("confirm") != "RESTORE":
        raise _Refused(
            'restore needs \'confirm\': "RESTORE" - it replaces everything stored'
        )

    was = {"months": len(store.periods), "answers": len(store.answers)}
    fresh = Store(store.path)
    try:
        fresh.restore(backup.get("server", {}))
    except ValueError as why:
        raise _passed(why)

    store.restore(fresh.state())
    store.save()
    return {
        "restored": {"months": len(store.periods), "answers": len(store.answers)},
        "replaced": was,
        "saved": backup.get("saved"),
        "rules": _same_rules(backup.get("rules")),
    }


def _do_reset(store: Store, event: dict):
    scope = event.get("scope")
    if scope not in ("answers", "month", "onward", "history", "config", "all"):
        raise _Refused(
            "reset needs 'scope': 'answers', 'month', 'onward' or 'all' "
            "('history' and 'config' are the older names for parts of 'all')"
        )
    if event.get("confirm") != "RESET":
        raise _Refused('reset needs \'confirm\': "RESET" - this cannot be undone')

    if scope == "answers":
        identity, span, period, _ = _classified(store, _need(event, "period"))
        _refuse_if_closed(store, identity, period, event)
        gone = [k for k in store.answers if k.startswith(f"{identity}|")]
        for key in gone:
            del store.answers[key]
        for key in [k for k in store.moves if k.startswith(f"{identity}|")]:
            del store.moves[key]
        store.omitted.pop(identity, None)
        store.adjusted.pop(identity, None)
        store.save()
        asked = len(_do_questions(store, {"period": event["period"]}))
        return {
            "scope": scope,
            "month": _month_label(store, identity, period, _lang(event)),
            "span": span,
            "wiped": {"answers": len(gone)},
            "questions": asked,
        }

    if scope in ("month", "onward"):
        identity, _, period = _need_period(store, _need(event, "period"))
        anchor = store.anchor_of(identity)
        if anchor is None:
            raise _Refused(
                f"{month_of(period)} has no year recorded - set its year first, "
                "or a scoped reset cannot know which months it covers",
                code="reset_no_year", month=speech.Month(month_of(period)),
            )
        _refuse_if_closed(store, identity, period, event)
        doomed = [
            (ident, per) for ident, per in store.assembled()
            if _covers(scope, anchor, store.anchor_of(ident))
        ]
        for ident, per in doomed:
            _refuse_if_closed(store, ident, per, event)
        months = [_month_label(store, ident, per, _lang(event)) for ident, per in doomed]
        for ident, _ in doomed:
            store.periods.pop(ident, None)
            store.years.pop(ident, None)
            store.omitted.pop(ident, None)
            store.adjusted.pop(ident, None)
            store.left_set.pop(ident, None)
            for key in [k for k in store.answers if k.startswith(f"{ident}|")]:
                del store.answers[key]
        here = anchor[0] * 12 + anchor[1]
        store.config_versions = [
            v for v in store.config_versions
            if not _covers(scope, anchor,
                           (v["from"].get("year"), v["from"].get("month")))
        ] if scope == "onward" else [
            v for v in store.config_versions
            if v["from"].get("year", 0) * 12 + v["from"].get("month", 0) != here
        ]
        store._assembled = None
        store.forget_taxonomy()
        store.save()
        return {"scope": scope, "wiped": {"months": len(doomed)}, "months": months}

    wiped = {}
    if scope in ("history", "all"):
        wiped["months"] = len(store.periods)
        wiped["answers"] = len(store.answers)
        store.periods.clear()
        store.answers.clear()
        store.years.clear()
        store.omitted.clear()
        store.adjusted.clear()
        store.left_set.clear()
        store._assembled = None
    if scope in ("config", "all"):
        wiped["group_edits"] = len(store.config.get("majors", {})) + len(
            store.config.get("minors", {})
        )
        wiped["scoped_edits"] = len(store.config_versions)
        store.config = {}
        store.left_start = {}
        store.config_versions = []
    store.forget_taxonomy()
    store.save()
    return {"scope": scope, "wiped": wiped}


def _start_line(store: Store, slots) -> dict:
    return with_set({"raw": "", "text": assemble_left([], slots), "cells": left_cells([], slots),
                     "extra": 0, "date": None, "days_after": 0}, slots, store.left_start)


def _config_payload(store: Store, identity: str | None = None) -> dict:
    tax = _tax(store, identity)
    layer = (store.config_at(identity) if identity else store.config) or {}
    his_own = {name for name, patch in (layer.get("minors") or {}).items()
               if patch.get("added")}
    role_of = {name: role for role, name in RULES["groups"]["roles"].items() if role != "rent"}
    return {
        "majors": [
            {
                "name": m.name,
                "label": tax.major_label(m.name),
                "tier": m.tier.name,
                "limit": m.limit,
                "limit_label": m.limit_label,
                "income": m.is_income,
                "fixed": m.fixed,
                "minors": [
                    {"name": n, "label": tax.minor_label(n), "added": n in his_own,
                     "role": role_of.get(n)}
                    for n in m.minors
                ],
            }
            for m in tax.majors
        ],
        "limit_order": list(tax.limit_order),
        "left": {"slots": as_json(_slots(store, identity)), "kinds": list(KINDS),
                 "start": _start_line(store, _slots(store, identity))},
        "words": [
            {"word": word, "group": group, "label": tax.minor_label(group)}
            for word, group in words_of(
                store.config_at(identity) if identity else store.config)
        ],
        "overlay": store.config,
        "versions": [
            {"id": v["id"], "scope": v["scope"], "from": v["from"].get("month_name"),
             "year": v["from"].get("year"), "note": v.get("note", "")}
            for v in store.config_versions
        ],
        "closed": sorted(_frozen_months(store)),
    }


def _do_config(store: Store, event: dict):
    name = event.get("period")
    if not name:
        return _config_payload(store)
    identity, _, _ = _need_period(store, name)
    return _config_payload(store, identity)


def _limits_in(tax) -> int:
    return sum(1 for m in tax.majors if m.limit is not None)


def _apply_op(store: Store, tax, config: dict, event: dict, below: dict | None = None) -> dict:
    op = event.get("op")

    def need(field: str) -> str:
        value = event.get(field)
        if not isinstance(value, str) or not value.strip():
            raise _Refused(f"configure {op!r} needs {field!r}",
                           code="needs_field", field=field)
        return value.strip()

    def fresh_name(name: str, beside: str | None = None) -> str:
        if name in tax.all_names():
            minors = set(tax.minor_names()) | {tax.minor_label(m) for m in tax.minor_names()}
            if beside is None or name != tax.major_label(beside) or name in minors:
                raise _Refused(f"{name!r} already names a group", code="name_taken", name=name)
        return name

    def route(minor: str, target: str, dest) -> None:
        if minor == RULES["groups"]["roles"]["reimbursements"] and not dest.is_income:
            raise _Refused(f"{minor} is income - it can only route to an income group",
                           code="income_only", minor=minor)
        if dest.tier is Tier.EXCLUDED:
            raise _Refused(
                f"{target!r} is excluded from every total - routing "
                f"{minor!r} there would silently stop counting its money",
                code="excluded_route", target=target, minor=minor,
            )

    majors_cfg = config.setdefault("majors", {})
    minors_cfg = config.setdefault("minors", {})

    def int_limit(value):
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or not 0 < value < 10_000:
            raise _Refused("limit is thousands: a positive int, or null to remove",
                           code="limit_thousands")
        return value

    if op == "add_major":
        name = need("name")
        tier = event.get("tier", "NECESSARY")
        if not isinstance(tier, str) or tier not in Tier.__members__:
            raise _Refused(f"tier must be one of {list(Tier.__members__)}")
        removed = majors_cfg.get(name, {}).get("removed")
        if removed:
            patch = majors_cfg[name]
            del patch["removed"]
            patch["tier"] = tier
        else:
            if len(tax.majors) >= MAX_MAJORS:
                raise _Refused(f"at most {MAX_MAJORS} major groups",
                               code="most_majors", n=MAX_MAJORS)
            fresh_name(name)
            patch = majors_cfg.setdefault(name, {})
            patch["added"] = True
            patch["tier"] = tier
            if below is not None and below.get("majors", {}).get(name, {}).get("removed"):
                patch["removed"] = False
        if event.get("limit") is not None:
            if _limits_in(tax) >= MAX_LIMITS:
                raise _Refused(f"at most {MAX_LIMITS} limits", code="most_limits", n=MAX_LIMITS)
            patch["limit"] = int_limit(event["limit"])
        if event.get("income"):
            patch["income"] = True

    elif op == "remove_major":
        name = tax.canonical_major(need("major"))
        major = tax.major(name)
        if major is None:
            raise _Refused(f"no major group named {name!r}", code="no_major", name=name)
        counted = [m for m in tax.majors if m.tier is not Tier.EXCLUDED and not m.is_income]
        if counted == [major]:
            raise _Refused(f"{name!r} is the last group spending can go to - one always stays",
                           code="last_major", name=name)
        if major.minors:
            given = event.get("minors_to")
            if not isinstance(given, str) or not given.strip():
                for minor in major.minors:
                    minors_cfg[minor] = {"removed": True}
                entry = majors_cfg.get(name, {})
                if entry.get("added"):
                    del majors_cfg[name]
                else:
                    majors_cfg[name] = {"removed": True}
                return config
            target = tax.canonical_major(given.strip())
            dest = tax.major(target)
            if dest is None:
                raise _Refused(f"no major group named {target!r}", code="no_major", name=target)
            if target == name:
                raise _Refused(f"{name!r}'s minor groups must move to another group",
                               code="minors_to_itself", name=name)
            if major.tier is Tier.EXCLUDED and dest.tier is not Tier.EXCLUDED:
                raise _Refused(
                    f"{name!r} is counted in no total - moving its minor groups to "
                    f"{target!r} would start counting their money",
                    code="uncounted_route", name=name, target=target,
                )
            if major.tier is not Tier.EXCLUDED:
                for minor in major.minors:
                    route(minor, target, dest)
            for minor in major.minors:
                minors_cfg.setdefault(minor, {})["major"] = target
        entry = majors_cfg.get(name, {})
        if entry.get("added"):
            del majors_cfg[name]
        else:
            majors_cfg[name] = {"removed": True}

    elif op == "rename_major":
        name = tax.canonical_major(need("major"))
        major = tax.major(name)
        if major is None:
            raise _Refused(f"no major group named {name!r}", code="no_major", name=name)
        new = need("name")
        old = tax.major_label(name)
        if new not in (name, old):
            fresh_name(new)
        majors_cfg.setdefault(name, {})["renamed"] = new
        for minor in major.minors:
            if tax.minor_label(minor) == old:
                minors_cfg.setdefault(minor, {})["renamed"] = new

    elif op == "rename_minor":
        name = tax.canonical_minor(need("minor"))
        if name not in tax.minor_names():
            raise _Refused(f"no minor group named {name!r}", code="no_minor", name=name)
        new = need("name")
        if new not in (name, tax.minor_label(name)):
            home = tax.major_for(name)
            fresh_name(new, beside=home.name if home else None)
        minors_cfg.setdefault(name, {})["renamed"] = new

    elif op == "reroute_minor":
        minor = tax.canonical_minor(need("minor"))
        if minor not in tax.minor_names():
            raise _Refused(f"no minor group named {minor!r}", code="no_minor", name=minor)
        target = tax.canonical_major(need("major"))
        dest = tax.major(target)
        if dest is None:
            raise _Refused(f"no major group named {target!r} - add_major first",
                           code="no_major_add_first", target=target)
        route(minor, target, dest)
        minors_cfg.setdefault(minor, {})["major"] = target

    elif op == "add_minor":
        if len(tax.minor_names()) >= MAX_MINORS:
            raise _Refused(f"at most {MAX_MINORS} minor groups", code="most_minors", n=MAX_MINORS)
        name = need("name")
        target = tax.canonical_major(need("major"))
        if tax.major(target) is None:
            raise _Refused(f"no major group named {target!r} - add_major first",
                           code="no_major_add_first", target=target)
        fresh_name(name, beside=target)
        minors_cfg[name] = {"added": True, "major": target}

    elif op == "remove_minor":
        name = tax.canonical_minor(need("minor"))
        if name not in tax.minor_names():
            raise _Refused(f"no minor group named {name!r}", code="no_minor", name=name)
        entry = minors_cfg.get(name, {})
        given = event.get("lines_to")
        into = None
        if isinstance(given, str) and given.strip():
            into = tax.settled(tax.canonical_minor(given.strip()))
            if into not in tax.minor_names():
                raise _Refused(f"no minor group named {given.strip()!r}",
                               code="no_minor", name=given.strip())
            if into == name:
                raise _Refused(f"{name!r}'s lines must join another group",
                               code="lines_to_itself", name=name)
            here, there = tax.major_for(name), tax.major_for(into)
            if ((here.tier is Tier.EXCLUDED) != (there.tier is Tier.EXCLUDED)
                    or here.is_income != there.is_income):
                raise _Refused(
                    f"{name!r} and {into!r} are counted differently - moving the "
                    "lines there would change a total",
                    code="merge_counts_differently", minor=name, into=into,
                )
        minors_cfg[name] = {"removed": True, "into": into} if into else {"removed": True}

    elif op == "set_limit":
        name = tax.canonical_major(need("major"))
        major = tax.major(name)
        if major is None:
            raise _Refused(f"no major group named {name!r}", code="no_major", name=name)
        if major.tier is Tier.EXCLUDED:
            raise _Refused(f"{name!r} is excluded from every total - no limit applies",
                           code="excluded_no_limit", name=name)
        if (major.limit is None and event.get("value") is not None
                and _limits_in(tax) >= MAX_LIMITS):
            raise _Refused(f"at most {MAX_LIMITS} limits", code="most_limits", n=MAX_LIMITS)
        majors_cfg.setdefault(name, {})["limit"] = int_limit(event.get("value"))

    elif op == "rename_limit":
        name = tax.canonical_major(need("major"))
        major = tax.major(name)
        if major is None or major.limit is None:
            raise _Refused(f"{name!r} carries no limit", code="no_limit", name=name)
        majors_cfg.setdefault(name, {})["limit_label"] = need("label")

    elif op == "move_limit":
        source = tax.canonical_major(need("major"))
        target = tax.canonical_major(need("to"))
        s_major, t_major = tax.major(source), tax.major(target)
        if s_major is None or s_major.limit is None:
            raise _Refused(f"{source!r} carries no limit to move",
                           code="no_limit_to_move", source=source)
        if t_major is None:
            raise _Refused(f"no major group named {target!r}", code="no_major", name=target)
        if t_major.tier is Tier.EXCLUDED:
            raise _Refused(f"{target!r} is excluded from every total - no limit applies",
                           code="excluded_no_limit", name=target)
        if t_major.limit is not None:
            raise _Refused(f"{target!r} already carries a limit", code="has_limit", target=target)
        majors_cfg.setdefault(target, {})["limit"] = s_major.limit
        if s_major.limit_label:
            majors_cfg.setdefault(target, {})["limit_label"] = s_major.limit_label
        majors_cfg.setdefault(source, {})["limit"] = None
        majors_cfg.setdefault(source, {})["limit_label"] = None
        order = list(tax.limit_order)
        config["limit_order"] = [target if n == source else n for n in order]

    elif op == "learn_word":
        word = " ".join(need("word").split())
        if len(word) < 3 or not any(ch.isalpha() for ch in word):
            raise _Refused("a word to teach needs three characters and a letter in it",
                           code="word_short")
        if len(word) > 60:
            raise _Refused("that is a line, not a word - teach the word that names the thing",
                           code="word_is_line")
        group = need("group")
        resolved, choices = tax.resolve_group(group, word)
        if choices:
            raise _Refused(f"{group!r} is written as several lines - say which: {choices}",
                           code="several_lines", group=group, choices=choices)
        canonical = resolved or tax.canonical_minor(group)
        if canonical not in set(tax.minor_names()) and not event.get("new"):
            raise _Refused(
                f"{group!r} is not a group that exists - pass \"new\": true to start it",
                code="teach_new_group", group=group,
            )
        words_cfg = config.setdefault("words", {})
        key = word.casefold()
        already = {w.casefold() for w, _ in words_of(store.config)}
        already |= {w.casefold() for w, _ in words_of(config)}
        if key not in already and len(already) >= MAX_WORDS:
            raise _Refused(f"at most {MAX_WORDS} taught words", code="most_words", n=MAX_WORDS)
        words_cfg[key] = {"group": canonical, "shown": word}

    elif op == "forget_word":
        word = " ".join(need("word").split())
        key = word.casefold()
        words_cfg = config.setdefault("words", {})
        layers = [store.config, config] + [v.get("config", {}) for v in store.config_versions]
        if not any(key == w.casefold() for layer in layers for w, _ in words_of(layer)):
            raise _Refused(f"no word {word!r} has been taught", code="word_not_taught", word=word)
        if words_cfg.get(key, {}).get("group"):
            del words_cfg[key]
        else:
            words_cfg[key] = {"removed": True}

    elif op and op.startswith("left_"):
        slots = as_json(left_slots(config if below is None else compose([below, config])))
        index = {s["id"]: i for i, s in enumerate(slots)}

        def slot_at(field: str) -> int:
            wanted = need(field)
            if wanted not in index:
                raise _Refused(f"no figure named {wanted!r} in the Left line",
                               code="no_slot", wanted=wanted)
            return index[wanted]

        if op == "left_rename_slot":
            at = slot_at("slot")
            slots[at]["label"] = event.get("label", "")
            if event.get("place") in ("before", "after"):
                slots[at]["place"] = event["place"]
            if isinstance(event.get("join"), str):
                slots[at]["join"] = event["join"]

        elif op == "left_set_kind":
            at = slot_at("slot")
            kind = need("kind")
            if kind not in KINDS:
                raise _Refused(f"kind must be one of {list(KINDS)}")
            slots[at]["kind"] = kind
            if kind == "purse":
                slots[at].setdefault("reset", _purse_default())
                if isinstance(event.get("reset"), dict):
                    slots[at]["reset"] = event["reset"]
                if isinstance(event.get("minors"), list):
                    slots[at]["minors"] = [
                        tax.canonical_minor(m) for m in event["minors"]
                    ]
            else:
                slots[at].pop("reset", None)
                slots[at].pop("minors", None)

        elif op == "left_add_slot":
            if len(slots) >= MAX_SLOTS:
                raise _Refused(f"the Left line takes at most {MAX_SLOTS} figures",
                               code="most_figures", n=MAX_SLOTS)
            label = event.get("label", "")
            kind = event.get("kind", "carry")
            if kind not in KINDS:
                raise _Refused(f"kind must be one of {list(KINDS)}")
            base_id = re.sub(r"[^a-z0-9]+", "-", str(label).lower()).strip("-") or "figure"
            new_id, n = base_id, 2
            while new_id in index:
                new_id, n = f"{base_id}-{n}", n + 1
            fresh = {"id": new_id, "label": str(label), "place": "before",
                     "join": " ", "kind": kind, "unit": "thousands", "decimals": 1}
            if kind == "purse":
                fresh["reset"] = _purse_default()
                fresh["minors"] = []
            after = event.get("after")
            slots.insert(index[after] + 1 if after in index else len(slots), fresh)

        elif op == "left_remove_slot":
            at = slot_at("slot")
            if len(slots) == 1:
                raise _Refused("the Left line needs at least one figure",
                               code="left_needs_figure")
            del slots[at]

        elif op == "left_reorder":
            order = event.get("order")
            if not isinstance(order, list) or sorted(order) != sorted(index):
                raise _Refused("reorder needs 'order': every figure id, once each")
            slots = [slots[index[i]] for i in order]

        elif op == "left_reset":
            config.pop("left", None)
            slots = None if below is None else as_json(left_slots(None))

        else:
            raise _Refused(f"unknown Left operation {op!r}")

        if slots is not None:
            config["left"] = {"slots": slots}

    else:
        raise _Refused(
            "configure needs 'op': one of add_major, remove_major, rename_major, "
            "rename_minor, reroute_minor, add_minor, remove_minor, set_limit, "
            "rename_limit, move_limit, learn_word, forget_word, left_add_slot, "
            "left_remove_slot, left_rename_slot, left_set_kind, left_reorder, "
            "left_reset"
        )

    for entity in (majors_cfg, minors_cfg):
        for key in [k for k, v in entity.items() if not v]:
            del entity[key]
    try:
        effective(config)
        left_slots(config)
    except Exception as why:
        raise _Refused(f"that edit does not compose: {why}", code="does_not_compose", why=why)
    return config


def _do_configure(store: Store, event: dict):
    scope = event.get("scope", "always")
    if scope not in ("always", "month", "onward"):
        raise _Refused("scope is 'always', 'month' or 'onward'")

    ops = event.get("ops")
    if ops is None:
        ops = [event]
    if not isinstance(ops, list) or not ops:
        raise _Refused("configure needs 'op', or 'ops': a list of them")

    if scope == "always":
        config = copy.deepcopy(store.config) or {}
        tax = _tax(store)
        for one in ops:
            config = _apply_op(store, tax, config, one)
            tax = effective(config)
        store.config = config
        store.forget_taxonomy()
        store.save()
        return _config_payload(store)

    name = event.get("period")
    if not name:
        raise _Refused(f"a {scope} edit needs 'period': the month it starts at")
    identity, _, period = _need_period(store, name)
    anchor = store.anchor_of(identity)
    if anchor is None:
        raise _Refused(
            f"{month_of(period)} has no year recorded - set its year first, or "
            "a scoped edit cannot know which months it covers",
            code="edit_no_year", month=speech.Month(month_of(period)),
        )

    config: dict = {}
    tax = _tax(store, identity)
    below = store.config_at(identity)
    for one in ops:
        config = _apply_op(store, tax, config, one, below)
        tax = effective(compose([below, config]))

    covered = [
        _month_label(store, ident, per)
        for ident, per in store.assembled()
        if _covers(scope, anchor, store.anchor_of(ident))
    ]
    lang = _lang(event)
    if not event.get("confirm"):
        later = speech.say("every_later_month", lang, "and every later month")
        return {
            "pending": True,
            "scope": scope,
            "from": _month_label(store, identity, period, lang),
            "months": _labels(covered, lang) + ([later] if scope == "onward" else []),
            "ops": ops,
        }

    store.config_versions.append({
        "id": store.next_version_id(),
        "scope": scope,
        "from": {
            "year": anchor[0], "month": anchor[1],
            "identity": identity, "month_name": month_of(period),
        },
        "note": event.get("note", ""),
        "config": config,
    })
    store.forget_taxonomy()
    store.save()
    result = _config_payload(store, identity)
    result["applied"] = {"scope": scope, "months": _labels(covered, lang)}
    return result


def _covers(scope: str, anchor, other) -> bool:
    if other is None:
        return False
    here, there = anchor[0] * 12 + anchor[1], other[0] * 12 + other[1]
    return there == here if scope == "month" else there >= here


def _need_period(store: Store, name: str):
    matches = [
        (ident, per) for ident, per in store.assembled()
        if month_of(per).lower() == str(name).lower()
    ]
    if len(matches) > 1:
        months = [speech.Month(_month_label(store, i, p)) for i, p in matches]
        labels = ", ".join(months)
        raise _Refused(f"{name!r} matches more than one month - say which: {labels}",
                       code="several_months", name=name, labels=months)
    found = store.period(name)
    if found is None:
        raise _Refused(f"no period matches {name!r}", code="no_period", name=name)
    return found


def _year(event: dict) -> int:
    import datetime

    year = event.get("year")
    return year if isinstance(year, int) else datetime.date.today().year


def _do_ocr(store: Store, event: dict):
    image = event.get("image")
    if not image:
        raise _Refused("ocr needs 'image': a base64 screenshot")
    if len(image) > 8_000_000:
        raise _Refused("image too large - keep it under about 5 MB", code="image_too_large")
    from budget.ocr import extract

    try:
        text = extract(image)
    except Exception as why:
        engine = getattr(extract, "__module__", "") or ""
        hint = (
            " (the cloud's reading service refused - check its permissions)"
            if "ocr" in engine and "local" not in engine
            else ""
        )
        raise _Refused(f"could not read that screenshot: {why}{hint}",
                       code="ocr_failed", why=why, hint=hint)
    return {"text": text}


def _do_move(store: Store, event: dict):
    identity, span, period, results = _classified(store, _need(event, "period"))
    _refuse_if_closed(store, identity, period, event)
    raw = event.get("raw")
    if not isinstance(raw, str) or not raw.strip():
        raise _Refused('move needs \'raw\': the entry line, from the minor list')
    occurrence = event.get("occurrence", 0)
    if not isinstance(occurrence, int) or occurrence < 0:
        raise _Refused("move needs 'occurrence': which copy of the line (from 0)")

    seen = 0
    target = None
    for c in results:
        if c.entry.raw == raw:
            if seen == occurrence:
                target = c
                break
            seen += 1
    if target is None:
        raise _Refused(f"no entry {raw!r} (occurrence {occurrence}) in {span}",
                       code="no_entry", raw=raw, occurrence=occurrence,
                       span=speech.Month(span))

    key = f"{identity}|{raw}|{occurrence}"
    group = event.get("group")
    if group is None:
        was = store.moves.pop(key, None)
        store.save()
        return {"span": span, "raw": raw, "moved": None,
                "lifted": was is not None}

    if not isinstance(group, str) or not group.strip():
        raise _Refused("move needs 'group': where the entry should be booked")
    tax = _tax(store, identity)
    resolved, choices = tax.resolve_group(group, target.entry.text)
    if choices:
        raise _Refused(f"{group!r} is written as several lines - say which: {choices}",
                       code="several_lines", group=group, choices=choices)
    group = resolved or tax.canonical_minor(group)
    known = set(tax.minor_names()) | {c.minor for c in results if c.minor}
    if group not in known and not event.get("new"):
        raise _Refused(
            f"{group!r} is not an existing group - pass \"new\": true to start it",
            code="move_new_group", group=group,
        )
    store.moves[key] = group
    store.save()
    return {"span": span, "raw": raw, "moved": group}


def _do_unanswer(store: Store, event: dict):
    identity, span, period, _ = _classified(store, _need(event, "period"))
    _refuse_if_closed(store, identity, period, event)
    items = event.get("entries")
    if not isinstance(items, list) or not items:
        raise _Refused('unanswer needs \'entries\': [{"raw": …, "occurrence": …}]')
    removed = 0
    for item in items:
        key = f"{identity}|{item.get('raw')}|{item.get('occurrence', 0)}"
        if key in store.answers:
            del store.answers[key]
            removed += 1
    if removed:
        store.save()
    return {"removed": removed, "span": span}


def _compare_columns(store: Store, event: dict):
    names = event.get("periods")
    if not isinstance(names, list) or not names:
        raise _Refused("compare needs 'periods': a list of months")
    lang = _lang(event)
    columns, labels = [], []
    for name in names:
        identity, _, period, results = _classified(store, name)
        year = store.years.get(identity)
        label = f"{month_of(period)} {year}" if year else month_of(period)
        labels.append(label)
        columns.append((
            speech.month_label(label, lang), results, rent_fixed(store, identity),
            _tax(store, identity),
            (store.omitted.get(identity, ()), store.adjusted.get(identity, {})),
        ))
    return columns, labels


def _compare_title(labels: list[str], lang: str = "en") -> str:
    if not labels:
        return speech.say("comparison", lang, "Comparison")
    years = {label.rsplit(" ", 1)[-1] for label in labels}
    if len(years) == 1 and next(iter(years)).isdigit():
        year = next(iter(years))
        return speech.say("comparison_of_year", lang,
                          f"Comparison - {len(labels)} months of {year}",
                          n=len(labels), year=year)
    return speech.say("comparison_range", lang, f"Comparison - {labels[0]} to {labels[-1]}",
                      first=speech.Month(labels[0]), last=speech.Month(labels[-1]))


def _do_compare(store: Store, event: dict):
    names = event.get("periods")
    average = bool(event.get("average"))
    least = 1 if average else 2
    if not isinstance(names, list) or len(names) < least:
        raise _Refused(
            "compare needs 'periods': a list of "
            + ("one or more" if average else "two or more")
        )
    columns, _ = _compare_columns(store, event)
    return compare(
        columns,
        _tax(store, names and store.period(names[-1])[0]),
        average=average,
        lang=_lang(event),
    )


def _need(event: dict, field: str) -> str:
    value = event.get(field)
    if not value:
        raise _Refused(f"{event.get('action')} needs {field!r}")
    return value


_ACTIONS = {
    "periods": _do_periods,
    "import": _do_import,
    "show": _do_show,
    "questions": _do_questions,
    "day": _do_day,
    "answer": _do_answer,
    "compare": _do_compare,
    "totals": _do_totals,
    "empty": _do_empty,
    "left_value": _do_left_value,
    "raw": _do_raw,
    "ocr": _do_ocr,
    "unanswer": _do_unanswer,
    "move": _do_move,
    "export": _do_export,
    "setyear": _do_setyear,
    "config": _do_config,
    "configure": _do_configure,
    "omit": _do_omit,
    "adjust": _do_adjust,
    "reset": _do_reset,
    "backup": _do_backup,
    "restore": _do_restore,
}


def dispatch(store: Store, event: dict) -> dict:
    lang = _lang(event)
    action = event.get("action")
    handler = _ACTIONS.get(action)
    if handler is None:
        return {
            "ok": False,
            "error": speech.render(
                None, {}, lang, f"unknown action {action!r} - one of {sorted(_ACTIONS)}"
            ),
        }
    try:
        return {"ok": True, "result": handler(store, event)}
    except _Refused as refusal:
        reply = {
            "ok": False,
            "error": speech.render(refusal.code, refusal.values, lang, str(refusal)),
        }
        if refusal.code:
            reply["code"] = refusal.code
        return reply
    except Exception as why:
        said = isinstance(why, speech.Said)
        english = f"internal: {'ValueError' if said else type(why).__name__}: {why}"
        return {
            "ok": False,
            "error": speech.render(
                why.code if said else None, why.values if said else {}, lang, english
            ),
        }
