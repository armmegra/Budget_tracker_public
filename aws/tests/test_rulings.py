"""What the person decides outranks what the rules decide.

Three ways to say where a line goes, most particular first: a move (this line is
booked wrongly), an answer (to a question the rules asked), a taught word (every
line carrying it). Each outranks every rule, including rules written later, so a
month keeps the picture it was given and a restored backup shows what was saved.
"""

from __future__ import annotations

from conftest import Book


def answer(book: Book, month: str, raw: str, group: str, **more) -> None:
    book(action="answer", period=month, number=book.question(month, raw)["number"],
         group=group, **more)


# -- answers ---------------------------------------------------------------------


def test_an_answer_books_the_line_and_the_question_is_gone(book: Book) -> None:
    answer(book, "January", "480 wine", "Food")
    assert "480 wine" not in book.asked("January")
    assert book(action="totals", period="January")["questions"] == 4


def test_an_answer_naming_a_group_that_does_not_exist_is_refused(book: Book) -> None:
    """A typing slip must not start a group. Starting one is said outright."""
    number = book.question("January", "740 cinema")["number"]
    refused = book.refused(action="answer", period="January", number=number, group="Leisure")
    assert refused["code"] == "answer_new_group"
    assert "740 cinema" in book.asked("January")


def test_a_new_group_is_counted_after_the_first_total(book: Book) -> None:
    """A group the person starts is an occasional one: it is added after the
    first Total, so one unusual purchase does not read as the month's groceries
    getting dearer."""
    answer(book, "January", "740 cinema", "Leisure", new=True)
    month = book(action="totals", period="January")
    assert month["totals"] == {"necessary": 34.3, "appended": 0.7, "grand": 35.0}
    assert [(g["name"], g["value"]) for g in month["appended"]] == [("Leisure", 0.7)]


def test_an_answer_is_for_its_own_month_only(book: Book) -> None:
    """The same words can mean different things in different months, so an
    answer in January does not quietly decide February's line."""
    answer(book, "January", "1620 heating card", "Heating", new=True)
    assert "1620 heating card" not in book.asked("January")
    assert "1560 heating card" in book.asked("February")


def test_the_other_questions_keep_their_numbers(book: Book) -> None:
    """A question is answered by number. If answering one renumbered the rest,
    the next answer would land on the wrong line."""
    before = {q["raw"]: q["number"] for q in book(action="questions", period="January")}
    answer(book, "January", "740 cinema", "Leisure", new=True)
    after = {q["raw"]: q["number"] for q in book(action="questions", period="January")}
    del before["740 cinema"]
    assert after == before


def test_an_answer_outranks_a_rule_that_is_sure_of_the_line(book: Book) -> None:
    """`330 cafe` is Food by the rules, with no doubt. An answer stored for that
    line - given before a rule could place it, say - still decides it."""
    assert "330 cafe" not in book.asked("January")
    book.store.answers["salary:57300|330 cafe|0"] = "Road"
    book.store.save()
    majors = book.majors("January")
    assert (majors["Food"], majors["Road"]) == (19.5, 2.8)


# -- moves -----------------------------------------------------------------------


def test_a_move_takes_a_line_the_rules_were_sure_of(book: Book) -> None:
    book(action="move", period="January", raw="330 cafe", occurrence=0, group="Road")
    majors = book.majors("January")
    assert (majors["Food"], majors["Road"]) == (19.5, 2.8)
    # 19.83 - 0.33 and 2.42 + 0.33: each group rounds on its own, as a sheet of
    # paper does, and the Total is the sum of what is shown. So moving 0.33 can
    # move the Total by 0.1, and it does here.
    assert book(action="totals", period="January")["totals"]["necessary"] == 34.4


def test_lifting_a_move_lets_the_rules_decide_again(book: Book) -> None:
    book(action="move", period="January", raw="330 cafe", occurrence=0, group="Road")
    lifted = book(action="move", period="January", raw="330 cafe", occurrence=0, group=None)
    assert lifted["lifted"] is True
    majors = book.majors("January")
    assert (majors["Food"], majors["Road"]) == (19.8, 2.4)


def test_a_move_outranks_an_answer_on_the_same_line(book: Book) -> None:
    answer(book, "January", "740 cinema", "Food")
    book(action="move", period="January", raw="740 cinema", occurrence=0, group="Road")
    majors = book.majors("January")
    assert (majors["Food"], majors["Road"]) == (19.8, 3.2)


def test_a_move_to_a_group_that_does_not_exist_is_refused(book: Book) -> None:
    refused = book.refused(action="move", period="January", raw="330 cafe", occurrence=0,
                           group="Leisure")
    assert refused["code"] == "move_new_group"


