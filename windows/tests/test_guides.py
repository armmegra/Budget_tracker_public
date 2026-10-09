from __future__ import annotations

import ast
import html
import importlib.util
import json
import re
from pathlib import Path

import pytest

LOCAL = Path(__file__).resolve().parent.parent
GUIDES = {"en": LOCAL / "GUIDE.md", "ru": LOCAL / "GUIDE.ru.md"}
PAGE = LOCAL / "web" / "index.html"
SPEECH = LOCAL / "app" / "budget" / "speech.py"
CLASSIFY = LOCAL / "app" / "budget" / "classify.py"

ENGINE = (
    "ни одно правило не подошло",
    "алкоголь — это «Еда» или отдельный праздник?",
    "группу «Еда» удалили — куда это отнести?",
    "в строке названы Медицина и Еда — что именно это было?",
    "«обеденный» — это не «еде»: к какой группе это отнести?",
)

PROSE = frozenset({
    "единственная идея, которую стоит понять как следует",
    "Суммы показываются в тысячах.",
    "Групп немного, и это нарочно.",
    "Выбирайте ответы, которые не изменятся.",
    "Выбирайте ответы, которые не придётся восстанавливать.",
    "Слово или число, которое придёт в голову только вам, — вполне хороший «вопрос».",
    "Заглавные буквы и лишние пробелы не важны.",
    "Верными должны быть все ответы",
    "После пяти неверных попыток вопросы не задаются четверть часа.",
    "Ваши записи здесь ни при чём.",
    "http://127.0.0.1:8765/security",
    "Пропадёт только вход и больше ничего",
    "плюс",
    "Это важно.",
    "Пробелы в числах не мешают.",
    "Пустая строка разделяет поездки.",
    "Если не трудно, пишите, что это был за проезд.",
    "Месяц начинается с зарплаты и заканчивается строкой из `#`.",
    "закрытию",
    "«— новый месяц —» или месяц по названию.",
    "Вставлять повторно безопасно.",
    "не считать, относится к",
    "даже если декабря в приложении ещё нет",
    "Тетр",
    "Театр",
    "Название группы — не слово.",
    "дорога",
    "Группа, которую вы удалили.",
    "Строка, в которой названы две группы.",
    "Слово внутри другого слова.",
    "Ответы запоминаются для каждого месяца и каждой строки отдельно.",
    "вино → Праздники",
    "Сначала приложение спрашивает, к каким месяцам это относится",
    "То, что вы ответили или перенесли вручную, всё равно важнее.",
    "Если к строке подходят два слова, решает более длинное.",
    "Слово, а не кусок слова.",
    "Полосы",
    "Зелёный",
    "Жёлтый",
    "Красный",
    "Синий",
    "Два итога",
    "Список подгрупп",
    "всё, собранное по группам",
    "в два этажа",
    "Подгруппа",
    "Основная группа",
    "Зачем два этажа?",
    "одно",
    "«Аренда» — единственная группа, не похожая на другие.",
    "к каким месяцам применить изменения",
    "Названия — это подписи, а под ними постоянные идентификаторы.",
    "Ничто из этого не обязано быть вашим.",
    "уровень",
    "первый итог",
    "исключённая",
    "после",
    "Зачем два?",
    "Для чего «исключённая».",
    "Лимит никогда не спрашивает, к каким месяцам он относится.",
    "Лимиты необязательны.",
    "Правильного числа нет, и ограничивает вас не приложение.",
    "бывает ли это каждый месяц, как часть обычной жизни?",
    "захочу ли я когда-нибудь видеть это по отдельности?",
    "в очередь",
    "сколько я потратил",
    "сколько у меня есть прямо сейчас",
    "вид",
    "наличные",
    "счёт",
    "Ваше решение всегда важнее.",
    "Старые месяцы закрываются сами.",
    "открывается там, где вы остановились",
    "Что переключается:",
    "Что не переключается никогда:",
    "Группы меняются только в нетронутом приложении.",
    "У записей свои слова.",
    "До входа",
    "Язык сохраняется в файле.",
    "Сумма не в той группе.",
    "Итог сдвинулся на 0.1 без причины.",
    "Месяц пропал.",
    "День появился дважды.",
    "Всё превратилось в вопросы.",
    "Страница говорит, что месяц закрыт.",
    "Вы забыли пароль.",
})

