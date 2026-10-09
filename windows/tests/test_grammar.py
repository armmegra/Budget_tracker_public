from __future__ import annotations

import ast
import copy
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

pytestmark = pytest.mark.skipif(
    not ENGLISH.is_file(), reason="the example household is not present"
)

TODAY = [
    ("balance", "notes", "_BALANCE", r"^L?eft:\s*(?P<body>.*)$"),
    ("deferred", "notes", "_DEFERRED", r"previous month|refers to \w+"),
    ("refers_to", "notes", "_REFERS_TO",
     r"refers to\s+(january|february|march|april|may|june|july|august|september"
     r"|october|november|december)"),
    ("marker", "notes", "_MARKER",
     r"\s*#?\s*(?:do not count|don'?t count|not counted)\s*,?\s*"
     r"(?:previous month|refers to \w+)\s*(?:\([^)]*\)\s*)?$"),
    ("instant_refund", "notes", "_INSTANT_REFUND", r"\(\s*-\s*(\d+)\s*(?:return|refund)\s*\)"),
    ("fare", "classify", "_FARE", r"^taxi\b"),
    ("road", "classify", "_ROAD", r"^road\b"),
    ("homeward", "classify", "_HOMEWARD", r"^taxi$|^taxi\s+(?:to\s+home|back)\b"),
    ("prepayment", "classify", "_PREPAYMENT", r"\bpre[-\s]?payment\b"),
    ("flowers", "classify", "_FLOWERS", r"\bflower|\brose"),
    ("occasion", "classify", "_OCCASION",
     r"^\d{1,2}\s*(?:st|nd|rd|th)?\s+of\s+"
     r"(january|february|march|april|may|june|july|august|september|october|"
     r"november|december)\b"),
    ("groceries_named", "classify", "_GROCERIES_NAMED", r"\bfood\b"),
    ("carve_out", "classify", "_CARVE_OUT",
     r"^(?P<rest>.*?)\s*(?:and|&|\+)\s+(?P<amount>\d+)k\s+(?P<group>\w+)\s*$"),
    ("unplaced_fare", "classify", "_UNPLACED_FARE", r"^(?:taxi|road)\b"),
    ("named_fare", "classify", "_NAMED_FARE", r"^(?P<what>\S.*?)[\s,]+(?:taxi|road)\b"),
    ("paid_by_card", "classify", "_PAID_BY_CARD", r"\bcard\b"),
    ("gift", "classify", "_GIFT", r"(\w+)\s+(present|gift)\b"),
    ("tip", "classify", "_TIP", r"\btips?\b"),
    ("fare_word", "display", "_FARE_TEXT", r"\btaxi\b|\broad\b"),
    ("fare_word", "groups", None, r"\btaxi\b|\broad\b"),
    ("paid_by_card", "groups", None, r"\bcard\b"),
]

TODAY_STOP_WORDS = frozenset({
    "or", "and", "the", "for", "of", "to", "in", "on", "at", "from",
    "back", "her", "his", "our", "new", "old", "one", "two",
})
TODAY_LEFT = "Left: "
TODAY_SUFFIXES = ("taxi", "card", "cash")

RU_NOTES = r"""
[notes]
left = 'Остаток|Осталось|L?eft'
left_word = "Остаток"
decimal = ","
skip = '''не\s+считать|не\s+считаем|не\s+учитывать|не\s+в\s+сч[её]т|do not count|don'?t count|not counted'''
previous = '(?:за\s+)?(?:прошлый|предыдущий)\s+месяц|previous month'
refers = 'относится\s+к|refers to'
months = [
  'январ[ьяюе]|january', 'феврал[ьяюе]|february', 'март[ауе]?|march',
  'апрел[ьяюе]|april', 'ма[йяюе]|may', 'июн[ьяюе]|june', 'июл[ьяюе]|july',
  'август[ауе]?|august', 'сентябр[ьяюе]|september', 'октябр[ьяюе]|october',
  'ноябр[ьяюе]|november', 'декабр[ьяюе]|december',
]
capitalise_months = false
occasion = '\s+'
refund = 'возврат|return|refund'
taxi = 'такси|taxi'
road = 'дорог[аиуе]'
homeward = 'домой|обратно|назад|to\s+home|back'
prepayment = 'аванс\w*|предоплат\w*|pre[-\s]?payment'
flowers = '\bцвет(?:ы|ок|очки|ов|очек)\b|\bроз(?:а|ы|у)\b'
food = 'продукт\w*|ед[аыу]'
and = '\bи\b'
thousands = '[kк]'
card = 'карт(?:а|ой|у|е|очка|очкой|очку)|по\s+карте|card'
card_ledger = '\bкарт(?:а|ой|у|е|очка|очкой|очку)\b|\bпо\s+карте\b|card'
gift = '(подар(?:ок|ки|ка|ку))\s+((?:для\s+)?\w+)'
tip = 'ча[её]в\w*|на\s+чай|tips?'
stop_words = ["или", "для", "без", "про", "над", "под", "его", "её", "наш", "мой", "моя",
              "мои", "свой", "один", "одна", "два", "две", "три", "это", "тоже", "ещё",
              "еще", "новый", "новая", "старый", "обратно", "назад"]
nested_taxi = "taxi"
nested_card = "card"
nested_cash = "cash"
ocr = "rus+eng"
"""

