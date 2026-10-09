"""The sign-in, set-up and recovery pages, in English and Russian."""

from __future__ import annotations

import html
import re

from accounts import (
    MAX_QUESTIONS,
    MIN_ANSWER,
    MIN_PASSWORD,
    MIN_QUESTIONS,
    SUGGESTED,
    SUGGESTED_QUESTIONS,
)

__all__ = ["login_page", "setup_page", "forgot_page", "security_page",
           "LANGS", "NAMES", "pick", "say", "refusal"]

ROWS = 3

LANGS = ("en", "ru")
NAMES = {"en": "English", "ru": "Русский"}

RU = {
    "product": "Учёт бюджета",
    "field.name": "Имя",
    "field.password": "Пароль",
    "field.new_password": "Новый пароль",
    "field.new_password_again": "Новый пароль ещё раз",
    "field.your_password": "Ваш пароль",
    "row.question": "Вопрос {i}",
    "row.optional": " (необязательно)",
    "row.placeholder": "Введите свой или выберите из списка",
    "row.answer": "Ответ",

    "login.title": "Вход — Учёт бюджета",
    "login.lead": "Работает на этом компьютере. Ничто здесь не обращается к интернету.",
    "login.button": "Войти",
    "login.foot": (
        '<a href="/forgot">Забыли пароль?</a> Если вы задали контрольные вопросы,'
        " ответьте на них и выберите новый пароль. Ваши записи хранятся в"
        " <code>data/store.json</code>, и всё это их никак не затрагивает."
    ),

    "setup.title": "Первый запуск — Учёт бюджета",
    "setup.heading": "Первый запуск",
    "setup.lead": (
        "Это первый запуск, поэтому учётной записи ещё нет. Создайте её. В"
        " приложении ровно одна учётная запись, она хранится только в этой папке,"
        " и как только она создана, эта страница закрывается навсегда."
    ),
    "setup.name_rule": "2–32 символа: буквы, цифры, точка, дефис или подчёркивание",
    "setup.forget": "Если вы его забудете",
    "setup.help": (
        "Электронной почты для ссылки нет, поэтому эти ответы — единственный"
        " способ снова войти. Выбирайте вопросы, ответы на которые не изменятся и"
        " над которыми через год не придётся долго думать."
        " <b>Заглавные буквы и лишние пробелы не важны</b> — «Рекс» и «  рекс» —"
        " один и тот же ответ."
    ),
    "setup.button": "Создать и войти",
    "setup.foot": (
        "Пароль — не короче {n} {n|символа|символов|символов}. Он и ответы"
        " хранятся не сами по себе, а как хеши PBKDF2-SHA256 с собственной солью, —"
        " но по-настоящему ваши записи защищает то, что этот сервер слушает только"
        " этот компьютер."
    ),

    "locked.title": "Слишком много попыток — Учёт бюджета",
    "locked.heading": "Слишком много попыток",
    "locked.lead": (
        "Восстановление закрыто ещё на {n} {n|минуту|минуты|минут}. Это касается"
        " только вопросов — если вы помните сам пароль, вы можете"
        ' <a href="/login">войти</a> прямо сейчас.'
    ),
    "locked.foot": (
        "Если это были вы и ждать нельзя: удалите <code>data/users.json</code> —"
        " учётная запись исчезнет, и приложение предложит создать её заново. Ваши"
        " записи хранятся в <code>data/store.json</code> и не пострадают."
    ),

    "none.title": "Контрольных вопросов нет — Учёт бюджета",
    "none.heading": "Контрольных вопросов нет",
    "none.lead": "Учётная запись создана без них, поэтому отвечать здесь не на что.",
    "none.next": (
        'Если вы ещё можете <a href="/login">войти</a>, задайте их сейчас на'
        " странице <code>/security</code> — и в следующий раз эта страница"
        " сработает."
    ),
    "none.foot": (
        "Если не можете: удалите <code>data/users.json</code>, и приложение"
        " предложит создать учётную запись заново, как при первом запуске."
        " Пропадёт только вход и больше ничего — ваши записи хранятся в"
        " <code>data/store.json</code>, это отдельный файл, и его это не затронет."
    ),

    "forgot.title": "Восстановление пароля — Учёт бюджета",
    "forgot.heading": "Восстановление пароля",
    "forgot.lead.two": (
        "Ответьте на оба вопроса и выберите новый пароль. Заглавные буквы и"
        " лишние пробелы не важны."
    ),
    "forgot.lead.all": (
        "Ответьте на все {n} {n|вопрос|вопроса|вопросов} и выберите новый пароль."
        " Заглавные буквы и лишние пробелы не важны."
    ),
    "forgot.button": "Сохранить новый пароль",
    "forgot.foot": (
        "Все ответы должны быть верными, и эта страница никогда не говорит, какой"
        ' из них был неверным. <a href="/login">Вернуться ко входу.</a>'
    ),

    "security.title": "Контрольные вопросы — Учёт бюджета",
    "security.heading": "Контрольные вопросы",
    "security.back": "Вернуться в приложение",
    "security.have": (
        "У вас {n} {n|контрольный вопрос|контрольных вопроса|контрольных вопросов}."
        " Сохранение заменит {n|его|их|их} полностью — наполовину изменённый набор"
        " хуже любого из двух, поэтому ответьте в каждой строке, которую"
        " оставляете."
    ),
    "security.none": (
        "У этой учётной записи нет контрольных вопросов, поэтому, если вы забудете"
        " пароль, придётся удалить <code>data/users.json</code> и создать учётную"
        " запись заново. Два вопроса это исправят."
    ),
    "security.saved": "Сохранено.",
    "security.why": (
        "Нужен потому, что иначе любой, кто найдёт это окно открытым, мог бы"
        " переписать ответы и закрыть вам вход."
    ),
    "security.button": "Сохранить эти вопросы",
    "security.foot": (
        "От {min} до {max} {max|вопроса|вопросов|вопросов}. Ответы хешируются так"
        " же, как пароль, и прочитать их обратно нельзя — поэтому поля выше пусты"
        " даже для вопросов, которые у вас уже есть."
    ),

    "wrong_login": "Имя и пароль не совпадают.",
    "account_exists": "На этом компьютере учётная запись уже есть.",
    "passwords_differ": "Пароли не совпадают.",
    "answers_wrong": "Ответы не подходят. Ничего не изменено.",
    "not_your_password": "Это не ваш пароль.",

    "name_shape": (
        "имя — от 2 до 32 символов: буквы любого алфавита, цифры, точка, дефис"
        " или подчёркивание"
    ),
    "name_taken": "имя «{name}» уже занято",
    "one_account": "в приложении может быть только одна учётная запись, и она уже есть",
    "most_accounts": (
        "в приложении может быть не больше {n}"
        " {n|учётной записи|учётных записей|учётных записей}"
    ),
    "short_password": "пароль — не короче {n} {n|символа|символов|символов}",
    "no_account": "нет учётной записи с именем «{name}»",
    "few_questions": "задайте хотя бы {n} {n|вопрос|вопроса|вопросов}, каждый с ответом",
    "many_questions": "не больше {n} {n|вопроса|вопросов|вопросов}",
    "short_answer": (
        "ответ на вопрос «{question}» слишком короткий, чтобы этот вопрос имел смысл"
    ),
    "same_questions": "два вопроса совпадают",
}