_TAG = re.compile(r"<[^>]+>")
_SLOT = re.compile(r"\{(\w+)((?:\|[^{}|]*)*)\}")
_HEADING = re.compile(r"^(#{1,4}) (.+?)\s*$")
_ENGINE_SPAN = re.compile(r"`[^`]+` — «(.+)»\.?")


def _plain(text: str) -> str:
    return " ".join(html.unescape(_TAG.sub("", text)).split())


def _straight(quote: str) -> str:
    return quote.replace("„", "«").replace("“", "»")


def _spans(text: str) -> list[str]:
    import guide

    body = guide._blocks(text)
    return [
        _plain(re.sub(r"<code>(.*?)</code>", lambda m: f"`{m.group(1)}`", inner, flags=re.S))
        for kind in ("strong", "em")
        for inner in re.findall(rf"<{kind}>(.*?)</{kind}>", body, re.S)
    ]


def _headings(text: str) -> list[tuple[int, str]]:
    found, fenced = [], False
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and (m := _HEADING.match(line)):
            found.append((number, m.group(2)))
    return found


def _t_ru() -> dict[str, str]:
    page = PAGE.read_text(encoding="utf-8")
    start = page.index("const T = { ru: {")
    block = page[start:page.index("\n} };", start)]
    return {key: json.loads(f'"{value}"') for key, value in re.findall(
        r'^\s*"([^"\n]+)":\s*"((?:[^"\\\n]|\\.)*)",?\s*(?://.*)?$', block, re.M)}


def _catalogue() -> list[str]:
    import guide
    import pages

    t_ru = _t_ru()
    assert len(t_ru) > 250, f"only {len(t_ru)} entries read from the page's T.ru"
    switch = " · ".join(pages.NAMES[code] for code in pages.LANGS)
    return [*t_ru.values(), *pages.RU.values(), *guide._NAV["ru"], *pages.NAMES.values(), switch]


def _pieces(text: str) -> set[str]:
    whole = _plain(text)
    found = {whole}
    found.update(_plain(m.group(2)) for m in re.finditer(
        r"<(a|b|strong|code)\b[^>]*>(.*?)</\1>", text, re.S))
    found.update(m.group(1) for m in re.finditer(r"«([^«»]+)»", whole))
    return {piece for piece in found if piece}


def _template(text: str) -> re.Pattern[str] | None:
    whole = _plain(text)
    if not _SLOT.search(whole):
        return None
    pattern, at = "", 0
    for m in _SLOT.finditer(whole):
        pattern += re.escape(whole[at:m.start()])
        forms = m.group(2)[1:].split("|") if m.group(2) else None
        pattern += "(?:" + "|".join(map(re.escape, forms)) + ")" if forms else ".+?"
        at = m.end()
    return re.compile(pattern + re.escape(whole[at:]), re.IGNORECASE)


