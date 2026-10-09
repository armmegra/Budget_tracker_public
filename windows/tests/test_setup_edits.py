from __future__ import annotations

import textwrap

from test_speech import _engine, needs_household

pytestmark = needs_household

REMOVED = "the group {name} was removed - where does this go?"

LOAD = """
    book = Book()
    for text in MONTHS:
        book({"action": "import", "text": text, "year": 2026})

    def every(**op):
        return book({"action": "configure", **op})

    def onward(month, *ops):
        return book({"action": "configure", "scope": "onward", "period": month,
                     "ops": list(ops), "confirm": True})

    def month(name):
        return book({"action": "totals", "period": name, "year": 2026})["result"]

    def rows(name):
        out = []
        for row in month(name)["minors"]:
            out += [sub["name"] for sub in row.get("subgroups", [])] or [row["name"]]
        return out

    def row(month_name, group):
        for one in month(month_name)["minors"]:
            for part in one.get("subgroups", []) or [one]:
                if part["name"] == group:
                    return part["total"]
        return None

    def setup(name=None):
        event = {"action": "config"}
        if name:
            event["period"] = name
        return book(event)["result"]

    def refused(reply):
        return None if reply["ok"] else reply["code"]

    def asked(name):
        return book({"action": "questions", "period": name, "year": 2026})["result"]

    def answer(name, question, group):
        # Answers are the one thing a closed month still guards.
        return book({"action": "answer", "period": name, "year": 2026,
                     "number": question["number"], "group": group, "override": True})

    def majors(name=None):
        return [m["name"] for m in setup(name)["majors"]]

    def minors_of(major, name=None):
        return [n["name"] for m in setup(name)["majors"] if m["name"] == major
                for n in m["minors"]]
"""


def run(tmp_path, body: str) -> dict:
    return _engine(tmp_path, textwrap.dedent(LOAD) + textwrap.dedent(body))


def test_a_minor_goes_and_then_its_major(tmp_path) -> None:
    facts = run(tmp_path, """
        before = month("February")
        facts["food"] = row("February", "Food")
        facts["asked_before"] = len(asked("February"))
        facts["minor"] = refused(every(op="remove_minor", minor="Food"))
        questions = asked("February")
        facts["asked_after"] = len(questions)
        facts["removed"] = sorted({q["review"] for q in questions if "removed" in q["review"]})
        facts["rows"] = rows("February")
        facts["necessary"] = [before["totals"]["necessary"],
                              month("February")["totals"]["necessary"]]
        facts["food_minors"] = minors_of("Food")
        facts["major"] = refused(every(op="remove_major", major="Food"))
        facts["majors"] = majors()
        facts["limits"] = [r["group"] for r in month("February")["limits"]]
    """)
    assert facts["food"] > 0
    assert facts["minor"] is None
    assert facts["asked_after"] > facts["asked_before"]
    assert facts["removed"] == [REMOVED.format(name="Food")]
    assert "Food" not in facts["rows"]
    assert facts["necessary"][1] < facts["necessary"][0]
    assert facts["food_minors"] == []
    assert facts["major"] is None
    assert "Food" not in facts["majors"] and "Food" not in facts["limits"]


def test_every_line_a_removed_group_held_is_asked_again(tmp_path) -> None:
    facts = run(tmp_path, """
        cinema = next(q for q in asked("January") if q["raw"] == "740 cinema")
        facts["answered"] = answer("January", cinema, "Medicine")["ok"]
        facts["cinema_placed"] = "740 cinema" not in [q["raw"] for q in asked("January")]
        facts["removed"] = refused(every(op="remove_minor", minor="Medicine"))
        again = {q["raw"]: q for q in asked("January") if "removed" in q["review"]}
        facts["again"] = sorted(again)
        facts["reviews"] = sorted({q["review"] for q in again.values()})
        chemist = again["480 chemist"]
        facts["to_road"] = answer("January", chemist, "Road")["ok"]
        facts["still"] = [q["raw"] for q in asked("January")].count("480 chemist")
    """)
    assert facts["answered"] and facts["cinema_placed"]
    assert facts["removed"] is None
    assert {"740 cinema", "480 chemist"} <= set(facts["again"])
    assert facts["reviews"] == [REMOVED.format(name="Medicine")]
    assert facts["to_road"] and facts["still"] == 0


