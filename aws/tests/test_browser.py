from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "web" / "index.html"
DRIVER = Path(__file__).parent / "browser_backup.js"

_CANDIDATES = (
    "chrome",
    "google-chrome",
    "chromium",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)


def _browser() -> str | None:
    for name in _CANDIDATES:
        found = shutil.which(name) or (name if Path(name).exists() else None)
        if found:
            return found
    return None


def _run(html: str, tmp_path: Path, browser: str) -> str:
    page = tmp_path / "harness.html"
    page.write_text(html, encoding="utf-8")
    done = subprocess.run(
        [
            browser,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            f"--user-data-dir={tmp_path / 'profile'}",
            "--virtual-time-budget=20000",
            "--dump-dom",
            page.as_uri(),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        encoding="utf-8",
        errors="replace",
    )
    return done.stdout


@pytest.fixture(scope="module")
def browser() -> str:
    found = _browser()
    if not found:
        pytest.skip("no Chrome or Edge installed - browser checks skipped")
    return found


def test_the_shipped_script_parses(tmp_path: Path, browser: str) -> None:
    script = _script_of(PAGE.read_text(encoding="utf-8"))
    assert "</script" not in script
    dom = _run(
        '<!doctype html><meta charset="utf-8"><title>PENDING</title>\n'
        '<script type="text/plain" id="src">' + script + "</script>\n"
        "<script>try { new Function(document.getElementById('src').textContent);"
        " document.title = 'PARSE-OK'; }"
        " catch (e) { document.title = 'PARSE-ERR ' + e.message; }</script>",
        tmp_path,
        browser,
    )
    assert "<title>PARSE-OK</title>" in dom, _title(dom)


def _drive(driver: Path, least: int, tmp_path: Path, browser: str) -> None:
    html = PAGE.read_text(encoding="utf-8")
    assert html.count("\nboot();\n") == 1
    harness = html.replace("\nboot();\n", "\n" + driver.read_text(encoding="utf-8") + "\n")
    dom = _run(harness, tmp_path, browser)

    lines = [
        line
        for line in re.sub(r"<[^>]*>", "", dom).splitlines()
        if line.startswith(("PASS ", "FAIL "))
    ]
    assert lines, f"the harness produced no results: {_title(dom)}"
    failed = [line for line in lines if line.startswith("FAIL")]
    assert not failed, "\n".join(failed)
    assert len(lines) >= least, f"only {len(lines)} checks ran"


def test_backup_and_the_three_step_restore(tmp_path: Path, browser: str) -> None:
    _drive(DRIVER, 43, tmp_path, browser)


def test_answering_and_comparing(tmp_path: Path, browser: str) -> None:
    _drive(Path(__file__).parent / "browser_questions.js", 36, tmp_path, browser)


def test_moving_any_minor_figure(tmp_path: Path, browser: str) -> None:
    _drive(Path(__file__).parent / 'browser_moves.js', 16, tmp_path, browser)


def test_the_words_the_user_teaches(tmp_path: Path, browser: str) -> None:
    _drive(Path(__file__).parent / "browser_words.js", 9, tmp_path, browser)


def _script_of(html: str) -> str:
    blocks = re.findall(r"<script>\n(.*?)\n</script>", html, re.S)
    assert len(blocks) == 1, f"expected one inline script, found {len(blocks)}"
    return blocks[0]


def _title(dom: str) -> str:
    found = re.search(r"<title>(.*?)</title>", dom, re.S)
    return found.group(1) if found else dom[:400]


def test_an_empty_app_draws_its_own_example(tmp_path: Path, browser: str) -> None:
    _drive(Path(__file__).parent / "browser_empty.js", 12, tmp_path, browser)


def test_start_over_says_what_went_and_then_puts_it_away(tmp_path: Path, browser: str) -> None:
    _drive(Path(__file__).parent / "browser_wipe.js", 11, tmp_path, browser)


def test_the_app_opens_on_the_newest_month(tmp_path: Path, browser: str) -> None:
    _drive(Path(__file__).parent / "browser_restore.js", 7, tmp_path, browser)


def test_switching_views_while_one_is_still_drawing(tmp_path: Path, browser: str) -> None:
    _drive(Path(__file__).parent / "browser_views.js", 6, tmp_path, browser)


def test_a_change_for_one_month_is_staged_and_applied(tmp_path: Path, browser: str) -> None:
    _drive(Path(__file__).parent / "browser_staged.js", 8, tmp_path, browser)


def test_the_setup_editors_do_what_was_chosen(tmp_path: Path, browser: str) -> None:
    _drive(Path(__file__).parent / "browser_setup.js", 14, tmp_path, browser)
