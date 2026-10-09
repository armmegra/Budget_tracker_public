"""The Windows build's server: a standard-library HTTP server bound to 127.0.0.1.
It serves the page, signs the one user in with a cookie session, and passes API
requests to the same `dispatch` the cloud uses, over a JSON file store.
"""

from __future__ import annotations

import gzip
import http.cookies
import json
import mimetypes
import os
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "app"))

_RULES_FROM_OUTSIDE = bool(os.environ.get("BUDGET_RULES"))

import guide
import local_ocr
from accounts import Accounts
from budget.api import dispatch
from budget.store import Store
from pages import (
    LANGS, ROWS, forgot_page, login_page, refusal, say, security_page, setup_page,
)

HOST = "127.0.0.1"
PORT = 8765
DATA = HERE / "data"
WEB = HERE / "web"
STORE_FILE = DATA / "store.json"
USERS_FILE = DATA / "users.json"
COOKIE = "budget_session"
MAX_BODY = 12 * 1024 * 1024

LANG_COOKIE = "budget_lang"
LANG_AGE = 157_680_000

ACCOUNTS = Accounts(USERS_FILE)

HOUSEHOLDS = {"en": HERE / "app" / "budget" / "rules.toml"}
if (HERE / "app" / "budget" / "rules.ru.toml").is_file():
    HOUSEHOLDS["ru"] = HERE / "app" / "budget" / "rules.ru.toml"


def _household_loaded() -> str | None:
    if not _RULES_FROM_OUTSIDE:
        return "en"
    from budget.rules import path_in_use
    here = path_in_use().resolve()
    return next((lang for lang, path in HOUSEHOLDS.items() if path.resolve() == here), None)


HOUSEHOLD = _household_loaded()


def _takes_gzip(accept: str | None) -> bool:
    for part in (accept or "").lower().split(","):
        name, _, params = part.strip().partition(";")
        if name.strip() in ("gzip", "*"):
            return params.replace(" ", "") not in ("q=0", "q=0.0", "q=0.00", "q=0.000")
    return False