_WORDS = {"ru": RU}
_SLOT = re.compile(r"\{(\w+)(?:\|([^{}|]*)\|([^{}|]*)\|([^{}|]*))?\}")


def pick(code: object) -> str:
    return code if isinstance(code, str) and code in LANGS else "en"


def _plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def _fill(template: str, values: dict) -> str:
    def slot(m: re.Match) -> str:
        value = values[m.group(1)]
        if m.group(2) is None:
            return str(value)
        return _plural(int(value), m.group(2), m.group(3), m.group(4))
    return _SLOT.sub(slot, template)


def say(key: str, lang: str, english: str, **values) -> str:
    table = _WORDS.get(lang)
    if table is None or key not in table:
        return english
    try:
        return _fill(table[key], values)
    except (KeyError, IndexError, TypeError, ValueError):
        return english


def refusal(why: Exception, lang: str = "en") -> str:
    return say(getattr(why, "code", None) or "", lang, str(why),
               **(getattr(why, "values", None) or {}))


def _words(lang: str):
    return lambda key, english, **values: say(key, lang, english, **values)


_SHELL = """<!doctype html>
<html lang="{lang}"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{
    --ink: #1c1c1e; --dim: #6b6b70; --rule: #d3d3d8; --bg: #fbfbfa;
    --card: #ffffff; --accent: #3f9d5a; --err: #c8482f;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --ink: #ececf0; --dim: #9a9aa2; --rule: #34343a; --bg: #161618;
      --card: #1e1e21; --accent: #4fbf88; --err: #ff6f5c;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; min-height: 100vh; display: grid; place-items: center;
    padding: 24px; background: var(--bg); color: var(--ink);
    font: 15px/1.5 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }}
  .card {{
    width: 100%; max-width: {width}; background: var(--card);
    border: 1px solid var(--rule); border-radius: 10px; padding: 28px 26px 26px;
    display: flex; flex-direction: column; gap: 16px;
  }}
  h1 {{ font-size: 20px; margin: 0; font-weight: 600; }}
  h2 {{ font-size: 14px; margin: 4px 0 0; font-weight: 600; }}
  p {{ margin: 0; color: var(--dim); font-size: 13.5px; }}
  form {{ display: flex; flex-direction: column; gap: 12px; }}
  label {{ display: flex; flex-direction: column; gap: 5px; font-size: 13px; color: var(--dim); }}
  input {{
    font: inherit; font-size: 16px; padding: 9px 11px; color: var(--ink);
    background: var(--bg); border: 1px solid var(--rule); border-radius: 7px;
  }}
  input:focus {{ outline: 2px solid var(--accent); outline-offset: -1px; }}
  button {{
    font: inherit; font-weight: 500; padding: 10px 14px; margin-top: 4px;
    color: #fff; background: var(--accent); border: 0; border-radius: 7px;
    cursor: pointer;
  }}
  button:hover {{ filter: brightness(1.06); }}
  .err {{ color: var(--err); font-size: 13.5px; }}
  .foot {{ color: var(--dim); font-size: 12.5px; border-top: 1px solid var(--rule); padding-top: 14px; }}
  .qa {{
    display: flex; flex-direction: column; gap: 8px; padding: 12px;
    border: 1px solid var(--rule); border-radius: 8px;
  }}
  .ask {{ font-size: 14px; color: var(--ink); font-weight: 500; }}
  .quiet {{ font-size: 12.5px; }}
  a {{ color: var(--accent); }}
  .between {{ display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }}
</style>
</head><body>
<div class="card">
{switch}
{body}
</div>
</body></html>
"""


