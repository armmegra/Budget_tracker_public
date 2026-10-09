"""The notes' control words - the closing line, "previous month", a refund in
brackets, fares, an amount carved out of a line - as patterns built from the
rules file, so a household writes its notes in its own words.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["DEFAULTS", "Grammar", "GrammarError", "build"]


DEFAULTS: dict = {
    "left": r"L?eft",
    "left_word": "Left",
    "decimal": ".",
    "skip": r"do not count|don'?t count|not counted",
    "previous": r"previous month",
    "refers": r"refers to",
    "months": ("january", "february", "march", "april", "may", "june", "july",
               "august", "september", "october", "november", "december"),
    "capitalise_months": True,
    "refund": r"return|refund",
    "taxi": r"taxi",
    "road": r"road",
    "homeward": r"to\s+home|back",
    "prepayment": r"pre[-\s]?payment",
    "flowers": r"\bflower|\brose",
    "occasion": r"\s*(?:st|nd|rd|th)?\s+of\s+",
    "food": r"food",
    "and": r"and",
    "thousands": r"k",
    "card": r"card",
    "card_ledger": None,
    "gift": r"(\w+)\s+(present|gift)\b",
    "tip": r"tips?",
    "stop_words": ("or", "and", "the", "for", "of", "to", "in", "on", "at", "from",
                   "back", "her", "his", "our", "new", "old", "one", "two"),
    "nested_taxi": "taxi",
    "nested_card": "card",
    "nested_cash": "cash",
    "ocr": "eng",
}

_FRAGMENTS = ("left", "skip", "previous", "refers", "refund", "taxi", "road", "homeward",
              "prepayment", "flowers", "occasion", "food", "and", "thousands", "card",
              "card_ledger", "gift", "tip")
_WORDS = ("left_word", "nested_taxi", "nested_card", "nested_cash")
_OCR = re.compile(r"[a-z_]{3,}(?:\+[a-z_]{3,})*")


class GrammarError(ValueError):
    def __init__(self, key: str, why: str):
        super().__init__(f"{key}: {why}" if key else why)
        self.key = key
        self.why = why


def _choice(fragment: str) -> bool:
    depth = 0
    i = 0
    while i < len(fragment):
        c = fragment[i]
        if c == "\\":
            i += 2
            continue
        if c == "[":
            i += 1
            if i < len(fragment) and fragment[i] == "^":
                i += 1
            if i < len(fragment) and fragment[i] == "]":
                i += 1
            while i < len(fragment) and fragment[i] != "]":
                i += 2 if fragment[i] == "\\" else 1
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == "|" and depth == 0:
            return True
        i += 1
    return False


def _bare(fragment: str) -> str:
    return f"(?:{fragment})" if _choice(fragment) else fragment


def _months(w: dict) -> str:
    return "|".join(_bare(m) for m in w["months"])


_SHAPES = {
    "balance": (("left",), lambda w: "^" + _bare(w["left"]) + r":\s*(?P<body>.*)$"),
    "deferred": (("previous", "refers"),
                 lambda w: _bare(w["previous"]) + "|" + _bare(w["refers"]) + r" \w+"),
    "refers_to": (("refers", "months"),
                  lambda w: _bare(w["refers"]) + r"\s+(" + _months(w) + ")"),
    "marker": (("skip", "previous", "refers"),
               lambda w: r"\s*#?\s*(?:" + w["skip"] + r")\s*,?\s*(?:" + _bare(w["previous"])
               + "|" + _bare(w["refers"]) + r" \w+)\s*(?:\([^)]*\)\s*)?$"),
    "instant_refund": (("refund",),
                       lambda w: r"\(\s*-\s*(\d+)\s*(?:" + w["refund"] + r")\s*\)"),
    "fare": (("taxi",), lambda w: "^" + _bare(w["taxi"]) + r"\b"),
    "road": (("road",), lambda w: "^" + _bare(w["road"]) + r"\b"),
    "homeward": (("taxi", "homeward"),
                 lambda w: "^" + _bare(w["taxi"]) + "$|^" + _bare(w["taxi"])
                 + r"\s+(?:" + w["homeward"] + r")\b"),
    "prepayment": (("prepayment",), lambda w: r"\b" + _bare(w["prepayment"]) + r"\b"),
    "flowers": (("flowers",), lambda w: w["flowers"]),
    "occasion": (("occasion", "months"),
                 lambda w: r"^\d{1,2}" + _bare(w["occasion"]) + "(" + _months(w) + r")\b"),
    "groceries_named": (("food",), lambda w: r"\b" + _bare(w["food"]) + r"\b"),
    "carve_out": (("and", "thousands"),
                  lambda w: r"^(?P<rest>.*?)\s*(?:" + w["and"] + r"|&|\+)\s+(?P<amount>\d+)"
                  + _bare(w["thousands"]) + r"\s+(?P<group>\w+)\s*$"),
    "unplaced_fare": (("taxi", "road"),
                      lambda w: "^(?:" + w["taxi"] + "|" + w["road"] + r")\b"),
    "named_fare": (("taxi", "road"),
                   lambda w: r"^(?P<what>\S.*?)[\s,]+(?:" + w["taxi"] + "|" + w["road"] + r")\b"),
    "paid_by_card": (("card",), lambda w: r"\b" + _bare(w["card"]) + r"\b"),
    "gift": (("gift",), lambda w: w["gift"]),
    "tip": (("tip",), lambda w: r"\b" + _bare(w["tip"]) + r"\b"),
    "fare_word": (("taxi", "road"),
                  lambda w: r"\b" + _bare(w["taxi"]) + r"\b|\b" + _bare(w["road"]) + r"\b"),
}


@dataclass(frozen=True)
class Grammar:
    balance: re.Pattern[str]
    deferred: re.Pattern[str]
    refers_to: re.Pattern[str]
    marker: re.Pattern[str]
    instant_refund: re.Pattern[str]
    fare: re.Pattern[str]
    road: re.Pattern[str]
    homeward: re.Pattern[str]
    prepayment: re.Pattern[str]
    flowers: re.Pattern[str]
    occasion: re.Pattern[str]
    groceries_named: re.Pattern[str]
    carve_out: re.Pattern[str]
    unplaced_fare: re.Pattern[str]
    named_fare: re.Pattern[str]
    paid_by_card: re.Pattern[str]
    gift: re.Pattern[str]
    tip: re.Pattern[str]
    fare_word: re.Pattern[str]
    card_ledger: re.Pattern[str] | None
    months: tuple[str, ...]
    month_words: tuple[re.Pattern[str], ...]
    capitalise_months: bool
    stop_words: frozenset[str]
    left_word: str
    decimal: str
    nested_taxi: str
    nested_card: str
    nested_cash: str
    ocr: str

    def on_card(self, text: str) -> bool:
        if self.card_ledger is None:
            return "card" in text.lower()
        return self.card_ledger.search(text) is not None

    def month_of(self, word: str, names: tuple[str, ...]) -> str | None:
        if self.months == DEFAULTS["months"]:
            return word.capitalize()
        for name, pattern in zip(names, self.month_words):
            if pattern.fullmatch(word):
                return name
        return None


def _clean(key: str, value: str) -> None:
    for c in value:
        if ord(c) < 0x20 or 0x7F <= ord(c) < 0xA0:
            raise GrammarError(key, f"holds the control character U+{ord(c):04X}. In a "
                                    'double-quoted TOML string "\\b" is a backspace, not a '
                                    "word boundary: write patterns in single quotes")


def _fragment(key: str, value, which: str = "") -> str:
    if not isinstance(value, str) or not value:
        raise GrammarError(key, f"{which}must be a regular expression")
    _clean(key, value)
    try:
        re.compile(value, re.IGNORECASE)
    except re.error as err:
        raise GrammarError(key, f"{which}bad regular expression {value!r}: {err}") from None
    return value


def _word(key: str, value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GrammarError(key, "must be a word")
    _clean(key, value)
    return value


def _checked(key: str, value):
    if key == "card_ledger" and value is None:
        return None
    if key in _FRAGMENTS:
        return _fragment(key, value)
    if key in _WORDS:
        return _word(key, value)
    if key == "months":
        if not isinstance(value, (list, tuple)) or len(value) != 12:
            raise GrammarError(key, "must list the twelve months, January first")
        return tuple(_fragment(key, m, f"month {i + 1}: ") for i, m in enumerate(value))
    if key == "stop_words":
        if not isinstance(value, (list, tuple)) or not all(isinstance(w, str) and w for w in value):
            raise GrammarError(key, "must be a list of words")
        for w in value:
            _clean(key, w)
        return tuple(value)
    if key == "decimal":
        if value not in (".", ","):
            raise GrammarError(key, 'must be "." or ","')
        return value
    if key == "capitalise_months":
        if not isinstance(value, bool):
            raise GrammarError(key, "must be true or false")
        return value
    if not isinstance(value, str) or not _OCR.fullmatch(value):
        raise GrammarError(key, 'must name Tesseract languages, as "eng" or "rus+eng"')
    return value


def _compile(key: str, pattern: str) -> re.Pattern[str]:
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as err:
        raise GrammarError(key, f"does not fit its pattern {pattern!r}: {err}") from None


def build(notes: dict | None = None) -> Grammar:
    table = {} if notes is None else notes
    if not isinstance(table, dict):
        raise GrammarError("", "must be a table")
    unknown = sorted(set(table) - set(DEFAULTS))
    if unknown:
        raise GrammarError("", f"unknown key(s) {unknown}")
    words = dict(DEFAULTS)
    for key, value in table.items():
        words[key] = _checked(key, value)

    for key in ("refers", "occasion"):
        if re.compile(words[key], re.IGNORECASE).groups:
            raise GrammarError(key, "must not capture: write a group as (?:...)")
    if re.compile(words["gift"], re.IGNORECASE).groups != 2:
        raise GrammarError("gift", "needs exactly two groups, in the order the name takes them")

    for key in table:
        trial = dict(DEFAULTS, **{key: words[key]})
        for keys, shape in _SHAPES.values():
            if key in keys:
                _compile(key, shape(trial))

    built = {}
    for name, (keys, shape) in _SHAPES.items():
        built[name] = _compile(", ".join(k for k in keys if k in table) or keys[0], shape(words))
    ledger = words["card_ledger"]
    grammar = Grammar(
        **built,
        card_ledger=None if ledger is None else re.compile(ledger, re.IGNORECASE),
        months=words["months"],
        month_words=tuple(re.compile(m, re.IGNORECASE) for m in words["months"]),
        capitalise_months=words["capitalise_months"],
        stop_words=frozenset(w.lower() for w in words["stop_words"]),
        left_word=words["left_word"],
        decimal=words["decimal"],
        nested_taxi=words["nested_taxi"],
        nested_card=words["nested_card"],
        nested_cash=words["nested_cash"],
        ocr=words["ocr"],
    )

    written = f"{grammar.left_word}: 1, 2"
    if not grammar.balance.match(written):
        raise GrammarError("left_word", f"the Left pattern {words['left']!r} cannot read "
                                        f"{written!r}, so a line the app writes would be lost")
    return grammar