class Handler(BaseHTTPRequestHandler):
    server_version = "BudgetTrackerLocal"
    sys_version = ""
    _read: bytes | None = None
    _lang_cookie: str | None = None


    def log_message(self, fmt, *args):
        if self.path not in ("/config.js", "/favicon.ico"):
            sys.stderr.write("  %s %s\n" % (self.command, self.path))

    def _send(self, status, body: bytes, ctype: str, cookie: str | None = None):
        packed = (
            len(body) > 1024
            and not ctype.startswith("image/")
            and _takes_gzip(self.headers.get("Accept-Encoding"))
        )
        if packed:
            body = gzip.compress(body, compresslevel=6)
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if packed:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _html(self, status, markup: str, cookie: str | None = None):
        self._send(status, markup.encode("utf-8"), "text/html; charset=utf-8", cookie)

    def _json(self, status, payload: dict, cookie: str | None = None):
        self._send(
            status,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
            cookie,
        )

    def _redirect(self, where: str, cookie: str | None = None):
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", where)
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def end_headers(self):
        chosen, self._lang_cookie = self._lang_cookie, None
        if chosen:
            self.send_header(
                "Set-Cookie",
                f"{LANG_COOKIE}={chosen}; Path=/; Max-Age={LANG_AGE}; SameSite=Strict")
        super().end_headers()

    def _body(self) -> bytes:
        if self._read is None:
            length = int(self.headers.get("Content-Length") or 0)
            self._read = self.rfile.read(min(length, MAX_BODY)) if length else b""
            if length > MAX_BODY:
                remaining = length - MAX_BODY
                while remaining > 0:
                    chunk = self.rfile.read(min(remaining, 65536))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                self._read = b""
        return self._read

    def _form(self) -> dict[str, str]:
        from urllib.parse import parse_qs
        raw = self._body().decode("utf-8", errors="replace")
        return {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}

    def _cookie(self, name: str) -> str | None:
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        jar = http.cookies.SimpleCookie()
        try:
            jar.load(raw)
        except http.cookies.CookieError:
            return None
        found = jar.get(name)
        return found.value if found else None

    def _token(self) -> str | None:
        return self._cookie(COOKIE)

    def _asked_lang(self) -> str | None:
        query = self.path.partition("?")[2]
        asked = parse_qs(query).get("lang", [None])[0] if query else None
        return asked if asked in LANGS else None

    def _lang(self) -> str:
        kept = self._cookie(LANG_COOKIE)
        return (self._asked_lang() or (kept if kept in LANGS else None)
                or _marker() or "en")

    def _cookie_for(self, token: str | None) -> str:
        if token is None:
            return f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"
        return f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict"


    def do_GET(self):
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        who = ACCOUNTS.whoami(self._token())
        self._lang_cookie = self._asked_lang()

        if path == "/logout":
            ACCOUNTS.end_session(self._token())
            return self._redirect("/", self._cookie_for(None))

        if path in ("/", "/index.html"):
            if ACCOUNTS.empty:
                return self._html(HTTPStatus.OK, setup_page(lang=self._lang()))
            if who is None:
                return self._html(HTTPStatus.OK, login_page(lang=self._lang()))
            return self._file(WEB / "index.html")

        if path == "/login":
            lang = self._lang()
            return self._html(HTTPStatus.OK, setup_page(lang=lang) if ACCOUNTS.empty
                              else login_page(lang=lang))

        if path == "/forgot":
            if ACCOUNTS.empty:
                return self._redirect("/")
            return self._html(HTTPStatus.OK, forgot_page(
                ACCOUNTS.recovery_questions(),
                locked_for=ACCOUNTS.recovery_locked_for(),
                lang=self._lang(),
            ))

        if path == "/security":
            if who is None:
                return self._redirect("/login")
            return self._html(HTTPStatus.OK,
                              security_page(ACCOUNTS.recovery_questions(who),
                                            lang=self._lang()))

        if path == "/config.js":
            lang = self._lang()
            if lang != "en" and self._cookie(LANG_COOKIE) not in LANGS:
                self._lang_cookie = lang
            said = {"local": True, "user": who, "lang": lang, "household": HOUSEHOLD or "en"}
            body = f"window.BUDGET_CONFIG = {json.dumps(said)};\n"
            return self._send(HTTPStatus.OK, body.encode("utf-8"),
                              "application/javascript; charset=utf-8")

        if path == "/favicon.ico":
            return self._send(HTTPStatus.NO_CONTENT, b"", "image/x-icon")

        if path.lstrip("/") in guide.DOCS:
            page = guide.render(path.lstrip("/"), self._lang())
            if page is None:
                return self._html(HTTPStatus.NOT_FOUND, "<h1>404</h1>")
            return self._html(HTTPStatus.OK, page)
        if path.startswith("/guide/"):
            shot = guide.picture(path[len("/guide/"):])
            if shot is None:
                return self._html(HTTPStatus.NOT_FOUND, "<h1>404</h1>")
            return self._file(shot)

        if who is None:
            return self._redirect("/login")
        target = (WEB / path.lstrip("/")).resolve()
        if not str(target).startswith(str(WEB.resolve())) or not target.is_file():
            return self._html(HTTPStatus.NOT_FOUND, "<h1>404</h1>")
        return self._file(target)

    def _file(self, target: Path):
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self._send(HTTPStatus.OK, target.read_bytes(), ctype)

    def do_POST(self):
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        self._read = None
        self._body()
        who = ACCOUNTS.whoami(self._token())
        self._lang_cookie = self._asked_lang()

        if path == "/login":
            form = self._form()
            name, password = form.get("username", ""), form.get("password", "")
            if ACCOUNTS.check(name, password):
                token = ACCOUNTS.start_session(name.strip())
                return self._redirect("/", self._cookie_for(token))
            lang = self._lang()
            return self._html(HTTPStatus.OK, login_page(
                say("wrong_login", lang, "That name and password do not match."), lang=lang))

        if path == "/setup":
            form = self._form()
            chosen = form.get("lang") if form.get("lang") in LANGS else None
            lang = chosen or self._lang()
            if not ACCOUNTS.empty:
                return self._html(
                    HTTPStatus.FORBIDDEN,
                    login_page(say("account_exists", lang,
                                   "This computer already has its account."), lang=lang),
                )
            try:
                ACCOUNTS.add(form.get("username", ""), form.get("password", ""),
                             _recovery_from(form))
            except ValueError as why:
                said = refusal(why, lang)
                page = (setup_page(said, lang=lang) if ACCOUNTS.empty
                        else login_page(said, lang=lang))
                return self._html(HTTPStatus.OK, page)
            if chosen:
                with self.server.lock:
                    _follow_household(chosen)
                self._lang_cookie = chosen
            token = ACCOUNTS.start_session(form["username"].strip())
            return self._redirect("/", self._cookie_for(token))

        if path == "/forgot":
            if ACCOUNTS.empty:
                return self._redirect("/")
            form = self._form()
            questions = ACCOUNTS.recovery_questions()
            locked = ACCOUNTS.recovery_locked_for()
            lang = self._lang()

            def refuse(why: str, code=HTTPStatus.OK):
                return self._html(code, forgot_page(questions, why, locked, lang=lang))

            if locked:
                return refuse("", HTTPStatus.TOO_MANY_REQUESTS)
            if not questions:
                return refuse("")
            if form.get("password", "") != form.get("confirm", ""):
                return refuse(say("passwords_differ", lang,
                                  "Those two passwords are not the same."))
            answers = [form.get(f"answer{i}", "") for i in range(len(questions))]
            try:
                ok = ACCOUNTS.reset_password(answers, form.get("password", ""))
            except ValueError as why:
                return refuse(refusal(why, lang))
            if not ok:
                locked = ACCOUNTS.recovery_locked_for()
                if locked:
                    return refuse("", HTTPStatus.TOO_MANY_REQUESTS)
                return refuse(say("answers_wrong", lang,
                                  "Those answers do not match. Nothing was changed."))
            token = ACCOUNTS.start_session(ACCOUNTS.sole)
            return self._redirect("/", self._cookie_for(token))

        if path == "/security":
            if who is None:
                return self._json(HTTPStatus.UNAUTHORIZED,
                                  {"ok": False, "error": "sign in first"})
            form = self._form()
            current = ACCOUNTS.recovery_questions(who)
            lang = self._lang()
            if not ACCOUNTS.check(who, form.get("password", "")):
                return self._html(HTTPStatus.FORBIDDEN, security_page(
                    current, say("not_your_password", lang, "That is not your password."),
                    lang=lang))
            try:
                ACCOUNTS.set_recovery(who, _recovery_from(form))
            except ValueError as why:
                return self._html(HTTPStatus.OK, security_page(
                    current, refusal(why, lang), lang=lang))
            return self._html(HTTPStatus.OK,
                              security_page(ACCOUNTS.recovery_questions(who),
                                            saved=True, lang=lang))

        if path == "/logout":
            ACCOUNTS.end_session(self._token())
            return self._redirect("/", self._cookie_for(None))

        if path != "/api":
            return self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "no such route"})

        if who is None:
            return self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "sign in first"})

        raw = self._body()
        if not raw:
            return self._json(HTTPStatus.OK, {"ok": False, "error": "empty request"})
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            return self._json(HTTPStatus.OK, {"ok": False, "error": "body is not valid JSON"})
        if not isinstance(event, dict):
            return self._json(HTTPStatus.OK, {"ok": False, "error": "event must be a JSON object"})

        with self.server.lock:
            reply = _answer(event)
        return self._json(HTTPStatus.OK, reply)


