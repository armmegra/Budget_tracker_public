"""What the engine says in languages other than English: Russian templates keyed
by code, with plurals, filled from the same values as the English sentence.
"""

from __future__ import annotations

import re

LANGS = ("en", "ru")
NAMES = {"en": "English", "ru": "Русский"}


def pick(code) -> str:
    return code if isinstance(code, str) and code in LANGS else "en"


class Month(str):
    __slots__ = ()


class And(tuple):
    __slots__ = ()


class Said(ValueError):
    def __init__(self, english: str, code: str | None = None, **values) -> None:
        super().__init__(english)
        self.code = code
        self.values = values


class Question(str):
    def __new__(cls, english: str, code: str | None = None, **values) -> Question:
        self = super().__new__(cls, english)
        self.code = code
        self.values = values
        return self


def ask(code: str, english: str, **values) -> Question:
    return Question(english, code, **values)


LEAD_IN = {"ru": "Не удалось: "}

MONTHS = {
    "ru": {
        "January": "Январь", "February": "Февраль", "March": "Март",
        "April": "Апрель", "May": "Май", "June": "Июнь",
        "July": "Июль", "August": "Август", "September": "Сентябрь",
        "October": "Октябрь", "November": "Ноябрь", "December": "Декабрь",
    },
}
UNDATED = {"ru": "без даты"}

AND = {"ru": " и "}

