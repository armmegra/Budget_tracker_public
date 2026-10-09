"""One file holds everything, and a restore shows what was saved.

The backup carries the months as written, every answer, move, tick and set
figure, the group edits - and the rules, because notes become figures only
through the rules. So the same file read by another build of the app gives the
same figures.
"""

from __future__ import annotations

import json
from pathlib import Path

from budget.rules import path_in_use
from conftest import Book


def as_a_browser_saves_it(value):
    """JSON.parse(JSON.stringify(value)): what a backup is by the time it comes
    back from a file. A float with nothing after the point is written as an
    integer, and keys that look like array indexes move to the front."""
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


def everything_shown(book: Book) -> dict:
    """Every reading the page and the printouts make, for every month stored."""
    shown = {"periods": book(action="periods"), "config": book(action="config")}
    months = [p["identity"] for p in shown["periods"]]
    for month in months:
        for action in ("show", "totals", "questions", "raw", "config"):
            shown[f"{month} {action}"] = book(action=action, period=month)
        for fmt in ("rtf", "txt"):
            shown[f"{month} print {fmt}"] = book(action="export", period=month, format=fmt)
    for fmt in ("rtf", "txt"):
        shown[f"year {fmt}"] = book(action="export", year=2026, format=fmt)
    shown["compare"] = book(action="compare", periods=months, average=True)
    return shown


def worked_on(book: Book) -> Book:
    """One of every kind of thing a person can do to a month."""
    wine = book.question("January", "480 wine")["number"]
    cinema = book.question("January", "740 cinema")["number"]
    book(action="answer", period="January", number=wine, group="Food")
    book(action="answer", period="January", number=cinema, group="Leisure", new=True)
    book(action="move", period="February", raw="980 haircut", occurrence=0, group="Medicine")
    book(action="adjust", period="January", group="Leisure", value=0.5)
    book(action="configure", op="learn_word", word="heating", group="Heating", new=True)
    book(action="omit", period="February", groups=["Heating"])
    book(action="configure", op="rename_major", major="Food", name="Groceries")
    book(action="configure", op="set_limit", major="Rent", value=12)
    book(action="configure", scope="onward", period="March", confirm=True,
         ops=[{"op": "set_limit", "major": "Road", "value": 5}])
    return book


def test_a_backup_says_what_it_holds(book: Book) -> None:
    backup = book(action="backup")
    assert backup["kind"] == "budget-backup" and backup["version"] == 1
    assert (backup["months"], backup["answers"]) == (3, 0)
    assert set(backup) == {"kind", "version", "saved", "months", "answers", "server", "rules"}


def test_a_backup_carries_the_rules_it_was_read_with(book: Book) -> None:
    assert book(action="backup")["rules"] == path_in_use().read_text(encoding="utf-8")


def test_a_backup_that_cannot_carry_the_rules_is_refused(book: Book, tmp_path: Path,
                                                       monkeypatch) -> None:
    """One file holds everything: none is written without them."""
    monkeypatch.setenv("BUDGET_RULES", str(tmp_path / "gone.toml"))
    assert "no backup was made" in book.refused(action="backup")["error"]


def test_a_restore_puts_back_exactly_what_was_there(book: Book, tmp_path: Path) -> None:
    """Every view and every printout, compared as text, before the backup and
    after the restore - onto a store that already holds something else, so a
    restore that merged instead of replacing would show."""
    source = worked_on(book)
    before = everything_shown(source)
    backup = as_a_browser_saves_it(source(action="backup"))

    target = Book(tmp_path / "elsewhere.json")
    target.add("12.01\n+ 41 500\n\n13.01\n500 bus\n")
    target(action="configure", op="add_major", name="Garden", tier="FREQUENT")

    said = target(action="restore", backup=backup, confirm="RESTORE")
    assert said["restored"] == {"months": 3, "answers": 2}
    assert said["replaced"] == {"months": 1, "answers": 0}

    after = everything_shown(Book.reopened(target.store.path))    # read back from disk
    assert after.keys() == before.keys()
    for view in before:
        assert json.dumps(after[view], ensure_ascii=False) == json.dumps(
            before[view], ensure_ascii=False), view


def test_a_restore_says_whether_the_files_rules_are_the_ones_in_use(book: Book,
                                                                  tmp_path: Path) -> None:
    """This build keeps its own rules - they belong to the code it runs - and
    only says when a file was made with others, since its months then read
    differently here from where the file was saved."""
    backup = book(action="backup")
    ours = backup["rules"]

    def said(document) -> str:
        return Book(tmp_path / "target.json")(action="restore", backup=document,
                                              confirm="RESTORE")["rules"]

    assert said(backup) == "same"
    assert said(dict(backup, rules=ours.replace("\n", "\r\n"))) == "same"     # a Windows copy
    assert said(dict(backup, rules=ours + "\n# another household\n")) == "different"
    assert said({k: v for k, v in backup.items() if k != "rules"}) == "absent"
    assert path_in_use().read_text(encoding="utf-8") == ours                 # never replaced


def test_a_restore_needs_its_confirmation(book: Book, empty: Book) -> None:
    """It replaces everything stored, so a request without the word does nothing."""
    backup = book(action="backup")
    assert "RESTORE" in empty.refused(action="restore", backup=backup)["error"]
    assert empty(action="periods") == []


def test_a_file_that_is_not_a_backup_is_refused_and_nothing_is_lost(book: Book) -> None:
    refused = book.refused(action="restore", backup={"kind": "something else"}, confirm="RESTORE")
    assert "not a budget backup" in refused["error"]
    assert len(book(action="periods")) == 3
