from __future__ import annotations

import http.cookiejar
import importlib
import json
import socket
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

LOCAL = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(
    not (LOCAL / "serve.py").is_file(), reason="the local build is not present"
)


@pytest.fixture()
def app(tmp_path, monkeypatch):
    for name in ("serve", "accounts", "pages", "local_ocr"):
        sys.modules.pop(name, None)
    monkeypatch.syspath_prepend(str(LOCAL))
    monkeypatch.syspath_prepend(str(LOCAL / "app"))
    serve = importlib.import_module("serve")

    import accounts
    monkeypatch.setattr(accounts, "_ITERATIONS", 1000)

    monkeypatch.setattr(serve, "DATA", tmp_path)
    monkeypatch.setattr(serve, "STORE_FILE", tmp_path / "store.json")
    monkeypatch.setattr(serve, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(serve, "ACCOUNTS", serve.Accounts(tmp_path / "users.json"))

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    httpd = serve.Server(("127.0.0.1", port), serve.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    class Decline(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    quiet = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar), Decline)

    class Reply:
        def __init__(self, reply):
            self.code = self.status = reply.status
            self.headers = reply.headers
            self._body = reply.read()

        def read(self):
            return self._body

    def fetch(call):
        for last in (False, True):
            try:
                return Reply(call())
            except ConnectionResetError:
                if last:
                    raise

    class Client:
        base = f"http://127.0.0.1:{port}"
        accounts = serve.ACCOUNTS
        store_file = tmp_path / "store.json"

        def get(self, path, headers=None):
            return fetch(lambda: opener.open(
                urllib.request.Request(self.base + path, headers=headers or {}), timeout=60))

        def form(self, path, **fields):
            from urllib.parse import urlencode
            return Reply(opener.open(
                self.base + path, data=urlencode(fields).encode(), timeout=60))

        def submit(self, path, **fields):
            from urllib.parse import urlencode
            try:
                return Reply(quiet.open(
                    self.base + path, data=urlencode(fields).encode(), timeout=60))
            except urllib.error.HTTPError as stopped:
                if stopped.code in (301, 302, 303, 307, 308):
                    return stopped
                raise

        def api(self, **body):
            req = urllib.request.Request(
                self.base + "/api", data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            return json.loads(opener.open(req, timeout=60).read())

    try:
        yield Client()
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_it_binds_to_loopback_and_nothing_else(app) -> None:
    import serve
    assert serve.HOST == "127.0.0.1"

    code = [
        line for line in (LOCAL / "serve.py").read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]
    inside_docstring = False
    for line in code:
        if line.count('"""') == 1:
            inside_docstring = not inside_docstring
            continue
        assert inside_docstring or "0.0.0.0" not in line, line


def test_the_first_visit_offers_to_make_an_account(app) -> None:
    page = app.get("/").read().decode()
    assert "Set up" in page and "/setup" in page
    assert app.accounts.empty


def test_the_api_is_shut_until_someone_signs_in(app) -> None:
    with pytest.raises(urllib.error.HTTPError) as raised:
        app.api(action="periods")
    assert raised.value.code == 401


SETUP = {
    "username": "sam",
    "password": "a-good-password",
    "question0": "First pet?",
    "answer0": "Rex",
    "question1": "First street?",
    "answer1": "Baker Street",
}


def test_making_the_first_account_signs_you_in(app) -> None:
    app.submit("/setup", **SETUP)
    assert not app.accounts.empty
    assert "budget" in app.get("/").read().decode().lower()
    assert app.api(action="periods") == {"ok": True, "result": []}


@pytest.fixture()
def signed_in(app):
    app.submit("/setup", **SETUP)
    return app


def test_a_wrong_password_does_not_sign_you_in(signed_in) -> None:
    signed_in.get("/logout")
    page = signed_in.form("/login", username="sam", password="wrong").read().decode()
    assert "do not match" in page
    with pytest.raises(urllib.error.HTTPError):
        signed_in.api(action="periods")


def test_a_name_that_does_not_exist_says_the_same_thing(signed_in) -> None:
    signed_in.get("/logout")
    page = signed_in.form("/login", username="nobody", password="wrong").read().decode()
    assert "do not match" in page


def test_signing_out_ends_the_session(signed_in) -> None:
    assert signed_in.api(action="periods")["ok"]
    signed_in.get("/logout")
    with pytest.raises(urllib.error.HTTPError) as raised:
        signed_in.api(action="periods")
    assert raised.value.code == 401


def test_the_session_cookie_is_not_readable_by_script(signed_in) -> None:
    from urllib.parse import urlencode

    class Keep(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    opener = urllib.request.build_opener(Keep)
    try:
        reply = opener.open(signed_in.base + "/login",
                            data=urlencode({"username": "sam",
                                            "password": "a-good-password"}).encode(),
                            timeout=30)
    except urllib.error.HTTPError as stopped:
        reply = stopped
    header = reply.headers.get("Set-Cookie", "") or ""
    assert reply.code == 303, reply.code
    assert "HttpOnly" in header, header
    assert "SameSite=Strict" in header, header
    assert "budget_session=" in header, header


def test_it_holds_one_account_and_no_more(signed_in) -> None:
    from accounts import MAX_USERS
    assert MAX_USERS == 1
    assert len(signed_in.accounts.users) == MAX_USERS
    with pytest.raises(ValueError, match="at most"):
        signed_in.accounts.add("one-too-many", "a-good-password")


def test_setup_shuts_itself_once_the_account_exists(signed_in) -> None:
    signed_in.get("/logout")
    with pytest.raises(urllib.error.HTTPError) as refused:
        signed_in.form("/setup", username="intruder", password="a-good-password")
    assert refused.value.code == 403
    assert list(signed_in.accounts.users) == ["sam"]
    with pytest.raises(urllib.error.HTTPError) as shut:
        signed_in.api(action="periods")
    assert shut.value.code == 401


def test_a_password_has_a_floor_and_a_name_has_a_shape(app) -> None:
    from accounts import MIN_PASSWORD
    with pytest.raises(ValueError, match="at least"):
        app.accounts.add("sam", "x" * (MIN_PASSWORD - 1))
    with pytest.raises(ValueError, match="2 to 32"):
        app.accounts.add("a", "a-good-password")
    with pytest.raises(ValueError, match="2 to 32"):
        app.accounts.add("has a space", "a-good-password")
    assert app.accounts.empty


def test_a_name_cannot_be_taken_twice_in_another_case(signed_in) -> None:
    with pytest.raises(ValueError, match="taken"):
        signed_in.accounts.add("SAM", "a-good-password")


def test_the_password_is_never_stored(signed_in, tmp_path) -> None:
    written = (tmp_path / "users.json").read_text(encoding="utf-8")
    assert "a-good-password" not in written
    assert "Rex" not in written and "Baker Street" not in written
    assert "First pet?" in written
    record = json.loads(written)["sam"]
    assert set(record) == {"salt", "hash", "iterations", "created", "recovery"}
    for asked in record["recovery"]["questions"]:
        assert set(asked) == {"ask", "salt", "hash", "iterations"}


def test_the_hashing_is_slow_on_purpose() -> None:
    import accounts
    assert accounts._ITERATIONS >= 600_000


def test_the_data_lands_in_this_directory(signed_in, sample_notes) -> None:
    signed_in.api(action="import", text=sample_notes, year=2026)
    assert signed_in.store_file.exists()
    saved = json.loads(signed_in.store_file.read_text(encoding="utf-8"))
    assert "salary:61800" in saved["periods"]


def test_a_cloud_backup_restores_into_it(signed_in, sample_notes) -> None:
    signed_in.api(action="import", text=sample_notes, year=2026)
    backup = signed_in.api(action="backup")["result"]
    assert backup["kind"] == "budget-backup"
    fresh = signed_in.api(action="restore", backup=backup, confirm="RESTORE")
    assert fresh["ok"] and fresh["result"]["restored"]["months"] >= 1


def test_a_backup_carries_the_rules_and_a_restore_says_if_they_differ(
        tmp_path, sample_notes, monkeypatch) -> None:
    from budget.api import dispatch
    from budget.rules import path_in_use
    from budget.store import Store

    ours = path_in_use().read_text(encoding="utf-8")
    source = Store(tmp_path / "source.json")
    assert dispatch(source, {"action": "import", "text": sample_notes, "year": 2026})["ok"]
    backup = dispatch(source, {"action": "backup"})["result"]
    assert backup["rules"] == ours

    def said(document) -> str:
        reply = dispatch(Store(tmp_path / "target.json"),
                         {"action": "restore", "backup": document, "confirm": "RESTORE"})
        assert reply["ok"], reply
        return reply["result"]["rules"]

    assert said(backup) == "same"
    assert said(dict(backup, rules=ours.replace("\n", "\r\n"))) == "same"
    assert said(dict(backup, rules=ours + "\n# another household\n")) == "different"
    assert said({k: v for k, v in backup.items() if k != "rules"}) == "absent"
    assert path_in_use().read_text(encoding="utf-8") == ours

    monkeypatch.setenv("BUDGET_RULES", str(tmp_path / "gone.toml"))
    refused = dispatch(source, {"action": "backup"})
    assert not refused["ok"] and "no backup was made" in refused["error"]


def test_text_goes_gzipped_to_a_browser_that_takes_it(signed_in) -> None:
    import gzip

    plain = signed_in.get("/")
    packed = signed_in.get("/", headers={"Accept-Encoding": "gzip, deflate, br, zstd"})
    assert plain.headers.get("Content-Encoding") is None
    assert packed.headers["Content-Encoding"] == "gzip"
    assert gzip.decompress(packed.read()) == plain.read()
    assert len(packed.read()) < len(plain.read()) / 2

    refused = signed_in.get("/", headers={"Accept-Encoding": "gzip;q=0, identity"})
    assert refused.headers.get("Content-Encoding") is None
    picture = signed_in.get("/guide/month.png", headers={"Accept-Encoding": "gzip"})
    assert picture.headers.get("Content-Encoding") is None


def _as_the_browser_saves_it(value):
    def settle(v):
        if isinstance(v, float) and v.is_integer():
            return int(v)
        if isinstance(v, dict):
            first = sorted((k for k in v if k.isdigit() and str(int(k)) == k), key=int)
            return {k: settle(v[k]) for k in first + [k for k in v if k not in first]}
        if isinstance(v, list):
            return [settle(x) for x in v]
        return v
    return settle(json.loads(json.dumps(value, ensure_ascii=False)))


def _everything_shown(store) -> dict:
    from budget.api import dispatch

    def read(**event):
        reply = dispatch(store, event)
        assert reply["ok"], (event, reply)
        return reply["result"]

    shown = {"periods": read(action="periods"), "config": read(action="config")}
    months = [p["identity"] for p in shown["periods"]]
    for month in months:
        for action in ("show", "totals", "questions", "raw", "config"):
            shown[f"{month} {action}"] = read(action=action, period=month)
        for fmt in ("rtf", "txt"):
            shown[f"{month} print {fmt}"] = read(action="export", period=month, format=fmt)
    for fmt in ("rtf", "txt"):
        shown[f"year {fmt}"] = read(action="export", year=2026, format=fmt)
        shown[f"compare {fmt}"] = read(action="export", periods=months, average=True, format=fmt)
    shown["compare"] = read(action="compare", periods=months, average=True)
    return shown


def _teacher(store):
    from budget.api import dispatch

    def do(**event):
        reply = dispatch(store, dict(event, override=True))
        assert reply["ok"], (event, reply)
        return reply["result"]
    return do


def test_the_page_is_told_it_is_local(signed_in) -> None:
    config = signed_in.get("/config.js").read().decode()
    assert '"local": true' in config
    assert "sam" in config


EXE = LOCAL / "budget.exe"
BUNDLED = LOCAL / "vendor" / "python" / "python.exe"


def test_the_launcher_is_a_real_executable() -> None:
    assert EXE.is_file(), "run: python launcher/build.py"
    assert EXE.read_bytes()[:2] == b"MZ"
    assert (LOCAL / "launcher" / "budget.cs").is_file()


@pytest.mark.skipif(sys.platform != "win32" or not EXE.is_file(),
                    reason="needs Windows and a built budget.exe")
def test_double_clicking_it_starts_the_app(tmp_path) -> None:
    import os
    import subprocess
    import time

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    proc = subprocess.Popen(
        [str(EXE), "--port", str(port), "--no-browser"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        env=dict(os.environ, PYTHONUNBUFFERED="1"), cwd=str(tmp_path),
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 30
        while True:
            try:
                page = urllib.request.urlopen(base + "/", timeout=5).read().decode()
                break
            except OSError:
                assert proc.poll() is None, "the launcher exited before the server answered"
                assert time.time() < deadline, "the server never answered"
                time.sleep(0.25)
        assert "Budget tracker" in page
        req = urllib.request.Request(base + "/api", data=b'{"action":"periods"}',
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        with pytest.raises(urllib.error.HTTPError) as shut:
            urllib.request.urlopen(req, timeout=5)
        assert shut.value.code == 401
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        banner = proc.stdout.read().decode(errors="replace")
        proc.wait(timeout=10)

    assert f"Budget tracker - {base}" in banner, banner
    if BUNDLED.is_file():
        assert str(BUNDLED) in banner, banner


@pytest.mark.skipif(not BUNDLED.is_file(), reason="no bundled Python in vendor/")
def test_the_bundled_python_can_load_the_app(tmp_path) -> None:
    import subprocess
    done = subprocess.run([str(BUNDLED), str(LOCAL / "serve.py"), "--help"],
                          capture_output=True, text=True, cwd=str(tmp_path), timeout=60)
    assert done.returncode == 0, done.stderr
    assert "--port" in done.stdout and "--no-browser" in done.stdout


TESSERACT = LOCAL / "vendor" / "tesseract" / "tesseract.exe"


@pytest.mark.skipif(not TESSERACT.is_file(), reason="no bundled Tesseract in vendor/")
def test_the_stripped_engine_is_a_fraction_of_what_was_downloaded() -> None:
    kept = sum(f.stat().st_size for f in TESSERACT.parent.rglob("*") if f.is_file())
    assert kept < 40_000_000, f"vendor/tesseract has grown to {kept / 1e6:.0f} MB"
    assert (TESSERACT.parent / "LICENSE").is_file(), "Apache-2.0 needs its licence shipped"
    engine = TESSERACT.parent / "libtesseract-5.dll"
    assert engine.is_file() and engine.stat().st_size < 20_000_000


def test_the_guide_opens_without_signing_in(app) -> None:
    page = app.get("/guide").read().decode()
    assert "<h1" in page and "the guide" in page
    assert 'src="guide/month.png"' in page
    assert 'href="/readme' in page
    assert app.get("/third-party").read().decode().count("<h2") > 3


def test_the_screenshots_are_served_and_nothing_else_is(app) -> None:
    shot = app.get("/guide/month.png")
    assert shot.headers["Content-Type"] == "image/png"
    assert shot.read()[:8] == b"\x89PNG\r\n\x1a\n"
    for sneaky in ("/guide/../serve.py", "/guide/..%2Fserve.py", "/guide/serve.py",
                   "/guide/month.png.txt"):
        with pytest.raises(urllib.error.HTTPError) as refused:
            app.get(sneaky)
        assert refused.value.code == 404, sneaky


def test_the_renderer_handles_what_the_guide_is_written_in() -> None:
    import guide
    text = """# The guide

Some **bold**, some *italic*, some `code with **stars** in`, a
[link](README.md#first-run) and ![a shot](guide/x.png).

## Tiers, and the two Totals

- one
  continued
- two

| | |
| --- | --- |
| `a` | b |

```
03.02
+ 61 800
```
"""
    out = guide._blocks(text)
    assert '<h2 id="tiers-and-the-two-totals">' in out
    assert "<strong>bold</strong>" in out and "<em>italic</em>" in out
    assert "<code>code with **stars** in</code>" in out
    assert 'href="/readme#first-run"' in out
    assert '<img alt="a shot" src="guide/x.png">' in out
    assert "<li>one continued</li><li>two</li>" in out
    assert "<td><code>a</code></td><td>b</td>" in out and "<th>" not in out
    assert "<pre><code>03.02\n+ 61 800</code></pre>" in out


def test_setup_insists_on_recovery_questions(app) -> None:
    page = app.form("/setup", username="sam", password="a-good-password").read().decode()
    assert "at least 2 questions" in page
    assert app.accounts.empty


def test_one_question_is_not_enough(app) -> None:
    page = app.form("/setup", username="sam", password="a-good-password",
                    question0="First pet?", answer0="Rex").read().decode()
    assert "at least 2 questions" in page
    assert app.accounts.empty


def test_the_questions_are_shown_and_the_answers_are_not(signed_in) -> None:
    signed_in.get("/logout")
    page = signed_in.get("/forgot").read().decode()
    assert "First pet?" in page and "First street?" in page
    assert "Rex" not in page and "Baker Street" not in page


def test_answering_them_sets_a_new_password(signed_in) -> None:
    signed_in.api(action="import", text="03.02\n+ 61 800\n", year=2026)
    signed_in.get("/logout")

    signed_in.submit("/forgot", answer0="Rex", answer1="Baker Street",
                   password="a-different-one", confirm="a-different-one")
    assert signed_in.api(action="periods")["ok"]

    signed_in.get("/logout")
    assert not signed_in.accounts.check("sam", "a-good-password")
    assert signed_in.accounts.check("sam", "a-different-one")
    assert signed_in.store_file.exists()


def test_capitals_and_spacing_do_not_matter(signed_in) -> None:
    signed_in.get("/logout")
    signed_in.submit("/forgot", answer0="  rEX ", answer1="baker   street",
                   password="a-different-one", confirm="a-different-one")
    assert signed_in.accounts.check("sam", "a-different-one")


def test_a_wrong_answer_changes_nothing_and_says_nothing(signed_in) -> None:
    signed_in.get("/logout")
    page = signed_in.form("/forgot", answer0="Rex", answer1="Wrong Street",
                          password="a-different-one",
                          confirm="a-different-one").read().decode()
    assert "do not match" in page
    assert "First street?" not in page.split("do not match")[1][:200]
    assert signed_in.accounts.check("sam", "a-good-password")
    assert not signed_in.accounts.check("sam", "a-different-one")


def test_the_two_new_passwords_have_to_agree(signed_in) -> None:
    page = signed_in.form("/forgot", answer0="Rex", answer1="Baker Street",
                          password="a-different-one",
                          confirm="a-mistyped-one").read().decode()
    assert "not the same" in page
    assert signed_in.accounts.check("sam", "a-good-password")


def test_guessing_is_locked_out_after_five_tries(signed_in) -> None:
    from accounts import RECOVERY_ATTEMPTS

    for _ in range(RECOVERY_ATTEMPTS):
        try:
            signed_in.form("/forgot", answer0="no", answer1="no",
                           password="a-different-one", confirm="a-different-one")
        except urllib.error.HTTPError as refused:
            assert refused.code == 429
    assert signed_in.accounts.recovery_locked_for() > 0

    with pytest.raises(urllib.error.HTTPError) as shut:
        signed_in.form("/forgot", answer0="Rex", answer1="Baker Street",
                       password="a-different-one", confirm="a-different-one")
    assert shut.value.code == 429
    assert signed_in.accounts.check("sam", "a-good-password")

    signed_in.get("/logout")
    signed_in.submit("/login", username="sam", password="a-good-password")
    assert signed_in.api(action="periods")["ok"]


def test_the_lockout_survives_a_restart(signed_in, tmp_path) -> None:
    from accounts import RECOVERY_ATTEMPTS

    for _ in range(RECOVERY_ATTEMPTS):
        try:
            signed_in.form("/forgot", answer0="no", answer1="no",
                           password="a-different-one", confirm="a-different-one")
        except urllib.error.HTTPError as refused:
            assert refused.code == 429

    import accounts
    fresh = accounts.Accounts(tmp_path / "users.json")
    assert fresh.recovery_locked_for() > 0


def test_the_questions_can_be_changed_while_signed_in(signed_in) -> None:
    page = signed_in.form("/security", password="a-good-password",
                          question0="A word only I know", answer0="periwinkle",
                          question1="First boss?", answer1="Mrs Hall").read().decode()
    assert "Saved" in page
    assert signed_in.accounts.recovery_questions() == [
        "A word only I know", "First boss?"]

    signed_in.get("/logout")
    signed_in.submit("/forgot", answer0="Periwinkle", answer1="mrs hall",
                   password="a-different-one", confirm="a-different-one")
    assert signed_in.accounts.check("sam", "a-different-one")


def test_changing_them_needs_the_password(signed_in) -> None:
    with pytest.raises(urllib.error.HTTPError) as refused:
        signed_in.form("/security", password="not-the-password",
                       question0="Mine now", answer0="hah",
                       question1="And this", answer1="hah")
    assert refused.value.code == 403
    assert signed_in.accounts.recovery_questions() == ["First pet?", "First street?"]


def test_the_recovery_pages_are_shut_to_a_stranger(signed_in) -> None:
    signed_in.get("/logout")
    landing = signed_in.get("/security")
    assert "Sign in" in landing.read().decode()

    with pytest.raises(urllib.error.HTTPError) as shut:
        signed_in.form("/security", password="a-good-password",
                       question0="a", answer0="b", question1="c", answer1="d")
    assert shut.value.code == 401


def test_an_account_without_questions_is_told_what_to_do(app) -> None:
    app.accounts.add("sam", "a-good-password")
    page = app.get("/forgot").read().decode()
    assert "No recovery questions" in page
    assert "data/users.json" in page
    assert "/security" in page


def test_the_ceilings_are_what_was_asked_for() -> None:
    from budget import groups, left
    assert (groups.MAX_MAJORS, groups.MAX_MINORS, groups.MAX_LIMITS) == (200, 500, 200)
    assert left.MAX_SLOTS == 20


def test_the_sign_in_pages_offer_both_languages(app) -> None:
    seen = {"setup": app.get("/").read().decode(),
            "setup, at /login": app.get("/login").read().decode()}
    app.submit("/setup", **SETUP)
    seen["security"] = app.get("/security").read().decode()
    app.get("/logout")
    seen["login"] = app.get("/login").read().decode()
    seen["forgot"] = app.get("/forgot").read().decode()
    for name, page in seen.items():
        assert '<html lang="en">' in page, name
        assert 'English · <a href="?lang=ru" lang="ru" hreflang="ru">Русский</a>' in page, name
        assert "<script" not in page, name
    assert '<input type="hidden" name="lang" value="en">' in seen["setup"]


def test_a_language_link_sets_the_cookie_and_the_page_follows_it(app) -> None:
    first = app.get("/?lang=ru")
    page = first.read().decode()
    assert '<html lang="ru">' in page and "<h1>Первый запуск</h1>" in page
    assert '<input type="hidden" name="lang" value="ru">' in page
    assert '<a href="?lang=en" lang="en" hreflang="en">English</a> · Русский' in page
    assert '<option value="Как звали вашего первого питомца?">' in page
    cookie = first.headers.get("Set-Cookie", "")
    assert cookie.startswith("budget_lang=ru;"), cookie
    for part in ("Path=/", "SameSite=Strict", "Max-Age=157680000"):
        assert part in cookie, cookie
    assert "HttpOnly" not in cookie

    again = app.get("/login")
    assert '<html lang="ru">' in again.read().decode()
    assert again.headers.get("Set-Cookie") is None

    assert "<h1>Set up</h1>" in app.get("/?lang=en").read().decode()
    assert '<html lang="en">' in app.get("/").read().decode()

    odd = app.get("/?lang=xx")
    assert '<html lang="en">' in odd.read().decode()
    assert odd.headers.get("Set-Cookie") is None


def test_a_refusal_is_said_in_the_language_of_the_page(app) -> None:
    english = app.form("/setup", username="a", password="a-good-password").read().decode()
    assert "a name is 2 to 32 characters" in english
    russian = app.form("/setup", username="a", password="a-good-password",
                       lang="ru").read().decode()
    assert '<html lang="ru">' in russian and "2 to 32" not in russian
    assert "имя — от 2 до 32 символов: буквы любого алфавита" in russian
    short = app.form("/setup", username="Анна", password="short", lang="ru").read().decode()
    assert "пароль — не короче 8 символов" in short
    bare = app.form("/setup", username="Анна", password="a-good-password",
                    lang="ru").read().decode()
    assert "задайте хотя бы 2 вопроса, каждый с ответом" in bare
    assert app.accounts.empty

    app.submit("/setup", **SETUP)
    app.get("/logout")
    wrong = app.form("/login?lang=ru", username="sam", password="wrong").read().decode()
    assert "Имя и пароль не совпадают." in wrong
    differ = app.form("/forgot", answer0="Rex", answer1="Baker Street",
                      password="a-different-one", confirm="a-mistyped-one").read().decode()
    assert "Пароли не совпадают." in differ
    unlike = app.form("/forgot", answer0="Rex", answer1="Wrong Street",
                      password="a-different-one", confirm="a-different-one").read().decode()
    assert "Ответы не подходят. Ничего не изменено." in unlike
    assert "First pet?" in unlike and "First street?" in unlike


def test_russian_pages_count_in_russian() -> None:
    import pages

    for minutes, word in ((1, "минуту"), (2, "минуты"), (5, "минут"), (11, "минут"),
                          (21, "минуту"), (22, "минуты")):
        page = pages.forgot_page(["a?", "b?"], locked_for=minutes * 60, lang="ru")
        assert f"Восстановление закрыто ещё на {minutes} {word}." in page, minutes
    assert "Ответьте на оба вопроса" in pages.forgot_page(["a?", "b?"], lang="ru")
    assert "Ответьте на все 3 вопроса" in pages.forgot_page(["a?", "b?", "c?"], lang="ru")
    assert "У вас 1 контрольный вопрос. Сохранение заменит его" in pages.security_page(
        ["a?"], lang="ru")
    assert "У вас 2 контрольных вопроса. Сохранение заменит их" in pages.security_page(
        ["a?", "b?"], lang="ru")
    assert "У вас 5 контрольных вопросов." in pages.security_page(list("abcde"), lang="ru")
    assert "closed for another 1 minute.\n" in pages.forgot_page(["a?"], locked_for=60)


def test_a_russian_page_has_no_english_left() -> None:
    import html.parser

    import pages

    class Texts(html.parser.HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.found: set[str] = set()
            self.skip = 0

        def handle_starttag(self, tag, attrs):
            self.skip += tag in ("style", "script")
            for name, value in attrs:
                if name in ("placeholder", "title") or (tag == "option" and name == "value"):
                    self.found.add(" ".join((value or "").split()))

        def handle_endtag(self, tag):
            self.skip -= tag in ("style", "script")

        def handle_data(self, data):
            if not self.skip and data.strip():
                self.found.add(" ".join(data.split()))

    def texts(markup: str) -> set[str]:
        parser = Texts()
        parser.feed(markup)
        return parser.found

    asked = ["Typed question one?", "Typed question two?"]
    variants = [
        lambda **k: pages.login_page("x", **k),
        lambda **k: pages.setup_page(**k),
        lambda **k: pages.forgot_page(asked, **k),
        lambda **k: pages.forgot_page(asked + ["Typed question three?"], **k),
        lambda **k: pages.forgot_page([], **k),
        lambda **k: pages.forgot_page(asked, locked_for=300, **k),
        lambda **k: pages.security_page(asked, saved=True, **k),
        lambda **k: pages.security_page(asked[:1], **k),
        lambda **k: pages.security_page([], **k),
    ]
    kept = {"English", "·", "x", "data/store.json", "data/users.json", "/security",
            "PBKDF2-SHA256", *asked, "Typed question three?"}
    for number, draw in enumerate(variants):
        english, russian = texts(draw()), texts(draw(lang="ru"))
        assert (english & russian) - kept == set(), (number, (english & russian) - kept)
        assert "· Русский" in russian, number


def test_every_page_text_has_its_russian() -> None:
    import ast
    import re

    import pages

    used: dict[str, set[str]] = {}

    def collect(file: str, callee: str, at: int) -> None:
        for node in ast.walk(ast.parse((LOCAL / file).read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == callee and len(node.args) > at):
                continue
            key = node.args[at]
            keys = [key.body, key.orelse] if isinstance(key, ast.IfExp) else [key]
            for one in keys:
                if isinstance(one, ast.Constant) and isinstance(one.value, str):
                    used.setdefault(one.value, set()).update(
                        k.arg for k in node.keywords if k.arg)

    collect("pages.py", "w", 0)
    collect("serve.py", "say", 0)
    collect("accounts.py", "Refused", 1)
    assert len(used) > 50, sorted(used)
    for key, given in used.items():
        assert key in pages.RU, key
        wanted = set(re.findall(r"\{(\w+)", pages.RU[key]))
        assert wanted <= given, (key, wanted - given)
    assert set(pages.RU) == set(used), set(pages.RU) ^ set(used)


def test_a_cyrillic_account_name_passes_the_form_pattern(app) -> None:
    import html as markup
    import re

    import accounts

    page = app.get("/").read().decode()
    pattern = markup.unescape(
        re.search(r'name="username"[^>]*?pattern="([^"]*)"', page).group(1))
    assert pattern == r"[\p{L}\p{N}._\-]{2,32}"
    python = re.compile(pattern.replace(r"\p{L}\p{N}", r"\w"))
    for name in ("Анна", "anna", "Ann-Marie.K_2", "Ωμέγα", "李雷", "a", "a b",
                 "ab/cd", "x" * 32, "x" * 33, ""):
        assert bool(python.fullmatch(name)) == bool(accounts._NAME.match(name)), name
    assert python.fullmatch("Анна")
    assert not python.fullmatch("a") and not python.fullmatch("a b")

    app.submit("/setup", **dict(SETUP, username="Анна"))
    assert list(app.accounts.users) == ["Анна"]
    assert app.api(action="periods")["ok"]


_BROWSERS = (
    "chrome",
    "google-chrome",
    "chromium",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)


def test_a_browser_takes_a_cyrillic_name_and_refuses_a_short_one(tmp_path) -> None:
    import re
    import shutil
    import subprocess

    import pages

    browser = next((found for name in _BROWSERS
                    if (found := shutil.which(name) or (name if Path(name).exists() else None))),
                   None)
    if browser is None:
        pytest.skip("no Chrome or Edge installed - the browser's check skipped")
    probe = """<script>
const box = document.querySelector('input[name="username"]');
const said = [];
for (const name of ["Анна", "anna.k-1_2", "a", "a b"]) {
  box.value = name;
  said.push(name + "=" + box.checkValidity());
}
document.title = "VALIDITY " + said.join(" ");
</script>"""
    harness = tmp_path / "setup.html"
    harness.write_text(pages.setup_page(lang="ru").replace("</body>", probe + "</body>"),
                       encoding="utf-8")
    done = subprocess.run(
        [browser, "--headless", "--disable-gpu", "--no-sandbox",
         f"--user-data-dir={tmp_path / 'profile'}", "--dump-dom", harness.as_uri()],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    title = re.search(r"<title>(.*?)</title>", done.stdout)
    assert title, done.stdout[-2000:] + done.stderr[-2000:]
    assert title.group(1) == "VALIDITY Анна=true anna.k-1_2=true a=false a b=false"


def test_the_guide_follows_the_language_and_falls_back_to_english(
        app, tmp_path, monkeypatch) -> None:
    import guide

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "GUIDE.md").write_text("# The guide\n\nIn English.\n", encoding="utf-8")
    monkeypatch.setattr(guide, "HERE", docs)

    page = app.get("/guide?lang=ru").read().decode()
    assert '<html lang="ru">' in page and ">Справка</a>" in page
    assert ">Вернуться в приложение</a>" in page
    assert '<div lang="en">\n<h1 id="the-guide">The guide</h1>' in page
    assert '<a href="?lang=en" lang="en" hreflang="en">English</a>' in page

    (docs / "GUIDE.ru.md").write_text(
        "# Справка\n\nПо-русски, и [README](README.ru.md#первый-запуск).\n", encoding="utf-8")
    page = app.get("/guide").read().decode()
    assert '<html lang="ru">' in page and '<div lang="en">' not in page
    assert '<h1 id="справка">Справка</h1>' in page
    assert 'href="/readme#первый-запуск"' in page

    page = app.get("/guide?lang=en").read().decode()
    assert '<html lang="en">' in page and "In English." in page
    assert '<div lang="en">' not in page
    assert ">Back to the app</a>" in page
    assert '<a href="?lang=ru" lang="ru" hreflang="ru">Русский</a>' in page


def test_level_four_headings_render() -> None:
    import guide

    out = guide._blocks("#### When a month closes\n\ntext\n##### not a heading\n")
    assert '<h4 id="when-a-month-closes">When a month closes</h4>' in out
    assert "##### not a heading" in out


def test_the_page_is_told_its_language_and_household(app) -> None:
    assert '"lang": "en", "household": "en"' in app.get("/config.js").read().decode()
    app.get("/?lang=ru")
    assert '"lang": "ru", "household": "en"' in app.get("/config.js").read().decode()


def test_a_copy_set_up_in_russian_greets_in_russian(app, tmp_path) -> None:
    (tmp_path / "household").write_text("ru", encoding="utf-8")
    assert '<html lang="ru">' in app.get("/").read().decode()

    bare = urllib.request.urlopen(app.base + "/config.js", timeout=60)
    assert '"lang": "ru"' in bare.read().decode()
    assert bare.headers.get("Set-Cookie", "").startswith("budget_lang=ru;")

    chose = urllib.request.urlopen(urllib.request.Request(
        app.base + "/config.js", headers={"Cookie": "budget_lang=en"}), timeout=60)
    assert '"lang": "en"' in chose.read().decode()
    assert chose.headers.get("Set-Cookie") is None

    for damaged in (b"\xff\xfe\x00", b"klingon"):
        (tmp_path / "household").write_bytes(damaged)
        assert '<html lang="en">' in urllib.request.urlopen(app.base + "/", timeout=60).read().decode()


SERVE_THERE = (
    "import sys; sys.path.insert(0, sys.argv[1]); "
    "import accounts; accounts._ITERATIONS = 1000; "
    "import serve; raise SystemExit(serve.main(sys.argv[2:]))"
)


def _plain_env() -> dict:
    import os

    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONIOENCODING", "PYTHONUTF8", "BUDGET_RULES")}
    env.update(PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1")
    return env


def _copy_of_the_app(where: Path, russian: bool = True) -> tuple[Path, str, str]:
    import re
    import shutil

    copy = where / "copy"
    (copy / "web").mkdir(parents=True)
    for name in ("serve.py", "pages.py", "accounts.py", "guide.py", "local_ocr.py"):
        shutil.copy2(LOCAL / name, copy / name)
    shutil.copytree(LOCAL / "app" / "budget", copy / "app" / "budget",
                    ignore=shutil.ignore_patterns("__pycache__", "*.toml"))
    rules = (LOCAL / "clean" / "rules.toml").read_text(encoding="utf-8")
    english = "Repairs"
    before = '[[groups.majors]]\nname = "Set aside"'
    assert rules.count(before) == 1, "the household the app starts from changed shape"
    rules = rules.replace(before, '[[groups.majors]]\nname = "Repairs"\ntier = "OCCASIONAL"\n'
                                  'minors = ["Repairs"]\n\n' + before)
    assert len(re.findall(rf'^name = "{english}"$', rules, re.MULTILINE)) == 1
    (copy / "app" / "budget" / "rules.toml").write_text(rules, encoding="utf-8")
    (copy / "web" / "index.html").write_text("<!doctype html><title>the page</title>",
                                             encoding="utf-8")
    other = "Ремонт"
    if russian:
        renamed = rules.replace(f'name = "{english}"', f'name = "{other}"')
        (copy / "app" / "budget" / "rules.ru.toml").write_text(renamed, encoding="utf-8")
    return copy, english, other


class _Declined(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


class _Running:
    def __init__(self, copy: Path, where: Path, env: dict | None = None) -> None:
        import subprocess
        import time

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.log = where / f"serve-{self.port}.log"
        with self.log.open("wb") as out:
            self.proc = subprocess.Popen(
                [sys.executable, "-B", "-c", SERVE_THERE, str(copy),
                 "--port", str(self.port), "--no-browser"],
                stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                env=env or _plain_env(), cwd=str(where))
        jar = http.cookiejar.CookieJar()
        self._open = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)).open
        self._quiet = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar), _Declined).open
        deadline = time.time() + 60
        while True:
            try:
                urllib.request.urlopen(self.base + "/favicon.ico", timeout=5).read()
                return
            except OSError:
                if self.proc.poll() is not None:
                    raise AssertionError("the server stopped:\n" + self.said()) from None
                if time.time() > deadline:
                    raise AssertionError("the server never answered:\n" + self.said()) from None
                time.sleep(0.2)

    def said(self) -> str:
        return self.log.read_bytes().decode("utf-8", errors="replace")

    def get(self, path: str) -> str:
        for last in (False, True):
            try:
                with self._open(self.base + path, timeout=60) as reply:
                    return reply.read().decode()
            except ConnectionResetError:
                if last:
                    raise
        raise AssertionError("unreachable")

    def api(self, **body) -> dict:
        request = urllib.request.Request(
            self.base + "/api", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with self._open(request, timeout=60) as reply:
            return json.loads(reply.read())

    def _post(self, path: str, **fields) -> None:
        from urllib.parse import urlencode
        try:
            self._quiet(self.base + path, data=urlencode(fields).encode(), timeout=60)
        except urllib.error.HTTPError as stopped:
            assert stopped.code == 303, (path, stopped.code, stopped.read()[:500])
            return
        raise AssertionError(f"{path} did not sign in")

    def setup(self, **fields) -> None:
        self._post("/setup", **{**SETUP, **fields})

    def sign_in(self) -> None:
        self._post("/login", username=SETUP["username"], password=SETUP["password"])

    def majors(self) -> list[str]:
        reply = self.api(action="config")
        assert reply["ok"], reply
        return [m["name"] for m in reply["result"]["majors"]]

    def stop(self) -> None:
        import subprocess
        self.proc.terminate()
        try:
            self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=20)


@pytest.fixture()
def served():
    running: list[_Running] = []

    def start(copy: Path, where: Path, env: dict | None = None) -> _Running:
        running.append(_Running(copy, where, env))
        return running[-1]

    try:
        yield start
    finally:
        for one in running:
            one.stop()


def _month_one() -> str:
    return (LOCAL / "clean" / "examples" / "month-1.txt").read_text(encoding="utf-8")


def test_the_console_speaks_english_only(tmp_path, served) -> None:
    import subprocess

    copy, _, _ = _copy_of_the_app(tmp_path)
    app = served(copy, tmp_path)
    app.stop()
    lines = app.log.read_bytes().decode("utf-8").splitlines()
    assert f"  Budget tracker - {app.base}" in lines
    assert "  Keep this window open while you use the app." in lines
    assert "  Ctrl-C to stop. Nothing here talks to the internet." in lines
    import re
    cyrillic = re.compile("[\u0400-\u04ff]")
    assert not any(cyrillic.search(line) for line in lines), lines

    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]
        done = subprocess.run(
            [sys.executable, "-B", str(copy / "serve.py"), "--port", str(port), "--no-browser"],
            capture_output=True, env=_plain_env(), cwd=str(tmp_path), timeout=120)
    said = done.stderr.decode("utf-8")
    assert done.returncode == 1, said
    assert f"! cannot listen on 127.0.0.1:{port} - " in said
    assert "  Something else is using that port, or a copy is already running.\n" in said.replace("\r", "")
    assert not cyrillic.search(said), said


def test_an_output_without_cyrillic_does_not_stop_the_server(tmp_path, served) -> None:
    copy, _, _ = _copy_of_the_app(tmp_path)
    app = served(copy, tmp_path, env=dict(_plain_env(), PYTHONIOENCODING="ascii"))
    assert '"local": true' in app.get("/config.js")
    app.stop()
    said = app.log.read_bytes().decode("ascii")
    assert f"  Budget tracker - {app.base}" in said
    assert "\\u0423\\u0447\\u0451\\u0442" not in said
    assert "Traceback" not in said


def test_setup_in_russian_starts_the_russian_example_household(tmp_path, served) -> None:
    copy, english, russian = _copy_of_the_app(tmp_path)
    app = served(copy, tmp_path)
    assert '<input type="hidden" name="lang" value="ru">' in app.get("/?lang=ru")
    app.setup(lang="ru")
    majors = app.majors()
    assert russian in majors and english not in majors
    assert (copy / "data" / "household").read_text(encoding="utf-8") == "ru"
    assert app.api(action="household")["result"] == {
        "household": "ru", "offered": ["en", "ru"], "swapped": False}
    config = app.get("/config.js")
    assert '"lang": "ru"' in config and '"household": "ru"' in config


def test_a_used_app_keeps_its_household_when_the_language_changes(tmp_path, served) -> None:
    copy, english, russian = _copy_of_the_app(tmp_path)
    marker = copy / "data" / "household"
    app = served(copy, tmp_path)
    app.setup(lang="en")
    assert english in app.majors() and not marker.exists()

    assert app.api(action="household", lang="ru")["result"] == {
        "household": "ru", "offered": ["en", "ru"], "swapped": True}
    assert russian in app.majors() and marker.read_text(encoding="utf-8") == "ru"
    assert app.api(action="household", lang="en")["result"]["swapped"]
    assert english in app.majors() and not marker.exists()

    assert app.api(action="import", text=_month_one(), year=2026)["ok"]
    assert app.api(action="household", lang="ru")["result"] == {
        "household": "en", "offered": ["en", "ru"], "swapped": False}
    assert english in app.majors() and not marker.exists()


def test_start_over_everything_brings_the_household_of_the_language(tmp_path, served) -> None:
    import re

    copy, english, russian = _copy_of_the_app(tmp_path)
    marker = copy / "data" / "household"
    app = served(copy, tmp_path)
    app.setup(lang="en")
    assert app.api(action="import", text=_month_one(), year=2026)["ok"]
    month = app.api(action="periods")["result"][-1]["month"]
    line = next(text for text in _month_one().splitlines()
                if re.match(r"\d[\d ]*\s+[^\d\s.]", text))
    moved = app.api(action="move", period=month, raw=line, occurrence=0,
                    group="Kept aside", new=True, override=True)
    assert moved["ok"], moved

    reset = app.api(action="reset", scope="all", confirm="RESET", lang="ru")
    assert reset["ok"] and set(reset["result"]) == {"scope", "wiped"}
    assert json.loads((copy / "data" / "store.json").read_text(encoding="utf-8"))["moves"]
    assert russian in app.majors() and marker.read_text(encoding="utf-8") == "ru"

    assert app.api(action="reset", scope="all", confirm="RESET")["ok"]
    assert english in app.majors() and not marker.exists()


def test_a_build_with_its_own_rules_never_swaps_them(tmp_path, served) -> None:
    copy, english, _ = _copy_of_the_app(tmp_path, russian=False)
    marker = copy / "data" / "household"
    app = served(copy, tmp_path)
    app.setup(lang="ru")
    assert app.api(action="household", lang="ru")["result"] == {
        "household": "en", "offered": ["en"], "swapped": False}
    assert english in app.majors() and not marker.exists()
    config = app.get("/config.js")
    assert '"lang": "ru"' in config and '"household": "en"' in config
    assert app.api(action="reset", scope="all", confirm="RESET", lang="ru")["ok"]
    assert english in app.majors() and not marker.exists()
    app.stop()

    both = tmp_path / "both"
    both.mkdir()
    copy, english, _ = _copy_of_the_app(both)
    named = dict(_plain_env(), BUDGET_RULES=str(copy / "app" / "budget" / "rules.toml"))
    app = served(copy, both, env=named)
    app.setup(lang="ru")
    assert app.api(action="household", lang="ru")["result"] == {
        "household": "en", "offered": [], "swapped": False}
    assert english in app.majors() and not (copy / "data" / "household").exists()


def test_a_russian_household_is_in_place_after_a_restart(tmp_path, served, monkeypatch) -> None:
    import re

    import accounts

    copy, english, russian = _copy_of_the_app(tmp_path)
    month_text = _month_one()
    ru_rules = LOCAL / "clean" / "ru" / "rules.toml"
    ru_month = LOCAL / "clean" / "ru" / "examples" / "month-1.txt"
    if ru_rules.is_file() and ru_month.is_file():
        text = ru_rules.read_text(encoding="utf-8")
        (copy / "app" / "budget" / "rules.ru.toml").write_text(text, encoding="utf-8")
        month_text = ru_month.read_text(encoding="utf-8")
        ours = set(re.findall(r'^name = "([^"]+)"', (LOCAL / "clean" / "rules.toml").read_text(
            encoding="utf-8"), re.MULTILINE))
        russian = next(n for n in re.findall(r'^name = "([^"]+)"', text, re.MULTILINE)
                       if n not in ours)
    monkeypatch.setattr(accounts, "_ITERATIONS", 1000)
    (copy / "data").mkdir()
    accounts.Accounts(copy / "data" / "users.json").add(SETUP["username"], SETUP["password"])
    (copy / "data" / "household").write_text("ru", encoding="utf-8")

    def left_of(app) -> list:
        month = app.api(action="periods")["result"][-1]["month"]
        left = app.api(action="totals", period=month)["result"]["left"]
        return [(cell["id"], cell["value"]) for cell in (left or {}).get("cells", [])]

    app = served(copy, tmp_path)
    app.sign_in()
    assert russian in app.majors()
    assert app.api(action="household")["result"]["household"] == "ru"
    assert app.api(action="import", text=month_text, year=2026)["ok"]
    read = left_of(app)
    assert read and all(value is not None for _, value in read), read
    app.stop()

    app = served(copy, tmp_path)
    app.sign_in()
    assert russian in app.majors()
    assert left_of(app) == read


def test_restoring_a_file_of_the_other_household_brings_that_household(tmp_path, served) -> None:
    copy, english, russian = _copy_of_the_app(tmp_path)
    marker = copy / "data" / "household"
    app = served(copy, tmp_path)
    app.setup(lang="ru")
    assert app.api(action="import", text=_month_one(), year=2026)["ok"]
    backup = app.api(action="backup")["result"]
    assert app.api(action="reset", scope="all", confirm="RESET")["ok"]
    assert english in app.majors() and not marker.exists()

    newer = dict(backup, version=backup["version"] + 1)
    assert not app.api(action="restore", backup=newer, confirm="RESTORE")["ok"]
    assert english in app.majors() and not marker.exists()

    restored = app.api(action="restore", backup=backup, confirm="RESTORE")
    assert restored["ok"] and restored["result"]["rules"] == "same", restored
    assert russian in app.majors() and marker.read_text(encoding="utf-8") == "ru"
    assert [p["month"] for p in app.api(action="periods")["result"]
            if not p["moved"]] == ["January"]


def _engine_with(where: Path, *models: str) -> Path:
    (where / "tessdata").mkdir(parents=True)
    for code in models:
        (where / "tessdata" / f"{code}.traineddata").write_bytes(b"")
    engine = where / "tesseract.exe"
    engine.write_bytes(b"")
    return engine


def _rules_naming(monkeypatch, notes: dict | None) -> None:
    import types

    rules = {"version": 1} if notes is None else {"version": 1, "notes": notes}
    monkeypatch.setitem(sys.modules, "budget.rules", types.SimpleNamespace(RULES=rules))


def _tesseract_saying(monkeypatch, stdout: bytes, stderr: bytes = b"") -> list[str]:
    import types

    import local_ocr

    handed: list[str] = []

    def run(args, **_):
        handed.append(args[args.index("-l") + 1])
        return types.SimpleNamespace(returncode=0, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(local_ocr, "subprocess", types.SimpleNamespace(run=run))
    return handed


A_SHOT = "data:image/png;base64,bm90IGEgcGljdHVyZQ=="


def test_ocr_languages_follow_the_household(tmp_path, monkeypatch, capsys) -> None:
    import local_ocr

    both = _engine_with(tmp_path / "both", "eng", "rus")
    monkeypatch.setattr(local_ocr, "BUNDLED", both)
    monkeypatch.setattr(local_ocr, "_SAID", set())

    monkeypatch.delitem(sys.modules, "budget.rules", raising=False)
    assert local_ocr.languages() == "eng"
    _rules_naming(monkeypatch, None)
    assert local_ocr.languages() == "eng"
    _rules_naming(monkeypatch, {"left": "L?eft"})
    assert local_ocr.languages() == "eng"
    _rules_naming(monkeypatch, {"ocr": "rus+eng"})
    assert local_ocr.languages() == "rus+eng"
    _rules_naming(monkeypatch, {"ocr": "eng --psm 0"})
    assert local_ocr.languages() == "eng"
    assert capsys.readouterr().err == ""

    _rules_naming(monkeypatch, {"ocr": "rus+eng"})
    older = _engine_with(tmp_path / "older", "eng")
    assert local_ocr.languages(older) == "eng"
    assert local_ocr.languages(older) == "eng"
    said = capsys.readouterr().err
    assert said.count("rus.traineddata") == 1, said
    assert "python fetch_runtime.py --ocr" in said and said.isascii(), said

    handed = _tesseract_saying(monkeypatch, b"740 taxi\r\n")
    assert local_ocr.extract(A_SHOT) == "740 taxi\n"
    monkeypatch.setattr(local_ocr, "BUNDLED", older)
    assert local_ocr.extract(A_SHOT) == "740 taxi\n"
    _rules_naming(monkeypatch, None)
    monkeypatch.setattr(local_ocr, "BUNDLED", both)
    assert local_ocr.extract(A_SHOT) == "740 taxi\n"
    assert handed == ["rus+eng", "eng", "eng"]


def test_a_russian_reading_keeps_each_word_in_one_alphabet(tmp_path, monkeypatch,
                                                           capsys) -> None:
    import local_ocr

    to_latin = str.maketrans("\u041e\u0430\u0441\u043a\u0440\u043e\u0445\u0435", "Oackpoxe")
    russian = ("Остаток", "такси", "картой", "домой")
    assert all("\u0400" <= c <= "\u04ff" for word in russian for c in word)
    for word in russian:
        mixed = word.translate(to_latin)
        assert mixed != word and any(c.isascii() for c in mixed)
        assert local_ocr._one_alphabet(mixed) == word, mixed
    for word, mixed in (("taxi", "t\u0430\u0445i"), ("Left", "L\u0435ft"),
                        ("card", "\u0441\u0430rd")):
        assert local_ocr._one_alphabet(mixed) == word, mixed
    for as_read in ("t\u0430\u043a\u0441\u0438",
                    "Остаток: наличные 6,8, счёт 61240\n740 такси домой\nLeft: purse 6.8, account 61240\n"
                    "Кофе, сок, Ecco, 2к\n"):
        assert local_ocr._one_alphabet(as_read) == as_read

    monkeypatch.setattr(local_ocr, "BUNDLED", _engine_with(tmp_path / "both", "eng", "rus"))
    monkeypatch.setattr(local_ocr, "_SAID", set())
    read = "Остаток: наличные 6,8\n740 taxi домой\n".translate(to_latin)
    _tesseract_saying(monkeypatch, read.encode())
    _rules_naming(monkeypatch, {"ocr": "rus+eng"})
    assert local_ocr.extract(A_SHOT) == "Остаток: наличные 6,8\n740 taxi домой\n"
    _rules_naming(monkeypatch, None)
    assert local_ocr.extract(A_SHOT) == read
    assert capsys.readouterr().err == ""

    _tesseract_saying(monkeypatch, read.encode(), b"Failed loading language 'rus'\r\n")
    _rules_naming(monkeypatch, {"ocr": "rus+eng"})
    assert local_ocr.extract(A_SHOT) == read
    said = capsys.readouterr().err
    assert "could not load rus" in said and said.isascii(), said


RUSSIAN_DAY = ("12.03", "450", "740 такси домой", "2300 пекарня картой", "1250 чаевые",
               "Остаток: наличные 6,8, счёт 61240")


def _cyrillic_font() -> Path | None:
    import os

    fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for font in (fonts / "segoeui.ttf", fonts / "arial.ttf", fonts / "tahoma.ttf",
                 Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")):
        if font.is_file():
            return font
    return None


@pytest.mark.skipif(not TESSERACT.is_file(), reason="no bundled Tesseract in vendor/")
def test_the_bundled_tesseract_reads_russian(signed_in, monkeypatch) -> None:
    import base64
    import io

    pytest.importorskip("PIL")
    from PIL import Image, ImageDraw, ImageFont

    import budget.rules

    font = _cyrillic_font()
    if font is None:
        pytest.skip("no font with Cyrillic letters on this machine")
    assert (TESSERACT.parent / "tessdata" / "rus.traineddata").is_file(), \
        "no Russian model in vendor/tesseract/tessdata - run: python fetch_runtime.py --ocr"

    face = ImageFont.truetype(str(font), 32)
    picture = Image.new("RGB", (1240, 60 * len(RUSSIAN_DAY) + 40), "white")
    draw = ImageDraw.Draw(picture)
    for row, line in enumerate(RUSSIAN_DAY):
        draw.text((48, 30 + 60 * row), line, fill="black", font=face)
    png = io.BytesIO()
    picture.save(png, format="PNG")
    shot = "data:image/png;base64," + base64.b64encode(png.getvalue()).decode()

    monkeypatch.setitem(budget.rules.RULES, "notes", {"ocr": "rus+eng"})
    text = signed_in.api(action="ocr", image=shot)["result"]["text"]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    assert lines[0] == "12.03", lines
    for wanted in RUSSIAN_DAY[1:]:
        assert any(wanted in line for line in lines), (wanted, lines)
    letters = [c for c in text if c.isalpha()]
    assert letters and all("\u0400" <= c <= "\u04ff" for c in letters), text

    monkeypatch.setitem(budget.rules.RULES, "notes", {"ocr": "eng"})
    english = signed_in.api(action="ocr", image=shot)["result"]["text"]
    assert english.strip() and not any("\u0400" <= c <= "\u04ff" for c in english), english


def test_the_russian_model_is_kept_only_once_its_bytes_are_checked(tmp_path,
                                                                    monkeypatch) -> None:
    import hashlib

    import fetch_runtime

    tessdata = tmp_path / "tesseract" / "tessdata"
    tessdata.mkdir(parents=True)
    model = tessdata / "rus.traineddata"
    asked: list[str] = []

    def serving(blob: bytes):
        def download(url, timeout=900):
            asked.append(url)
            return blob
        return download

    monkeypatch.setattr(fetch_runtime, "_download", serving(b"not the model"))
    assert fetch_runtime.fetch_russian(tessdata.parent) == 1
    assert asked == [fetch_runtime.RUSSIAN_DATA] and not list(tessdata.iterdir())

    pinned = b"a stand-in for the model"
    monkeypatch.setattr(fetch_runtime, "RUSSIAN_SHA256", hashlib.sha256(pinned).hexdigest())
    monkeypatch.setattr(fetch_runtime, "_download", serving(pinned))
    assert fetch_runtime.fetch_russian(tessdata.parent) == 0
    assert model.read_bytes() == pinned
    assert [p.name for p in tessdata.iterdir()] == ["rus.traineddata"]

    asked.clear()
    assert fetch_runtime.fetch_russian(tessdata.parent) == 0
    assert asked == []

    model.write_bytes(pinned[:5])
    monkeypatch.setattr(fetch_runtime, "_download", serving(b"still not it"))
    assert fetch_runtime.fetch_russian(tessdata.parent) == 1
    assert model.read_bytes() == pinned[:5]
    monkeypatch.setattr(fetch_runtime, "_download", serving(pinned))
    assert fetch_runtime.fetch_russian(tessdata.parent) == 0
    assert model.read_bytes() == pinned
