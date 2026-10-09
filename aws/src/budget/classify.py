"""Sorts each entry of a period into a minor group.

In order: the context of its block (an outing claims its own fares), an ordered
keyword table from the rules file, a doubt rule that asks when two groups' words
share a line, then passes that place tips and match refunds to their purchases.
The user's answers, moves and taught words are laid over the result and outrank
every rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from functools import lru_cache

from budget import grammar, speech
from budget.groups import Tier, major_for
from budget.notes import Block, Entry, Period
from budget.rules import RULES, resolve_pattern

__all__ = ["Classification", "classify_block", "classify_period", "coverage", "ruled_group",
           "taught_group", "TAUGHT", "his_ruling"]


_CFG = RULES["classify"]
_ROLES = RULES["groups"]["roles"]

GRAMMAR = grammar.build(RULES.get("notes", {}))


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


def _named(name: str) -> str:
    return resolve_pattern(_CFG, "@" + name)


_CONTEXTS: tuple[tuple[str, str], ...] = tuple(
    (pattern, minor) for pattern, minor in _CFG["contexts"]
)
_COMPILED_CONTEXTS = tuple((_rx(pattern), minor) for pattern, minor in _CONTEXTS)

_APPOINTMENT: tuple[str, str] = (_CFG["appointment"][0], _CFG["appointment"][1])
_COMPILED_APPOINTMENT = _rx(_APPOINTMENT[0])

_CONTEXT_QUESTIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    minor: (speech.ask("context", question), tuple(offered))
    for minor, (question, offered) in _CFG["context_questions"].items()
}

_FARE = GRAMMAR.fare

_ROAD = GRAMMAR.road

_TRIP = _CFG["trip"]
_TRIP_ROAD: str = _TRIP["road"]
_TRIP_TAXI: str = _TRIP["taxi"]
_TRIP_RESTAURANTS: str = _TRIP["restaurants"]
_TRIP_FARE: int = _TRIP["fare"]
_TRIP_LEGS: tuple[tuple[int, int], ...] = tuple(
    (first, second) for first, second in _TRIP["legs"]
)

_HOMEWARD = GRAMMAR.homeward

_FOOD_WORDS = _named("food_words")
_FOOD = _rx(_FOOD_WORDS)

_PUB = _rx(_named("pubs"))

_NAMED_RESTAURANT = _rx(_named("named_restaurants"))

_MEAL = _rx(_named("meals"))

_SETTLEMENTS = _CFG["settlements"]
_PARTNER: str = _SETTLEMENTS["partner"]
_SETTLED: str = _SETTLEMENTS["group"]
_SETTLEMENT = _rx(_SETTLEMENTS["settlement"])
_PARTNER_NAMED = _rx(_SETTLEMENTS["named"])

_INSURER_NAMED = _rx(_CFG["reimbursements"]["named"])

_REIMBURSEMENTS: str = _ROLES["reimbursements"]
_SALARY: str = _ROLES["salary"]
_ELSEWHERE: str = _ROLES["elsewhere"]
_FOOD_CASH: str = _CFG["food"]["cash"]
_FOOD_CARD: str = _CFG["food"]["card"]
_FOOD_TAXI: str = _CFG["food"]["taxi"]

_PREPAYMENT = GRAMMAR.prepayment


def ruled_group(entry: Entry, group: str) -> str:
    if entry.income and _PREPAYMENT.search(group):
        return _SALARY
    return group

_STOP_WORDS = GRAMMAR.stop_words

_FLOWERS = GRAMMAR.flowers
_FLOWER_CEILING: int = _CFG["thresholds"]["flower_ceiling"]

_TICKETS = frozenset(_CFG["fares"]["tickets"])

_OCCASION = GRAMMAR.occasion

_GROCERY = _rx(_named("groceries"))

_GROCERIES_NAMED = GRAMMAR.groceries_named

_CARVE_OUT = GRAMMAR.carve_out

_PLATFORM = _rx(_CFG["platform_words"])

_SALARY_FLOOR: int = _CFG["thresholds"]["salary_floor"]

_ALCOHOL = _rx(_CFG["alcohol"]["words"])
_CELEBRATION: str = _CFG["alcohol"]["celebration"]

_UNPLACED_FARE = GRAMMAR.unplaced_fare

_NAMED_FARE = GRAMMAR.named_fare

_PAID_BY_CARD = GRAMMAR.paid_by_card

_GIFT = GRAMMAR.gift

_RULES: tuple[tuple[str, str], ...] = tuple(
    (resolve_pattern(_CFG, pattern), minor) for pattern, minor in _CFG["rules"]
)
_COMPILED = tuple((_rx(pattern), minor) for pattern, minor in _RULES)

_PLATFORMS = frozenset(_CFG["platforms"])


def _shown(minor: str) -> str:
    owner = major_for(minor)
    return owner.name if owner else minor


_TRIP_NAME = _shown(_TRIP_ROAD)
_FOOD_NAME = _shown(_FOOD_CASH)


@dataclass(frozen=True)
class Classification:
    entry: Entry
    minor: str | None
    rule: str
    review: str | None = None
    candidates: tuple[str, ...] = ()
    block: int = -1
    date: str | None = None

    @property
    def confident(self) -> bool:
        return self.review is None


def _context_of(block: Block) -> tuple[re.Pattern[str], str] | None:
    for pattern, minor in _COMPILED_CONTEXTS:
        if any(pattern.search(entry.text) for entry in block.entries):
            return pattern, minor
    if any(_COMPILED_APPOINTMENT.search(e.text) for e in block.entries) and not any(
        _FOOD.search(e.text) or _GROCERY.search(e.text) for e in block.entries
    ):
        return _COMPILED_APPOINTMENT, _APPOINTMENT[1]
    return None


def _claimed(entry: Entry, pattern: re.Pattern[str]) -> bool:
    if entry.income:
        return False
    if entry.bare or _FARE.search(entry.text):
        return True
    return bool(pattern.search(entry.text))


def _by_keyword(entry: Entry) -> Classification:
    text = entry.text

    if entry.income and _PREPAYMENT.search(text):
        return Classification(entry, _SALARY, "prepayment is salary")

    if entry.deferred:
        named = entry.refers_to
        return Classification(
            entry, _ELSEWHERE, f"belongs to {named}" if named else "belongs to another month"
        )

    if entry.income and not text:
        return Classification(entry, None, "none",
                              speech.ask("unlabelled_income", "unlabelled income"))
    if entry.bare:
        if entry.amount in _TICKETS:
            return Classification(
                entry, None, "none",
                speech.ask("fare_unnamed",
                           "a fare with nothing naming it - where did this one go?"),
            )
        return Classification(entry, None, "none",
                              speech.ask("bare_amount",
                                         "bare amount with no outing to attach it to"))

    if _UNPLACED_FARE.search(text):
        return Classification(entry, None, "none",
                              speech.ask("fare_unplaced", "fare with no outing to attach it to"))

    named_fare = _NAMED_FARE.match(text)
    if named_fare and not entry.income:
        what = named_fare.group("what").strip(" ,")
        known = next((minor for pattern, minor in _COMPILED if pattern.search(what)), None)
        if known is not None:
            return Classification(entry, known, f"a fare for {known}")
        return Classification(
            entry, None, "none",
            speech.ask("fare_for", f"a fare for {what} - which group does it belong to?",
                       what=what),
            (what[:1].upper() + what[1:],),
        )

    if entry.income and _INSURER_NAMED.search(text):
        return Classification(entry, _REIMBURSEMENTS, f"a credit naming {_REIMBURSEMENTS}")

    if entry.income and _SETTLEMENT.search(text):
        named = next((minor for p, minor in _COMPILED if p.search(text)), None)
        if named is not None:
            return Classification(entry, named, f"money back from {_PARTNER}, for what it names")
        return Classification(
            entry,
            _SETTLED,
            f"a {_PARTNER} settlement",
            speech.ask(
                "partner_unsaid",
                f"money from {_PARTNER}, with nothing saying what for - {_SETTLED.lower()}?",
                partner=_PARTNER, settled=_SETTLED,
            ),
            (_SETTLED,),
        )

    if entry.income and _PARTNER_NAMED.search(text):
        return Classification(
            entry,
            None,
            "none",
            speech.ask(
                "partner_money",
                f"money from {_PARTNER} - {_SETTLED.lower()}, or does it offset something else?",
                partner=_PARTNER, settled=_SETTLED,
            ),
            (_SETTLED,),
        )

    if _SETTLEMENT.search(text):
        return Classification(
            entry,
            _SETTLED,
            f"a {_PARTNER} settlement",
            speech.ask(
                "partner_settling",
                f"settling what {_PARTNER} paid for - {_SETTLED} unless it was something else",
                partner=_PARTNER, settled=_SETTLED,
            ),
            (_SETTLED,),
        )

    occasion = _OCCASION.match(text.strip())
    if occasion:
        month = occasion.group(1)
        name = " ".join(occasion.group().split()).lower()
        if GRAMMAR.capitalise_months:
            name = name.replace(month.lower(), month.capitalize())
        return Classification(entry, name, "an occasion, named first")

    if _FLOWERS.search(text) and entry.amount < _FLOWER_CEILING:
        return Classification(entry, _FOOD_CASH, "small flowers")

    for pattern, minor in _COMPILED:
        if pattern.search(text):
            found = _inside_a_longer_word(pattern, text)
            if found is not None:
                inside, matched = found
                elsewhere = [
                    _shown(other)
                    for other_pattern, other in _COMPILED
                    if other != minor and other_pattern.search(text)
                    and _inside_a_longer_word(other_pattern, text) is None
                ]
                offer = tuple(dict.fromkeys(
                    [inside[:1].upper() + inside[1:], _shown(minor)] + elsewhere
                ))
                return Classification(
                    entry, None, "none",
                    speech.ask("inside_word", f"{inside} is not {matched} - which group is this?",
                               inside=inside, matched=matched),
                    offer,
                )
            review = None
            offer: tuple[str, ...] = ()
            if minor == _FOOD_CASH:
                if _ALCOHOL.search(text):
                    review = speech.ask(
                        "alcohol", f"alcohol - {_FOOD_NAME}, or a celebration of its own?",
                        food=_FOOD_NAME,
                    )
                    offer = (_FOOD_NAME, _CELEBRATION)
                if _PAID_BY_CARD.search(text):
                    minor = _FOOD_CARD
            named = list(dict.fromkeys(
                _shown(other)
                for other_pattern, other in _COMPILED
                if other not in _PLATFORMS and other_pattern.search(text)
            ))
            if len(named) > 1 and minor not in _PLATFORMS:
                review = review or speech.ask(
                    "names_several",
                    "this line names " + " and ".join(named) + " - which was it?",
                    names=speech.And(named),
                )
                offer = offer or tuple(named)
            return Classification(entry, minor, pattern.pattern[:24], review, offer)

    if _UNPLACED_FARE.search(text):
        return Classification(entry, None, "none",
                              speech.ask("fare_unplaced", "fare with no outing to attach it to"))

    if not entry.income:
        word = _occasional_name(text)
        if len(word) >= 3 and word.isalpha() and word.lower() not in _STOP_WORDS:
            return Classification(entry, None, "none",
                                  speech.ask("no_rule", "no rule matched"), (word,))

    return Classification(entry, None, "none", speech.ask("no_rule", "no rule matched"))


def _trip(block: Block) -> list[Classification] | None:
    if not any(
        _ROAD.search(entry.text) and entry.amount >= _TRIP_FARE
        for entry in block.entries
    ):
        return None

    results = []
    for entry in block.entries:
        if entry.income:
            results.append(_by_keyword(entry))
        elif _ROAD.search(entry.text) or _HOMEWARD.search(entry.text):
            results.append(Classification(entry, _TRIP_ROAD, f"context:{_TRIP_NAME}"))
        elif _FARE.search(entry.text):
            results.append(Classification(entry, _TRIP_TAXI, f"context:{_TRIP_NAME}"))
        else:
            results.append(_eaten_out_or_bought(_by_keyword(entry)))
    return results


def _eaten_out_or_bought(result: Classification) -> Classification:
    if result.rule == "an occasion, named first":
        return result
    text = result.entry.text
    if _GROCERIES_NAMED.search(text):
        return result
    if _MEAL.search(text):
        return replace(result, minor=_TRIP_RESTAURANTS, rule="a meal out", review=None)
    return result


def _expand_splits(block: Block) -> Block:
    expanded: list[Entry] = []
    for entry in block.entries:
        match = _CARVE_OUT.match(entry.text) if not entry.income else None
        carved = int(match.group("amount")) * 1000 if match else 0
        if not match or carved >= entry.amount:
            expanded.append(entry)
            continue
        expanded.append(replace(entry, amount=entry.amount - carved, text=match.group("rest")))
        expanded.append(replace(entry, amount=carved, text=match.group("group")))
    return Block(tuple(expanded))


def _gift_outing(block: Block) -> list[Classification] | None:
    named = None
    for entry in block.entries:
        match = _GIFT.search(entry.text)
        if match and not entry.income:
            named = (entry, f"{match.group(1).capitalize()} {match.group(2).lower()}")
            break
    if named is None:
        return None

    anchor, name = named
    naming = speech.ask("gift_group", f"{name} - start an occasional group for this?",
                        name=name)
    aim = speech.ask("gift_trip", f"was this trip for the {name.lower()}, or ordinary fares?",
                     name=name)
    results = []
    for entry in block.entries:
        if entry.income:
            results.append(_by_keyword(entry))
        elif entry is anchor:
            results.append(Classification(entry, name, "gift", naming, (name,)))
        elif entry.bare or _FARE.search(entry.text):
            results.append(
                Classification(entry, name, "gift outing", aim, (name, _FOOD_TAXI))
            )
        else:
            results.append(_by_keyword(entry))
    return results


def _inside_a_longer_word(pattern: re.Pattern[str], text: str):
    inside = None
    for hit in pattern.finditer(text):
        if hit.start() == 0 or not text[hit.start() - 1].isalnum():
            return None
        if inside is None:
            start, end = hit.start(), hit.end()
            while start > 0 and text[start - 1].isalnum():
                start -= 1
            while end < len(text) and text[end].isalnum():
                end += 1
            inside = (text[start:end], hit.group(0))
    return inside


def _occasional_name(text: str) -> str:
    word = re.split(r"[\s,:]+", text.strip())[0]
    return word[:1].upper() + word[1:]


def _occasional_outing(block: Block) -> list[Classification] | None:
    base = [_by_keyword(entry) for entry in block.entries]
    unknown = [
        (position, result)
        for position, result in enumerate(base)
        if result.minor is None
        and result.review == "no rule matched"
        and not result.entry.income
    ]
    if len(unknown) != 1:
        return None
    anchor_position, anchor = unknown[0]

    spending = [r.entry.amount for r in base if not r.entry.income]
    if anchor.entry.amount < max(spending):
        return None

    fares = [
        position
        for position, result in enumerate(base)
        if not result.entry.income
        and (result.entry.bare or _FARE.search(result.entry.text))
    ]
    if not fares or min(fares) > anchor_position or max(fares) < anchor_position:
        return None

    name = _occasional_name(anchor.entry.text)
    question = speech.ask(
        "outing_group", f"{name} - start an occasional group and charge this outing to it?",
        name=name,
    )

    claimed = []
    for position, result in enumerate(base):
        entry = result.entry
        eaten_out = result.minor in {_FOOD_CASH, _FOOD_CARD} and not _GROCERY.search(entry.text)
        if entry.income:
            claimed.append(result)
        elif position == anchor_position or entry.bare or _FARE.search(entry.text) or eaten_out:
            claimed.append(
                Classification(entry, name, "occasional outing", question, (name,))
            )
        else:
            claimed.append(result)
    return claimed


def _food_trip(block: Block) -> bool:
    return any(
        not entry.income and not entry.bare and _FOOD.search(entry.text)
        for entry in block.entries
    )


def _offer_fare_options(results: list[Classification]) -> list[Classification]:
    if not any(c.review == "a fare with nothing naming it - where did this one go?"
               for c in results):
        return results

    fares = [
        i for i, c in enumerate(results)
        if c.review == "a fare with nothing naming it - where did this one go?"
    ]
    first, last = min(fares), max(fares)
    subject = None
    best = 0
    for i, c in enumerate(results):
        if not first < i < last:
            continue
        if c.minor is None or c.entry.income or c.entry.bare:
            continue
        if _FARE.search(c.entry.text) or _UNPLACED_FARE.search(c.entry.text):
            continue
        if c.entry.amount > best:
            subject, best = c.minor, c.entry.amount

    offered = tuple(
        dict.fromkeys(
            ([subject] if subject else []) + [_TRIP_ROAD, _FOOD_TAXI]
        )
    )
    return [
        replace(c, candidates=offered)
        if c.review == "a fare with nothing naming it - where did this one go?"
        else c
        for c in results
    ]


_TIP = GRAMMAR.tip

_HIS = ("answered by the user", "moved by the user")

TAUGHT = "the word you taught: "


def his_ruling(rule: str) -> bool:
    return rule in _HIS or rule.startswith(TAUGHT)


@lru_cache(maxsize=1024)
def _taught_pattern(word: str) -> re.Pattern[str]:
    body = r"\s+".join(re.escape(part) for part in word.split())
    left = r"\b" if word[:1].isalnum() else ""
    right = r"\b" if word[-1:].isalnum() else ""
    return re.compile(left + body + right, re.IGNORECASE)


def taught_group(text: str, words) -> tuple[str, str] | None:
    best: tuple[str, str] | None = None
    for word, group in words:
        if _taught_pattern(word).search(text) and (best is None or len(word) > len(best[1])):
            best = (group, word)
    return best


def _suggest_by_keyword(results: list[Classification]) -> list[Classification]:
    out = []
    for c in results:
        if c.confident or c.entry.income or c.entry.bare:
            out.append(c)
            continue
        guess = _by_keyword(c.entry).minor
        if guess is None:
            out.append(c)
            continue
        owner = major_for(guess)
        guess = owner.name if owner else guess
        if guess in c.candidates:
            out.append(c)
            continue
        out.append(replace(c, candidates=c.candidates + (guess,)))
    return out


def _place_tips(results: list[Classification]) -> list[Classification]:
    out = []
    for i, c in enumerate(results):
        if (
            c.entry.income
            or not _TIP.search(c.entry.text)
            or his_ruling(c.rule)
        ):
            out.append(c)
            continue
        owner = None
        for earlier in reversed(results[:i]):
            if earlier.block != c.block:
                break
            if earlier.entry.income or earlier.entry.bare or earlier.minor is None:
                continue
            if _FARE.search(earlier.entry.text) or _UNPLACED_FARE.search(earlier.entry.text):
                continue
            if _TIP.search(earlier.entry.text):
                continue
            owner = earlier.minor
            break
        if owner is not None:
            out.append(replace(c, minor=owner, rule="a tip on what came before it",
                               review=None, candidates=()))
        else:
            out.append(replace(
                c,
                minor=None,
                rule="none",
                review=speech.ask("tip_alone", "a tip, with nothing before it saying what for"),
                candidates=(_TRIP_RESTAURANTS, _FOOD_CASH),
            ))
    return out


def _place_bare_income(results: list[Classification]) -> list[Classification]:
    placed = list(results)
    for index, result in enumerate(placed):
        entry = result.entry
        if not (entry.income and entry.bare and result.minor is None):
            continue

        if entry.amount >= _SALARY_FLOOR:
            placed[index] = Classification(entry, _SALARY, "salary")
            continue

        previous = placed[index - 1] if index else None
        if (
            previous is not None
            and previous.minor is not None
            and not previous.entry.income
            and abs(entry.amount - previous.entry.amount) <= previous.entry.amount * 0.1
        ):
            placed[index] = Classification(entry, previous.minor, "refund of the line above")
            continue

        placed[index] = Classification(
            entry, _REIMBURSEMENTS, f"unlabelled income is {_REIMBURSEMENTS}"
        )
    return placed


def classify_block(block: Block, on_a_trip: bool = False) -> list[Classification]:
    return _offer_fare_options(
        _place_bare_income(_classify_block(_expand_splits(block), on_a_trip))
    )


def _classify_block(block: Block, on_a_trip: bool = False) -> list[Classification]:
    trip = _trip(block)
    if trip is not None:
        return trip

    context = _context_of(block)
    if context is not None:
        question, candidates = _CONTEXT_QUESTIONS.get(context[1], (None, ()))
        return [
            Classification(entry, context[1], f"context:{context[1]}", question, candidates)
            if _claimed(entry, context[0])
            else _by_keyword(entry)
            for entry in block.entries
        ]

    gift = _gift_outing(block)
    if gift is not None:
        return gift

    outing = _occasional_outing(block)
    if outing is not None:
        return outing

    if on_a_trip:
        return [
            Classification(entry, _TRIP_ROAD, f"context:{_TRIP_NAME} day")
            if not entry.income and (entry.bare or _FARE.search(entry.text))
            else _eaten_out_or_bought(_by_keyword(entry))
            for entry in block.entries
        ]

    if _food_trip(block):
        doubted = _rival_purchases(block)
        return [
            Classification(
                entry, _FOOD_TAXI, f"context:{_FOOD_NAME}",
                *((speech.ask("food_trip_fare",
                              "a fare on a trip that bought other things too - "
                              "was it for the food?"),
                   (_FOOD_NAME,) + doubted) if doubted else ()),
            )
            if not entry.income and (entry.bare or _UNPLACED_FARE.search(entry.text))
            else _by_keyword(entry)
            for entry in block.entries
        ]

    return [_by_keyword(entry) for entry in block.entries]


def _rival_purchases(block: Block) -> tuple[str, ...]:
    food = other = 0
    names: list[str] = []
    for entry in block.entries:
        if entry.income or entry.bare or _UNPLACED_FARE.search(entry.text):
            continue
        if _FOOD.search(entry.text):
            food += entry.amount
            continue
        other += entry.amount
        placed = _by_keyword(entry).minor
        shown = _shown(placed) if placed else _occasional_name(entry.text)
        if shown and shown not in names:
            names.append(shown)
    return tuple(names) if other > food and names else ()


def _platform_of(text: str) -> str | None:
    match = _PLATFORM.search(text)
    return match.group().lower() if match else None


def _match_refunds(results: list[Classification]) -> list[Classification]:
    matched = list(results)
    for index, refund in enumerate(matched):
        entry = refund.entry
        if not entry.income or entry.bare:
            continue
        if his_ruling(refund.rule):
            continue

        near = [*reversed(matched[:index]), *matched[index + 1 :]]
        equal = [
            c for c in near
            if not c.entry.income and c.entry.amount == entry.amount and c.minor is not None
        ]
        if not equal:
            continue

        platform = _platform_of(entry.text)
        if platform is not None:
            sharing = [c for c in equal if platform in c.entry.text.lower()]
            if sharing:
                equal = sharing

        if refund.candidates or (not refund.confident and refund.minor is not None):
            continue

        owner = major_for(refund.minor) if refund.minor else None
        if owner is not None and (owner.is_income or owner.tier is Tier.EXCLUDED):
            continue

        groups = list(dict.fromkeys(c.minor for c in equal))
        if len(groups) == 1 and groups[0] != refund.minor:
            matched[index] = replace(
                refund, minor=groups[0], rule="refund matched to its purchase",
                review=None, candidates=(),
            )
    return matched


def _day_is_a_trip(day) -> bool:
    for block in day.blocks:
        for first, second in zip(block.entries, block.entries[1:]):
            if (
                first.bare
                and second.bare
                and not first.income
                and not second.income
                and (first.amount, second.amount) in _TRIP_LEGS
            ):
                return True
    return False


def classify_period(period: Period, overlay=None) -> list[Classification]:
    results = []
    block_id = 0
    for day in period.days:
        on_a_trip = _day_is_a_trip(day)
        for block in day.blocks:
            results.extend(
                replace(c, block=block_id, date=day.date)
                for c in classify_block(block, on_a_trip=on_a_trip)
            )
            block_id += 1
    if overlay is not None:
        results = overlay(results)
    return _match_refunds(_suggest_by_keyword(_place_tips(results)))


def coverage(results: list[Classification]) -> tuple[int, int]:
    return sum(1 for r in results if r.confident), len(results)