RU = {
    "closed": (
        "{label} закрыт: месяц закрывается через {freeze} "
        "{freeze|месяц|месяца|месяцев} после окончания, а этот закрылся {age} "
        "{age|месяц|месяца|месяцев} назад. Чтобы всё же исправить его, сначала "
        "откройте его."
    ),
    "paste_closed": (
        "эта вставка перезаписала бы "
        "{n|закрытый месяц|закрытые месяцы|закрытые месяцы}: {months}. "
        "Сначала {n|откройте его|откройте их|откройте их}."
    ),
    "configure_closed": (
        "изменение для всех месяцев затронуло бы и {n} "
        "{n|закрытый месяц|закрытых месяца|закрытых месяцев}. Примените его к "
        "одному месяцу и последующим или сначала откройте закрытые месяцы."
    ),
    "no_period": "месяц «{name}» не найден",
    "no_period_stored": "месяц «{name}» не найден; сохранены: {spans}",
    "no_period_nothing_stored": "месяц «{name}» не найден: сохранённых месяцев пока нет",
    "no_period_refresh": "месяц «{target}» не найден — обновите страницу",
    "several_months": "под «{name}» подходит больше одного месяца — выберите один: {labels}",
    "no_complete_period": (
        "не найдено ни одного полного месяца: в записях нужна строка с "
        "зарплатой, или выберите месяц, в который их добавить"
    ),
    "no_open_question": "открытого вопроса №{number} нет — обновите страницу",
    "several_lines": "группа «{group}» записана несколькими строками — выберите одну: {choices}",
    "answer_new_group": (
        "группы «{group}» нет{hint} — чтобы завести новую, введите её название "
        "через «Другое…»"
    ),
    "suggests": " — вопрос предлагает: {candidates}",
    "move_new_group": (
        "группы «{group}» нет — чтобы завести новую, введите её название через "
        "«Другое…»"
    ),
    "teach_new_group": "группы «{group}» нет — сначала создайте её",
    "no_year_stored": "ни у одного сохранённого месяца нет года {wanted}",
    "not_groups_here": "в этом месяце нет таких групп: {unknown}",
    "not_group_here": "в этом месяце нет группы «{group}»",
    "backup_no_rules": (
        "не удалось прочитать файл правил, поэтому резервная копия не сделана: {why}"
    ),
    "backup_newer": (
        "эта резервная копия сделана более новой версией приложения (версия "
        "{version}, а эта читает версии до {max})"
    ),
    "reset_no_year": (
        "у месяца {month} не записан год — сначала задайте год, иначе нельзя "
        "понять, какие месяцы затронет сброс"
    ),
    "edit_no_year": (
        "у месяца {month} не записан год — сначала задайте год, иначе нельзя "
        "понять, какие месяцы затронет изменение"
    ),
    "needs_field": "не заполнено поле ({field})",
    "name_taken": "группа «{name}» уже есть",
    "limit_thousands": (
        "лимит задаётся в тысячах: целое положительное число, или пусто, чтобы "
        "его убрать"
    ),
    "most_majors": "не больше {n} основных групп",
    "most_limits": "не больше {n} лимитов",
    "most_minors": "не больше {n} подгрупп",
    "most_words": "не больше {n} выученных слов",
    "most_figures": "в строке остатка может быть не больше {n} сумм",
    "no_major": "нет основной группы «{name}»",
    "no_major_add_first": "нет основной группы «{target}» — сначала добавьте её",
    "no_minor": "нет подгруппы «{name}»",
    "minors_still_route": (
        "в группу «{name}» ещё {n|входит|входят|входят} {n} "
        "{n|подгруппа|подгруппы|подгрупп} — сначала перенесите {n|её|их|их}"
    ),
    "last_major": (
        "«{name}» — последняя группа, куда могут идти расходы: одна группа остаётся всегда"
    ),
    "minors_to_itself": "подгруппы группы «{name}» нужно перенести в другую группу",
    "uncounted_route": (
        "группа «{name}» не входит ни в один итог — в группе «{target}» деньги её "
        "подгрупп начали бы учитываться"
    ),
    "income_only": (
        "подгруппа «{minor}» — это доход: её можно перенести только в группу доходов"
    ),
    "excluded_route": (
        "группа «{target}» не входит ни в один итог — если перенести туда "
        "«{minor}», её деньги молча перестанут учитываться"
    ),
    "excluded_no_limit": (
        "группа «{name}» не входит ни в один итог — лимит к ней не применяется"
    ),
    "no_limit": "у группы «{name}» нет лимита",
    "no_limit_to_move": "у группы «{source}» нет лимита, который можно перенести",
    "has_limit": "у группы «{target}» уже есть лимит",
    "word_short": "слово для обучения — не короче трёх символов и хотя бы с одной буквой",
    "word_is_line": (
        "это строка, а не слово — научите приложение слову, которое называет саму вещь"
    ),
    "word_not_taught": "слова «{word}» нет среди выученных",
    "no_slot": "в строке остатка нет суммы «{wanted}»",
    "backup_left": "в резервной копии суммы строки остатка должны быть числами",
    "left_needs_figure": "в строке остатка должна быть хотя бы одна сумма",
    "does_not_compose": "это изменение несовместимо с остальными: {why}",
    "image_too_large": "изображение слишком большое — нужно меньше примерно 5 МБ",
    "ocr_failed": "не удалось распознать этот скриншот: {why}{hint}",
    "no_entry": "в месяце {span} нет строки «{raw}» (вхождение {occurrence})",
    "backup_not_object": "резервная копия — не объект JSON",
    "backup_not_dict": "в резервной копии поле '{name}' — не объект JSON",
    "backup_not_list": "в резервной копии поле '{name}' — не список",
    "backup_periods": (
        "в резервной копии поле 'periods' должно быть текстом с "
        "ключами-идентификаторами месяцев"
    ),
    "backup_years": "в резервной копии поле 'years' должно содержать целые календарные годы",
    "backup_omitted": (
        "в резервной копии поле 'omitted' должно содержать списки названий групп"
    ),
    "backup_moves": (
        "в резервной копии поле 'moves' должно содержать названия групп с такими "
        "же ключами, как у ответов"
    ),
    "backup_adjusted": "в резервной копии поле 'adjusted' должно содержать суммы по группам",
    "no_dated_day": (
        "во вставке нет ни одного дня с датой (дд.мм): в уже сохранённый месяц "
        "добавляйте дни — начальные строки у него уже есть"
    ),
    "no_salary_line": (
        "в этих записях нет строки с зарплатой, поэтому они не могут начать "
        "новый месяц, — а {name} уже сохранён. Вместо этого выберите {name} в "
        "списке «Добавить в»."
    ),
    "left_no_id": "у каждой суммы должен быть идентификатор",
    "left_same_id": "у двух сумм один и тот же идентификатор {id}",
    "left_kind": "вид должен быть одним из: {kinds}",
    "left_comma": "подпись не может содержать запятую",
    "left_one_card": "только одна сумма может быть остатком на карте",
    "left_one_cash": "только одна сумма может быть наличными на руках",
    "purse_weekday": "кошелёк пополняется в день недели от 0 (понедельник) до 6",
    "purse_amount": "у кошелька должна быть сумма больше нуля",
    "unlabelled_income": "доход без подписи",
    "fare_unnamed": "проезд без подписи — куда была эта поездка?",
    "bare_amount": "сумма без подписи, которую не к чему отнести",
    "fare_unplaced": "проезд, который не к чему отнести",
    "fare_for": "проезд с пометкой «{what}» — к какой группе его отнести?",
    "partner_unsaid": "{partner}: деньги без пояснения, за что. Это «{settled}»?",
    "partner_money": "{partner}: деньги — это «{settled}» или они возмещают что-то другое?",
    "partner_settling": (
        "{partner}: расчёт за покупку — «{settled}», если только это не что-то другое"
    ),
    "inside_word": "«{inside}» — это не «{matched}»: к какой группе это отнести?",
    "alcohol": "алкоголь — это «{food}» или отдельный праздник?",
    "names_several": "в строке названы {names} — что именно это было?",
    "no_rule": "ни одно правило не подошло",
    "gift_group": "{name} — завести для этого разовую группу?",
    "gift_trip": "эта поездка была ради «{name}» или это обычный проезд?",
    "outing_group": "{name} — завести разовую группу и отнести к ней всю эту поездку?",
    "tip_alone": "чаевые, но перед ними нет строки, за что они",
    "food_trip_fare": (
        "проезд в поездке, где покупали не только продукты, — она была ради продуктов?"
    ),
    "total": "Итого",
    "total_occasional": "Итого + разовые",
    "delta": "разница",
    "average_of": "Среднее за {n} {n|месяц|месяца|месяцев}",
    "average_of_year": "Среднее за {n} {n|месяц|месяца|месяцев} {year} года",
    "over_by": "перерасход {x}",
    "under_by": "осталось {x}",
    "major_groups_heading": "ОСНОВНЫЕ ГРУППЫ (тыс.)",
    "total_line": "Итого: {x}",
    "total_line_occasional": "Итого: {x} + {tail}: {grand}",
    "minor_groups_heading": "{title} — подгруппы",
    "page_of": "{title} — стр. {i} из {n}",
    "comparison": "Сравнение",
    "comparison_of_year": "Сравнение — {n} {n|месяц|месяца|месяцев} {year} года",
    "comparison_range": "Сравнение: {first} — {last}",
    "outcome.imported": "добавлено",
    "outcome.replaced": "заменено",
    "outcome.kept": "оставлена более полная копия",
    "outcome.kept_carry": "оставлена более полная копия (начало следующего месяца)",
    "outcome.skipped": "пропущено: нет дней с датой",
    "every_later_month": "и все последующие месяцы",
}