RU_EDITS = [
    ("food_words = [", "food_words = [\n  'пекарн', 'рын', 'бистро', 'обед', 'ужин', 'хлеб',"),
    ('label = "purse"', 'label = "кошелёк"'),
    ('label = "account"', 'label = "счёт"'),
]

RUSSIAN_DAYS = """\
10.01
+ 57 300
Остаток: кошелёк 6,8, счёт 61 240

11.01
135 пекарня картой
840 рынок (-120 возврат)
2600 утюг и 1к лампочки
+ 210 не считать, относится к декабрю
Остаток: кошелёк 3,5, счёт 61 105

12.01
{fare} дорога
190 такси до выставки
620 бистро обед
60 чаевые
230 такси домой
{fare} дорога
Осталось: кошелёк 2,4, счёт 61 105

13.01
+ 8 000 аванс
540 3 апреля ужин
eft: кошелёк 1,9, счёт 69 105

15.01
135 пекарня картой
100 хлеб
"""


def _without_notes(text: str) -> str:
    head, marker, table = text.partition("\n[notes]\n")
    assert marker and text.count("\n[notes]\n") == 1, "the example household changed shape"
    assert set(tomllib.loads("[notes]\n" + table)["notes"]) == {"road", "taxi"}, \
        "the example household's [notes] table changed shape"
    return head + "\n"


def _russian_rules(tmp_path: Path) -> Path:
    text = _without_notes(ENGLISH.read_text(encoding="utf-8"))
    for old, new in RU_EDITS:
        assert text.count(old) == 1, f"the example household changed shape: {old!r}"
        text = text.replace(old, new)
    path = tmp_path / "rules-ru.toml"
    path.write_text(text + RU_NOTES, encoding="utf-8")
    return path


def _english_without_notes(tmp_path: Path) -> Path:
    path = tmp_path / "rules-no-notes.toml"
    path.write_text(_without_notes(ENGLISH.read_text(encoding="utf-8")), encoding="utf-8")
    return path


_PRELUDE = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "INPUT = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))\n"
    "facts = {}\n"
)
_POSTLUDE = "\nprint(json.dumps(facts, ensure_ascii=True))\n"