def test_a_major_goes_with_its_minor_groups(tmp_path) -> None:
    facts = run(tmp_path, """
        facts["done"] = refused(every(op="remove_major", major="Road"))
        facts["majors"] = majors()
        facts["rows"] = rows("February")
        facts["removed"] = sorted({q["review"] for q in asked("February")
                                   if "removed" in q["review"]})
        facts["limits"] = [r["group"] for r in month("February")["limits"]]
    """)
    assert facts["done"] is None
    assert "Road" not in facts["majors"] and "Road" not in facts["rows"]
    assert facts["removed"] == [REMOVED.format(name="Road")]
    assert "Road" not in facts["limits"]


def test_a_major_can_send_its_minor_groups_elsewhere_instead(tmp_path) -> None:
    facts = run(tmp_path, """
        before = month("February")["totals"]
        facts["itself"] = refused(every(op="remove_major", major="Medicine",
                                        minors_to="Medicine"))
        facts["done"] = refused(every(op="remove_major", major="Medicine", minors_to="Road"))
        facts["same_totals"] = month("February")["totals"] == before
        facts["road"] = minors_of("Road")
        facts["removed"] = [q["raw"] for q in asked("February") if "removed" in q["review"]]
    """)
    assert facts["itself"] == "minors_to_itself"
    assert facts["done"] is None and facts["same_totals"]
    assert facts["road"] == ["Road", "Medicine"]
    assert facts["removed"] == []


def test_uncounted_groups_move_only_among_themselves(tmp_path) -> None:
    facts = run(tmp_path, """
        facts["counted"] = refused(every(op="remove_major", major="Set aside",
                                         minors_to="Food"))
        every(op="add_major", name="Parked", tier="EXCLUDED")
        facts["uncounted"] = refused(every(op="remove_major", major="Set aside",
                                           minors_to="Parked"))
        facts["parked"] = minors_of("Parked")
    """)
    assert facts["counted"] == "uncounted_route"
    assert facts["uncounted"] is None
    assert "Salary" in facts["parked"] and "Savings" in facts["parked"]


def test_the_last_group_spending_can_go_to_stays(tmp_path) -> None:
    facts = run(tmp_path, """
        facts["said"] = [refused(every(op="remove_major", major=name))
                         for name in ("Rent", "Food", "Road")]
        facts["last"] = refused(every(op="remove_major", major="Medicine"))
        facts["counted"] = [m["name"] for m in setup()["majors"]
                            if m["tier"] != "EXCLUDED" and not m["income"]]
        facts["totals"] = month("February")["totals"]
    """)
    assert facts["said"] == [None, None, None]
    assert facts["last"] == "last_major"
    assert facts["counted"] == ["Medicine"]
    assert facts["totals"]["necessary"] >= 0


def test_any_limit_goes_at_any_time(tmp_path) -> None:
    facts = run(tmp_path, """
        facts["box"] = [r["group"] for r in month("February")["limits"]]
        facts["gone"] = refused(every(op="set_limit", major="Food", value=None))
        facts["after"] = [r["group"] for r in month("February")["limits"]]
        facts["back"] = refused(every(op="set_limit", major="Food", value=30))
        facts["again"] = [r["group"] for r in month("February")["limits"]]
    """)
    assert facts["box"] == ["Food", "Road", "Medicine"]
    assert facts["gone"] is None and facts["after"] == ["Road", "Medicine"]
    assert facts["back"] is None and "Food" in facts["again"]


def test_an_edit_for_some_months_needs_no_unlocking(tmp_path) -> None:
    facts = run(tmp_path, """
        facts["done"] = refused(onward("January", {"op": "rename_major", "major": "Food",
                                                   "name": "Meals"}))
        facts["labels"] = [[m["label"] for m in setup(name)["majors"]]
                           for name in ("January", "February")]
    """)
    assert facts["done"] is None
    assert all("Meals" in labels and "Food" not in labels for labels in facts["labels"])


