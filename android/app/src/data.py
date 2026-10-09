"""Everything the screens ask of the app, with no Flet in it. Each call goes to the
same `dispatch` as the other builds, over a JSON store in the app's private
folder. Restoring a configuration file puts the file's rules in place before
its months.
"""

from __future__ import annotations

import datetime
import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path

import bundled
import words
from words import t


INVENTED = "invented:"

EARLIER = {"invented": "en", "invented:simple": "en", "invented:simple-ru": "ru"}

HINTS = {"en": "12.01\n26 bus\n180 soup\n26 bus\nLeft: purse 2.9, account 61110",
         "ru": "12.01\n26 автобус\n180 суп\n26 автобус\nОстаток: наличные 2,9, счёт 61110"}


class Refused(Exception):
    def __init__(self, text: str = "", code: str | None = None) -> None:
        super().__init__(text)
        self.code = code


def _home() -> Path:
    where = os.environ.get("FLET_APP_STORAGE_DATA")
    return Path(where) if where else Path.home() / ".budget-tracker-mobile"


class Budget:
    def __init__(self, folder: Path | str | None = None) -> None:
        self.folder = Path(folder) if folder else _home()
        self.folder.mkdir(parents=True, exist_ok=True)

        self.rules = self.folder / "rules.toml"
        self._origin = self.folder / "rules.origin"
        origin = self._rules_origin()
        if not self.rules.is_file():
            lang = _offered(Look(self.folder).language)
            self._put_rules(bundled.HOUSEHOLDS[lang]["rules"], INVENTED + lang, load=False)
        elif origin is not None and origin.startswith(INVENTED):
            text = bundled.HOUSEHOLDS[origin[len(INVENTED):]]["rules"]
            if self.rules.read_text(encoding="utf-8") != text:
                self._put_rules(text, origin, load=False)
        elif origin != "file":
            _write_whole(self._origin, _origin_of(self.rules.read_text(encoding="utf-8")))
        self._load_engine()

        self.path = self.folder / "store.json"
        self.unlocked: set[str] = set()

    def _rules_origin(self) -> str | None:
        try:
            said = self._origin.read_text(encoding="utf-8").strip()
        except (OSError, ValueError):
            return None
        if said in EARLIER:
            return INVENTED + EARLIER[said]
        if said == "file" or (said.startswith(INVENTED)
                              and said[len(INVENTED):] in bundled.HOUSEHOLDS):
            return said
        return None

    @property
    def own_rules(self) -> bool:
        return self._rules_origin() == "file"

    @property
    def household(self) -> str | None:
        origin = self._rules_origin()
        return origin[len(INVENTED):] if origin and origin.startswith(INVENTED) else None

    def untouched(self) -> bool:
        if not self.path.exists():
            return True
        try:
            return not any(self._store.load(self.path).state().values())
        except Exception:
            return False

    def _load_engine(self) -> None:
        os.environ["BUDGET_RULES"] = str(self.rules)
        for name in [m for m in sys.modules if m == "budget" or m.startswith("budget.")]:
            del sys.modules[name]
        from budget.api import dispatch
        from budget.store import Store

        self._dispatch = dispatch
        self._store = Store


    def call(self, **event):
        os.environ["BUDGET_RULES"] = str(self.rules)
        if words.LANG != "en":
            event["lang"] = words.LANG
        store = self._store.load(self.path)
        reply = self._dispatch(store, event)
        if not reply.get("ok"):
            raise Refused(reply.get("error") or t("refused.unknown", "the app could not do that"),
                          code=reply.get("code"))
        return reply["result"]

    def _unlocked(self, identity: str, event: dict) -> dict:
        if identity in self.unlocked:
            event["override"] = True
        return event


    def months(self) -> list[dict]:
        return self.call(action="periods", year=datetime.date.today().year)

    def month(self, identity: str) -> dict:
        return self.call(action="totals", period=identity)

    def empty(self) -> dict:
        return self.call(action="empty")

    def questions(self, identity: str) -> list[dict]:
        return self.call(action="questions", period=identity)

    def day(self, identity: str, lines: list[dict]) -> list[dict]:
        return self.call(action="day", period=identity,
                         entries=[{"raw": line["raw"], "occurrence": line["occurrence"]}
                                  for line in lines])

    def closed(self) -> set[str]:
        return set(self.call(action="config")["closed"])

    def compare(self, identities: list[str], average: bool = False) -> dict:
        text = self.call(action="compare", periods=list(identities), average=bool(average))
        return {"text": text, "table": read_comparison(text, len(identities))}

    def export(self, identity: str, year: int | None = None) -> tuple[str, bytes]:
        event = {"action": "export", "format": "txt", "period": identity}
        if year:
            event["year"] = year
        said = self.call(**event)
        return said["name"], said["body"].encode("utf-8")

    def _examples_of(self) -> str:
        return _offered(self.household or words.LANG)

    def examples(self) -> list[str]:
        return list(bundled.HOUSEHOLDS[self._examples_of()]["examples"])

    def example_hint(self) -> str:
        return HINTS.get(self._examples_of(), HINTS["en"])


    def add(self, text: str, into: str | None = None) -> list[dict]:
        if not text.strip():
            raise Refused(t("refused.empty", "There is nothing to add."))
        event = {"action": "import", "text": text, "year": datetime.date.today().year}
        if into:
            event["period"] = into
            event = self._unlocked(into, event)
        return self.call(**event)

    def ask_again(self, identity: str) -> dict:
        return self.call(**self._unlocked(identity, {
            "action": "reset", "scope": "answers", "period": identity, "confirm": "RESET"}))

    def add_example(self, name: str) -> list[dict]:
        return self.add(bundled.HOUSEHOLDS[self._examples_of()]["examples"][name])

    def answer(self, identity: str, number: int, group: str, new: bool = False) -> None:
        self.call(**self._unlocked(identity, {
            "action": "answer", "period": identity, "number": number,
            "group": group, "new": new,
        }))

    def move(self, identity: str, lines: list[dict], group: str | None,
             new: bool = False) -> None:
        def one(line: dict, to: str | None, as_new: bool) -> None:
            event = {"action": "move", "period": identity, "raw": line["raw"],
                     "occurrence": line["occurrence"], "group": to}
            if to is not None:
                event["new"] = as_new
            self.call(**self._unlocked(identity, event))

        if group is None:
            for line in lines:
                if line.get("kind") == "moved":
                    one(line, None, False)
            return
        answered = [line for line in lines if line.get("kind") == "answered"]
        for line in lines:
            if line.get("kind") != "answered":
                one(line, group, new or group not in (line.get("candidates") or []))
        if not answered:
            return
        self.call(**self._unlocked(identity, {
            "action": "unanswer", "period": identity,
            "entries": [{"raw": line["raw"], "occurrence": line["occurrence"]}
                        for line in answered]}))
        asked = self.questions(identity)
        for line in answered:
            as_new = new or group not in (line.get("candidates") or [])
            question = next((q for q in asked if q["raw"] == line["raw"]
                             and q["occurrence"] == line["occurrence"]), None)
            if question:
                self.answer(identity, question["number"], group, as_new)
            else:
                one(line, group, as_new)

    def group_names(self, identity: str | None = None) -> list[str]:
        names = [name for major in self.setup(identity)["majors"]
                 for name in (major["label"], *(n["label"] for n in major.get("minors", [])))]
        if identity:
            names += [g["name"] for g in self.month(identity)["majors"]
                      if g.get("tier") != "READING"]
        return list(dict.fromkeys(names))

    def groups(self) -> list[str]:
        return [minor["label"] for major in self.call(action="config")["majors"]
                for minor in major.get("minors", [])]


    def setup(self, identity: str | None = None) -> dict:
        event = {"action": "config"}
        if identity:
            event["period"] = identity
        return self.call(**event)

    def configure(self, op: dict) -> dict:
        return self.call(action="configure", **op)

    def configure_months(self, identity: str, scope: str, ops: list[dict],
                         confirm: bool = False) -> dict:
        event = {"action": "configure", "scope": scope, "period": identity,
                 "ops": [dict(op) for op in ops]}
        if confirm:
            event["confirm"] = True
        return self.call(**event)

    def omit(self, identity: str, groups: list[str]) -> None:
        self.call(**self._unlocked(identity, {
            "action": "omit", "period": identity, "groups": groups}))

    def adjust(self, identity: str, group: str, value: float | None) -> None:
        self.call(**self._unlocked(identity, {
            "action": "adjust", "period": identity, "group": group, "value": value}))

    def left_value(self, slot: str, value: float | None, identity: str | None = None) -> dict:
        event = {"action": "left_value", "slot": slot, "value": value}
        if identity:
            event["period"] = identity
            event = self._unlocked(identity, event)
        return self.call(**event)

    def start_over(self) -> dict:
        said = self.call(action="reset", scope="all", confirm="RESET")
        lang = _offered(words.LANG)
        self._put_rules(bundled.HOUSEHOLDS[lang]["rules"], INVENTED + lang)
        return said

    def follow_language(self, lang: str) -> bool:
        now = self.household
        if lang not in bundled.HOUSEHOLDS or now is None or now == lang or not self.untouched():
            return False
        self._put_rules(bundled.HOUSEHOLDS[lang]["rules"], INVENTED + lang)
        return True


    def backup(self) -> tuple[str, bytes]:
        document = self.call(action="backup")
        if not isinstance(document.get("rules"), str):
            raise Refused(t("refused.backup",
                            "The rules could not be read, so no configuration file was made."))
        look = Look(self.folder)
        document["lang"] = look.language
        document["phone"] = {"theme": look.theme, "sizes": look.sizes}
        day = (document.get("saved") or "")[:10] or datetime.date.today().isoformat()
        text = json.dumps(document, ensure_ascii=False, indent=1)
        return f"budget-backup-{day}.json", text.encode("utf-8")

    @staticmethod
    def read_backup(raw: bytes) -> dict:
        try:
            document = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, ValueError):
            raise Refused(t("refused.unreadable",
                            "That file is not a configuration file - it cannot be read.")) from None
        if not isinstance(document, dict) or document.get("kind") != "budget-backup":
            raise Refused(t("refused.notbackup", "That file is not a budget configuration file."))
        if not isinstance(document.get("rules"), str):
            raise Refused(t("refused.norules",
                            "This file has no rules in it - it was saved before a "
                            "configuration file carried everything, so its months would not "
                            "read here as they do where it was saved. Save a new "
                            "configuration file there and restore that one."))
        return {
            "months": document.get("months"),
            "answers": document.get("answers"),
            "saved": (document.get("saved") or "")[:10],
            "document": document,
        }

    def restore(self, raw: bytes) -> dict:
        document = self.read_backup(raw)["document"]
        text = document["rules"]
        self._check_rules(text)

        now = self.rules.read_text(encoding="utf-8")
        before = (now, self._rules_origin() or _origin_of(now))
        self._put_rules(text, "file")
        try:
            result = self.call(action="restore", backup=document, confirm="RESTORE")
        except BaseException:
            self._put_rules(*before)
            raise
        phone = document.get("phone")
        lang = document.get("lang")
        if isinstance(phone, dict) or lang in words.LANGS:
            look = Look(self.folder)
            if isinstance(phone, dict):
                if phone.get("theme") in Look.THEMES:
                    look.theme = phone["theme"]
                for kind, value in (phone.get("sizes") or {}).items():
                    if kind in Look.SIZES and isinstance(value, (int, float)):
                        look.set_size(kind, value)
            if lang in words.LANGS:
                look.language = lang
            look.save()
        self.unlocked.clear()
        return result

    def _check_rules(self, text: str) -> None:
        from budget.rules import RulesError, load

        with tempfile.TemporaryDirectory() as scratch:
            candidate = Path(scratch) / "rules.toml"
            candidate.write_text(text, encoding="utf-8")
            try:
                load(candidate)
            except RulesError as why:
                raise Refused(t("refused.badrules", "The rules in that file cannot be used: {why}",
                                why=why)) from None

    def _put_rules(self, text: str, origin: str, load: bool = True) -> None:
        _write_whole(self.rules, text)
        _write_whole(self._origin, origin)
        if load:
            self._load_engine()