def _recovery_from(form: dict[str, str]) -> list[tuple[str, str]]:
    return [
        (form.get(f"question{i}", ""), form.get(f"answer{i}", ""))
        for i in range(ROWS)
    ]


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, *args, **kwargs):
        self.lock = threading.Lock()
        super().__init__(*args, **kwargs)

    allow_reuse_address = False


def install_local_ocr() -> None:
    import types

    shim = types.ModuleType("budget.ocr")
    shim.__doc__ = "Local stand-in for budget.ocr, reading with Tesseract."
    shim.extract = local_ocr.extract
    sys.modules["budget.ocr"] = shim


install_local_ocr()


def _marker() -> str | None:
    try:
        said = (DATA / "household").read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return None
    return said if said in LANGS else None


def _untouched() -> bool:
    if not STORE_FILE.exists():
        return True
    try:
        return not any(Store.load(STORE_FILE).state().values())
    except Exception:
        return False


def _load_engine() -> None:
    global dispatch, Store
    import importlib

    for name in [m for m in sys.modules if m == "budget" or m.startswith("budget.")]:
        del sys.modules[name]
    dispatch = importlib.import_module("budget.api").dispatch
    Store = importlib.import_module("budget.store").Store
    install_local_ocr()


def _follow_household(lang: object, *, anyway: bool = False) -> dict:
    swapped = False
    if (isinstance(lang, str) and not _RULES_FROM_OUTSIDE and lang in HOUSEHOLDS
            and lang != HOUSEHOLD and (anyway or _untouched())):
        swapped = _swap(lang)
    return {
        "household": HOUSEHOLD or "en",
        "offered": [] if _RULES_FROM_OUTSIDE else list(HOUSEHOLDS),
        "swapped": swapped,
    }