CATALOGUES = {"ru": RU}

_SLOT = re.compile(r"\{(\w+)(?:\|([^{}]*))?\}")


def month_label(label, lang: str) -> str:
    text = str(label)
    months = MONTHS.get(lang) if isinstance(lang, str) else None
    if months is None:
        return text
    if text == "undated":
        return UNDATED[lang]
    name, space, year = text.partition(" ")
    said = UNDATED[lang] if name == "undated" else months.get(name)
    if said is None or (space and not year.isdigit()):
        return text
    return said + space + year


def _count(n) -> int | None:
    if isinstance(n, bool) or not isinstance(n, (int, float)):
        n = float(n)
    if isinstance(n, float):
        if not n.is_integer():
            return None
        n = int(n)
    return abs(n)


def plural(n, one: str, few: str, many: str) -> str:
    k = _count(n)
    if k is None:
        return many
    if k % 10 == 1 and k % 100 != 11:
        return one
    if 2 <= k % 10 <= 4 and not 12 <= k % 100 <= 14:
        return few
    return many


def _said(value, lang: str) -> str:
    if isinstance(value, Month):
        return month_label(value, lang)
    if isinstance(value, And):
        return AND.get(lang, " and ").join(_said(item, lang) for item in value)
    if isinstance(value, (list, tuple)):
        return ", ".join(_said(item, lang) for item in value)
    code = getattr(value, "code", None)
    values = getattr(value, "values", None)
    if isinstance(code, str) and isinstance(values, dict):
        template = CATALOGUES.get(lang, {}).get(code)
        if template is not None:
            return _fill(template, values, lang)
    return str(value)


def _fill(template: str, values: dict, lang: str) -> str:
    def slot(match: re.Match) -> str:
        name, forms = match.group(1), match.group(2)
        value = values[name]
        if forms is None:
            return _said(value, lang)
        one, few, many = forms.split("|")
        return plural(value, one, few, many)

    return _SLOT.sub(slot, template)


def fill(template: str, values: dict, lang: str, english: str | None = None) -> str:
    try:
        return _fill(template, dict(values or {}), lang)
    except Exception:
        if english is None:
            return str(template)
        return LEAD_IN.get(lang, "") + str(english)


def _template(code, lang):
    catalogue = CATALOGUES.get(lang) if isinstance(lang, str) else None
    if catalogue is None or not isinstance(code, str):
        return None
    return catalogue.get(code)


def say(code, lang: str, english: str, **values) -> str:
    template = _template(code, lang)
    if template is None:
        return english
    return fill(template, values, lang, english)


def render(code, values: dict, lang: str, english: str) -> str:
    if not isinstance(lang, str) or lang not in CATALOGUES:
        return english
    template = _template(code, lang)
    if template is None:
        return LEAD_IN.get(lang, "") + str(english)
    return fill(template, values or {}, lang, english)


def review(text, lang: str):
    template = _template(getattr(text, "code", None), lang)
    if template is None:
        return text
    try:
        return _fill(template, dict(getattr(text, "values", None) or {}), lang)
    except Exception:
        return text