def _engine(tmp_path: Path, rules: Path, body: str, **given) -> dict:
    run = Path(tempfile.mkdtemp(dir=tmp_path))
    (run / "input.json").write_text(json.dumps(given, ensure_ascii=False), encoding="utf-8")
    (run / "probe.py").write_text(_PRELUDE + textwrap.dedent(body) + _POSTLUDE, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in ("BUDGET_RULES", "PYTHONPATH")}
    env.update(BUDGET_RULES=str(rules), PYTHONPATH=str(APP), PYTHONDONTWRITEBYTECODE="1")
    done = subprocess.run(
        [sys.executable, "-B", str(run / "probe.py"), str(run / "input.json")],
        cwd=run, env=env, capture_output=True, timeout=120,
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    return json.loads(done.stdout.decode("ascii").strip().splitlines()[-1])


def test_no_notes_table_builds_todays_patterns(tmp_path) -> None:
    from budget import grammar

    assert len(TODAY) == 21
    built = grammar.build({})
    assert grammar.build(None) == built == grammar.build(dict(grammar.DEFAULTS))
    for name, module, alias, pattern in TODAY:
        mine = getattr(built, name)
        assert mine.pattern == pattern, f"{module}.{alias or name}"
        assert mine.flags == re.compile(pattern, re.IGNORECASE).flags, f"{module}.{alias or name}"
    assert built.stop_words == TODAY_STOP_WORDS
    assert f"{built.left_word}: " == TODAY_LEFT
    assert built.decimal == "."
    assert (built.nested_taxi, built.nested_card, built.nested_cash) == TODAY_SUFFIXES
    assert built.capitalise_months is True
    assert built.ocr == "eng"

    assert built.card_ledger is None
    for text in ("postcard", "Card 5", "cardigan", "карта", ""):
        assert built.on_card(text) == ("card" in text.lower()), text

    no_table = _english_without_notes(tmp_path)
    assert "notes" not in tomllib.loads(no_table.read_text(encoding="utf-8"))
    facts = _engine(tmp_path, no_table, """
        import importlib
        from decimal import Decimal
        for name, module, alias, pattern in INPUT["today"]:
            m = importlib.import_module("budget." + module)
            used = getattr(m.GRAMMAR, name)
            facts[module + "." + (alias or name)] = [
                used.pattern, used.flags, alias is None or getattr(m, alias) is used]
        from budget import classify, groups, left
        facts["stop words"] = sorted(classify._STOP_WORDS)
        facts["suffixes"] = [groups.GRAMMAR.nested_taxi, groups.GRAMMAR.nested_card,
                             groups.GRAMMAR.nested_cash]
        facts["assembled"] = left.assemble((Decimal("6.8"), Decimal("61240")),
                                           left.DEFAULT_SLOTS[:2])
    """, today=TODAY)
    for name, module, alias, pattern in TODAY:
        where = module + "." + (alias or name)
        assert facts[where] == [pattern, re.compile(pattern, re.IGNORECASE).flags, True], where
    assert facts["stop words"] == sorted(TODAY_STOP_WORDS)
    assert tuple(facts["suffixes"]) == TODAY_SUFFIXES
    assert facts["assembled"].startswith(TODAY_LEFT)
    assert "6.8" in facts["assembled"]


def test_the_english_table_moves_only_the_fare_words(tmp_path) -> None:
    table = tomllib.loads(ENGLISH.read_text(encoding="utf-8"))["notes"]
    assert set(table) == {"taxi", "road"}
    for phrase in table.values():
        assert re.fullmatch(r"[a-z]+(?: [a-z]+)+", phrase), phrase
    facts = _engine(tmp_path, ENGLISH, """
        import importlib
        for name, module, alias, pattern in INPUT["today"]:
            m = importlib.import_module("budget." + module)
            used = getattr(m.GRAMMAR, name)
            facts[module + "." + (alias or name)] = [used.pattern, used.flags]
        from budget import classify, groups, left
        facts["stop words"] = sorted(classify._STOP_WORDS)
        facts["suffixes"] = [groups.GRAMMAR.nested_taxi, groups.GRAMMAR.nested_card,
                             groups.GRAMMAR.nested_cash]
        facts["left word"] = left.GRAMMAR.left_word
        facts["decimal"] = left.GRAMMAR.decimal
    """, today=TODAY)
    moved = set()
    for name, module, alias, pattern in TODAY:
        where = module + "." + (alias or name)
        if "taxi" in pattern or "road" in pattern:
            moved.add(where)
        expected = pattern.replace("taxi", table["taxi"]).replace("road", table["road"])
        assert facts[where] == [expected, re.compile(pattern, re.IGNORECASE).flags], where
    assert moved == {"classify._FARE", "classify._ROAD", "classify._HOMEWARD",
                     "classify._UNPLACED_FARE", "classify._NAMED_FARE",
                     "display._FARE_TEXT", "groups.fare_word"}
    assert facts["stop words"] == sorted(TODAY_STOP_WORDS)
    assert tuple(facts["suffixes"]) == TODAY_SUFFIXES
    assert f"{facts['left word']}: " == TODAY_LEFT
    assert facts["decimal"] == "."


def test_a_russian_table_reads_a_russian_day(tmp_path) -> None:
    rules = _russian_rules(tmp_path)
    data = tomllib.loads(rules.read_text(encoding="utf-8"))
    food, trip, roles = data["classify"]["food"], data["classify"]["trip"], data["groups"]["roles"]
    nested = "Errands"
    notes = RUSSIAN_DAYS.format(fare=trip["fare"])

    facts = _engine(tmp_path, rules, """
        from budget.notes import parse
        from budget.classify import classify_period
        from budget.display import _FARE_TEXT, closing_left
        from budget.groups import BASE
        from budget.left import DEFAULT_SLOTS

        period = parse(INPUT["notes"])[0]
        facts["balances"] = {
            d.date: None if d.balances is None else [str(v) for v in d.balances.values]
            for d in period.days}
        facts["unparsed"] = period.unparsed
        facts["lines"] = [[c.entry.raw, c.entry.amount, c.entry.text, c.minor, c.rule]
                          for c in classify_period(period)]
        facts["refers to"] = [e.refers_to for e in period.entries if e.deferred]
        left = closing_left(period, 2026, DEFAULT_SLOTS)
        facts["recount"] = left["computed"]["text"] if "computed" in left else None
        # A nested major whose lines are the medium the money moved by. The
        # household's own nested major (the crossings) has named lines, so an
        # invented one is added beside it, its lines by the table's suffixes.
        from budget.groups import GRAMMAR, Major, Taxonomy, Tier
        name = INPUT["nested"]
        lines = [GRAMMAR.nested_taxi, GRAMMAR.nested_card, GRAMMAR.nested_cash]
        errands = Major(name, Tier.NECESSARY, tuple(f"{name} {s}" for s in lines))
        taxonomy = Taxonomy(BASE.majors + (errands,), BASE.limit_order, BASE.minor_order,
                            dict(BASE.nested, **{name: tuple((s, f"{name} {s}") for s in lines)}),
                            {}, {})
        facts["resolved"] = [taxonomy.resolve_group(name, t)[0] for t in INPUT["typed"]]
        facts["fare words"] = [bool(_FARE_TEXT.search(t)) for t in INPUT["fares"]]
    """, notes=notes, nested=nested,
        typed=["такси домой", "пекарня картой", "рынок", "taxi back", "bakery card"],
        fares=["такси до врача", "дорога", "таксист", "taxi", "дорожка"])

    assert facts["unparsed"] == []
    assert facts["balances"] == {
        "10.01": ["6.8", "61240"],
        "11.01": ["3.5", "61105"],
        "12.01": ["2.4", "61105"],
        "13.01": ["1.9", "69105"],
        "15.01": None,
    }

    def placed(raw: str) -> list:
        found = [line[1:] for line in facts["lines"] if line[0] == raw]
        assert found, raw
        return found

    assert [x[:3] for x in placed("135 пекарня картой")] == [[135, "пекарня картой", food["card"]]] * 2
    assert placed("840 рынок (-120 возврат)")[0][:3] == [720, "рынок (-120 возврат)", food["cash"]]
    split = placed("2600 утюг и 1к лампочки")
    assert [(amount, text) for amount, text, *_ in split] == [(1600, "утюг"), (1000, "лампочки")]
    assert facts["refers to"] == ["December"]
    assert placed("+ 210 не считать, относится к декабрю")[0][2:] == [
        roles["elsewhere"], "belongs to December"]
    assert {tuple(x[2:]) for x in placed(f"{trip['fare']} дорога")} == {
        (trip["road"], f"context:{_major_of(data, trip['road'])}")}
    assert placed("190 такси до выставки")[0][2] == trip["taxi"]
    assert placed("230 такси домой")[0][2] == trip["road"]
    bill = placed("620 бистро обед")[0][2]
    assert placed("60 чаевые")[0][2:] == [bill, "a tip on what came before it"]
    assert placed("+ 8 000 аванс")[0][2:] == [roles["salary"], "prepayment is salary"]
    assert placed("540 3 апреля ужин")[0][2:] == ["3 апреля", "an occasion, named first"]

    assert facts["recount"] == "Остаток: кошелёк 1,8, счёт 68970"

    assert facts["resolved"] == [f"{nested} taxi", f"{nested} card", f"{nested} cash",
                                 f"{nested} taxi", f"{nested} card"]
    assert facts["fare words"] == [True, True, False, True, False]


def _major_of(data: dict, minor: str) -> str:
    return next(m["name"] for m in data["groups"]["majors"] if minor in m.get("minors", []))


def test_refers_to_names_the_english_month_key(tmp_path) -> None:
    probe = """
        from budget.notes import Entry, month_of, parse, reassign_deferred
        facts["named"] = [Entry.read(line).refers_to for line in INPUT["lines"]]
        periods = reassign_deferred(parse(INPUT["months"]))
        facts["moved"] = {month_of(p): [[e.amount, e.income, e.text, e.deferred]
                                        for e in p.entries] for p in periods}
    """
    english = _engine(tmp_path, ENGLISH, probe, lines=[
        "+ 1900 don't count, refers to October",
        "+ 1700 not counted, refers to january (paid late)",
        "+ 1200 not counted, refers to DECEMBER",
        "+ 1300 not counted, previous month",
        "+ 640 dont count, refers to aprıl",
    ], months="03.12\n+ 57 300\n1200 honey\n#####\n03.01\n+ 57 300\n"
              "+ 1200 not counted, refers to december\n")
    assert english["named"] == ["October", "January", "December", None, "Aprıl"]
    assert [1200, True, "", False] in english["moved"]["December"]
    assert all(e[0] != 1200 or not e[1] for e in english["moved"]["January"])

    russian = _engine(tmp_path, _russian_rules(tmp_path), probe, lines=[
        "+ 1200 не считать, относится к декабрю",
        "+ 1200 не считать, относится к маю",
        "+ 1200 не считать, относится к октябрю",
        "+ 1200 НЕ СЧИТАТЬ, ОТНОСИТСЯ К ЯНВАРЮ",
        "+ 1200 не считать, прошлый месяц",
        "+ 1900 don't count, refers to October",
    ], months="03.12\n+ 57 300\n1200 пекарня\n#####\n03.01\n+ 57 300\n"
              "+ 1200 не считать, относится к декабрю\n")
    assert russian["named"] == ["December", "May", "October", "January", None, "October"]
    assert [1200, True, "", False] in russian["moved"]["December"]
    assert all(e[0] != 1200 or not e[1] for e in russian["moved"]["January"])


def test_notes_table_validation_names_the_key(tmp_path) -> None:
    from budget.rules import RulesError, load, validate

    base = tomllib.loads(ENGLISH.read_text(encoding="utf-8"))
    russian = tomllib.loads(RU_NOTES)["notes"]
    validate(copy.deepcopy(dict(base, notes=russian)), "test")

    eleven = russian["months"][:11]
    for table, key in [
        ({"frobnicate": "x"}, "frobnicate"),
        ({"taxi": "такси("}, "notes.taxi"),
        ({"taxi": "a)("}, "notes.taxi"),
        ({"months": eleven}, "notes.months"),
        ({"left": "Остаток", "left_word": "Итого"}, "notes.left_word"),
        ({"skip": "не\bсчитать"}, "notes.skip"),
        ({"decimal": ";"}, "notes.decimal"),
        ({"capitalise_months": "no"}, "notes.capitalise_months"),
        ({"ocr": "rus eng"}, "notes.ocr"),
        ({"refers": r"(относится)\s+к"}, "notes.refers"),
        ({"gift": r"(подарок)\s+\w+"}, "notes.gift"),
        ({"and": r"(?P<amount>и)"}, "notes.and"),
        ({"stop_words": "или"}, "notes.stop_words"),
        ({"nested_cash": " "}, "notes.nested_cash"),
        ("Остаток", "notes"),
    ]:
        with pytest.raises(RulesError) as refused:
            validate(copy.deepcopy(dict(base, notes=table)), "test")
        assert key in str(refused.value), (table, str(refused.value))

    path = tmp_path / "quoted.toml"
    path.write_text(_without_notes(ENGLISH.read_text(encoding="utf-8"))
                    + '\n[notes]\nskip = "не\\bсчитать"\n', encoding="utf-8")
    with pytest.raises(RulesError, match=r"notes\.skip: .*control character"):
        load(path)
    assert load(_russian_rules(tmp_path))["notes"]["left_word"] == "Остаток"


def test_the_left_line_round_trips(tmp_path) -> None:
    probe = """
        from budget.notes import parse
        from budget.left import DEFAULT_SLOTS, assemble
        for line in INPUT["lines"]:
            b = parse("03.01\\n" + line + "\\n")[0].days[0].balances
            facts[line] = assemble(b.values, DEFAULT_SLOTS, b.fields)
    """
    russian = [
        "Остаток: кошелёк 6,8, счёт 61240",
        "Остаток: кошелёк -0,5, счёт 1061240",
    ]
    facts = _engine(tmp_path, _russian_rules(tmp_path), probe, lines=russian)
    assert facts == {line: line for line in russian}

    english = [
        "Left: purse 6.8, account 61240",
        "Left: purse -0.5, account 1061240",
    ]
    facts = _engine(tmp_path, ENGLISH, probe, lines=english)
    assert facts == {line: line for line in english}


def test_a_no_break_space_between_thousands_is_read(tmp_path) -> None:
    facts = _engine(tmp_path, ENGLISH, """
        import tempfile
        from budget.api import dispatch
        from budget.notes import parse
        from budget.store import Store
        facts["amounts"] = [[e.amount, e.income] for e in parse(INPUT["notes"])[0].entries]
        with tempfile.TemporaryDirectory() as folder:
            reply = dispatch(Store(Path(folder) / "store.json"),
                             {"action": "import", "text": INPUT["notes"], "year": 2026})
        facts["imported"] = reply["ok"]
    """, notes="03.05\n+ 57 300\n2 600 ceramics workshop\n"
               "1 450 honey\n3 300 power\n")
    assert facts["amounts"] == [[57300, True], [2600, False], [1450, False], [3300, False]]
    assert facts["imported"] is True


def _tokens(pattern: str) -> set[str]:
    stripped = re.sub(r"\(\?P<\w+>", "(", pattern)
    stripped = re.sub(r"\\[A-Za-z]", " ", stripped)
    return {t.lower() for t in re.findall(r"[A-Za-z']{2,}", stripped)}


def _constant(node) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _constant(node.left), _constant(node.right)
        return None if left is None or right is None else left + right
    return None


def test_no_control_word_is_left_in_the_modules() -> None:
    from budget import grammar

    control: set[str] = set()
    for key, value in grammar.DEFAULTS.items():
        if key in ("stop_words", "decimal", "capitalise_months", "ocr") or value is None:
            continue
        for item in value if isinstance(value, tuple) else (value,):
            control |= _tokens(item)
    months = set(grammar.DEFAULTS["months"])
    assert {"taxi", "road", "card", "cash", "refund", "tips", "left", "january"} <= control

    found = []
    modules = sorted(p for p in ENGINE.glob("*.py") if p.name != "grammar.py")
    assert len(modules) >= 12
    for path in modules:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docs = {id(n.value) for n in ast.walk(tree)
                if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
        for node in ast.walk(tree):
            where = f"{path.name}:{getattr(node, 'lineno', '?')}"
            if isinstance(node, ast.Call) and node.args and (
                (isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                 and node.func.value.id == "re")
                or (isinstance(node.func, ast.Name) and node.func.id == "_rx")
            ):
                pattern = _constant(node.args[0])
                if pattern is not None and _tokens(pattern) & control:
                    found.append(f"{where} pattern {pattern!r}")
            if isinstance(node, ast.Compare) and any(
                isinstance(op, (ast.In, ast.NotIn)) for op in node.ops
            ) and any(
                isinstance(n, ast.Attribute) and n.attr in ("text", "raw", "lower", "casefold")
                for side in node.comparators for n in ast.walk(side)
            ):
                word = _constant(node.left)
                if word is not None and word.lower() in control:
                    found.append(f"{where} {word!r} in ...")
            if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and id(node) not in docs:
                if re.match(r"\s*L?eft:", node.value, re.IGNORECASE):
                    found.append(f"{where} {node.value!r}")
                if path.name == "groups.py" and node.value in TODAY_SUFFIXES:
                    found.append(f"{where} {node.value!r}")
            if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
                words = {_constant(e) for e in node.elts} - {None}
                if len(words & TODAY_STOP_WORDS) >= 3 or len(words & months) >= 3:
                    found.append(f"{where} a word list")
    assert found == []
