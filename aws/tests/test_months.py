"""Reading a month: periods, groups, the Totals, questions, limits, printouts.

The figures asserted here were worked out by hand from `examples/month-1.txt`
before the engine was asked, which is the only way a pinned figure is a test.
"""

from __future__ import annotations

from conftest import Book, month_text

JANUARY = {"Rent": 9.4, "Food": 19.8, "Road": 2.4, "Medicine": 4.2, "Refunds": -1.5}


def test_three_months_are_three_periods(book: Book) -> None:
    periods = book(action="periods")
    assert [(p["month"], p["year"], p["span"], p["days"]) for p in periods] == [
        ("January", 2026, "10.01..27.01", 13),
        ("February", 2026, "10.02..27.02", 13),
        ("March", 2026, "10.03..27.03", 13),
    ]


def test_a_month_is_identified_by_the_income_that_opens_it(book: Book) -> None:
    """Not by its name: two Januaries of different years would otherwise be one."""
    assert [p["identity"] for p in book(action="periods")] == [
        "salary:57300", "salary:58650", "salary:60100"]


def test_january_group_by_group(book: Book) -> None:
    majors = book.majors("January")
    assert {name: majors[name] for name in JANUARY} == JANUARY


def test_the_total_is_the_sum_of_the_groups_that_count(book: Book) -> None:
    totals = book(action="totals", period="January")["totals"]
    assert totals["necessary"] == round(sum(JANUARY.values()), 1) == 34.3
    assert totals == {"necessary": 34.3, "appended": 0.0, "grand": 34.3}


def test_salary_and_cash_withdrawn_are_listed_and_counted_nowhere(book: Book) -> None:
    """A salary is what the month is measured against, and cash taken out is
    counted when the notes say what it was spent on. Both are shown, so no money
    looks lost, and neither reaches a Total."""
    minors = book.minors("January")
    assert minors["Salary"] == -57300 and minors["Withdrawal"] == 9500
    with_them = book(action="totals", period="January")["totals"]["grand"]
    assert with_them == 34.3


def test_amounts_written_with_a_space_are_read_whole(book: Book) -> None:
    """`9 500 atm` and `+ 57 300`, as a phone's notes app writes them."""
    minors = book.minors("January")
    assert (minors["Withdrawal"], minors["Salary"]) == (9500, -57300)


def test_rent_counts_whole_in_the_month_it_is_paid(book: Book) -> None:
    """This household's rules say `months = 1`. Another's may spread a lump paid
    every second month over the two it covers."""
    assert [book.majors(m)["Rent"] for m in ("January", "February", "March")] == [9.4, 9.4, 9.4]


def test_money_coming_back_reduces_the_month(book: Book) -> None:
    assert book.minors("January")["Refunds"] == -1540
    assert book.majors("January")["Refunds"] == -1.5


def test_a_line_marked_for_another_month_is_counted_in_neither(book: Book) -> None:
    """`+ 210 do not count, refers to December` - December is not stored, so the
    credit waits for it and reaches no group here."""
    listed = [amount for row in book(action="totals", period="January")["minors"]
              for amount in row.get("amounts", [])]
    assert 210 not in listed and -210 not in listed


def test_the_lines_no_rule_can_place_are_asked_about(book: Book) -> None:
    assert book.asked("January") == [
        "1620 heating card", "740 cinema", "480 wine", "1220 new shoes", "650 book"]
    assert book(action="totals", period="January")["questions"] == 5


def test_a_question_offers_what_the_line_itself_suggests(book: Book) -> None:
    assert book.question("January", "740 cinema")["candidates"] == ["Cinema"]
    assert book.question("January", "1220 new shoes")["candidates"] == []


def test_alcohol_is_asked_about_with_both_readings(book: Book) -> None:
    """The same bottle is groceries on one day and a celebration on another; the
    rules cannot know which, so they say so."""
    wine = book.question("January", "480 wine")
    assert wine["candidates"] == ["Food", "Celebrations"]
    assert "celebration" in wine["review"]