def test_renaming_a_major_renames_its_twin_minor(tmp_path) -> None:
    facts = run(tmp_path, """
        every(op="learn_word", word="bakery", group="Food")
        every(op="rename_major", major="Food", name="Groceries")
        cfg = setup()
        facts["food"] = next(m for m in cfg["majors"] if m["name"] == "Food")["minors"]
        facts["words"] = cfg["words"]
        facts["rows"] = rows("February")
    """)
    assert facts["food"] == [{"name": "Food", "label": "Groceries", "added": False,
                             "role": None}]
    assert facts["words"] == [{"word": "bakery", "group": "Food", "label": "Groceries"}]
    assert "Groceries" in facts["rows"] and "Food" not in facts["rows"]


def test_a_minor_may_take_its_own_majors_name_and_no_other(tmp_path) -> None:
    facts = run(tmp_path, """
        every(op="add_minor", name="Taxi", major="Road")
        every(op="rename_major", major="Road", name="Transport")
        facts["twin"] = [n["label"] for m in setup()["majors"] if m["name"] == "Road"
                         for n in m["minors"]]
        facts["second"] = refused(every(op="rename_minor", minor="Taxi", name="Transport"))
        facts["elsewhere"] = refused(every(op="rename_minor", minor="Medicine",
                                           name="Transport"))
        every(op="add_major", name="Pets", tier="NECESSARY")
        facts["added"] = refused(every(op="add_minor", name="Pets", major="Pets"))
        facts["added_elsewhere"] = refused(every(op="add_minor", name="Pets", major="Food"))
        facts["rows"] = rows("February")
    """)
    assert facts["twin"] == ["Transport", "Taxi"]
    assert facts["second"] == "name_taken"
    assert facts["elsewhere"] == "name_taken"
    assert facts["added"] is None
    assert facts["added_elsewhere"] == "name_taken"
    assert "Transport" in facts["rows"] and "Road" not in facts["rows"]


def test_a_removed_group_leaves_no_row(tmp_path) -> None:
    facts = run(tmp_path, """
        facts["before"] = "Rent" in rows("February")
        facts["done"] = refused(every(op="remove_major", major="Rent"))
        facts["after"] = "Rent" in rows("February")
    """)
    assert facts["before"] and facts["done"] is None and not facts["after"]


def test_a_limit_set_after_watch_stays_in_the_box(tmp_path) -> None:
    facts = run(tmp_path, """
        every(op="add_major", name="Pets", tier="NECESSARY")
        every(op="add_major", name="Books", tier="NECESSARY")
        every(op="move_limit", major="Medicine", to="Pets")
        every(op="set_limit", major="Books", value=5)
        facts["order"] = setup()["limit_order"]
        facts["box"] = [row["group"] for row in month("February")["limits"]]
    """)
    assert "Pets" in facts["order"] and "Medicine" not in facts["order"]
    assert facts["order"][-1] == "Books"
    assert "Books" in facts["box"]


def test_the_left_line_changes_for_some_months(tmp_path) -> None:
    facts = run(tmp_path, """
        slots = setup("February")["left"]["slots"]
        first = slots[0]["id"]
        facts["was"] = slots[0]["label"]
        facts["renamed"] = refused(onward("February", {"op": "left_rename_slot", "slot": first,
                                                        "label": "cash"}))
        second = setup("February")["left"]["slots"][1]["id"]
        onward("February", {"op": "left_rename_slot", "slot": second, "label": "bank"})
        facts["jan"] = [s["label"] for s in setup("January")["left"]["slots"]]
        facts["feb"] = [s["label"] for s in setup("February")["left"]["slots"]]
        facts["mar"] = [s["label"] for s in setup("March")["left"]["slots"]]
        facts["mar_line"] = month("March")["left"]["text"]
        every(op="left_rename_slot", slot=first, label="coins")
        onward("March", {"op": "left_reset"})
        facts["reset"] = [s["label"] for s in setup("March")["left"]["slots"]]
        facts["jan_after"] = [s["label"] for s in setup("January")["left"]["slots"]]
    """)
    assert facts["renamed"] is None
    assert facts["jan"] == ["purse", "account"] and facts["was"] == "purse"
    assert facts["feb"] == ["cash", "bank"] and facts["mar"] == ["cash", "bank"]
    assert "cash" in facts["mar_line"]
    assert facts["reset"][0] == "purse"
    assert facts["jan_after"][0] == "coins"