def _write_whole(path: Path, text: str) -> None:
    part = path.with_name(path.name + ".part")
    part.write_text(text, encoding="utf-8")
    os.replace(part, path)


def _offered(lang) -> str:
    return lang if lang in bundled.HOUSEHOLDS else "en"


def _origin_of(text: str) -> str:
    same = next((lang for lang, household in bundled.HOUSEHOLDS.items()
                 if household["rules"] == text), None)
    return INVENTED + same if same else "file"


class Look:
    THEMES = ("system", "light", "dark")
    SIZES = {
        "names": ("Group names", 17, 13, 28),
        "figures": ("Figures by the bars", 17, 13, 28),
        "limits": ("Limits and what is left", 13, 11, 20),
        "totals": ("Totals", 26, 18, 40),
        "minors": ("Minor groups", 15, 12, 24),
        "left": ("Left line", 15, 12, 24),
    }

    def __init__(self, folder: Path | str) -> None:
        self.path = Path(folder) / "look.json"
        self.theme = "system"
        self.language = "en"
        self.sizes = {key: normal for key, (_, normal, _, _) in self.SIZES.items()}
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if saved.get("theme") in self.THEMES:
            self.theme = saved["theme"]
        if saved.get("language") in words.LANGS:
            self.language = saved["language"]
        for key, value in (saved.get("sizes") or {}).items():
            if key in self.SIZES and isinstance(value, (int, float)):
                self.set_size(key, value)

    def set_size(self, key: str, value: float) -> None:
        _, _, low, high = self.SIZES[key]
        self.sizes[key] = int(min(max(round(value), low), high))

    def normal_sizes(self) -> None:
        self.sizes = {key: normal for key, (_, normal, _, _) in self.SIZES.items()}

    def save(self) -> None:
        self.path.write_text(json.dumps({"theme": self.theme, "sizes": self.sizes,
                                         "language": self.language}), encoding="utf-8")