def _datalist(lang: str) -> str:
    return (
        '<datalist id="suggested">'
        + "".join(f'<option value="{html.escape(q)}">'
                  for q in SUGGESTED.get(lang, SUGGESTED_QUESTIONS))
        + "</datalist>"
    )


def _switch(lang: str) -> str:
    names = (
        NAMES[code] if code == lang
        else f'<a href="?lang={code}" lang="{code}" hreflang="{code}">{NAMES[code]}</a>'
        for code in LANGS
    )
    return '  <p class="quiet" style="text-align:right">' + " · ".join(names) + "</p>"


def _err(message: str | None) -> str:
    return f'<p class="err">{html.escape(message)}</p>' if message else ""


def _shell(title: str, body: str, width: str = "23rem", *, lang: str = "en") -> str:
    return _SHELL.format(title=title, body=body, width=width, lang=lang,
                         switch=_switch(lang))


def _question_rows(existing: list[str] | None = None, lang: str = "en") -> str:
    w = _words(lang)
    existing = existing or []
    rows = []
    for i in range(ROWS):
        was = existing[i] if i < len(existing) else ""
        need = " required" if i < MIN_QUESTIONS else ""
        spare = "" if i < MIN_QUESTIONS else w("row.optional", " (optional)")
        question = w("row.question", f"Question {i + 1}", i=i + 1)
        rows.append(f"""    <div class="qa">
      <label>{question}{spare}<input name="question{i}" list="suggested"
        placeholder="{w("row.placeholder", "Type your own, or pick one")}" value="{html.escape(was)}"
        maxlength="120"{need}></label>
      <label>{w("row.answer", "Answer")}<input name="answer{i}" autocomplete="off"
        minlength="{MIN_ANSWER}"{need}></label>
    </div>""")
    return "\n".join(rows)