def test_a_group_removed_for_later_months_only(tmp_path) -> None:
    facts = run(tmp_path, """
        every(op="add_major", name="Kayak club", tier="OCCASIONAL")
        onward("March", {"op": "remove_major", "major": "Kayak club"})
        facts["feb"] = "Kayak club" in majors("February")
        facts["mar"] = "Kayak club" in majors("March")
        onward("March", {"op": "add_major", "name": "Kayak club", "tier": "OCCASIONAL"})
        facts["back"] = majors("March").count("Kayak club")
        facts["food"] = refused(onward("March", {"op": "remove_minor", "minor": "Food"}))
        facts["feb_rows"] = rows("February")
        facts["mar_rows"] = rows("March")
        facts["feb_removed"] = [q["raw"] for q in asked("February") if "removed" in q["review"]]
        facts["mar_removed"] = [q["raw"] for q in asked("March") if "removed" in q["review"]]
    """)
    assert facts["feb"] and not facts["mar"]
    assert facts["back"] == 1
    assert facts["food"] is None
    assert "Food" in facts["feb_rows"] and "Food" not in facts["mar_rows"]
    assert facts["feb_removed"] == [] and facts["mar_removed"]


def test_a_minor_can_join_another_instead(tmp_path) -> None:
    facts = run(tmp_path, """
        every(op="learn_word", word="bakery", group="Medicine")
        facts["totals_before"] = month("February")["totals"]
        facts["medicine"] = row("February", "Medicine")
        facts["road_before"] = row("February", "Road")
        facts["itself"] = refused(every(op="remove_minor", minor="Medicine",
                                        lines_to="Medicine"))
        facts["nowhere"] = refused(every(op="remove_minor", minor="Medicine",
                                         lines_to="Kayak club"))
        facts["other_kind"] = refused(every(op="remove_minor", minor="Medicine",
                                            lines_to="Salary"))
        facts["done"] = refused(every(op="remove_minor", minor="Medicine", lines_to="Road"))
        facts["totals_after"] = month("February")["totals"]
        facts["road_after"] = row("February", "Road")
        facts["rows"] = rows("February")
        facts["words"] = setup()["words"]
        facts["removed"] = [q["raw"] for q in asked("February") if "removed" in q["review"]]
    """)
    assert facts["itself"] == "lines_to_itself"
    assert facts["nowhere"] == "no_minor"
    assert facts["other_kind"] == "merge_counts_differently"
    assert facts["done"] is None
    assert facts["totals_after"] == facts["totals_before"]
    assert facts["road_after"] == facts["road_before"] + facts["medicine"]
    assert "Medicine" not in facts["rows"] and facts["rows"].count("Road") == 1
    assert facts["words"] == [{"word": "bakery", "group": "Medicine", "label": "Road"}]
    assert facts["removed"] == []


def test_a_minor_added_by_hand_can_simply_end(tmp_path) -> None:
    facts = run(tmp_path, """
        every(op="add_minor", name="Taxi", major="Road")
        facts["flag"] = [n["added"] for m in setup()["majors"] for n in m["minors"]
                         if n["name"] == "Taxi"]
        facts["done"] = refused(every(op="remove_minor", minor="Taxi"))
        facts["left"] = "Taxi" in minors_of("Road")
    """)
    assert facts["flag"] == [True]
    assert facts["done"] is None and not facts["left"]


def test_minor_groups_merged_one_after_another(tmp_path) -> None:
    facts = run(tmp_path, """
        parts = [row("February", n) for n in ("Medicine", "Road", "Food")]
        every(op="remove_minor", minor="Medicine", lines_to="Road")
        every(op="remove_minor", minor="Road", lines_to="Food")
        facts["food"] = row("February", "Food")
        facts["parts"] = sum(parts)
        facts["rows"] = rows("February")
        question = asked("February")[0]
        facts["answered"] = answer("February", question, "Medicine")
        facts["after_answer"] = row("February", "Food")
        facts["rows_after"] = rows("February")
    """)
    assert facts["food"] == facts["parts"]
    assert not {"Medicine", "Road"} & set(facts["rows"]) and facts["rows"].count("Food") == 1
    assert facts["answered"]["ok"], facts["answered"]
    assert facts["after_answer"] > facts["food"]
    assert "Medicine" not in facts["rows_after"]