# -- taught words ----------------------------------------------------------------


def teach(book: Book, word: str, group: str, **more):
    return book(action="configure", op="learn_word", word=word, group=group, **more)


def test_a_taught_word_books_every_line_carrying_it(book: Book) -> None:
    """An answer settles one line in one month; the same bill comes round next
    month and is asked about again. A taught word ends that."""
    teach(book, "heating", "Heating", new=True)
    for month in ("January", "February", "March"):
        assert not [raw for raw in book.asked(month) if "heating" in raw]
    assert book.majors("January")["Heating"] == 1.6
    assert book(action="config")["words"] == [
        {"word": "heating", "group": "Heating", "label": "Heating"}]


def test_teaching_a_word_only_ever_removes_questions(book: Book) -> None:
    before = {m: book.asked(m) for m in ("January", "February", "March")}
    teach(book, "heating", "Heating", new=True)
    for month, asked in before.items():
        now = book.asked(month)
        assert set(now) <= set(asked) and len(now) == len(asked) - 1


def test_the_longest_taught_word_decides(book: Book) -> None:
    """`heating` for Heating and `heating card` for Medicine: a line reading
    `1620 heating card` means the second, the more particular."""
    teach(book, "heating", "Heating", new=True)
    teach(book, "heating card", "Medicine")
    majors = book.majors("January")
    assert "Heating" not in majors or majors["Heating"] == 0
    assert majors["Medicine"] == 5.8          # 4.2 + 1.62


def test_an_answer_still_wins_over_a_taught_word(book: Book) -> None:
    answer(book, "January", "1620 heating card", "Food")
    teach(book, "heating", "Heating", new=True)
    majors = book.majors("January")
    assert majors["Food"] == 21.5             # 19.83 + 1.62
    assert majors.get("Heating", 0) == 0


def test_a_word_matches_whole_and_never_inside_another(book: Book) -> None:
    """`book` is taught; `650 book` goes, and a line about a `booking` would not."""
    teach(book, "book", "Reading", new=True)
    assert "650 book" not in book.asked("January")
    book.add("28.01\n300 booking fee\n", period="January")
    assert "300 booking fee" in book.asked("January")


def test_forgetting_a_word_puts_its_lines_back(book: Book) -> None:
    teach(book, "heating", "Heating", new=True)
    book(action="configure", op="forget_word", word="heating")
    assert "1620 heating card" in book.asked("January")
    assert book(action="config")["words"] == []


def test_what_cannot_be_taught_is_refused_by_name(book: Book) -> None:
    def code(**op):
        return book.refused(action="configure", **op)["code"]

    assert code(op="learn_word", word="ab", group="Food") == "word_short"
    assert code(op="learn_word", word="cinema", group="Nowhere") == "teach_new_group"
    assert code(op="forget_word", word="zebra") == "word_not_taught"


def test_a_word_taught_from_february_on_leaves_january_alone(book: Book) -> None:
    """Which months an edit is for is asked first. A month already read and
    printed keeps its reading."""
    ops = [{"op": "learn_word", "word": "heating", "group": "Heating", "new": True}]
    preview = book(action="configure", scope="onward", period="February", ops=ops)
    assert preview["pending"] is True
    assert preview["months"] == ["February 2026", "March 2026", "and every later month"]
    assert "1560 heating card" in book.asked("February")        # a preview changes nothing

    book(action="configure", scope="onward", period="February", ops=ops, confirm=True)
    assert "1620 heating card" in book.asked("January")
    assert "1560 heating card" not in book.asked("February")
    assert "1390 heating card" not in book.asked("March")


# -- the second Total --------------------------------------------------------------


def test_an_occasional_group_can_be_left_out_of_the_second_total(book: Book) -> None:
    answer(book, "January", "740 cinema", "Leisure", new=True)
    book(action="omit", period="January", groups=["Leisure"])
    assert book(action="totals", period="January")["totals"] == {
        "necessary": 34.3, "appended": 0.0, "grand": 34.3}


def test_its_figure_can_be_set_by_hand_and_the_page_is_told(book: Book) -> None:
    """The row keeps what the notes say; only the Total takes the figure set, and
    the reply marks it so the difference is never silent."""
    answer(book, "January", "740 cinema", "Leisure", new=True)
    book(action="adjust", period="January", group="Leisure", value=0.5)
    month = book(action="totals", period="January")
    assert month["totals"]["grand"] == 34.8
    leisure = month["appended"][0]
    assert (leisure["value"], leisure["actual"], leisure["adjusted"]) == (0.5, 0.7, True)