def login_page(message: str | None = None, *, lang: str = "en") -> str:
    lang = pick(lang)
    w = _words(lang)
    foot = w("login.foot", """<a href="/forgot">Forgotten your password?</a> If you set up
    recovery questions you can answer them and choose a new one. Your notes are
    in <code>data/store.json</code> and are never touched by any of this.""")
    body = f"""  <h1>{w("product", "Budget tracker")}</h1>
  <p>{w("login.lead", "Running on this computer. Nothing here talks to the internet.")}</p>
{_err(message)}
  <form method="post" action="/login">
    <label>{w("field.name", "Name")}<input name="username" autocomplete="username" autofocus required></label>
    <label>{w("field.password", "Password")}<input name="password" type="password"
      autocomplete="current-password" required></label>
    <button type="submit">{w("login.button", "Sign in")}</button>
  </form>
  <p class="foot">{foot}</p>"""
    return _shell(w("login.title", "Sign in - Budget tracker"), body, lang=lang)


def setup_page(message: str | None = None, *, lang: str = "en") -> str:
    lang = pick(lang)
    w = _words(lang)
    lead = w("setup.lead", """First run, so there is no account yet. Make it. This app holds exactly
    one, it lives only in this directory, and once it exists this page is
    closed for good.""")
    help_text = w("setup.help", """There is no email to send a link to, so these answers are
      the only way back in. Pick questions whose answers will not change and
      that you will not have to think hard about in a year.
      <b>Capitals and extra spaces do not matter</b> - "Rex" and "  rex" are
      the same answer.""")
    foot = w("setup.foot", f"""The password needs {MIN_PASSWORD} characters or more. It and
    the answers are stored as PBKDF2-SHA256 hashes with their own salts, never
    as themselves - but the real reason your notes are private is that this
    server listens only to this machine.""", n=MIN_PASSWORD)
    body = f"""  <h1>{w("setup.heading", "Set up")}</h1>
  <p>{lead}</p>
{_err(message)}
  <form method="post" action="/setup">
    <input type="hidden" name="lang" value="{lang}">
    <label>{w("field.name", "Name")}<input name="username" autocomplete="username" autofocus required
      pattern="[\\p{{L}}\\p{{N}}._\\-]{{2,32}}" title="{w("setup.name_rule", "2-32 letters, digits, dot, dash or underscore")}"></label>
    <label>{w("field.password", "Password")}<input name="password" type="password" autocomplete="new-password"
      required minlength="{MIN_PASSWORD}"></label>

    <h2>{w("setup.forget", "If you forget it")}</h2>
    <p class="quiet">{help_text}</p>
{_question_rows(lang=lang)}
{_datalist(lang)}
    <button type="submit">{w("setup.button", "Create and sign in")}</button>
  </form>
  <p class="foot">{foot}</p>"""
    return _shell(w("setup.title", "Set up - Budget tracker"), body, width="27rem", lang=lang)