def test_an_empty_app_has_a_month_to_show(tmp_path) -> None:
    facts = run(tmp_path, """
        blank = Book()
        first = blank({"action": "empty"})["result"]
        month = book({"action": "totals", "period": "February", "year": 2026})["result"]
        facts["same keys"] = sorted(set(month) - set(first)) == [] and \
            sorted(set(first) - set(month)) == ["empty"]
        facts["majors"] = [[m["name"], m["value"], m["limit"]] for m in first["majors"]]
        facts["minors"] = [[m["name"], m["amounts"], m["total"]] for m in first["minors"]]
        facts["limits"] = [[r["label"], r["value"]] for r in first["limits"]]
        facts["totals"] = first["totals"]
        facts["left"] = first["left"]["text"]
        facts["rest"] = [first["questions"], first["closed"], first["appended"], first["span"]]
        blank({"action": "configure", "op": "rename_major", "major": "Food", "name": "Groceries"})
        blank({"action": "configure", "op": "remove_major", "major": "Medicine"})
        after = blank({"action": "empty"})["result"]
        facts["after"] = [m["name"] for m in after["majors"]]
        facts["after rows"] = [m["name"] for m in after["minors"]]
        facts["ru"] = Book("ru")({"action": "empty"})["ok"]
    """)
    assert facts["same keys"]
    assert facts["majors"] == [
        ["Rent", 0.0, None], ["Food", 0.0, 30], ["Road", 0.0, 10], ["Medicine", 0.0, 8],
        ["Refunds", 0.0, None], ["Set aside", 0.0, None],
        ["Totally saved", 0.0, None], ["Totally overspent", 0.0, None]]
    assert facts["minors"] == [[n, [], 0] for n in
                               ("Rent", "Food", "Road", "Medicine", "Refunds", "Withdrawal",
                                "Salary")]
    assert facts["limits"] == [["Food", 30], ["Road", 10], ["Medicine", 8]]
    assert facts["totals"] == {"necessary": 0.0, "appended": 0.0, "grand": 0.0}
    assert facts["left"] == "Left: purse —, account —"
    assert facts["rest"] == [0, False, [], ""]
    assert "Groceries" in facts["after"] and "Medicine" not in facts["after"]
    assert "Groceries" in facts["after rows"] and "Medicine" not in facts["after rows"]
    assert facts["ru"]


def test_a_left_figure_typed_by_hand_takes_the_notes_place(tmp_path) -> None:
    facts = run(tmp_path, """
        def left(name):
            return month(name)["left"]
        feb, mar = left("February"), left("March")
        facts["closed"] = refused(book({"action": "left_value", "period": "February",
                                        "slot": "account", "value": 50000}))
        facts["set"] = refused(book({"action": "left_value", "period": "February",
                                     "slot": "account", "value": 50000, "override": True}))
        now = left("February")
        shown = now.get("computed") or now
        facts["cells"] = [[c["figure"], c.get("set", False), c.get("noted")] for c in shown["cells"]]
        facts["was"] = [c["figure"] for c in (feb.get("computed") or feb)["cells"]]
        facts["march same"] = left("March") == mar
        facts["no slot"] = refused(book({"action": "left_value", "period": "February",
                                         "slot": "kitty", "value": 1, "override": True}))
        facts["not a number"] = book({"action": "left_value", "period": "February",
                                      "slot": "purse", "value": "lots",
                                      "override": True})["ok"]
        book({"action": "left_value", "period": "February", "slot": "account", "value": None,
              "override": True})
        facts["back"] = left("February") == feb
    """)
    assert facts["closed"] == "closed"
    assert facts["set"] is None
    assert facts["cells"][1] == ["50000", True, facts["was"][1]]
    assert facts["cells"][0] == [facts["was"][0], False, None]
    assert facts["march same"] and facts["back"]
    assert facts["no slot"] == "no_slot" and facts["not a number"] is False


