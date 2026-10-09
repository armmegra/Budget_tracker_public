"""Shaping the groups, the limits and the closing line - and what a closed month
refuses.

Nothing is recomputed wrongly by any of this, because no figure is stored: every
total is worked out from the notes each time, through whatever the groups are at
that moment for that month.
"""

from __future__ import annotations

import datetime

from budget import api
from conftest import Book


def configure(book: Book, **op):
    return book(action="configure", **op)


def setup(book: Book, month: str | None = None) -> dict:
    return book(action="config", period=month) if month else book(action="config")


# -- limits ----------------------------------------------------------------------


def test_a_limit_can_be_changed_and_taken_off(book: Book) -> None:
    configure(book, op="set_limit", major="Food", value=25)
    assert book(action="totals", period="January")["limits"][0] == {
        "label": "Food", "group": "Food", "value": 25}
    configure(book, op="set_limit", major="Food", value=None)
    assert [row["group"] for row in book(action="totals", period="January")["limits"]] == [
        "Road", "Medicine"]


def test_a_limit_added_later_joins_the_end_of_the_order(book: Book) -> None:
    """The order of the limits is the order they were set in. A limit set after
    that order was fixed once fell out of it, and with it out of the box."""
    configure(book, op="set_limit", major="Rent", value=12)
    assert setup(book)["limit_order"] == ["Food", "Road", "Medicine", "Rent"]


def test_a_limit_can_be_shown_under_another_name(book: Book) -> None:
    configure(book, op="rename_limit", major="Road", label="Getting about")
    labels = [row["label"] for row in book(action="totals", period="January")["limits"]]
    assert labels == ["Food", "Getting about", "Medicine"]


# -- groups ----------------------------------------------------------------------


def test_renaming_a_group_renames_the_line_that_shares_its_name(book: Book) -> None:
    """`Food` the heading and `Food` the line under it are two things with one
    name. Renaming the heading alone left the line reading `Food` under
    `Groceries`."""
    configure(book, op="rename_major", major="Food", name="Groceries")
    food = next(m for m in setup(book)["majors"] if m["name"] == "Food")
    assert food["label"] == "Groceries"
    assert [(n["name"], n["label"]) for n in food["minors"]] == [("Food", "Groceries")]
    assert book.majors("January")["Groceries"] == 19.8


def test_a_rename_changes_no_figure(book: Book) -> None:
    before = book(action="totals", period="January")["totals"]
    configure(book, op="rename_major", major="Food", name="Groceries")
    assert book(action="totals", period="January")["totals"] == before


def test_a_group_holding_lines_is_removed_only_with_somewhere_for_them(book: Book) -> None:
    """The rules keep writing into its lines, so they cannot simply vanish."""
    assert book.refused(action="configure", op="remove_major",
                        major="Medicine")["code"] == "minors_still_route"
    assert book.refused(action="configure", op="remove_major", major="Medicine",
                        minors_to="Medicine")["code"] == "minors_to_itself"


def test_removing_a_group_moves_its_money_and_loses_none(book: Book) -> None:
    before = book(action="totals", period="January")["totals"]
    configure(book, op="remove_major", major="Medicine", minors_to="Road")
    majors = book.majors("January")
    assert "Medicine" not in majors
    assert majors["Road"] == 6.6                       # 2.42 + 4.205
    assert book(action="totals", period="January")["totals"] == before


def test_a_new_group_can_be_added_with_its_limit(book: Book) -> None:
    configure(book, op="add_major", name="Hobbies", tier="FREQUENT", limit=6)
    hobbies = next(m for m in setup(book)["majors"] if m["name"] == "Hobbies")
    assert (hobbies["tier"], hobbies["limit"]) == ("FREQUENT", 6)
    assert "Hobbies" in setup(book)["limit_order"]


# -- the closing line ------------------------------------------------------------


def test_a_figure_of_the_closing_line_can_be_renamed(book: Book) -> None:
    configure(book, op="left_rename_slot", slot="purse", label="wallet", place="before", join=" ")
    assert [(s["id"], s["label"]) for s in setup(book)["left"]["slots"]] == [
        ("purse", "wallet"), ("account", "account")]


# -- which months a change is for --------------------------------------------------


def test_a_change_for_march_onward_leaves_the_earlier_months(book: Book) -> None:
    ops = [{"op": "set_limit", "major": "Road", "value": 5}]
    book(action="configure", scope="onward", period="March", ops=ops, confirm=True)

    def road(month: str) -> int:
        return next(row["value"] for row in book(action="totals", period=month)["limits"]
                    if row["group"] == "Road")

    assert (road("January"), road("February"), road("March")) == (10, 10, 5)


def test_a_change_for_one_month_is_previewed_before_it_is_made(book: Book) -> None:
    ops = [{"op": "set_limit", "major": "Road", "value": 5}]
    preview = book(action="configure", scope="month", period="February", ops=ops)
    assert preview["pending"] is True and preview["months"] == ["February 2026"]
    assert book(action="totals", period="February")["limits"][1]["value"] == 10


# -- closed months -----------------------------------------------------------------


def test_a_month_closes_three_months_after_it_ends(book: Book, monkeypatch) -> None:
    """January ends on the 27th, so it is open on the 26th of April and closed
    on the 1st of May. Nothing stores this: it is worked out from the date."""
    monkeypatch.setattr(api, "_today", lambda: datetime.date(2026, 4, 26))
    assert setup(book)["closed"] == []
    monkeypatch.setattr(api, "_today", lambda: datetime.date(2026, 5, 1))
    assert setup(book)["closed"] == ["salary:57300"]


def test_a_closed_month_refuses_a_change_and_says_how_to_make_it(book: Book, monkeypatch) -> None:
    monkeypatch.setattr(api, "_today", lambda: datetime.date(2026, 8, 1))
    number = 17                                         # `740 cinema`
    refused = book.refused(action="answer", period="January", number=number, group="Food")
    assert refused["code"] == "closed" and "read-only" in refused["error"]
    added = book.refused(action="import", text="28.01\n26 bus\n", period="January", year=2026)
    assert added["code"] == "closed"
    # Deliberately, for one request: the page's Unlock sends this.
    book(action="answer", period="January", number=number, group="Food", override=True)
    assert "740 cinema" not in book.asked("January")


def test_an_every_month_change_is_refused_while_months_are_closed(book: Book, monkeypatch) -> None:
    """It would rewrite months already read and printed. Scope it to a month and
    onward instead, or say outright that the closed ones are meant too."""
    monkeypatch.setattr(api, "_today", lambda: datetime.date(2026, 8, 1))
    refused = book.refused(action="configure", op="set_limit", major="Food", value=20)
    assert refused["code"] == "configure_closed"
    configure(book, op="set_limit", major="Food", value=20, override=True)
    assert book(action="totals", period="January")["limits"][0]["value"] == 20