def test_limits_and_the_room_left_under_them(book: Book) -> None:
    month = book(action="totals", period="January")
    assert month["limits"] == [{"label": "Food", "group": "Food", "value": 30},
                               {"label": "Road", "group": "Road", "value": 10},
                               {"label": "Medicine", "group": "Medicine", "value": 8}]
    majors = {m["name"]: m for m in month["majors"]}
    # (30 - 19.8) + (10 - 2.4) + (8 - 4.2)
    assert majors["Totally saved"]["value"] == 21.6
    assert majors["Totally overspent"]["value"] == 0.0


def test_a_group_past_its_limit_is_overspent(book: Book) -> None:
    book(action="configure", op="set_limit", major="Food", value=15)
    majors = {m["name"]: m["value"] for m in book(action="totals", period="January")["majors"]}
    assert majors["Totally overspent"] == 4.8          # 19.8 against 15
    assert majors["Totally saved"] == 11.4             # Road 7.6 + Medicine 3.8


def test_the_closing_line_is_read_figure_by_figure(book: Book) -> None:
    left = book(action="totals", period="January")["left"]
    assert left["raw"] == "Left: purse 1, account 32500"
    assert [(c["id"], c["value"]) for c in left["cells"]] == [("purse", 1.0), ("account", 32500.0)]


def test_adding_the_same_month_again_does_not_double_it(book: Book) -> None:
    before = book.majors("January")
    again = book.add(month_text(1))
    assert [item["span"] for item in again] == ["10.01..27.01"]
    assert book.majors("January") == before
    assert len(book(action="periods")) == 3


def test_two_months_in_one_paste_need_the_line_between_them(empty: Book) -> None:
    """A line of three or more # ends a month. Without it the second month's
    days run on into the first, silently."""
    empty.add(month_text(1) + "\n######\n" + month_text(2))
    assert [p["month"] for p in empty(action="periods")] == ["January", "February"]


def test_without_that_line_they_are_one_month(empty: Book) -> None:
    empty.add(month_text(1) + "\n" + month_text(2))
    periods = empty(action="periods")
    assert len(periods) == 1 and periods[0]["span"] == "10.01..27.02"


def test_a_paste_with_no_dated_day_is_set_aside_and_said_so(empty: Book) -> None:
    """Nothing is stored, and the reply says why - a paste is never dropped in
    silence."""
    said = empty.add("just some words\n")
    assert said == [{"span": "undated", "outcome": "skipped: no dated days"}]
    assert empty(action="periods") == []


def test_months_side_by_side(book: Book) -> None:
    table = book(action="compare", periods=["January", "February", "March"])
    rows = [line.split() for line in table.splitlines()]
    assert ["Food", "19.8", "19.6", "15.9"] in rows
    assert ["Total", "34.3", "34.3", "28.9"] in rows


def test_the_average_of_the_months_chosen(book: Book) -> None:
    table = book(action="compare", periods=["January", "February", "March"], average=True)
    assert "Average of 3 months of 2026" in table
    # (34.3 + 34.3 + 28.9) / 3
    assert any(line.split() == ["Total", "32.5"] for line in table.splitlines())
    two = book(action="compare", periods=["January", "March"], average=True)
    assert any(line.split() == ["Total", "31.6"] for line in two.splitlines())


def test_a_month_prints_as_plain_text(book: Book) -> None:
    page = book(action="export", period="January", format="txt")
    assert page["format"] == "txt" and page["name"].endswith(".txt")
    assert "Food: 19.8 / 30  (10.2 left)" in page["body"]
    assert "Total: 34.3" in page["body"]
    assert "Left: purse 1, account 32500" in page["body"]


def test_a_month_prints_as_rtf(book: Book) -> None:
    page = book(action="export", period="January", format="rtf")
    assert page["body"].startswith("{\\rtf") and page["body"].rstrip().endswith("}")


def test_the_year_prints_every_month(book: Book) -> None:
    year = book(action="export", year=2026, format="txt")["body"]
    for month in ("January 2026", "February 2026", "March 2026"):
        assert month in year