def test_starting_figures_and_months_that_count_on(tmp_path) -> None:
    facts = run(tmp_path, """
        blank = Book()
        facts["start"] = [refused(blank({"action": "left_value", "slot": "purse", "value": 5.5})),
                          refused(blank({"action": "left_value", "slot": "account",
                                         "value": 60000}))]
        empty = blank({"action": "empty"})["result"]["left"]
        facts["empty"] = [[c["figure"], c.get("set", False)] for c in empty["cells"]]
        blank({"action": "import", "year": 2026,
               "text": "10.01\\n+ 57 300\\n9400 rent card\\n\\n11.01\\n26 bus\\n2340 grocer card\\n"})
        jan = blank({"action": "totals", "period": "January", "year": 2026})["result"]["left"]
        facts["jan"] = [jan["text"], jan.get("counted_on"), jan.get("counted_from")]
        blank({"action": "import", "year": 2026,
               "text": "10.02\\n+ 58 650\\n9400 rent card\\n\\n11.02\\n26 bus\\n"})
        feb = blank({"action": "totals", "period": "February", "year": 2026})["result"]["left"]
        facts["feb"] = [feb["text"], feb.get("counted_from")]
        backup = blank({"action": "backup"})["result"]
        facts["carried"] = backup["server"]["left_start"]
        # The example months write their own Left lines: read as ever.
        book({"action": "left_value", "slot": "account", "value": 1})
        mar = month("March")["left"]
        facts["own line"] = [mar.get("counted_on"), (mar.get("computed") or mar)["text"]]
        blank({"action": "reset", "scope": "all", "confirm": "RESET"})
        facts["wiped"] = blank({"action": "empty"})["result"]["left"]["text"]
    """)
    assert facts["start"] == [None, None]
    assert facts["empty"] == [["5.5", True], ["60000", True]]
    assert facts["jan"] == ["Left: purse 5.5, account 105560", True, "start"]
    assert facts["feb"] == ["Left: purse 5.5, account 154810", "before"]
    assert facts["carried"] == {"purse": 5.5, "account": 60000.0}
    assert facts["own line"] == [None, "Left: purse 1.1, account 69450"]
    assert facts["wiped"] == "Left: purse —, account —"