def _speech():
    spec = importlib.util.spec_from_file_location("_guides_speech", SPEECH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _question_codes() -> set[str]:
    tree = ast.parse(CLASSIFY.read_text(encoding="utf-8"))
    return {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and node.args
        and (getattr(node.func, "attr", None) == "ask" or getattr(node.func, "id", None) == "ask")
        and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
    }


@pytest.mark.parametrize("part", ["labels", "engine questions"])
def test_every_bold_label_in_the_russian_guide_exists(part: str) -> None:
    text = GUIDES["ru"].read_text(encoding="utf-8")
    spans = _spans(text)
    flat = " ".join(text.split())

    if part == "engine questions":
        quoted = [q for q in ENGINE if f"«{q.replace('«', '„').replace('»', '“')}»" not in flat]
        assert quoted == [], f"ENGINE lists questions the guide does not quote: {quoted}"
        codes = _question_codes()
        if not codes:
            pytest.skip("classify.py asks no question with a code yet, so speech.py holds no "
                        "Russian question to hold the guide's quotes to (speech-engine)")
        said = _speech().RU
        asked = [pattern for code in sorted(codes) if code in said
                 if (pattern := _template(said[code]) or re.compile(re.escape(said[code])))]
        unsaid = [q for q in ENGINE if not any(p.fullmatch(q) for p in asked)]
        assert unsaid == [], (
            f"the guide quotes questions the engine does not ask in these words: {unsaid}")
        return

    texts = _catalogue()
    labels = {piece.casefold() for t in texts for piece in _pieces(t)}
    templates = [p for t in texts if (p := _template(t)) is not None]
    sections = {words for _, words in _headings(text)}

    unknown = []
    for span in dict.fromkeys(spans):
        bare = span[1:-1] if span[:1] == "«" and span[-1:] == "»" and span.count("«") == 1 else span
        engine = _ENGINE_SPAN.fullmatch(span)
        if span in PROSE or span in sections or not re.search(r"[^\W\d_]", span):
            continue
        if engine or _straight(bare) in ENGINE:
            quote = _straight(engine.group(1) if engine else bare)
            if quote not in ENGINE:
                unknown.append(f"{span}  (an engine question missing from ENGINE)")
            continue
        if bare.casefold() in labels or any(p.fullmatch(bare) for p in templates):
            continue
        unknown.append(span)
    assert unknown == [], (
        "bold or italic spans of GUIDE.ru.md that no catalogue says and PROSE does not "
        f"list: {unknown}")

    stale = sorted(PROSE - set(spans))
    assert stale == [], f"PROSE lists spans GUIDE.ru.md no longer has: {stale}"


@pytest.mark.parametrize("lang", ["en", "ru"])
def test_every_anchor_resolves(lang: str) -> None:
    import guide

    text = GUIDES[lang].read_text(encoding="utf-8")
    ids: dict[str, int] = {}
    for number, words in _headings(text):
        slug = guide._slug(words)
        assert slug not in ids, f"#{slug}: lines {ids[slug]} and {number}"
        ids[slug] = number
    links = [(n, target) for n, line in enumerate(text.splitlines(), 1)
             for target in re.findall(r"\]\(#([^)\s]+)\)", line)]
    assert len(links) > 15
    assert [(n, target) for n, target in links if target not in ids] == []
    others = {target for line in text.splitlines()
              for target in re.findall(r"\]\(([^)#\s]+\.md)(?:#[^)\s]*)?\)", line)}
    assert others and others <= set(guide._CROSS), sorted(others - set(guide._CROSS))


def test_the_russian_guide_is_served_in_russian() -> None:
    import guide

    page = guide.render("guide", "ru")
    english = guide.render("guide", "en")
    assert page is not None and english is not None
    assert '<html lang="ru">' in page and '<div lang="en">' not in page
    assert '<h1 id="учёт-бюджета-справка">Учёт бюджета — справка</h1>' in page
    assert "<title>Учёт бюджета — справка</title>" in page
    assert ">Справка</a>" in page and ">Вернуться в приложение</a>" in page
    assert 'href="/readme"' in page
    assert 'src="guide/month.ru.png"' in page
    for tag in ("<h1", "<h2", "<h4", "<img"):
        assert page.count(tag) == english.count(tag), tag
    assert page.count("<h3") == english.count("<h3") + 1
    assert page.count("<table>") == english.count("<table>") + 1


def test_every_picture_is_referenced_and_exists() -> None:
    import guide

    named = {lang: re.findall(r"\bguide/([\w.-]+\.png)\b", path.read_text(encoding="utf-8"))
             for lang, path in GUIDES.items()}
    assert named["en"] and len(named["ru"]) == len(named["en"])
    assert [name for name in named["en"] if name.endswith(".ru.png")] == []
    assert [name for name in named["ru"] if not name.endswith(".ru.png")] == []
    assert (sorted(name[:-len(".png")] for name in named["en"])
            == sorted(name[:-len(".ru.png")] for name in named["ru"]))
    shown = set(named["en"]) | set(named["ru"])
    assert sorted(name for name in shown if guide.picture(name) is None) == []
    assert sorted({p.name for p in (LOCAL / "guide").glob("*.png")} - shown) == []
