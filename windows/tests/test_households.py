from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import tomllib
from pathlib import Path

import pytest

LOCAL = Path(__file__).resolve().parent.parent
APP = LOCAL / "app"
ENGINE = APP / "budget"
ENGLISH = LOCAL / "clean" / "rules.toml"
RUSSIAN = LOCAL / "clean" / "ru" / "rules.toml"
ENGLISH_MONTHS = [LOCAL / "clean" / "examples" / f"month-{n}.txt" for n in (1, 2, 3)]
RUSSIAN_MONTHS = [LOCAL / "clean" / "ru" / "examples" / f"month-{n}.txt" for n in (1, 2, 3)]
HOUSEHOLDS = {"en": (ENGLISH, ENGLISH_MONTHS), "ru": (RUSSIAN, RUSSIAN_MONTHS)}

pytestmark = pytest.mark.skipif(
    not all(p.is_file() for p in [ENGLISH, RUSSIAN, *ENGLISH_MONTHS, *RUSSIAN_MONTHS]),
    reason="the invented households are not present",
)


_PRELUDE = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "INPUT = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))\n"
    "facts = {}\n"
)
_POSTLUDE = "\nprint(json.dumps(facts, ensure_ascii=True))\n"


def _engine(where: Path, rules: Path, body: str, **given) -> dict:
    run = Path(tempfile.mkdtemp(dir=where))
    (run / "input.json").write_text(json.dumps(given, ensure_ascii=False), encoding="utf-8")
    (run / "probe.py").write_text(_PRELUDE + textwrap.dedent(body) + _POSTLUDE, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in ("BUDGET_RULES", "PYTHONPATH")}
    env.update(BUDGET_RULES=str(rules), PYTHONPATH=str(APP), PYTHONDONTWRITEBYTECODE="1")
    done = subprocess.run(
        [sys.executable, "-B", str(run / "probe.py"), str(run / "input.json")],
        cwd=run, env=env, capture_output=True, timeout=300,
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    return json.loads(done.stdout.decode("ascii").strip().splitlines()[-1])


_READINGS = r"""
    import re, tempfile
    from budget.api import dispatch
    from budget.classify import classify_period, coverage
    from budget.rules import RULES, resolve_pattern
    from budget.store import Store

    cfg = RULES["classify"]
    roster = len(RULES["groups"]["minor_order"])
    tokens = {}

    def tok(name):
        if name is None:
            return None
        if name not in tokens:
            tokens[name] = "g%d" % len(tokens)
        return tokens[name]

    for major in RULES["groups"]["majors"]:
        tok(major["name"])
        for minor in major["minors"]:
            tok(minor)
    for _, group in cfg["contexts"]:
        tok(group)
    known = len(tokens)
    partner = cfg["settlements"]["partner"]
    asked = [question for question, _ in cfg["context_questions"].values()]
    keyword = {}
    for i, (pattern, _) in enumerate(cfg["rules"]):
        keyword.setdefault(resolve_pattern(cfg, pattern)[:24], "keyword rule %d" % i)
    # The engine's rules that name no group - kept as they are, or the English
    # household's "Salary" would turn the rule "salary" into a token.
    unnamed = {"salary", "prepayment is salary", "none", "an occasion, named first",
               "small flowers", "a meal out", "gift", "gift outing", "occasional outing",
               "a tip on what came before it", "refund of the line above",
               "refund matched to its purchase"}

    def shape(text):
        # A rule or a question with the names in it replaced by their tokens.
        if text is None:
            return None
        text = str(text)
        if text in keyword:
            return keyword[text]
        if text in unnamed or text.startswith("belongs to "):
            return text
        if text in asked:
            return "the context question %d" % asked.index(text)
        for name in sorted(tokens, key=len, reverse=True):
            text = re.sub(r"(?<![^\W_])" + re.escape(name) + r"(?![^\W_])", tokens[name],
                          text, flags=re.IGNORECASE)
        return re.sub(r"(?<![^\W_])" + re.escape(partner) + r"(?![^\W_])", "<partner>",
                      text, flags=re.IGNORECASE)

    def rows(minors):
        out = []
        for row in minors:
            parts = row.get("subgroups") or [row]
            out.append([row["total"], [
                [part["total"], part["amounts"],
                 [[m["kind"], len(m["candidates"]), m["occurrence"]]
                  for mark in part["marks"] for m in mark]]
                for part in parts]])
        return out

    def read(store, month):
        totals = dispatch(store, {"action": "totals", "period": month, "year": 2026})["result"]
        identity, _, period = store.period(month)
        results = classify_period(period, overlay=store.rulings(identity))
        lines = []
        for c in results:
            tok(c.minor)
            for name in c.candidates:
                tok(name)
            lines.append([c.entry.amount, c.entry.income, c.entry.bare, c.block, tok(c.minor),
                          shape(c.rule), shape(c.review), [tok(n) for n in c.candidates]])
        minors = rows(totals["minors"])
        left = totals["left"]
        return {
            "totals": totals["totals"],
            "questions": totals["questions"],
            "coverage": list(coverage(results)),
            "unparsed": len(period.unparsed),
            "majors": [[m["value"], m["tier"], m["limit"], m["income"], m["chart"]]
                       for m in totals["majors"]],
            "limits": [row["value"] for row in totals["limits"]],
            "appended": [[a["value"], a["actual"], a["adjusted"], a["counted"]]
                         for a in totals["appended"]],
            "minor rows": minors[:roster],
            # After the roster the minor page sorts its occasional groups by
            # NAME, so their order is the language's; compared as a set.
            "occasional minor rows": sorted(minors[roster:], key=repr),
            "left": [cell["value"] for cell in left["cells"]],
            "left day": [left["date"], left["days_after"], left["extra"]],
            # Every day's own Left figures, not only the last: a line whose word
            # the grammar missed is dropped without a trace in the Totals.
            "left each day": [[str(d.date), None if d.balances is None else
                               [None if v is None else str(v) for v in d.balances.values]]
                              for d in period.days],
            "left written back as written": left["text"] == left["raw"],
            "lines": lines,
        }

    stages = []
    with tempfile.TemporaryDirectory() as folder:
        store = Store(Path(folder) / "store.json")
        for n, path in enumerate(INPUT["months"], 1):
            reply = dispatch(store, {"action": "import", "year": 2026,
                                     "text": Path(path).read_text(encoding="utf-8")})
            assert reply["ok"], reply
            stages.append({
                "imported": [o["outcome"] for o in reply["result"]],
                "months": {m: read(store, m) for m in ["January", "February", "March"][:n]},
                "december": read(store, "December")["lines"] if store.period("December") else None,
            })
    facts["stages"] = stages
    facts["names"] = [known, len(tokens)]
"""


@pytest.fixture(scope="module")
def readings(tmp_path_factory) -> dict:
    where = tmp_path_factory.mktemp("households")
    return {
        lang: _engine(where, rules, _READINGS, months=[str(p) for p in months])
        for lang, (rules, months) in HOUSEHOLDS.items()
    }


def _differences(english, russian, where: str = "") -> list[str]:
    if isinstance(english, dict) and isinstance(russian, dict) and english.keys() == russian.keys():
        return [d for key in english
                for d in _differences(english[key], russian[key], f"{where} {key}".strip())]
    if isinstance(english, list) and isinstance(russian, list) and len(english) == len(russian):
        return [d for i, (a, b) in enumerate(zip(english, russian))
                for d in _differences(a, b, f"{where} {i}".strip())]
    return [] if english == russian else [f"{where}: English {english!r}, Russian {russian!r}"]


def test_both_invented_households_load(tmp_path) -> None:
    probe = """
        import budget.api
        from budget import grammar
        from budget.rules import load, path_in_use
        data = load()
        built = grammar.build(data.get("notes"))
        facts["file"] = str(path_in_use())
        facts["majors"] = len(data["groups"]["majors"])
        facts["notes"] = sorted(data.get("notes", {}))
        facts["words"] = [built.left_word, built.decimal, built.ocr, built.capitalise_months]
    """
    english = _engine(tmp_path, ENGLISH, probe)
    russian = _engine(tmp_path, RUSSIAN, probe)
    assert Path(english["file"]) == ENGLISH and Path(russian["file"]) == RUSSIAN
    assert english["majors"] == russian["majors"]
    assert english["notes"] == ["road", "taxi"]
    assert english["words"] == ["Left", ".", "eng", True]
    assert russian["words"] == ["Остаток", ",", "rus+eng", False]
    assert {"left", "skip", "refers", "months", "taxi", "road", "card"} <= set(russian["notes"])


def _names(english: dict, russian: dict) -> dict[str, str]:
    names: dict[str, str] = {}

    def pair(a: str, b: str) -> None:
        assert names.setdefault(a, b) == b, f"{a!r} is translated two ways"

    for a, b in zip(english["groups"]["majors"], russian["groups"]["majors"]):
        pair(a["name"], b["name"])
        for x, y in zip(a["minors"], b["minors"]):
            pair(x, y)
    c_en, c_ru = english["classify"], russian["classify"]
    for (_, a), (_, b) in zip(c_en["contexts"], c_ru["contexts"]):
        pair(a, b)
    for a, b in zip(c_en["platforms"], c_ru["platforms"]):
        pair(a, b)
    for (_, a), (_, b) in zip(c_en["rules"], c_ru["rules"]):
        pair(a, b)
    pair(c_en["appointment"][1], c_ru["appointment"][1])
    pair(c_en["alcohol"]["celebration"], c_ru["alcohol"]["celebration"])
    pair(c_en["settlements"]["group"], c_ru["settlements"]["group"])
    return names


def _skeleton(value, key: str = ""):
    if key == "patterns":
        return sorted(value)
    if key in ("nested", "context_questions"):
        return [_skeleton(v) for v in value.values()]
    if isinstance(value, dict):
        return {k: _skeleton(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_skeleton(v) for v in value]
    if isinstance(value, str):
        return value if key in ("tier", "kind", "unit", "place", "id") else "text"
    return value


def test_the_russian_household_is_the_english_one_translated() -> None:
    english = tomllib.loads(ENGLISH.read_text(encoding="utf-8"))
    russian = tomllib.loads(RUSSIAN.read_text(encoding="utf-8"))
    notes, english_notes = russian.pop("notes"), english.pop("notes")
    assert sorted(english_notes) == ["road", "taxi"] and {"road", "taxi"} <= set(notes)
    for key in ("road", "taxi"):
        mine = re.compile(notes[key], re.IGNORECASE)
        assert all(mine.fullmatch(w) for w in english_notes[key].split("|")), key
    assert _skeleton(russian) == _skeleton(english)

    names = _names(english, russian)
    assert len(names) == len(set(names.values())) >= 15
    for a, b in names.items():
        assert a != b and re.search("[а-яё]", b, re.IGNORECASE), (a, b)

    def same(en, ru, what: str) -> None:
        assert [names[n] for n in en] == list(ru), what

    g_en, g_ru = english["groups"], russian["groups"]
    same(g_en["limit_order"], g_ru["limit_order"], "limit_order")
    same(g_en["minor_order"], g_ru["minor_order"], "minor_order")
    same(g_en.get("nested", {}), g_ru.get("nested", {}), "the nested header")
    for (header, subs), (_, ours) in zip(g_en.get("nested", {}).items(),
                                         g_ru.get("nested", {}).items()):
        same([minor for _, minor in subs], [minor for _, minor in ours], f"nested {header}")
        for (label, _), (translated, _) in zip(subs, ours):
            assert translated != label and re.search("[а-яё]", translated), (label, translated)
    same(g_en["roles"].values(), g_ru["roles"].values(), "roles")
    assert list(g_en["roles"]) == list(g_ru["roles"])

    c_en, c_ru = english["classify"], russian["classify"]
    same(c_en["platforms"], c_ru["platforms"], "platforms")
    same([g for _, g in c_en["contexts"]], [g for _, g in c_ru["contexts"]], "contexts")
    same([c_en["appointment"][1]], [c_ru["appointment"][1]], "appointment")
    same([g for _, g in c_en["rules"]], [g for _, g in c_ru["rules"]], "rules")
    assert [p for p, _ in c_en["rules"] if p.startswith("@")] == \
        [p for p, _ in c_ru["rules"] if p.startswith("@")]
    same(c_en["context_questions"], c_ru["context_questions"], "context_questions")
    for (_, (_, offered)), (_, (question, ours)) in zip(c_en["context_questions"].items(),
                                                        c_ru["context_questions"].items()):
        same(offered, ours, "a context question's groups")
        assert all(f"«{name}»" in question for name in ours), question
    same(c_en["food"].values(), c_ru["food"].values(), "classify.food")
    same([c_en["trip"][k] for k in ("road", "taxi", "restaurants")],
         [c_ru["trip"][k] for k in ("road", "taxi", "restaurants")], "classify.trip")
    same([c_en["alcohol"]["celebration"], c_en["settlements"]["group"]],
         [c_ru["alcohol"]["celebration"], c_ru["settlements"]["group"]], "alcohol, settlements")
    assert sorted(c_en["patterns"]) == sorted(c_ru["patterns"])
    for key in ("per_visit_whole", "per_visit_service"):
        same(english["display"][key], russian["display"][key], f"display.{key}")

    for a, b in zip(english["left"]["slots"], russian["left"]["slots"]):
        assert b["id"] == a["id"] and b["id"].isascii()
        assert b.get("place") == a.get("place")
        assert b["label"] != a["label"] and re.search("[а-яё]", b["label"])
        same(a.get("minors", []), b.get("minors", []), f"slot {a['id']}")


def test_the_russian_months_read_as_the_english_ones(readings) -> None:
    english, russian = readings["en"], readings["ru"]
    assert english["names"] == russian["names"]
    assert [list(s["months"]) for s in english["stages"]] == [
        ["January"], ["January", "February"], ["January", "February", "March"]]
    assert _differences(english["stages"], russian["stages"]) == []

    for stage in english["stages"]:
        for month in stage["months"].values():
            confident, total = month["coverage"]
            assert total > 30 and total / 2 < confident < total and month["questions"] > 0
            assert month["unparsed"] == 0 and month["left written back as written"]
            assert month["left"] and all(value is not None for value in month["left"])
            assert month["left each day"] and all(day[1] for day in month["left each day"])
            assert month["totals"]["grand"] >= month["totals"]["necessary"] > 0
            assert any(part[1] for row in month["minor rows"] for part in row[1])


def test_the_russian_left_lines_are_read_not_dropped(tmp_path) -> None:
    probe = """
        from budget.left import DEFAULT_SLOTS, assemble
        from budget.notes import parse
        for path in INPUT["months"]:
            text = Path(path).read_text(encoding="utf-8")
            period = parse(text)[0]
            written = [line.strip() for line in text.splitlines()
                       if line.strip().split(":")[0] in ("Остаток", "Left")]
            read = [d.balances for d in period.days if d.balances is not None]
            facts[Path(path).name] = {
                "days": len(period.days),
                "written": len(written),
                "read": len(read),
                "unparsed": period.unparsed,
                "written back": sum(
                    assemble(b.values, DEFAULT_SLOTS, b.fields) == b.raw for b in read),
            }
    """
    russian = [str(p) for p in RUSSIAN_MONTHS]
    under_ru = _engine(tmp_path, RUSSIAN, probe, months=russian)
    for name, month in under_ru.items():
        assert month["days"] == month["written"] == month["read"] == month["written back"] > 0, name
        assert month["unparsed"] == [], name
    under_en = _engine(tmp_path, ENGLISH, probe, months=russian)
    assert all(m["read"] == 0 and m["written"] > 0 for m in under_en.values())
    english_under_ru = _engine(tmp_path, RUSSIAN, probe, months=[str(p) for p in ENGLISH_MONTHS])
    assert all(m["read"] == m["written"] == m["days"] for m in english_under_ru.values())


def test_the_deferred_credit_moves_in_russian(readings) -> None:
    changes = {}
    for lang, reading in readings.items():
        alone = reading["stages"][0]["months"]["January"]
        beside = reading["stages"][1]["months"]["January"]
        february = reading["stages"][1]["months"]["February"]["lines"]
        moved = beside["lines"][-1]
        assert len(beside["lines"]) == len(alone["lines"]) + 1, lang
        assert moved[:3] == [340, True, True], lang
        assert moved[5].startswith("unlabelled income is g"), lang
        assert not any(line[0] == 340 and line[1] for line in february), lang
        assert not any(line[0] == 210 and line[1] for line in alone["lines"]), lang
        december = reading["stages"][0]["december"]
        assert [line[:3] for line in december] == [[210, True, True]], lang
        changes[lang] = {key: (alone[key], beside[key]) for key in alone
                         if alone[key] != beside[key]}
    assert changes["en"] and set(changes["en"]) >= {"coverage", "totals", "lines"}
    assert changes["ru"] == changes["en"]


_EXERCISE = {
    "en": (
        "10.01\n"
        "+ 57 300\n"
        "9400 rent card\n"
        "740 yarn (-210 return)\n"
        "+ 210 do not count, refers to December\n"
        "Left: purse 6.8, account 62730\n"
        "\n"
        "11.01\n"
        "2340 combs and 1k hairdresser\n"
        "2860 grocer card\n"
        "280 soup\n"
        "70 tips\n"
        "Left: purse 4.2, account 61110\n"
    ),
    "ru": (
        "10.01\n"
        "+ 57 300\n"
        "9400 аренда картой\n"
        "740 пряжа (-210 возврат)\n"
        "+ 210 не считать, относится к декабрю\n"
        "Осталось: наличные 6,8, счёт 62730\n"
        "\n"
        "11.01\n"
        "2340 расчёска и 1к стрижка\n"
        "2860 бакалея по карте\n"
        "280 суп\n"
        "70 на чай\n"
        "Остаток: наличные 4,2, счёт 61110\n"
    ),
}


def test_the_words_the_months_do_not_use_read_alike(tmp_path) -> None:
    got = {}
    for lang, (rules, _) in HOUSEHOLDS.items():
        days = tmp_path / f"exercise-{lang}.txt"
        days.write_text(_EXERCISE[lang], encoding="utf-8")
        got[lang] = _engine(tmp_path, rules, _READINGS, months=[str(days)])
    assert got["en"]["names"] == got["ru"]["names"]
    assert _differences(got["en"]["stages"], got["ru"]["stages"]) == []

    january = got["en"]["stages"][0]["months"]["January"]
    amounts = [line[0] for line in january["lines"]]
    assert 530 in amounts and 740 not in amounts
    assert {1340, 1000} <= set(amounts) and 2340 not in amounts
    assert len(january["left each day"]) == 2 and all(day[1] for day in january["left each day"])


_ENGLISH_FORMS = {
    "balance": ["Left: 1, 2", "eft: 61 240, 6.8", "Leftover: 5"],
    "deferred": ["do not count, previous month", "refers to October", "a previous months"],
    "refers_to": ["don't count, refers to december", "refers to May 5", "refers to them"],
    "marker": [" do not count, previous month", " don't count, refers to October (moved)",
               " not counted, previous month", " do count, previous month"],
    "instant_refund": ["boots (-1200 return)", "coat ( - 5 refund )", "(-1200)"],
    "fare": ["fare on a gathered day to the vet", "fare on a gathered days", "taxi to the vet"],
    "road": ["the way to a gathered day", "the way to a gathered day home", "road"],
    "homeward": ["fare on a gathered day", "fare on a gathered day back",
                 "fare on a gathered day to home", "fare on a gathered day to the vet", "taxi"],
    "prepayment": ["prepayment", "pre-payment", "pre payment", "payment"],
    "flowers": ["flowers", "roses", "a rose"],
    "occasion": ["22nd of january supper", "3rd of May", "1 of december", "22nd of the month"],
    "groceries_named": ["food", "seafood"],
    "carve_out": ["towels and 2k stamps", "kettle & 3k batteries", "mints*3 snacks"],
    "unplaced_fare": ["fare on a gathered day", "the way to a gathered day home", "taxi",
                      "a fare on a gathered day"],
    "named_fare": ["vet fare on a gathered day", "museum, the way to a gathered day", "vet taxi"],
    "paid_by_card": ["grocer card", "cardigan"],
    "tip": ["tips", "tip", "tipsy"],
    "fare_word": ["the fare on a gathered day", "a the way to a gathered day trip", "taxis",
                  "a road trip"],
}


def test_the_russian_table_reads_the_english_words(tmp_path) -> None:
    probe = """
        from budget import grammar
        from budget.notes import MONTH_NAMES, parse
        from budget.rules import RULES
        mine, english = grammar.build(RULES.get("notes")), grammar.build(INPUT["english notes"])

        def found(pattern, text):
            m = pattern.search(text)
            return None if m is None else [m.group(0), list(m.groups())]

        facts["patterns"] = {
            f"{name}: {form!r}": [found(getattr(english, name), form), found(getattr(mine, name), form)]
            for name, forms in INPUT["forms"].items() for form in forms}
        facts["months"] = [[english.month_of(w, MONTH_NAMES), mine.month_of(w, MONTH_NAMES)]
                           for w in INPUT["month words"]]
        facts["card"] = [[english.on_card(s), mine.on_card(s)] for s in INPUT["card"]]
        facts["parsed"] = []
        for text in INPUT["texts"]:
            facts["parsed"].append([
                [day.date,
                 None if day.balances is None else [None if v is None else str(v)
                                                    for v in day.balances.values],
                 [[e.amount, e.income, e.deferred, e.bare, e.refers_to, e.text]
                  for block in day.blocks for e in block.entries],
                 day.unparsed]
                for period in parse(text) for day in period.days])
    """
    given = {
        "forms": _ENGLISH_FORMS,
        "english notes": tomllib.loads(ENGLISH.read_text(encoding="utf-8"))["notes"],
        "texts": [p.read_text(encoding="utf-8") for p in ENGLISH_MONTHS] + [_EXERCISE["en"]],
        "card": ["supermarket card", "cardigan", "CARD", "boots"],
        "month words": ["january", "May", "DECEMBER", "august", "September", "march"],
    }
    under_en = _engine(tmp_path, ENGLISH, probe, **given)
    under_ru = _engine(tmp_path, RUSSIAN, probe, **given)

    for form, (english, russian) in under_ru["patterns"].items():
        assert russian == english, form
    matched = [english for english, _ in under_ru["patterns"].values() if english]
    assert 0 < len(matched) < len(under_ru["patterns"])
    assert under_ru["patterns"]["fare: 'fare on a gathered day to the vet'"][1]
    assert under_ru["patterns"]["road: 'the way to a gathered day'"][1]
    assert under_ru["patterns"]["fare: 'taxi to the vet'"] == [None, None]
    assert under_ru["patterns"]["road: 'road'"] == [None, None]
    assert under_ru["months"] == [[w.capitalize()] * 2 for w in given["month words"]]
    assert [a == b for a, b in under_ru["card"]] == [True] * 4
    assert under_ru["parsed"] == under_en["parsed"]
    days = [day for text in under_en["parsed"] for day in text]
    assert len(days) > 40 and all(day[1] for day in days)
    assert sum(entry[4] == "December" for day in days for entry in day[2]) == 2


def _russian_text() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in [RUSSIAN, *RUSSIAN_MONTHS])


def test_every_pattern_is_written_so_its_backslashes_stay() -> None:
    text = RUSSIAN.read_text(encoding="utf-8")
    basic, i = [], 0
    while i < len(text):
        if text.startswith("#", i):
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
        elif text.startswith("'''", i):
            i = text.index("'''", i + 3) + 3
        elif text.startswith("'", i):
            i = text.index("'", i + 1) + 1
        elif text.startswith('"""', i):
            end = text.index('"""', i + 3)
            basic.append(text[i + 3:end])
            i = end + 3
        elif text.startswith('"', i):
            end = i + 1
            while text[end] != '"':
                end += 2 if text[end] == "\\" else 1
            basic.append(text[i + 1:end])
            i = end + 1
        else:
            i += 1
    assert len(basic) > 50
    assert [s for s in basic if "\\" in s] == []

    def strings(value):
        if isinstance(value, dict):
            return [s for k, v in value.items() for s in [k, *strings(v)]]
        if isinstance(value, list):
            return [s for v in value for s in strings(v)]
        return [value] if isinstance(value, str) else []

    values = strings(tomllib.loads(text))
    assert [s for s in values if any(ord(c) < 0x20 or 0x7F <= ord(c) < 0xA0 for c in s)] == []
    assert sum("\\" in s for s in values) > 40


_SCHEMES = [dict(zip("жхцчшщйюяёеыэьъвгиук", spelling)) for spelling in (
    ("zh", "kh", "ts", "ch", "sh", "shch", "y", "yu", "ya", "yo", "e", "y", "e", "", "",
     "v", "g", "i", "u", "k"),
    ("j", "h", "tz", "ch", "sh", "sch", "i", "iu", "ia", "e", "e", "i", "e", "", "",
     "v", "g", "i", "u", "k"),
    ("zh", "x", "c", "ch", "sh", "sh", "j", "ju", "ja", "jo", "e", "y", "e", "", "",
     "v", "g", "i", "u", "k"),
    ("zh", "h", "ts", "ch", "sh", "sh", "y", "u", "ya", "e", "e", "i", "e", "", "",
     "v", "gh", "y", "ou", "k"),
    ("sch", "ch", "z", "tsch", "sch", "schtsch", "j", "ju", "ja", "jo", "e", "y", "e", "", "",
     "w", "g", "i", "u", "k"),
    ("g", "kh", "c", "c", "s", "s", "y", "yu", "ya", "yo", "e", "y", "e", "", "",
     "v", "g", "i", "u", "c"),
)]
_PLAIN = dict(zip("абдзлмнопрстф", "abdzlmnoprstf"))


def _latin(text: str, scheme: dict) -> str:
    return "".join(scheme.get(c.lower(), _PLAIN.get(c.lower(), c)) for c in text)


def _words(text: str) -> set[str]:
    return {w.casefold() for w in re.findall(r"[^\W\d_]{4,}", re.sub(r"\\[A-Za-z]", " ", text))}