def test_a_line_for_a_month_not_stored_makes_that_month(tmp_path) -> None:
    facts = run(tmp_path, """
        SEPT = "03.09\\n+ 60 000\\n4000 rent\\n\\n06.09\\n+ 1800 ladder, do not count refers to August\\n"
        blank = Book()
        blank({"action": "configure", "op": "add_major", "name": "Ladder", "tier": "OCCASIONAL"})
        blank({"action": "import", "year": 2026, "text": SEPT})
        facts["months"] = [[p["month"], p["year"], p["moved"], p["days"]]
                           for p in blank({"action": "periods"})["result"]]
        sep = blank({"action": "totals", "period": "September", "year": 2026})["result"]
        facts["held"] = sep["held"]
        facts["aside"] = [m["value"] for m in sep["majors"] if m["name"] == "Set aside"]
        facts["rent"] = [[r["amounts"], r["total"]] for r in sep["minors"] if r["name"] == "Rent"]
        facts["sep asked"] = [q["raw"] for q in blank({"action": "questions",
                                                       "period": "September"})["result"]]
        aug = blank({"action": "questions", "period": "August"})["result"]
        facts["aug asked"] = [[q["raw"], q["candidates"]] for q in aug]
        facts["aug readings"] = [m["value"] for m in blank({"action": "totals", "period": "August",
                                 "year": 2026})["result"]["majors"] if m["tier"] == "READING"]
        facts["answered"] = blank({"action": "answer", "period": "August",
                                   "number": aug[0]["number"], "group": "Ladder"})["ok"]
        facts["roles"] = {n["name"]: n["role"] for m in blank({"action": "config"})["result"]["majors"]
                          for n in m["minors"] if m["tier"] == "EXCLUDED"}
        blank({"action": "configure", "op": "remove_minor", "minor": "Elsewhere"})
        facts["still"] = [p["month"] for p in blank({"action": "periods"})["result"]]
        blank({"action": "import", "year": 2026, "text": "03.08\\n+ 58 000\\n\\n06.08\\n1000 bread\\n"})
        facts["after"] = [[p["month"], p["moved"]] for p in blank({"action": "periods"})["result"]]
        august = blank({"action": "totals", "period": "August", "year": 2026})["result"]
        facts["ladder"] = [m["value"] for m in august["majors"] if m["name"] == "Ladder"]
        facts["aug asked after"] = [q["raw"] for q in blank({"action": "questions",
                                                             "period": "August"})["result"]]
        for gone in ("Salary", "Savings", "Withdrawal", "Rent payment"):
            facts.setdefault("removed", []).append(
                blank({"action": "configure", "op": "remove_minor", "minor": gone})["ok"])

        # "Add to" the month made of moved lines: the days pasted are its notes.
        added = Book()
        added({"action": "configure", "op": "add_major", "name": "Ladder", "tier": "OCCASIONAL"})
        added({"action": "import", "year": 2026, "text": SEPT})
        number = added({"action": "questions", "period": "August"})["result"][0]["number"]
        added({"action": "answer", "period": "August", "number": number, "group": "Ladder"})
        facts["added"] = added({"action": "import", "year": 2026, "period": "August",
                                "text": "15.08\\n300 bread\\n"})["result"]
        facts["added months"] = [[p["month"], p["moved"], p["days"]]
                                 for p in added({"action": "periods"})["result"]]
        facts["added ladder"] = [m["value"] for m in added({"action": "totals", "period": "August",
                                  "year": 2026})["result"]["majors"] if m["name"] == "Ladder"]
        facts["old key"] = added({"action": "totals", "period": "moved:August 2026",
                                  "year": 2026})["result"]["span"]
    """)
    line = "+ 1800 ladder, do not count refers to August"
    assert facts["months"] == [["August", 2026, True, 1], ["September", 2026, False, 2]]
    assert facts["held"] == [] and facts["sep asked"] == []
    assert facts["aside"] == [-60.0 + 4.0]
    assert facts["rent"] == [[[4000], 4000]]
    assert facts["aug asked"] == [[line, ["Ladder"]]]
    assert facts["aug readings"] == [0.0, 0.0]
    assert facts["answered"] is True
    assert facts["roles"] == {"Salary": "salary", "Savings": "savings", "Withdrawal": "withdrawal",
                              "Rent payment": "rent_lump", "Elsewhere": "elsewhere"}
    assert "August" in facts["still"]
    assert facts["after"] == [["August", False], ["September", False]]
    assert facts["ladder"] == [-1.8] and line not in facts["aug asked after"]
    assert facts["removed"] == [True, True, True, True]
    assert facts["added"] == [{"span": "15.08..15.08", "outcome": "imported"}]
    assert facts["added months"] == [["August", False, 1], ["September", False, 2]]
    assert facts["added ladder"] == [-1.8]
    assert facts["old key"] == "15.08..15.08"


def test_a_question_carries_its_day_as_written(tmp_path) -> None:
    facts = run(tmp_path, """
        blank = Book()
        blank({"action": "import", "year": 2026, "text":
               "03.05\\n+ 57 300\\n\\n14.05\\n140\\n310 bird seed\\n\\n1400 window cleaner\\n"
               "+ 1400 window cleaner\\n\\n3600 choir fees\\nLeft: purse 3.1, account 41800\\n"})
        asked = blank({"action": "questions", "period": "May"})["result"]
        facts["asked"] = [[q["raw"], q["date"], [l["text"] for l in q["day"]],
                           [l["text"] for l in q["day"] if l["this"]]] for q in asked]
        q = asked[-1]
        facts["day"] = blank({"action": "day", "period": "May", "entries": [
            {"raw": q["raw"], "occurrence": q["occurrence"]}]})["result"] == [
            {"date": q["date"], "lines": q["day"]}]
        facts["two"] = [d["date"] for d in blank({"action": "day", "period": "May", "entries": [
            {"raw": "+ 57 300", "occurrence": 0}, {"raw": "140", "occurrence": 0}]})["result"]]
        facts["refused"] = blank({"action": "day", "period": "May",
                                  "entries": [{"raw": "x", "occurrence": 3}]}).get("code")
    """)
    day = ["140", "310 bird seed", "", "1400 window cleaner", "+ 1400 window cleaner", "", "3600 choir fees",
           "Left: purse 3.1, account 41800"]
    assert facts["asked"] and all(date == "14.05" and lines == day and this == [raw]
                                  for raw, date, lines, this in facts["asked"])
    assert facts["day"] is True
    assert facts["two"] == ["03.05", "14.05"]
    assert facts["refused"] == "no_entry"
