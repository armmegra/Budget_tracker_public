"""Fixtures for the AWS build's suite.

Every test here runs on the invented household in `src/budget/rules.toml` and
its three example months in `examples/`. Nothing in this repository is anybody's
real notes: the full suite of the original project runs against a real
household's months, which is exactly why it is not here, and these tests were
written for this copy to cover the same ground on invented data.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from budget import api
from budget.api import dispatch
from budget.store import Store

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"


@pytest.fixture(autouse=True)
def _pinned_today(monkeypatch):
    """A fixed today, 2026-04-01.

    Months close three months after they end, and the engine asks the real
    clock, so a suite that does not pin the date starts failing by itself as
    the calendar moves. On this day all three example months have ended and
    none has closed. A test about the closing rule sets its own today.
    """
    monkeypatch.setattr(api, "_today", lambda: datetime.date(2026, 4, 1))


def month_text(n: int) -> str:
    return (EXAMPLES / f"month-{n}.txt").read_text(encoding="utf-8")


class Book:
    """A store and the one way into it, as a front end uses it."""

    def __init__(self, path: Path) -> None:
        self.store = Store(path)

    @classmethod
    def reopened(cls, path: Path) -> "Book":
        """The store as it is on disk, the way a Lambda reads it for each request."""
        book = cls(path)
        book.store = Store.load(path)
        return book

    def reply(self, **event) -> dict:
        return dispatch(self.store, event)

    def __call__(self, **event):
        reply = self.reply(**event)
        assert reply["ok"], (event, reply)
        return reply["result"]

    def refused(self, **event) -> dict:
        reply = self.reply(**event)
        assert not reply["ok"], (event, reply)
        return reply

    def add(self, text: str, **more):
        return self(action="import", text=text, year=2026, **more)

    def majors(self, month: str) -> dict[str, float]:
        return {m["name"]: m["value"] for m in self(action="totals", period=month)["majors"]}

    def minors(self, month: str) -> dict[str, int]:
        return {m["name"]: m["total"] for m in self(action="totals", period=month)["minors"]}

    def asked(self, month: str) -> list[str]:
        return [q["raw"] for q in self(action="questions", period=month)]

    def question(self, month: str, raw: str) -> dict:
        return next(q for q in self(action="questions", period=month) if q["raw"] == raw)


@pytest.fixture()
def empty(tmp_path: Path) -> Book:
    return Book(tmp_path / "store.json")


@pytest.fixture()
def book(tmp_path: Path) -> Book:
    """January, February and March of the invented household."""
    b = Book(tmp_path / "store.json")
    for n in (1, 2, 3):
        b.add(month_text(n))
    return b
