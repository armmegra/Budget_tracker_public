from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

LOCAL = Path(__file__).resolve().parent.parent
APP = LOCAL / "app"
ENGINE = APP / "budget"
ENGLISH = LOCAL / "clean" / "rules.toml"
MONTHS = [LOCAL / "clean" / "examples" / f"month-{i}.txt" for i in (1, 2, 3)]
RUSSIAN = LOCAL / "clean" / "ru" / "rules.toml"
RU_MONTHS = [LOCAL / "clean" / "ru" / "examples" / f"month-{i}.txt" for i in (1, 2, 3)]
TODAY = (2026, 9, 18)


def _alone():
    spec = importlib.util.spec_from_file_location("speech_alone", ENGINE / "speech.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


speech = _alone()
RU = speech.RU
LEAD_IN = "Не удалось: "

SLOT = re.compile(r"\{(\w+)(?:\|([^{}]*))?\}")

needs_household = pytest.mark.skipif(
    not (ENGLISH.is_file() and all(m.is_file() for m in MONTHS)),
    reason="the example household is not present",
)
needs_both_households = pytest.mark.skipif(
    not (ENGLISH.is_file() and all(m.is_file() for m in MONTHS)
         and RUSSIAN.is_file() and all(m.is_file() for m in RU_MONTHS)),
    reason="the two example households are not present",
)

EN_CLOSED = ('January 2026 is read-only - months close 3 months on, and this one '
             'closed 5 month(s) ago - pass "override": true to correct it anyway')
RU_CLOSED = ("Январь 2026 закрыт: месяц закрывается через 3 месяца после окончания, "
             "а этот закрылся 5 месяцев назад. Чтобы всё же исправить его, сначала "
             "откройте его.")


_PRELUDE = '''\
import datetime, json, sys, tempfile
from pathlib import Path

INPUT = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))


# The day the months are read on - which decides the closed ones - and the
# backup's stamp with it, fixed before the engine is imported.
class _Day(datetime.date):
    @classmethod
    def today(cls):
        return cls(*INPUT["today"])


class _Moment(datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        moment = cls(*INPUT["today"], 12, 0, 0)
        return moment.replace(tzinfo=tz) if tz is not None else moment


datetime.date, datetime.datetime = _Day, _Moment

import budget.api as api
from budget.store import Store

MONTHS = [Path(p).read_text(encoding="utf-8") for p in INPUT["months"]]
facts = {}


class Book:
    """A store of its own, read from its file for every request as serve.py
    reads it. `Book("ru")` sends that "lang" with every event; `Book()` none."""

    def __init__(self, *lang):
        self.lang = lang
        self.path = Path(tempfile.mkdtemp(dir=INPUT["dir"])) / "store.json"

    def __call__(self, event):
        sent = dict(event)
        if self.lang:
            sent["lang"] = self.lang[0]
        return api.dispatch(Store.load(self.path), sent)

    def text(self):
        return self.path.read_text(encoding="utf-8") if self.path.exists() else ""
'''
_POSTLUDE = "\nprint(json.dumps(facts, ensure_ascii=True))\n"


def _engine(tmp_path: Path, body: str, *, rules: Path = ENGLISH,
            months: list[Path] = MONTHS, **given) -> dict:
    run = Path(tempfile.mkdtemp(dir=tmp_path))
    given = dict(given, today=TODAY, months=[str(m) for m in months], dir=str(run))
    (run / "input.json").write_text(json.dumps(given, ensure_ascii=False), encoding="utf-8")
    (run / "probe.py").write_text(_PRELUDE + textwrap.dedent(body) + _POSTLUDE,
                                  encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in ("BUDGET_RULES", "PYTHONPATH")}
    env.update(BUDGET_RULES=str(rules), PYTHONPATH=str(APP), PYTHONDONTWRITEBYTECODE="1")
    done = subprocess.run(
        [sys.executable, "-B", str(run / "probe.py"), str(run / "input.json")],
        cwd=run, env=env, capture_output=True, timeout=180,
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    return json.loads(done.stdout.decode("ascii").strip().splitlines()[-1])


CODE_AT = {"_Refused": 1, "Said": 1, "Question": 1, "ask": 0, "say": 0}
UNSAID = {"context"}


def _speech_calls():
    for path in sorted(ENGINE.glob("*.py")):
        if path.name == "speech.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
        modules, names = set(), {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "budget":
                modules |= {a.asname or a.name for a in node.names if a.name == "speech"}
            elif isinstance(node, ast.ImportFrom) and node.module == "budget.speech":
                names.update({a.asname or a.name: a.name for a in node.names})
            elif isinstance(node, ast.Import):
                modules |= {a.asname for a in node.names
                            if a.name == "budget.speech" and a.asname}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) \
                    and func.value.id in modules:
                name = func.attr
            elif isinstance(func, ast.Name) and func.id in names:
                name = names[func.id]
            elif isinstance(func, ast.Name) and func.id == "_Refused":
                name = "_Refused"
            else:
                continue
            if name in CODE_AT:
                yield f"{path.name}:{node.lineno}", name, node


def _codes(expr) -> set[str] | None:
    if expr is None or (isinstance(expr, ast.Constant) and expr.value is None):
        return set()
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return {expr.value}
    if isinstance(expr, ast.IfExp):
        body, orelse = _codes(expr.body), _codes(expr.orelse)
        if body is not None and orelse is not None:
            return body | orelse
    return None


def _code_of(name: str, node: ast.Call):
    for keyword in node.keywords:
        if keyword.arg == "code":
            return keyword.value
    at = CODE_AT[name]
    return node.args[at] if len(node.args) > at else None


def _slots(template: str) -> set[str]:
    return {m.group(1) for m in SLOT.finditer(template)}


def test_every_coded_refusal_has_russian_with_the_same_values() -> None:
    seen, dynamic, uncoded_api = set(), [], []
    for where, name, node in _speech_calls():
        codes = _codes(_code_of(name, node))
        if codes is None:
            dynamic.append(where)
            continue
        if not codes:
            if name == "_Refused" and where.startswith("api.py:"):
                uncoded_api.append(where)
            continue
        if any(k.arg is None for k in node.keywords):
            dynamic.append(where)
            continue
        values = {k.arg for k in node.keywords if k.arg != "code"}
        used = set()
        for code in codes:
            seen.add(code)
            if code in UNSAID:
                continue
            assert code in RU, f"{where}: {code!r} has no Russian"
            wanted = _slots(RU[code])
            assert wanted <= values, f"{where}: {code!r} needs {sorted(wanted - values)}"
            used |= wanted
        if not codes <= UNSAID:
            assert used == values, f"{where}: {sorted(values - used)} said in no language"

    assert len(uncoded_api) == 31, uncoded_api
    assert dynamic, "the pass-through refusals and the outcomes were not found"
    assert {"closed", "paste_closed"} <= seen

    literals = set()
    for path in ENGINE.glob("*.py"):
        if path.name != "speech.py":
            literals |= {n.value for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                         if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert not sorted(set(RU) - literals), "Russian for codes nothing uses"

    for code, template in RU.items():
        assert not re.search(r"[{}]", SLOT.sub("", template)), code
        for match in SLOT.finditer(template):
            if match.group(2) is not None:
                forms = match.group(2).split("|")
                assert len(forms) == 3 and all(forms), code


def test_the_catalogue_stands_alone_and_keeps_its_style() -> None:
    tree = ast.parse((ENGINE / "speech.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any(a.name.split(".")[0] == "budget" for a in node.names)
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] != "budget"
    tables = {t.id: node.value for node in tree.body if isinstance(node, ast.Assign)
              for t in node.targets if isinstance(t, ast.Name)}
    for name in ("RU", "MONTHS", "UNDATED", "LEAD_IN", "NAMES"):
        assert isinstance(tables[name], ast.Dict), name

    assert speech.LANGS == ("en", "ru")
    assert speech.NAMES == {"en": "English", "ru": "Русский"}
    assert speech.LEAD_IN == {"ru": LEAD_IN}
    for code, template in RU.items():
        assert isinstance(template, str) and template, code
        assert " - " not in template and "..." not in template, code
        assert template.count("«") == template.count("»"), code
        assert "override" not in template and "pass " not in template, code


def test_russian_plural_forms() -> None:
    forms = ("месяц", "месяца", "месяцев")
    expected = {1: "месяц", 2: "месяца", 4: "месяца", 5: "месяцев", 11: "месяцев",
                12: "месяцев", 14: "месяцев", 21: "месяц", 22: "месяца",
                25: "месяцев", 111: "месяцев", 0: "месяцев", 101: "месяц"}
    for n, form in expected.items():
        assert speech.plural(n, *forms) == form, n
        assert speech.fill("{n} {n|месяц|месяца|месяцев}", {"n": n}, "ru") == f"{n} {form}"
    assert speech.plural(1.5, *forms) == "месяцев"
    assert speech.plural(2.0, *forms) == "месяца"
    said = speech.fill(RU["paste_closed"], {"n": 1, "months": "Январь 2026"}, "ru")
    assert said == ("эта вставка перезаписала бы закрытый месяц: Январь 2026. "
                    "Сначала откройте его.")
    said = speech.fill(RU["paste_closed"], {"n": 3, "months": "Январь 2026, Февраль 2026, "
                                                                "Март 2026"}, "ru")
    assert said == ("эта вставка перезаписала бы закрытые месяцы: Январь 2026, "
                    "Февраль 2026, Март 2026. Сначала откройте их.")


def test_month_labels_in_russian() -> None:
    assert speech.month_label("June 2026", "ru") == "Июнь 2026"
    assert speech.month_label("undated", "ru") == "без даты"
    assert speech.month_label("June", "ru") == "Июнь"
    english = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]
    russian = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль",
               "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
    for name, said in zip(english, russian):
        assert speech.month_label(f"{name} 2027", "ru") == f"{said} 2027"
    for label in ("June 2026", "undated", "03.01..24.01", "Zzqx", "May flowers", ""):
        assert speech.month_label(label, "en") == label
    for label in ("03.01..24.01", "Zzqx", "May flowers", "june 2026", ""):
        assert speech.month_label(label, "ru") == label
    months = [speech.Month("June 2026"), speech.Month("July 2026")]
    assert speech.fill("{m} / {all} / {plain}", {"m": speech.Month("undated"),
                       "all": months, "plain": "June"}, "ru") == \
        "без даты / Июнь 2026, Июль 2026 / June"


def test_the_helpers_never_raise_and_keep_english_exact() -> None:
    english = "January 2026 is read-only"
    assert speech.render("closed", {}, "ru", english) == LEAD_IN + english
    assert speech.render(None, {}, "ru", english) == LEAD_IN + english
    assert speech.render("no_such_code", {}, "ru", english) == LEAD_IN + english
    assert speech.fill("{n|one|few}", {"n": 1}, "ru", english) == LEAD_IN + english
    assert speech.fill("{n|a|b|c}", {"n": object()}, "ru", english) == LEAD_IN + english
    assert speech.fill("{n|a|b|c}", {"n": object()}, "ru") == "{n|a|b|c}"
    assert speech.say("most_limits", "ru", "at most 5 limits") == LEAD_IN + "at most 5 limits"
    assert speech.say("no_such_code", "ru", "Total") == "Total"
    for lang in ("en", "de", None, 5, ["ru"]):
        assert speech.render("closed", {"label": "x"}, lang, english) == english
        assert speech.say("every_later_month", lang, "and every later month") == \
            "and every later month"
    hint = speech.Said(" - this question suggests ['A', 'B']", code="suggests",
                       candidates=["A", "B"])
    said = speech.render("answer_new_group", {"group": "Zzqx", "hint": hint}, "ru", "x")
    assert said == ("группы «Zzqx» нет — вопрос предлагает: A, B — чтобы завести новую, "
                    "введите её название через «Другое…»")
    assert speech.render("answer_new_group", {"group": "Zzqx", "hint": ""}, "ru", "x") == \
        "группы «Zzqx» нет — чтобы завести новую, введите её название через «Другое…»"
    raised = speech.Said("a label cannot contain a comma", code="left_comma")
    assert isinstance(raised, ValueError) and str(raised) == "a label cannot contain a comma"
    question = speech.ask("zz_unwritten", "a tip, with nothing before it saying what for")
    assert question == "a tip, with nothing before it saying what for"
    assert hash(question) == hash("a tip, with nothing before it saying what for")
    assert json.dumps({"q": question}) == json.dumps({"q": str(question)})
    assert (question.code, question.values) == ("zz_unwritten", {})
    assert speech.review(question, "en") is question
    assert speech.review(question, "ru") == question
    worded = speech.Question("fare with {n} words", "zz_unwritten", n=2)
    assert worded.values == {"n": 2} and worded == "fare with {n} words"
    assert speech.review("a plain question", "ru") == "a plain question"
    assert speech.review(None, "ru") is None
    for code in ("en", "ru"):
        assert speech.pick(code) == code
    for code in ("de", "", "RU", "ru-RU", " ru", None, 5, ["ru"], {"ru": 1}, True):
        assert speech.pick(code) == "en", code


@needs_household
def test_no_language_and_english_give_identical_replies(tmp_path) -> None:
    facts = _engine(tmp_path, """
        books = {"none": Book(), "en": Book("en"), "ru": Book("ru")}
        for key in ("en differs", "store differs", "ru differs", "refused", "coded"):
            facts[key] = []

        def send(label, event):
            got = {key: book(event) for key, book in books.items()}
            if got["none"] != got["en"]:
                facts["en differs"].append(label)
            texts = {key: book.text() for key, book in books.items()}
            if not texts["none"] == texts["en"] == texts["ru"]:
                facts["store differs"].append(label)
            one, ru = got["none"], got["ru"]
            if one.get("ok") != ru.get("ok") or one.get("code") != ru.get("code"):
                facts["ru differs"].append(label)
            if not one.get("ok"):
                facts["refused"].append(label)
                if one.get("code"):
                    facts["coded"].append(one["code"])
            return got

        for i, text in enumerate(MONTHS):
            send(f"import {i}", {"action": "import", "text": text, "year": 2026})
        # The example months, not the December example January's "+ 210" makes.
        months = [p["month"] for p in send("periods", {"action": "periods"})["none"]["result"]
                  if not p["moved"]]
        first, last = months[0], months[-1]
        config = send("config", {"action": "config"})["none"]["result"]
        major = next(m["name"] for m in config["majors"] if m["minors"])
        minor = next(m["minors"][0]["name"] for m in config["majors"] if m["minors"])
        slot = config["left"]["slots"][0]["id"]
        for month in months:
            send(f"totals {month}", {"action": "totals", "period": month, "year": 2026})
            send(f"raw {month}", {"action": "raw", "period": month})
            send(f"config {month}", {"action": "config", "period": month})
        questions = send("questions", {"action": "questions", "period": first})["none"]["result"]
        q = next(q for q in questions if q["candidates"])
        answer = {"action": "answer", "period": first, "number": q["number"]}
        send("answer, closed", dict(answer, group=q["candidates"][0]))
        send("answer, no group", dict(answer, group="Zzqx", override=True))
        send("answer", dict(answer, group=q["candidates"][0], override=True))
        send("answer, answered", dict(answer, group=q["candidates"][0], override=True))
        send("move", {"action": "move", "period": first, "raw": q["raw"], "occurrence": 0,
                      "group": minor, "override": True})
        send("move, no entry", {"action": "move", "period": first, "raw": "zzqx",
                                "occurrence": 0, "group": minor, "override": True})
        send("omit, no group", {"action": "omit", "period": first, "groups": ["Zzqx"],
                                "override": True})
        send("adjust, no group", {"action": "adjust", "period": first, "group": "Zzqx",
                                  "value": 1, "override": True})
        send("preview", {"action": "configure", "scope": "onward", "period": months[1],
                         "override": True,
                         "ops": [{"op": "rename_major", "major": major, "name": "Renamed"}]})
        send("always", {"action": "configure", "op": "learn_word",
                        "word": "pretzel", "group": minor})
        send("teach, short", {"action": "configure", "op": "learn_word", "word": "ab",
                              "group": minor, "override": True})
        send("teach", {"action": "configure", "op": "learn_word", "word": "kombucha",
                       "group": minor, "override": True})
        send("forget, untaught", {"action": "configure", "op": "forget_word",
                                  "word": "zzqx", "override": True})
        send("label, comma", {"action": "configure", "op": "left_rename_slot",
                              "slot": slot, "label": "a, b", "override": True})
        send("export", {"action": "export", "format": "txt", "period": first, "year": 2026})
        send("export, no year", {"action": "export", "format": "txt", "year": 1999})
        send("compare", {"action": "compare", "periods": months[:2]})
        send("no such month", {"action": "questions", "period": "Zzqx"})
        send("restore, newer", {"action": "restore", "confirm": "RESTORE",
                                "backup": {"kind": "budget-backup", "version": 99}})
        send("restore, damaged", {"action": "restore", "confirm": "RESTORE",
                                  "backup": {"kind": "budget-backup", "version": 1,
                                             "server": {"years": {"x": "y"}}}})
        backup = send("backup", {"action": "backup"})
        facts["backups equal"] = backup["none"] == backup["en"] == backup["ru"]
        send("restore", {"action": "restore", "backup": backup["none"]["result"],
                         "confirm": "RESTORE"})
        send("reset answers", {"action": "reset", "scope": "answers", "period": first,
                               "confirm": "RESET", "override": True})
        send("reset onward", {"action": "reset", "scope": "onward", "period": last,
                              "confirm": "RESET", "override": True})
        send("unknown action", {"action": "nope"})
        send("no action", {})
        send("a bug", {"action": "questions", "period": 5})
        send("reset all", {"action": "reset", "scope": "all", "confirm": "RESET"})
        facts["after"] = send("periods, after", {"action": "periods"})
    """)
    assert facts["en differs"] == []
    assert facts["store differs"] == []
    assert facts["ru differs"] == []
    assert facts["backups equal"] is True
    assert facts["refused"] == [
        "answer, closed", "answer, no group", "answer, answered", "move, no entry",
        "omit, no group", "adjust, no group", "teach, short",
        "forget, untaught", "label, comma", "export, no year", "no such month",
        "restore, newer", "restore, damaged", "unknown action", "no action", "a bug",
    ]
    assert {"closed", "answer_new_group", "no_open_question",
            "no_entry", "not_groups_here", "not_group_here", "word_short",
            "word_not_taught", "does_not_compose", "no_year_stored",
            "no_period_stored", "backup_newer", "backup_years"} <= set(facts["coded"])
    assert all(code in RU for code in facts["coded"])
    assert facts["after"] == {key: {"ok": True, "result": []} for key in ("none", "en", "ru")}


@needs_household
def test_a_closed_month_is_refused_in_russian_with_its_code(tmp_path) -> None:
    facts = _engine(tmp_path, """
        en, ru = Book(), Book("ru")
        for book in (en, ru):
            for text in MONTHS:
                book({"action": "import", "text": text, "year": 2026})
        first = next(p["month"] for p in en({"action": "periods"})["result"]
                     if not p["moved"])
        number = en({"action": "questions", "period": first})["result"][0]["number"]
        ways = {
            "answer": {"action": "answer", "period": first, "number": number, "group": "x"},
            "omit": {"action": "omit", "period": first, "groups": []},
            "adjust": {"action": "adjust", "period": first, "group": "x", "value": 1},
            "unanswer": {"action": "unanswer", "period": first,
                         "entries": [{"raw": "x", "occurrence": 0}]},
            "move": {"action": "move", "period": first, "raw": "x", "occurrence": 0,
                     "group": "x"},
            "reset answers": {"action": "reset", "scope": "answers", "period": first,
                              "confirm": "RESET"},
            "add to": {"action": "import", "period": first, "text": "25.01\\n100 honey\\n"},
            "scoped edit": {"action": "configure", "scope": "month", "period": first,
                            "ops": [{"op": "rename_major", "major": "x", "name": "y"}]},
            "paste": {"action": "import", "text": MONTHS[0], "year": 2026, "replace": True},
            "every month": {"action": "configure", "op": "learn_word", "word": "kombucha",
                            "group": "Food"},
        }
        facts["replies"] = {label: [en(event), ru(event)] for label, event in ways.items()}
        facts["stores equal"] = en.text() == ru.text()
    """)
    replies = facts.pop("replies")
    for label in ("answer", "omit", "adjust", "unanswer", "move", "reset answers",
                  "add to"):
        english, russian = replies[label]
        assert english == {"ok": False, "error": EN_CLOSED, "code": "closed"}, label
        assert russian == {"ok": False, "error": RU_CLOSED, "code": "closed"}, label
    assert [reply["code"] for reply in replies["scoped edit"]] == ["no_major", "no_major"]

    english, russian = replies["paste"]
    assert english == {"ok": False, "code": "paste_closed", "error":
                       'this paste would rewrite January 2026, which is read-only - '
                       'unlock it first, or pass "override": true'}
    assert russian == {"ok": False, "code": "paste_closed", "error":
                       "эта вставка перезаписала бы закрытый месяц: Январь 2026. "
                       "Сначала откройте его."}

    english, russian = replies["every month"]
    assert english["ok"] and russian["ok"], (english, russian)
    assert facts["stores equal"] is True


@needs_household
def test_an_unknown_language_is_english(tmp_path) -> None:
    facts = _engine(tmp_path, """
        weird = INPUT["weird"]
        events = [
            {"action": "import", "text": MONTHS[0], "year": 2026},
            {"action": "periods"},
            {"action": "answer", "period": "January", "number": 0, "group": "x"},
            {"action": "configure", "scope": "month", "period": "January",
             "override": True, "ops": [{"op": "rename_major", "major": "Zzqx", "name": "y"}]},
            {"action": "reset", "scope": "month", "period": "January", "confirm": "RESET",
             "override": True},
            {"action": "nope"},
        ]
        plain = Book()
        expected = [plain(event) for event in events]
        facts["differ"] = []
        for lang in weird:
            book = Book(lang)
            for event, reply in zip(events, expected):
                if book(event) != reply:
                    facts["differ"].append([repr(lang), event["action"]])
        facts["codes"] = [reply.get("code") for reply in expected]
    """, weird=["de", "", "RU", "ru-RU", " ru", None, 5, ["ru"], {"ru": 1}, True, "en"])
    assert facts["differ"] == []
    assert facts["codes"] == [None, None, "closed", "no_major", None, None]


@needs_household
def test_an_uncoded_refusal_gets_a_russian_lead_in(tmp_path) -> None:
    facts = _engine(tmp_path, """
        en, ru = Book(), Book("ru")
        for book in (en, ru):
            for text in MONTHS[:2]:
                book({"action": "import", "text": text, "year": 2026})
        events = {
            "unknown action": {"action": "nope"},
            "no action": {},
            "no text": {"action": "import", "text": "  "},
            "no backup": {"action": "restore"},
            "no confirm": {"action": "reset", "scope": "all"},
            "a bug": {"action": "questions", "period": 5},
            # Days added to January, carrying February's opening without its
            # salary line: store.import_text refuses it past every handler.
            "uncaught": {"action": "import", "period": "January", "override": True,
                         "text": "25.01\\n100 honey\\n####\\n06.02\\n200 milk\\n"},
        }
        facts["replies"] = {label: [en(event), ru(event)] for label, event in events.items()}
    """)
    replies = facts["replies"]
    for label in ("unknown action", "no action", "no text", "no backup", "no confirm",
                  "a bug"):
        english, russian = replies[label]
        assert set(english) == set(russian) == {"ok", "error"}, label
        assert english["ok"] is russian["ok"] is False, label
        assert russian["error"] == LEAD_IN + english["error"], label
    assert replies["no text"][0]["error"] == "import needs 'text': the raw notes"
    assert replies["a bug"][0]["error"].startswith("internal: AttributeError: ")

    english, russian = replies["uncaught"]
    assert english == {"ok": False, "error":
                       "internal: ValueError: these notes carry no salary line, so they "
                       "cannot start a month of their own - and February is already "
                       "stored. Choose February under 'Add to' instead."}
    assert russian == {"ok": False, "error":
                       "в этих записях нет строки с зарплатой, поэтому они не могут начать "
                       "новый месяц, — а Февраль уже сохранён. Вместо этого выберите "
                       "Февраль в списке «Добавить в»."}


@needs_household
def test_import_outcomes_are_said_in_russian_and_their_codes_stay(tmp_path) -> None:
    facts = _engine(tmp_path, """
        import re
        lines = MONTHS[1].splitlines()
        dated = [i for i, line in enumerate(lines) if re.fullmatch(r"\\d{2}\\.\\d{2}", line.strip())]
        february_opens = "\\n".join(lines[:dated[1]]) + "\\n"   # its salary day alone
        pastes = [
            {"action": "import", "text": MONTHS[1], "year": 2026},
            {"action": "import", "text": MONTHS[0], "year": 2026},
            {"action": "import", "text": MONTHS[0], "year": 2026},
            {"action": "import", "text": MONTHS[0], "year": 2026, "replace": True,
             "override": True},
            {"action": "import", "text": "+ 5000 from a friend\\n250 bread\\n", "year": 2026},
            {"action": "import", "text": MONTHS[0] + "\\n####\\n" + february_opens,
             "year": 2026, "replace": True, "override": True},
            {"action": "import", "period": "January", "override": True,
             "text": "25.01\\n100 honey\\n####\\n" + february_opens},
        ]
        en, ru = Book(), Book("ru")
        facts["replies"] = [[en(p), ru(p)] for p in pastes]
        facts["february opens"] = lines[dated[0]].strip()
    """)
    said = {"imported": "добавлено", "replaced": "заменено",
            "kept fuller copy": "оставлена более полная копия",
            "kept fuller copy (carry-over fragment)":
                "оставлена более полная копия (начало следующего месяца)",
            "skipped: no dated days": "пропущено: нет дней с датой"}
    met = set()
    for english, russian in facts["replies"][:6]:
        assert english["ok"] and russian["ok"]
        assert len(english["result"]) == len(russian["result"])
        for mine, theirs in zip(english["result"], russian["result"]):
            assert set(mine) == {"span", "outcome"}
            assert set(theirs) == {"span", "outcome", "said", "span_said"}
            assert (theirs["span"], theirs["outcome"]) == (mine["span"], mine["outcome"])
            assert theirs["said"] == said[mine["outcome"]]
            assert theirs["span_said"] == ("без даты" if mine["span"] == "undated"
                                           else mine["span"])
            met.add(mine["outcome"])
    assert met == set(said)

    english, russian = facts["replies"][6]
    day = facts["february opens"]
    assert re.fullmatch(r"\d{2}\.02", day)
    assert english["result"]["month"] == russian["result"]["month"] == "January"
    assert english["result"]["carried"] == [{"span": f"{day}..{day}",
                                             "outcome": "kept fuller copy"}]
    assert russian["result"]["carried"] == [{"span": f"{day}..{day}",
                                             "outcome": "kept fuller copy",
                                             "said": "оставлена более полная копия",
                                             "span_said": f"{day}..{day}"}]
    assert {k: v for k, v in russian["result"].items() if k != "carried"} == \
        {k: v for k, v in english["result"].items() if k != "carried"}


@needs_household
def test_english_success_replies_keep_their_keys(tmp_path) -> None:
    facts = _engine(tmp_path, """
        en, ru, plain = Book("en"), Book("ru"), Book()
        facts["empty"] = [plain({"action": "periods"}), en({"action": "periods"}),
                          ru({"action": "periods"})]
        for book in (en, ru):
            for text in MONTHS:
                book({"action": "import", "text": text, "year": 2026})
        major = en({"action": "config"})["result"]["majors"][0]["name"]
        rename = [{"op": "rename_major", "major": major, "name": "Renamed"}]
        events = {
            "onward": {"action": "configure", "scope": "onward", "period": "February",
                       "override": True, "ops": rename},
            "month": {"action": "configure", "scope": "month", "period": "February",
                      "override": True, "ops": rename},
            "applied": {"action": "configure", "scope": "onward", "period": "February",
                        "override": True, "confirm": True, "ops": rename},
            "reset answers": {"action": "reset", "scope": "answers", "period": "January",
                              "confirm": "RESET", "override": True},
            "reset month": {"action": "reset", "scope": "month", "period": "March",
                            "confirm": "RESET", "override": True},
        }
        facts["replies"] = {label: [en(e), ru(e)] for label, e in events.items()}
    """)
    assert facts["empty"] == [{"ok": True, "result": []}] * 3
    replies = facts["replies"]

    english, russian = replies["onward"]
    assert set(english["result"]) == set(russian["result"]) == \
        {"pending", "scope", "from", "months", "ops"}
    assert english["result"]["from"] == "February 2026"
    assert english["result"]["months"] == ["February 2026", "March 2026",
                                           "and every later month"]
    assert russian["result"]["from"] == "Февраль 2026"
    assert russian["result"]["months"] == ["Февраль 2026", "Март 2026",
                                           "и все последующие месяцы"]
    assert russian["result"]["ops"] == english["result"]["ops"]
    assert replies["month"][0]["result"]["months"] == ["February 2026"]
    assert replies["month"][1]["result"]["months"] == ["Февраль 2026"]

    english, russian = replies["applied"]
    assert english["result"]["applied"] == {"scope": "onward",
                                            "months": ["February 2026", "March 2026"]}
    assert russian["result"]["applied"] == {"scope": "onward",
                                            "months": ["Февраль 2026", "Март 2026"]}
    assert {k: v for k, v in russian["result"].items() if k != "applied"} == \
        {k: v for k, v in english["result"].items() if k != "applied"}

    english, russian = replies["reset answers"]
    assert set(english["result"]) == set(russian["result"]) == \
        {"scope", "month", "span", "wiped", "questions"}
    assert (english["result"]["month"], russian["result"]["month"]) == \
        ("January 2026", "Январь 2026")
    english, russian = replies["reset month"]
    assert english["result"] == {"scope": "month", "wiped": {"months": 1},
                                 "months": ["March 2026"]}
    assert russian["result"] == {"scope": "month", "wiped": {"months": 1},
                                 "months": ["Март 2026"]}


FARE = "fare on a gathered day"
ASKING = (
    "03.05\n+ 61 900\n\n"
    f"08.05\n700 tips\n2900 supper\n\n1350 {FARE}\n\n"
    f"09.05\n4200 optician, {FARE}\n900\n\n420\n\n"
    "13.05\n1200 greengrocer\n3100 milk and pills\n+ 4400 lottery\n"
    "+ 380 squared up with a friend\n+ 190 shared with a friend\n"
    "180 squared up with a friend\n480 wine\n360 vase housewarming gift card\n"
    f"26 {FARE}\n\n"
    f"16.05\n26 {FARE}\n1300 milk\n2600 pills\n26 {FARE}\n\n"
    f"17.05\n26 {FARE}\n9800 putty and bulbs\n26 {FARE}\n"
)

ASKED_IN_RUSSIAN = {
    ("480 wine", "алкоголь — это «Food» или отдельный праздник?"),
    ("+ 380 squared up with a friend", "a friend: деньги без пояснения, за что. Это «Shared»?"),
    ("+ 190 shared with a friend",
     "a friend: деньги — это «Shared» или они возмещают что-то другое?"),
    ("180 squared up with a friend",
     "a friend: расчёт за покупку — «Shared», если только это не что-то другое"),
    ("360 vase housewarming gift card",
     "Housewarming gift — завести для этого разовую группу?"),
    (f"26 {FARE}", "эта поездка была ради «Housewarming gift» или это обычный проезд?"),
    ("9800 putty and bulbs",
     "Putty — завести разовую группу и отнести к ней всю эту поездку?"),
    ("2900 supper", "ни одно правило не подошло"),
    ("+ 4400 lottery", "ни одно правило не подошло"),
    ("700 tips", "чаевые, но перед ними нет строки, за что они"),
    (f"1350 {FARE}", "проезд, который не к чему отнести"),
    (f"4200 optician, {FARE}", "проезд с пометкой «optician» — к какой группе его отнести?"),
    ("420", "сумма без подписи, которую не к чему отнести"),
    ("1200 greengrocer", "«greengrocer» — это не «grocer»: к какой группе это отнести?"),
    ("3100 milk and pills", "в строке названы Medicine и Food — что именно это было?"),
    (f"26 {FARE}", "проезд в поездке, где покупали не только продукты, — она была ради продуктов?"),
}


def test_every_question_the_engine_words_carries_a_code() -> None:
    tree = ast.parse((ENGINE / "classify.py").read_text(encoding="utf-8"))

    def asked(node) -> bool:
        return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "ask" and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "speech")

    reviews, bare = [], []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        given = [k.value for k in node.keywords if k.arg == "review"]
        if node.func.id == "Classification" and len(node.args) > 3 \
                and not isinstance(node.args[3], ast.Starred):
            given.append(node.args[3])
        if node.func.id not in ("Classification", "replace"):
            continue
        for value in given:
            if isinstance(value, ast.Constant) and value.value is None:
                continue
            reviews.append(value)
            if not (asked(value) or isinstance(value, ast.Name)):
                bare.append(node.lineno)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        names = {t.id for t in node.targets if isinstance(t, ast.Name)}
        if names & {"naming", "aim", "question"}:
            assert asked(node.value), node.lineno
        if "review" in names:
            value = node.value
            for part in value.values if isinstance(value, ast.BoolOp) else [value]:
                assert asked(part) or isinstance(part, ast.Name) or (
                    isinstance(part, ast.Constant) and part.value is None), node.lineno
    assert bare == [], bare
    assert len(reviews) >= 17
    asks = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and asked(n)]
    codes = {n.args[0].value for n in asks}
    assert len(codes - {"context"}) == 18 and "context" in codes


@needs_household
def test_questions_are_asked_in_russian_and_keep_their_identity(tmp_path) -> None:
    facts = _engine(tmp_path, """
        en, ru = Book(), Book("ru")
        for book in (en, ru):
            for text in MONTHS + [INPUT["asking"]]:
                assert book({"action": "import", "text": text, "year": 2026})["ok"]
        facts["asked"], facts["differ"] = [], []
        for period in en({"action": "periods"})["result"]:
            for action in ("questions", "totals", "config"):
                event = {"action": action, "period": period["month"], "year": 2026}
                english, russian = en(event), ru(event)
                if action == "questions":
                    facts["asked"] += [[q["raw"], q["review"], r["review"]]
                                       for q, r in zip(english["result"], russian["result"])]
                    for reply in (english, russian):
                        for q in reply["result"]:
                            del q["review"]
                if english != russian:
                    facts["differ"].append(f"{action} {period['month']}")
        facts["stores equal"] = en.text() == ru.text()
    """, asking=ASKING)
    assert facts["differ"] == []
    assert facts["stores equal"] is True

    import tomllib
    rules = tomllib.loads(ENGLISH.read_text(encoding="utf-8"))
    own = {question for question, _ in rules["classify"]["context_questions"].values()}
    asked, russian = facts["asked"], set()
    assert len(asked) >= 25
    for raw, english, said in asked:
        if english in own:
            assert said == english, raw
            continue
        assert said != english and not said.startswith(LEAD_IN), raw
        assert re.search("[а-яё]", said), raw
        russian.add((raw, said))
    assert ASKED_IN_RUSSIAN <= russian, sorted(ASKED_IN_RUSSIAN - russian)
    assert not own
    english = {(raw, text) for raw, text, _ in asked}
    assert ("3100 milk and pills",
            "this line names Medicine and Food - which was it?") in english
    assert ("1200 greengrocer",
            "greengrocer is not grocer - which group is this?") in english
    assert ("180 squared up with a friend",
            "settling what a friend paid for - Shared unless it was something else") in english


SHORT = [
    "03.01\n+ 57 300\n9400 rent card\n\n06.01\n240 milk\n",
    "03.02\n+ 58 100\n9400 rent card\n\n06.02\n300 milk\n",
]


def _widths(text: str) -> set[int]:
    return {len(line) for line in text.split("\n") if line.strip()}


@needs_household
def test_compare_and_printouts_in_russian(tmp_path) -> None:
    facts = _engine(tmp_path, """
        def books(texts):
            pair = Book(), Book("ru")
            for book in pair:
                for text in texts:
                    assert book({"action": "import", "text": text, "year": 2026})["ok"]
            return pair

        en, ru = books(MONTHS)
        # The example months keep within their limits; one lowered here shows
        # the printout's overspent wording too.
        for book in (en, ru):
            assert book({"action": "configure", "op": "set_limit", "major": "Road",
                         "value": 1})["ok"]
        months = [p["month"] for p in en({"action": "periods"})["result"] if not p["moved"]]
        events = {
            "pair": {"action": "compare", "periods": months[:2]},
            "three": {"action": "compare", "periods": months},
            "average": {"action": "compare", "periods": months, "average": True},
            "month": {"action": "export", "format": "txt", "period": months[0], "year": 2026},
            "month rtf": {"action": "export", "format": "rtf", "period": months[0],
                          "year": 2026},
            "year": {"action": "export", "format": "txt", "year": 2026},
            "printed": {"action": "export", "format": "txt", "periods": months,
                        "average": True, "year": 2026},
            "wide": {"action": "export", "format": "txt", "periods": months * 3, "year": 2026},
        }
        facts["replies"] = {k: [en(e)["result"], ru(e)["result"]] for k, e in events.items()}
        en, ru = books(INPUT["short"])
        pair = {"action": "compare", "periods": ["January", "February"]}
        facts["short"] = [en(pair)["result"], ru(pair)["result"]]
    """, short=SHORT)
    replies = facts["replies"]

    english, russian = replies["pair"]
    head = russian.split("\n")[0]
    assert "Январь 2026" in head and "Февраль 2026" in head and head.endswith("   разница")
    assert english.split("\n")[0].endswith("January 2026  February 2026     delta")
    for text in (russian, replies["three"][1], replies["average"][1]):
        labels = [line.split("  ")[0] for line in text.split("\n")]
        assert "Итого" in labels and "Итого + разовые" in labels
        assert "Total" not in text and "January 2026" not in text
    assert _widths(russian) <= {len(head), len(head) - 10}
    assert len(_widths(replies["three"][1])) == 1
    table, heading, tail = replies["average"][1].partition(
        "\n\nСреднее за 3 месяца 2026 года\n")
    assert heading and len(_widths(table)) == 1 and len(_widths(tail)) == 1
    assert [line.split("  ")[0] for line in tail.split("\n") if line] == \
        ["Итого", "Итого + разовые"]
    assert replies["average"][0].split("\n")[-3] == "Average of 3 months of 2026"

    english, russian = facts["short"]
    assert len(_widths(russian)) == 1
    assert russian.split("\n")[0].startswith(" " * len("  Итого + разовые"))
    assert english.split("\n")[0] == " " * len("Set aside  ") + \
        f"{'January 2026':>14}{'February 2026':>15}{'delta':>10}"

    english, russian = replies["month"]
    assert english["name"] == russian["name"] == "budget-January-2026.txt"
    lines = russian["body"].split("\n")
    assert lines[0] == "Январь 2026" and "ОСНОВНЫЕ ГРУППЫ (тыс.)" in lines
    assert any(line.startswith("Итого: ") for line in lines)
    assert "\fЯнварь 2026 — подгруппы" in lines
    assert "(осталось " in russian["body"] and "(перерасход " in russian["body"]
    assert "MAJOR GROUPS" not in russian["body"] and " left)" not in russian["body"]
    assert english["body"].split("\n")[0] == "January 2026"
    assert "MAJOR GROUPS (thousands)" in english["body"].split("\n")

    english, russian = replies["month rtf"]
    assert english["name"] == russian["name"] == "budget-January-2026.rtf"
    assert russian["body"].isascii()
    assert "\\u1048?\\u1090?\\u1086?\\u1075?\\u1086?" in russian["body"]

    english, russian = replies["year"]
    assert english["name"] == russian["name"] == "budget-2026.txt"
    for label in ("Январь 2026", "Февраль 2026", "Март 2026"):
        assert label + " — подгруппы" in russian["body"]

    english, russian = replies["printed"]
    assert english["name"] == russian["name"] == "budget-compare.txt"
    assert russian["body"].split("\n")[0] == "Сравнение — 3 месяца 2026 года"
    assert english["body"].split("\n")[0] == "Comparison - 3 months of 2026"
    assert "\nСреднее за 3 месяца 2026 года\n" in russian["body"]

    english, russian = replies["wide"]
    assert [page.split("\n")[0] for page in russian["body"].split("\f")] == [
        "Сравнение — 9 месяцев 2026 года — стр. 1 из 2",
        "Сравнение — 9 месяцев 2026 года — стр. 2 из 2",
    ]
    assert [page.split("\n")[0] for page in english["body"].split("\f")] == [
        "Comparison - 9 months of 2026 - page 1 of 2",
        "Comparison - 9 months of 2026 - page 2 of 2",
    ]


@needs_household
def test_a_comma_in_a_left_label_is_refused_in_russian(tmp_path) -> None:
    facts = _engine(tmp_path, """
        from budget import left, speech

        en, ru = Book(), Book("ru")
        for book in (en, ru):
            book({"action": "import", "text": MONTHS[0], "year": 2026})
        slot = en({"action": "config"})["result"]["left"]["slots"][0]["id"]
        event = {"action": "configure", "op": "left_rename_slot", "slot": slot,
                 "label": "a, b", "override": True}
        facts["replies"] = [en(event), ru(event)]
        facts["stores equal"] = en.text() == ru.text()

        facts["said"] = []
        for raw in INPUT["shapes"]:
            try:
                left._slots(raw)
            except ValueError as why:
                facts["said"].append([
                    str(why), type(why) is speech.Said, getattr(why, "code", None),
                    speech.render("does_not_compose", {"why": why}, "ru", "x"),
                ])
    """, shapes=[
        [],
        [{"id": f"f{i}"} for i in range(21)],
        [{"label": "x"}],
        [{"id": "a"}, {"id": "a"}],
        [{"id": "a", "kind": "zz"}],
        [{"id": "a", "label": "p, q"}],
        [{"id": "a", "kind": "card"}, {"id": "b", "kind": "card"}],
        [{"id": "a", "kind": "purse", "reset": {"weekday": 9, "amount": 5}}],
        [{"id": "a", "kind": "purse", "reset": {"weekday": 1, "amount": 0}}],
    ])
    english, russian = facts["replies"]
    assert english == {"ok": False, "code": "does_not_compose",
                       "error": "that edit does not compose: a label cannot contain a comma"}
    assert russian == {"ok": False, "code": "does_not_compose",
                       "error": "это изменение несовместимо с остальными: "
                                "подпись не может содержать запятую"}
    assert facts["stores equal"] is True

    lead = "это изменение несовместимо с остальными: "
    assert facts["said"] == [
        ["the Left line needs at least one figure", True, "left_needs_figure",
         lead + "в строке остатка должна быть хотя бы одна сумма"],
        ["the Left line takes at most 20 figures", True, "most_figures",
         lead + "в строке остатка может быть не больше 20 сумм"],
        ["every figure needs an id", True, "left_no_id",
         lead + "у каждой суммы должен быть идентификатор"],
        ["two figures share the id 'a'", True, "left_same_id",
         lead + "у двух сумм один и тот же идентификатор 'a'"],
        ["kind must be one of ['card', 'cash', 'purse', 'carry']", True, "left_kind",
         lead + "вид должен быть одним из: card, cash, purse, carry"],
        ["a label cannot contain a comma", True, "left_comma",
         lead + "подпись не может содержать запятую"],
        ["only one figure can be the card balance", True, "left_one_card",
         lead + "только одна сумма может быть остатком на карте"],
        ["a purse resets on a weekday 0 (Monday) to 6", True, "purse_weekday",
         lead + "кошелёк пополняется в день недели от 0 (понедельник) до 6"],
        ["a purse needs an amount above zero", True, "purse_amount",
         lead + "у кошелька должна быть сумма больше нуля"],
    ]


@needs_both_households
def test_the_printed_left_line_keeps_the_household_word(tmp_path) -> None:
    body = """
        en, ru = Book(), Book("ru")
        for book in (en, ru):
            for text in MONTHS:
                book({"action": "import", "text": text, "year": 2026})
        event = {"action": "export", "format": "txt", "period": "February", "year": 2026}
        facts["bodies"] = [en(event)["result"]["body"], ru(event)["result"]["body"]]
    """

    def closing(text: str) -> str:
        return text.rstrip("\n").split("\n")[-1]

    english, russian = _engine(tmp_path, body)["bodies"]
    assert closing(english).startswith("Left: ") and closing(russian) == closing(english)
    assert "ОСНОВНЫЕ ГРУППЫ (тыс.)" in russian and "Остаток" not in russian

    english, russian = _engine(tmp_path, body, rules=RUSSIAN, months=RU_MONTHS)["bodies"]
    assert closing(english).startswith("Остаток: ") and closing(russian) == closing(english)
    assert re.search(r"\d,\d", closing(english))
    assert "MAJOR GROUPS (thousands)" in english and "Left:" not in english
    assert "ОСНОВНЫЕ ГРУППЫ (тыс.)" in russian