def one_letter_off(a: str, b: str) -> bool:
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        at = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        return len(at) == 1 or (len(at) == 2 and at[1] == at[0] + 1
                                and a[at[0]] == b[at[1]] and a[at[1]] == b[at[0]])
    short, long = sorted((a, b), key=len)
    i = next((k for k, (x, y) in enumerate(zip(short, long)) if x != y), len(short))
    return short[i:] == long[i + 1:]


def near_group(typed: str, names: list[str]) -> str | None:
    key = typed.strip().lower()
    if len(key) < 4 or any(name.lower() == key for name in names):
        return None
    return next((name for name in names if one_letter_off(name.lower(), key)), None)


def by_year(months: list[dict]) -> dict[int | None, list[dict]]:
    years: dict[int | None, list[dict]] = {}
    for month in months:
        years.setdefault(month.get("year"), []).append(month)
    return dict(sorted(years.items(), key=lambda kv: kv[0] or 0, reverse=True))


def beside(months: list[dict], identity: str | None, step: int) -> str | None:
    ids = [m["identity"] for m in months]
    if identity not in ids:
        return None
    at = ids.index(identity) + step
    return ids[at] if 0 <= at < len(ids) else None


def newest_real(months: list[dict], count: int = 2) -> list[str]:
    real = [m for m in months if (m.get("days") or 0) >= 5]
    return [m["identity"] for m in (real if len(real) >= count else months)[-count:]]