def _swap(lang: str) -> bool:
    global HOUSEHOLD
    rules = HOUSEHOLDS[lang]
    try:
        from budget.rules import load
        load(rules)
    except Exception as why:
        print(f"! {rules.name} cannot be read, so the household stays as it is - {why}",
              file=sys.stderr)
        return False
    before = os.environ.get("BUDGET_RULES")
    if lang == "en":
        os.environ.pop("BUDGET_RULES", None)
    else:
        os.environ["BUDGET_RULES"] = str(rules)
    try:
        _load_engine()
    except Exception as why:
        if before is None:
            os.environ.pop("BUDGET_RULES", None)
        else:
            os.environ["BUDGET_RULES"] = before
        _load_engine()
        print(f"! the engine would not load {rules.name}, so the household stays as it is"
              f" - {why}", file=sys.stderr)
        return False
    marker = DATA / "household"
    if lang == "en":
        marker.unlink(missing_ok=True)
    else:
        DATA.mkdir(parents=True, exist_ok=True)
        marker.write_text(lang, encoding="utf-8")
    HOUSEHOLD = lang
    return True


def _household_of(backup: object) -> str | None:
    import tomllib

    if not isinstance(backup, dict) or not isinstance(backup.get("rules"), str):
        return None
    try:
        theirs = tomllib.loads(backup["rules"])
    except tomllib.TOMLDecodeError:
        return None
    for lang, path in HOUSEHOLDS.items():
        try:
            if tomllib.loads(path.read_text(encoding="utf-8")) == theirs:
                return lang
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            continue
    return None


def _answer(event: dict) -> dict:
    action = event.get("action")
    if action == "household":
        return {"ok": True, "result": _follow_household(event.get("lang"))}
    if action == "restore" and event.get("confirm") == "RESTORE":
        theirs, was = _household_of(event.get("backup")), HOUSEHOLD
        if theirs not in (None, was) and _follow_household(theirs, anyway=True)["swapped"]:
            reply = dispatch(Store.load(STORE_FILE), event)
            if not reply.get("ok"):
                _follow_household(was, anyway=True)
            return reply
    reply = dispatch(Store.load(STORE_FILE), event)
    if action == "reset" and event.get("scope") == "all" and reply.get("ok"):
        _follow_household(event.get("lang") or "en", anyway=True)
    return reply


def _any_alphabet() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.isatty() or os.environ.get("PYTHONIOENCODING"):
                stream.reconfigure(errors="backslashreplace")
            else:
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, OSError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _any_alphabet()
    import argparse
    args = argparse.ArgumentParser(description="the budget tracker, on this computer")
    args.add_argument("--port", type=int, default=PORT,
                      help=f"listen on this port instead of {PORT}")
    args.add_argument("--no-browser", action="store_true",
                      help="start the server without opening a browser tab")
    opts = args.parse_args(argv)
    port = opts.port

    DATA.mkdir(parents=True, exist_ok=True)
    if not (WEB / "index.html").is_file():
        print(f"! {WEB / 'index.html'} is missing - this directory is incomplete", file=sys.stderr)
        return 1

    _follow_household(_marker() or "en", anyway=True)

    try:
        httpd = Server((HOST, port), Handler)
    except OSError as why:
        print(f"! cannot listen on {HOST}:{port} - {why}", file=sys.stderr)
        print("  Something else is using that port, or a copy is already running.",
              file=sys.stderr)
        print(f"  Close the other one, or start this with --port {port + 1}.",
              file=sys.stderr)
        return 1

    where = f"http://{HOST}:{port}"
    print(f"\n  Budget tracker - {where}")
    print(f"  python    {sys.executable}")
    print(f"  data      {STORE_FILE}")
    print(f"  manual    {where}/guide")
    if not ACCOUNTS.empty and not ACCOUNTS.has_recovery():
        print(f"  ! no recovery questions set - {where}/security adds them")
    print("  account   "
          + ("none yet - the page will ask you to make one, and it is the only one"
             if ACCOUNTS.empty else ", ".join(ACCOUNTS.users)))
    engine = local_ocr.tesseract_path()
    print(f"  OCR       {engine if engine else 'not installed - everything else works'}")
    print("  Keep this window open while you use the app.")
    print("\n  Ctrl-C to stop. Nothing here talks to the internet.\n")

    if not opts.no_browser:
        try:
            webbrowser.open(where)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