def forgot_page(questions: list[str], message: str | None = None,
                locked_for: int = 0, *, lang: str = "en") -> str:
    lang = pick(lang)
    w = _words(lang)
    if locked_for > 0:
        minutes = max(1, (locked_for + 59) // 60)
        lead = w("locked.lead", f"""Recovery is closed for another {minutes} minute{'s' if minutes != 1 else ''}.
    This only stops the questions - if you remember the password itself, you can
    still <a href="/login">sign in</a> right now.""", n=minutes)
        foot = w("locked.foot", """If it was you and you cannot wait: deleting
    <code>data/users.json</code> clears the account and the app will ask you to
    set up again. Your notes are in <code>data/store.json</code> and survive it.""")
        body = f"""  <h1>{w("locked.heading", "Too many tries")}</h1>
  <p>{lead}</p>
  <p class="foot">{foot}</p>"""
        return _shell(w("locked.title", "Too many tries - Budget tracker"), body, lang=lang)

    if not questions:
        after = w("none.next", """If you can still <a href="/login">sign in</a>, set some up now at
    <code>/security</code> and this page will work next time.""")
        foot = w("none.foot", """If you cannot: delete <code>data/users.json</code> and the app
    will ask you to set up again, as it did on the first run. That loses the
    login and nothing else - your notes are in <code>data/store.json</code>,
    which is a separate file and is not touched.""")
        body = f"""  <h1>{w("none.heading", "No recovery questions")}</h1>
  <p>{w("none.lead", "This account was made without them, so there is nothing here to answer.")}</p>
{_err(message)}
  <p>{after}</p>
  <p class="foot">{foot}</p>"""
        return _shell(w("none.title", "No recovery questions - Budget tracker"), body, lang=lang)

    answer = w("row.answer", "Answer")
    asked = "\n".join(f"""    <div class="qa">
      <p class="ask">{html.escape(question)}</p>
      <label>{answer}<input name="answer{i}" autocomplete="off" required></label>
    </div>""" for i, question in enumerate(questions))

    lead = f"""Answer {'both' if len(questions) == 2 else 'all ' + str(len(questions))}
    and choose a new password. Capitals and extra spaces do not matter."""
    lead = (w("forgot.lead.two", lead) if len(questions) == 2
            else w("forgot.lead.all", lead, n=len(questions)))
    foot = w("forgot.foot", """Every answer has to be right, and this page never says which
    one was not. <a href="/login">Back to signing in.</a>""")
    body = f"""  <h1>{w("forgot.heading", "Forgotten password")}</h1>
  <p>{lead}</p>
{_err(message)}
  <form method="post" action="/forgot">
{asked}
    <label>{w("field.new_password", "New password")}<input name="password" type="password"
      autocomplete="new-password" required minlength="{MIN_PASSWORD}"></label>
    <label>{w("field.new_password_again", "New password again")}<input name="confirm" type="password"
      autocomplete="new-password" required minlength="{MIN_PASSWORD}"></label>
    <button type="submit">{w("forgot.button", "Set the new password")}</button>
  </form>
  <p class="foot">{foot}</p>"""
    return _shell(w("forgot.title", "Forgotten password - Budget tracker"), body,
                  width="27rem", lang=lang)


def security_page(questions: list[str], message: str | None = None,
                  saved: bool = False, *, lang: str = "en") -> str:
    lang = pick(lang)
    w = _words(lang)
    if questions:
        count = w("security.have", f"""You have {len(questions)} question{'s' if len(questions) != 1 else ''}
    set. Saving replaces {'them' if len(questions) != 1 else 'it'} entirely -
    a set half changed is worse than either, so answer every row you keep.""",
                  n=len(questions))
        have = f"""  <p>{count}</p>
  <ul class="quiet">{''.join(f'<li>{html.escape(q)}</li>' for q in questions)}</ul>"""
    else:
        none = w("security.none", """This account has no recovery questions, so forgetting the password would
    mean deleting <code>data/users.json</code> and setting up again. Two
    questions fix that.""")
        have = f"""  <p>{none}</p>"""

    done = w("security.saved", "Saved.")
    why = w("security.why", """Asked because anyone who finds this window open could
      otherwise rewrite the answers and lock you out with them.""")
    foot = w("security.foot", f"""Between {MIN_QUESTIONS} and {MAX_QUESTIONS} questions. The
    answers are hashed the way the password is and cannot be read back, which is
    why the boxes above are empty even for questions you already have.""",
             min=MIN_QUESTIONS, max=MAX_QUESTIONS)
    body = f"""  <div class="between"><h1>{w("security.heading", "Recovery questions")}</h1>
    <a class="quiet" href="/">{w("security.back", "Back to the app")}</a></div>
{have}
{f'<p class="err" style="color:var(--accent)">{done}</p>' if saved else ''}
{_err(message)}
  <form method="post" action="/security">
    <label>{w("field.your_password", "Your password")}<input name="password" type="password"
      autocomplete="current-password" required autofocus></label>
    <p class="quiet">{why}</p>
{_question_rows(questions, lang)}
{_datalist(lang)}
    <button type="submit">{w("security.button", "Save these questions")}</button>
  </form>
  <p class="foot">{foot}</p>"""
    return _shell(w("security.title", "Recovery questions - Budget tracker"), body,
                  width="27rem", lang=lang)