_GAP = re.compile(r" {2,}")
_CELL = re.compile(r"-|[+-]?\d+(?:\.\d+)?")


def read_comparison(text: str, count: int) -> dict | None:
    lines = text.split("\n")
    titles = _GAP.split(lines[0].strip()) if lines[0].strip() else []
    if count < 1 or len(titles) not in (count, count + 1):
        return None
    changes = len(titles) > count

    blocks: list[list[str]] = [[]]
    for line in lines[1:]:
        if line.strip():
            blocks[-1].append(line.strip())
        elif blocks[-1]:
            blocks.append([])
    blocks = [block for block in blocks if block]
    if len(blocks) not in (2, 3):
        return None

    def row(line: str, width: int, change: bool) -> dict | None:
        parts = _GAP.split(line, maxsplit=1)
        cells = parts[1].split() if len(parts) == 2 else []
        if len(cells) not in ((width, width + 1) if change else (width,)):
            return None
        if not all(_CELL.fullmatch(cell) for cell in cells):
            return None
        return {"name": parts[0], "cells": cells[:width],
                "delta": cells[width] if len(cells) > width else None}

    groups = [row(line, count, changes) for line in blocks[0]]
    totals = [row(line, count, changes) for line in blocks[1]]
    average = None
    if len(blocks) == 3:
        title, *rest = blocks[2]
        rows = [row(line, 1, False) for line in rest]
        if _GAP.search(title) or not rows or None in rows:
            return None
        average = {"title": title, "rows": rows}
    if None in groups or None in totals:
        return None
    return {"titles": titles[:count], "delta": titles[count] if changes else None,
            "groups": groups, "totals": totals, "average": average}


KEEP = "\u00a0"


def money(value: float) -> str:
    return f"{value:,.1f}".replace(",", KEEP)


def spaced(amount: int) -> str:
    return f"{amount:,}".replace(",", KEEP)


def grouped(figure: str) -> str:
    if figure == "-":
        return "—"
    whole, dot, tail = figure.partition(".")
    return re.sub(r"(?<=\d)(?=(?:\d{3})+$)", KEEP, whole) + dot + tail


def unbroken(text: str) -> str:
    return re.sub(r"(?<=\d) (?=\d{3}(?!\d))", KEEP, text)


def typed_number(text: str | None) -> float | None:
    plain = re.sub(r"\s+", "", text or "").replace(",", ".")
    try:
        value = float(plain)
    except ValueError:
        return None
    return value if math.isfinite(value) else None
