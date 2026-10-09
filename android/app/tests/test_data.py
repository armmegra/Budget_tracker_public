from __future__ import annotations

import ast
import json
import re
import sys
import tomllib
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import bundled
import words
from data import (HINTS, KEEP, Budget, Look, Refused, beside, by_year, grouped,
                  money, newest_real, read_comparison, spaced, typed_number, unbroken)


@pytest.fixture()
def budget(tmp_path: Path) -> Budget:
    return Budget(tmp_path)


def test_a_fresh_app_has_no_months_and_the_one_start(budget: Budget) -> None:
    assert budget.months() == []
    setup = budget.setup()
    spending = [m for m in setup["majors"] if m["tier"] != "EXCLUDED" and not m["income"]]
    assert [(m["name"], m["limit"], [n["name"] for n in m["minors"]]) for m in spending] == [
        ("Rent", None, []), ("Food", 30, ["Food"]), ("Road", 10, ["Road"]),
        ("Medicine", 8, ["Medicine"])]
    assert setup["limit_order"] == ["Food", "Road", "Medicine"]
    assert (budget.folder / "rules.toml").is_file()


def test_the_month_as_it_will_look_before_any_month(budget: Budget) -> None:
    said = budget.empty()
    assert said["empty"] and said["questions"] == 0 and not said["closed"] and not said["span"]
    assert [(m["name"], m["value"], m["limit"]) for m in said["majors"]
            if m["tier"] not in ("EXCLUDED", "READING")] == [
        ("Rent", 0.0, None), ("Food", 0.0, 30), ("Road", 0.0, 10), ("Medicine", 0.0, 8),
        ("Refunds", 0.0, None)]
    assert [m["value"] for m in said["majors"] if m.get("saved") or m.get("overspent")] == [0, 0]
    assert said["totals"] == {"necessary": 0.0, "appended": 0.0, "grand": 0.0}
    assert said["appended"] == []
    assert [(row["name"], row["total"], row["amounts"]) for row in said["minors"]][:4] == [
        ("Rent", 0, []), ("Food", 0, []), ("Road", 0, []), ("Medicine", 0, [])]
    assert said["left"]["text"] == "Left: purse —, account —"
    assert [cell["figure"] for cell in said["left"]["cells"]] == ["—", "—"]

    words.set_lang("ru")
    assert budget.follow_language("ru")
    said = budget.empty()
    assert [m["name"] for m in said["majors"] if m["tier"] == "NECESSARY"][:4] == [
        "Аренда", "Еда", "Дорога", "Медицина"]
    assert said["left"]["text"] == "Остаток: наличные —, счёт —"
    assert budget.months() == []


def test_every_example_month_books(budget: Budget) -> None:
    for name in budget.examples():
        outcome = budget.add_example(name)
        assert outcome and all(o["outcome"] for o in outcome), outcome
    months = budget.months()
    assert len(stored(months)) >= 3
    for m in stored(months):
        figures = budget.month(m["identity"])
        assert figures["totals"]["necessary"] > 0, m
    assert [(m["month"], m["days"]) for m in months if m["moved"]] == [("December", 1)]


def test_a_figure_moves_to_another_group_and_back(budget: Budget) -> None:
    budget.add_example("month-1")
    month = budget.months()[-1]["identity"]

    def group_of(raw: str) -> tuple[str, list] | None:
        for minor in budget.month(month)["minors"]:
            for row in [minor, *(minor.get("subgroups") or [])]:
                for lines in row.get("marks") or []:
                    if any(line["raw"] == raw for line in lines or []):
                        return row["name"], lines
        return None

    medicine = next(row for row in budget.month(month)["minors"] if row["name"] == "Medicine")
    lines = medicine["marks"][0]
    raw = lines[0]["raw"]
    assert lines[0]["date"]

    with pytest.raises(Refused, match="read-only"):
        budget.move(month, lines, "Road")
    budget.unlocked.add(month)
    budget.move(month, lines, "Road")
    name, moved = group_of(raw)
    assert name == "Road" and all(line["kind"] == "moved" for line in moved)

    budget.move(month, moved, None)
    assert group_of(raw)[0] == "Medicine"


def test_a_few_days_are_added_to_a_chosen_month(budget: Budget) -> None:
    budget.add_example("month-1")
    month = budget.months()[-1]["identity"]
    days = "28.01\n2340 grocer\n"
    with pytest.raises(Refused):
        budget.add(days, into=month)
    budget.unlocked.add(month)
    budget.add(days, into=month)
    assert len(stored(budget.months())) == 1
    assert "28.01" in budget.months()[-1]["span"]


def test_asking_again_forgets_the_answers_of_that_month(budget: Budget) -> None:
    budget.add_example("month-2")
    month = budget.months()[-1]["identity"]
    budget.unlocked.add(month)
    before = budget.questions(month)
    question = before[0]
    budget.answer(month, question["number"], (question["candidates"] or ["Heating"])[0])
    assert len(budget.questions(month)) == len(before) - 1
    done = budget.ask_again(month)
    assert done["wiped"]["answers"] == 1 and done["questions"] == len(before)
    assert len(budget.questions(month)) == len(before)


def test_a_closed_month_refuses_an_answer_until_unlocked(budget: Budget) -> None:
    budget.add_example("month-2")
    month = budget.months()[-1]["identity"]
    assert month in budget.closed()
    before = budget.month(month)["questions"]
    question = budget.questions(month)[0]
    group = (question["candidates"] or ["Heating"])[0]

    with pytest.raises(Refused, match="read-only"):
        budget.answer(month, question["number"], group)

    budget.unlocked.add(month)
    budget.answer(month, question["number"], group)
    assert budget.month(month)["questions"] < before


def test_pasting_nothing_is_refused_in_words(budget: Budget) -> None:
    with pytest.raises(Refused, match="nothing to add"):
        budget.add("   ")


def test_start_over_leaves_a_fresh_app(budget: Budget) -> None:
    budget.add_example("month-1")
    assert budget.months()
    budget.start_over()
    assert budget.months() == []


def test_the_data_survives_a_new_start_of_the_app(tmp_path: Path) -> None:
    Budget(tmp_path).add_example("month-3")
    assert Budget(tmp_path).months(), "a second start of the app lost the month"


def test_figures_are_written_the_way_the_sheets_write_them() -> None:
    assert money(1234.5) == f"1{KEEP}234.5"
    assert spaced(1234500) == f"1{KEEP}234{KEEP}500"


def test_an_amount_never_breaks_across_two_lines() -> None:
    assert (unbroken("Left: purse 21.4, account 1 234 500, jar 7")
            == f"Left: purse 21.4, account 1{KEEP}234{KEEP}500, jar 7")
    assert unbroken("12 07 then 3 1000") == "12 07 then 3 1000"


def test_a_look_keeps_its_theme_and_sizes_within_bounds(tmp_path: Path) -> None:
    look = Look(tmp_path)
    assert look.theme == "system"
    assert look.sizes == {key: normal for key, (_, normal, _, _) in Look.SIZES.items()}
    look.theme = "dark"
    look.set_size("totals", 99)
    look.set_size("minors", 3)
    look.save()
    again = Look(tmp_path)
    assert again.theme == "dark"
    assert again.sizes["totals"] == Look.SIZES["totals"][3]
    assert again.sizes["minors"] == Look.SIZES["minors"][2]
    (tmp_path / "look.json").write_text("not json", encoding="utf-8")
    assert Look(tmp_path).theme == "system"


def test_months_under_their_years_and_the_month_beside() -> None:
    months = [{"identity": i, "month": m, "year": y} for i, m, y in
              [("a", "November", 2026), ("b", "December", 2026), ("c", "January", 2027)]]
    assert list(by_year(months)) == [2027, 2026]
    assert [m["identity"] for m in by_year(months)[2026]] == ["a", "b"]
    assert beside(months, "b", +1) == "c"
    assert beside(months, "c", -1) == "b"
    assert beside(months, "c", +1) is None and beside(months, "a", -1) is None
    assert beside(months, "gone", +1) is None


def an_occasional_group(budget: Budget) -> str:
    budget.add_example("month-2")
    month = budget.months()[-1]["identity"]
    budget.unlocked.add(month)
    heating = next(q for q in budget.questions(month) if "heating" in q["raw"])
    budget.answer(month, heating["number"], "Heating")
    return month


def test_occasional_groups_ticked_out_and_a_figure_set(budget: Budget) -> None:
    month = an_occasional_group(budget)
    figures = budget.month(month)
    first = figures["appended"][0]
    assert first["id"] == "Heating"
    grand = figures["totals"]["grand"]

    budget.omit(month, [first["id"]])
    assert budget.month(month)["totals"]["grand"] == pytest.approx(grand - first["value"])
    budget.omit(month, [])
    assert budget.month(month)["totals"]["grand"] == pytest.approx(grand)

    budget.adjust(month, first["id"], 0.0)
    after = budget.month(month)
    assert after["totals"]["grand"] == pytest.approx(grand - first["actual"])
    assert after["appended"][0]["adjusted"]
    budget.adjust(month, first["id"], None)
    assert budget.month(month)["totals"]["grand"] == pytest.approx(grand)


def bare(text: str) -> str:
    return "\n".join(line for line in text.splitlines()
                     if not line.startswith(("Left:", "Остаток:")))


def test_a_left_figure_is_typed_for_a_month_or_as_a_starting_figure(budget: Budget) -> None:
    asked = []
    real = budget._dispatch

    def spy(store, event):
        asked.append(dict(event))
        return real(store, event)

    budget._dispatch = spy
    budget.left_value("purse", 5.5)
    assert asked[-1] == {"action": "left_value", "slot": "purse", "value": 5.5}
    cells = {c["id"]: c for c in budget.empty()["left"]["cells"]}
    assert (cells["purse"]["figure"], cells["purse"]["set"]) == ("5.5", True)
    assert cells["account"]["value"] is None and not cells["account"].get("set")
    assert budget.months() == []

    budget.add_example("month-1")
    month = budget.months()[-1]["identity"]
    with pytest.raises(Refused) as refused:
        budget.left_value("purse", 3.5, month)
    assert refused.value.code == "closed"
    budget.unlocked.add(month)
    budget.left_value("purse", 3.5, month)
    assert asked[-1]["period"] == month and asked[-1]["override"] is True
    purse = budget.month(month)["left"]["cells"][0]
    assert (purse["id"], purse["figure"], purse["set"], purse["noted"]) == ("purse", "3.5", True, "1")
    budget.left_value("purse", None, month)
    purse = budget.month(month)["left"]["cells"][0]
    assert purse["figure"] == "1" and not purse.get("set")

    with pytest.raises(Refused) as refused:
        budget.left_value("jar", 1.0)
    assert refused.value.code == "no_slot"


def test_a_month_without_a_left_line_counts_on(budget: Budget) -> None:
    budget.add(bare(bundled.EXAMPLES["month-1"]))
    january = budget.months()[-1]["identity"]
    line = budget.month(january)["left"]
    assert line["blank"] and [c["value"] for c in line["cells"]] == [None, None]

    budget.left_value("purse", 5.5)
    budget.left_value("account", 38500)
    line = budget.month(january)["left"]
    december = budget.month(budget.months()[0]["identity"])["left"]
    assert december["counted_on"] and december["counted_from"] == "start"
    assert line["counted_on"] and line["counted_from"] == "before" and not line.get("blank")
    assert all(c["value"] is not None for c in line["cells"])
    budget.add(bare(bundled.EXAMPLES["month-2"]))
    assert budget.month(budget.months()[-1]["identity"])["left"]["counted_from"] == "before"


def test_a_typed_figure_is_read_as_the_pc_reads_one() -> None:
    assert typed_number("5,5") == 5.5 and typed_number(" 61 240 ") == 61240
    assert typed_number(f"1{KEEP}304{KEEP}560") == 1304560 and typed_number("-2.6") == -2.6
    for nothing in ("", "   ", None, "abc", "1,2,3", "nan", "inf", "-"):
        assert typed_number(nothing) is None, nothing


def stored(months: list[dict]) -> list[dict]:
    return [m for m in months if not m["moved"]]


def three_months(budget: Budget) -> list[str]:
    for name in budget.examples():
        budget.add_example(name)
    return [m["identity"] for m in stored(budget.months())]


def test_compare_returns_the_months_chosen(budget: Budget) -> None:
    jan, feb, mar = three_months(budget)
    said = budget.compare([feb, mar])
    table = said["table"]
    assert "Food" in said["text"]
    assert table["titles"] == ["February 2026", "March 2026"] and table["delta"] == "delta"
    assert table["average"] is None
    names = [row["name"] for row in table["groups"]]
    assert {"Rent", "Food", "Road", "Medicine"} <= set(names) and len(names) == len(set(names))
    for row in table["groups"]:
        assert (row["delta"] is None) == ("-" in row["cells"]), row
    assert [row["name"] for row in table["totals"]] == ["Total", "Total + occasional"]
    for at, identity in enumerate((feb, mar)):
        totals = budget.month(identity)["totals"]
        assert float(table["totals"][0]["cells"][at]) == pytest.approx(totals["necessary"])
        assert float(table["totals"][1]["cells"][at]) == pytest.approx(totals["grand"])

    table = budget.compare([jan, feb, mar], average=True)["table"]
    assert table["titles"] == ["January 2026", "February 2026", "March 2026"]
    assert table["delta"] is None and all(row["delta"] is None for row in table["groups"])
    assert table["average"]["title"] == "Average of 3 months of 2026"
    for row, key in zip(table["average"]["rows"], ("necessary", "grand")):
        mean = sum(budget.month(m)["totals"][key] for m in (jan, feb, mar)) / 3
        assert float(row["cells"][0]) == pytest.approx(mean, abs=0.05)

    assert budget.compare([mar], average=True)["table"]["average"]["title"] == \
        "Average of 1 month of 2026"
    with pytest.raises(Refused):
        budget.compare([mar])


def test_compare_speaks_the_language_chosen(budget: Budget) -> None:
    jan, feb, _ = three_months(budget)
    words.set_lang("ru")
    table = budget.compare([jan, feb], average=True)["table"]
    assert table["titles"] == ["Январь 2026", "Февраль 2026"] and table["delta"] == "разница"
    assert [row["name"] for row in table["totals"]] == ["Итого", "Итого + разовые"]
    assert table["average"]["title"] == "Среднее за 2 месяца 2026 года"
    assert "Food" in [row["name"] for row in table["groups"]]


def test_a_comparison_that_is_not_the_table_expected_is_left_as_text() -> None:
    table = ("            May 2026    June 2026\n"
             "Food 2          12.0         11.8\n"
             "\n"
             "Total           12.0         11.8\n"
             "Total + occasional   13.0    12.9\n")
    read = read_comparison(table, 2)
    assert [row["name"] for row in read["groups"]] == ["Food 2"]
    assert read["totals"][1]["cells"] == ["13.0", "12.9"] and read["delta"] is None
    for broken in ("", "nothing like a table", table.replace("11.8\n\n", "11.8 99.9 1.0\n\n"),
                   table.replace("12.0", "twelve", 1), table + "\nAverage  of 2\nTotal  1.0\n"):
        assert read_comparison(broken, 2) is None, broken
    assert read_comparison(table, 3) is None


def test_a_comparison_opens_on_the_two_newest_whole_months() -> None:
    month = lambda i, days: {"identity": i, "days": days}
    assert newest_real([month("a", 30), month("b", 29), month("c", 2)]) == ["a", "b"]
    assert newest_real([month("a", 30), month("c", 2)]) == ["a", "c"]
    assert newest_real([month("a", 3)]) == ["a"] and newest_real([]) == []


def test_a_comparisons_figures_are_written_as_the_screens_write_them() -> None:
    assert grouped("12.0") == "12.0" and grouped("-0.8") == "-0.8"
    assert grouped("1234.5") == f"1{KEEP}234.5" and grouped("-12345.0") == f"-12{KEEP}345.0"
    assert grouped("+1234.5") == f"+1{KEEP}234.5" and grouped("-") == "—"


def test_a_month_is_exported_as_text_for_print(budget: Budget) -> None:
    *_, mar = three_months(budget)
    name, data = budget.export(mar, 2026)
    text = data.decode("utf-8")
    assert name == "budget-March-2026.txt"
    assert text.startswith("March 2026\n") and "Food" in text
    assert f"Total: {budget.month(mar)['totals']['necessary']:.1f}\n" in text
    words.set_lang("ru")
    name, data = budget.export(mar, 2026)
    assert name == "budget-March-2026.txt"
    assert data.decode("utf-8").startswith("Март 2026\n")


def test_a_file_is_handed_to_a_messenger_as_what_it_is() -> None:
    import send

    assert send.kind_of("budget-backup-2026-09-21.json") == "application/json"
    assert send.kind_of("budget-March-2026.txt") == "text/plain"
    assert send.kind_of("anything") == "application/octet-stream"


def major(setup: dict, name: str) -> dict:
    return next(m for m in setup["majors"] if m["name"] == name)


def test_the_setup_is_changed_for_every_month_before_any_month_is_stored(
        budget: Budget) -> None:
    setup = budget.setup()
    assert major(setup, "Food")["limit"] == 30 and setup["limit_order"][0] == "Food"
    assert [s["id"] for s in setup["left"]["slots"]] == ["purse", "account"]
    assert setup["words"] == [] and setup["closed"] == []

    after = budget.configure({"op": "set_limit", "major": "Food", "value": 35})
    assert major(after, "Food")["limit"] == 35
    budget.configure({"op": "learn_word", "word": "flapjack", "group": "Food"})
    assert budget.setup()["words"] == [{"word": "flapjack", "group": "Food", "label": "Food"}]
    with pytest.raises(Refused) as refused:
        budget.configure({"op": "rename_major", "major": "Road", "name": "Food"})
    assert refused.value.code == "name_taken" and "Food" in str(refused.value)

    budget.add_example("month-1")
    assert food_limit(budget) == 35


def test_an_edit_for_every_month_reaches_the_closed_months_too(budget: Budget) -> None:
    asked = []
    real = budget._dispatch

    def spy(store, event):
        asked.append(dict(event))
        return real(store, event)

    budget.add_example("month-1")
    assert budget.months()[-1]["identity"] in budget.closed()
    budget._dispatch = spy
    budget.configure({"op": "set_limit", "major": "Food", "value": 35})
    assert asked[-1]["action"] == "configure" and "override" not in asked[-1]
    assert food_limit(budget) == 35


def test_edits_for_some_months_are_previewed_then_applied_together(budget: Budget) -> None:
    jan, feb, mar = three_months(budget)
    ops = [{"op": "set_limit", "major": "Food", "value": 35},
           {"op": "rename_major", "major": "Road", "name": "Travel"}]
    asked = []
    real = budget._dispatch

    def spy(store, event):
        asked.append(dict(event))
        return real(store, event)

    budget._dispatch = spy
    said = budget.configure_months(mar, "onward", ops)
    assert said["pending"] and said["months"] == ["March 2026", "and every later month"]
    assert "override" not in asked[-1]
    assert food_limit(budget) == 30

    done = budget.configure_months(mar, "onward", ops, confirm=True)
    assert major(done, "Food")["limit"] == 35 and major(done, "Road")["label"] == "Travel"
    names = lambda identity: {g["name"]: g["limit"] for g in budget.month(identity)["majors"]}
    assert names(mar)["Food"] == 35 and "Travel" in names(mar)
    assert names(feb)["Food"] == 30 and "Road" in names(feb)
    assert major(budget.setup(), "Food")["limit"] == 30
    assert major(budget.setup(mar), "Food")["limit"] == 35

    words.set_lang("ru")
    said = budget.configure_months(mar, "onward", [{"op": "set_limit", "major": "Food",
                                                    "value": 31}])
    assert said["months"] == ["Март 2026", "и все последующие месяцы"]


def removed(name: str) -> str:
    return f"the group {name} was removed - where does this go?"


def lines_of(month: dict, name: str) -> int:
    row = next(row for row in month["minors"] if row["name"] == name)
    return sum(len(lines) for lines in row["marks"] if lines)


def test_any_minor_group_is_removed_and_its_lines_become_questions(budget: Budget) -> None:
    months = three_months(budget)
    before = {identity: budget.month(identity) for identity in months}
    setup = budget.configure({"op": "remove_minor", "minor": "Food"})
    assert major(setup, "Food")["minors"] == []
    for identity, was in before.items():
        now = budget.month(identity)
        asked = [q for q in budget.questions(identity) if q["review"] == removed("Food")]
        assert len(asked) == lines_of(was, "Food") > 10, identity
        assert all(q["candidates"] == [] for q in asked)
        assert "Food" not in [row["name"] for row in now["minors"]]
        assert now["totals"]["necessary"] < was["totals"]["necessary"]

    setup = budget.configure({"op": "remove_major", "major": "Food"})
    assert "Food" not in [m["name"] for m in setup["majors"]]
    assert len([q for q in budget.questions(months[0])
                if q["review"] == removed("Food")]) == lines_of(before[months[0]], "Food")


def test_a_major_group_is_removed_with_its_minor_groups(budget: Budget) -> None:
    *_, mar = three_months(budget)
    was = budget.month(mar)
    setup = budget.configure({"op": "remove_major", "major": "Road"})
    assert "Road" not in [m["name"] for m in setup["majors"]]
    assert "Road" not in [n["name"] for m in setup["majors"] for n in m["minors"]]
    now = budget.month(mar)
    road = lines_of(was, "Road")
    assert len([q for q in budget.questions(mar) if q["review"] == removed("Road")]) == road
    assert now["questions"] == was["questions"] + road
    assert "Road" not in [g["name"] for g in now["majors"]]
    kept = {g["name"]: g["value"] for g in now["majors"] if g["name"] in ("Food", "Medicine")}
    assert kept == {g["name"]: g["value"] for g in was["majors"] if g["name"] in kept}


def test_the_last_group_spending_can_go_to_always_stays(budget: Budget) -> None:
    for name in ("Rent", "Food", "Road"):
        budget.configure({"op": "remove_major", "major": name})
    with pytest.raises(Refused) as refused:
        budget.configure({"op": "remove_major", "major": "Medicine"})
    assert refused.value.code == "last_major"
    budget.configure({"op": "remove_major", "major": "Refunds"})
    assert [m["name"] for m in budget.setup()["majors"] if m["tier"] != "EXCLUDED"] == [
        "Medicine"]


def test_a_limit_is_removed_at_any_time_with_nothing_asked(budget: Budget) -> None:
    months = three_months(budget)
    budget.configure({"op": "set_limit", "major": "Medicine", "value": None})
    for identity in months:
        medicine = major(budget.month(identity), "Medicine")
        assert medicine["limit"] is None and medicine["value"] > 0
    assert budget.setup()["limit_order"] == ["Food", "Road"]


def test_a_removed_groups_lines_are_asked_about_in_russian(tmp_path: Path) -> None:
    budget = russian_first(tmp_path)
    budget.add_example("month-1")
    budget.configure({"op": "remove_minor", "minor": "Еда"})
    words.set_lang("ru")
    month = budget.months()[-1]["identity"]
    assert "группу «Еда» удалили — куда это отнести?" in [
        q["review"] for q in budget.questions(month)]


def other_household() -> str:
    text = bundled.RULES_TOML
    assert text.count("limit = 30\n") == 1 and text.count("limit_total = 48\n") == 1
    return text.replace("limit = 30\n", "limit = 32\n").replace("limit_total = 48\n",
                                                                  "limit_total = 50\n")


def food_limit(budget: Budget) -> float:
    month = budget.months()[-1]["identity"]
    return next(m["limit"] for m in budget.month(month)["majors"] if m["name"] == "Food")


def test_the_file_carries_the_rules_and_restores_elsewhere_to_the_same_figures(
        tmp_path: Path) -> None:
    source = Budget(tmp_path / "source")
    source.add_example("month-2")
    name, raw = source.backup()
    assert name.startswith("budget-backup-") and name.endswith(".json")
    document = json.loads(raw)
    assert document["kind"] == "budget-backup"
    assert document["rules"] == source.rules.read_text(encoding="utf-8")
    assert document["phone"]["theme"] == "system"

    target = Budget(tmp_path / "target")
    target.add_example("month-1")
    said = target.restore(raw)
    assert said["restored"]["months"] == 1
    month = source.months()[-1]["identity"]
    assert target.months() == source.months()
    assert target.month(month) == source.month(month)


def test_rules_from_a_file_are_used_and_kept_until_start_over(tmp_path: Path) -> None:
    pc = Budget(tmp_path / "pc")
    pc.add_example("month-2")
    document = json.loads(pc.backup()[1])
    document["rules"] = other_household()
    document["page"] = {"options": {"--green": "#000000"}}
    raw = json.dumps(document).encode("utf-8")

    phone = Budget(tmp_path / "phone")
    assert not phone.own_rules and food_limit(phone.__class__(tmp_path / "pc")) == 30
    phone.restore(raw)
    assert phone.own_rules and food_limit(phone) == 32

    again = Budget(tmp_path / "phone")
    assert again.own_rules and food_limit(again) == 32

    again.start_over()
    assert not again.own_rules
    again.add_example("month-2")
    assert food_limit(again) == 30


def test_a_file_without_its_rules_is_refused_and_replaces_nothing(tmp_path: Path) -> None:
    source = Budget(tmp_path / "source")
    source.add_example("month-2")
    document = json.loads(source.backup()[1])
    del document["rules"]
    raw = json.dumps(document).encode("utf-8")

    phone = Budget(tmp_path / "phone")
    phone.add_example("month-1")
    before = phone.months()
    for step in (phone.read_backup, phone.restore):
        with pytest.raises(Refused, match="no rules in it"):
            step(raw)
    assert phone.months() == before and not phone.own_rules


def test_a_broken_file_or_broken_rules_replace_nothing(tmp_path: Path) -> None:
    phone = Budget(tmp_path)
    phone.add_example("month-1")
    before = phone.months()
    with pytest.raises(Refused, match="not a configuration file"):
        phone.restore(b"\x89PNG not json")
    with pytest.raises(Refused, match="not a budget configuration file"):
        phone.restore(json.dumps({"kind": "something else"}).encode("utf-8"))

    document = json.loads(phone.backup()[1])
    document["rules"] = "[groups this is not a rules file"
    with pytest.raises(Refused, match="rules in that file cannot be used"):
        phone.restore(json.dumps(document).encode("utf-8"))
    assert phone.months() == before and not phone.own_rules


def test_a_refused_restore_puts_the_rules_back(tmp_path: Path) -> None:
    source = Budget(tmp_path / "source")
    source.add_example("month-2")
    document = json.loads(source.backup()[1])
    document["rules"] = other_household()
    document["server"]["periods"] = ["not", "a", "table"]

    phone = Budget(tmp_path / "phone")
    phone.add_example("month-1")
    before = (phone.months(), phone.rules.read_text(encoding="utf-8"))
    with pytest.raises(Refused):
        phone.restore(json.dumps(document).encode("utf-8"))
    assert (phone.months(), phone.rules.read_text(encoding="utf-8")) == before
    assert not phone.own_rules and food_limit(phone) == 30


def test_restored_rules_survive_a_lost_marker(tmp_path: Path) -> None:
    source = Budget(tmp_path / "source")
    source.add_example("month-2")
    document = json.loads(source.backup()[1])
    document["rules"] = other_household()
    phone = Budget(tmp_path / "phone")
    phone.restore(json.dumps(document).encode("utf-8"))

    for damage in ("", "garbage"):
        (tmp_path / "phone" / "rules.origin").write_text(damage, encoding="utf-8")
        again = Budget(tmp_path / "phone")
        assert again.own_rules and food_limit(again) == 32
    (tmp_path / "phone" / "rules.origin").unlink()
    again = Budget(tmp_path / "phone")
    assert again.own_rules and food_limit(again) == 32

    Budget(tmp_path / "fresh")
    (tmp_path / "fresh" / "rules.origin").unlink()
    assert not Budget(tmp_path / "fresh").own_rules


def test_no_configuration_file_is_made_without_the_rules(tmp_path: Path) -> None:
    phone = Budget(tmp_path)
    phone.add_example("month-1")
    phone.rules.unlink()
    with pytest.raises(Refused, match="no"):
        phone.backup()


def test_the_language_survives_a_restart(tmp_path: Path) -> None:
    budget = Budget(tmp_path)
    look = Look(tmp_path)
    assert look.language == "en"
    look.language = "ru"
    look.save()
    assert Look(tmp_path).language == "ru"
    again = Look(tmp_path)
    again.theme = "dark"
    again.save()
    assert Look(tmp_path).language == "ru"
    budget.add_example("month-1")
    budget.start_over()
    assert Look(tmp_path).language == "ru"
    (tmp_path / "look.json").write_text(json.dumps({"language": "xx"}), encoding="utf-8")
    assert Look(tmp_path).language == "en"


def test_the_language_travels_in_the_file(tmp_path: Path) -> None:
    source = Budget(tmp_path / "source")
    source.add_example("month-2")
    assert json.loads(source.backup()[1])["lang"] == "en"
    look = Look(tmp_path / "source")
    look.language = "ru"
    look.save()
    document = json.loads(source.backup()[1])
    assert document["lang"] == "ru"
    assert set(document["phone"]) == {"theme", "sizes"}

    target = Budget(tmp_path / "target")
    assert Look(tmp_path / "target").language == "en"
    target.restore(json.dumps(document).encode("utf-8"))
    assert Look(tmp_path / "target").language == "ru"
    assert target.months() == source.months()


def test_a_file_without_a_language_keeps_the_current_one(tmp_path: Path) -> None:
    source = Budget(tmp_path / "source")
    source.add_example("month-2")
    document = json.loads(source.backup()[1])
    target = Budget(tmp_path / "target")
    look = Look(tmp_path / "target")
    look.language, look.theme = "ru", "dark"
    look.save()
    for lang in (None, "xx", 5, ["ru"]):
        if lang is None:
            document.pop("lang", None)
        else:
            document["lang"] = lang
        target.restore(json.dumps(document).encode("utf-8"))
        assert Look(tmp_path / "target").language == "ru", lang
    del document["phone"]
    document.pop("lang")
    look = Look(tmp_path / "target")
    look.theme = "dark"
    look.save()
    target.restore(json.dumps(document).encode("utf-8"))
    kept = Look(tmp_path / "target")
    assert (kept.language, kept.theme) == ("ru", "dark")


def test_the_engine_is_asked_in_the_language_chosen(budget: Budget) -> None:
    asked = []
    real = budget._dispatch

    def spy(store, event):
        asked.append(dict(event))
        return real(store, event)

    budget._dispatch = spy
    budget.months()
    words.set_lang("ru")
    budget.months()
    assert "lang" not in asked[0] and asked[1]["lang"] == "ru"

    budget._dispatch = lambda store, event: {"ok": False, "error": "закрыт", "code": "closed"}
    with pytest.raises(Refused) as refused:
        budget.months()
    assert (str(refused.value), refused.value.code) == ("закрыт", "closed")
    budget._dispatch = lambda store, event: {"ok": False}
    with pytest.raises(Refused, match="приложению не удалось") as refused:
        budget.months()
    assert refused.value.code is None


def test_the_phones_own_refusals_are_said_in_russian(budget: Budget) -> None:
    words.set_lang("ru")
    with pytest.raises(Refused, match="Добавлять нечего"):
        budget.add("   ")
    with pytest.raises(Refused, match="Это не файл конфигурации —"):
        budget.restore(b"\x89PNG not json")
    with pytest.raises(Refused, match="Это не файл конфигурации бюджета"):
        budget.restore(json.dumps({"kind": "something else"}).encode("utf-8"))
    with pytest.raises(Refused, match="В этом файле нет правил"):
        budget.read_backup(json.dumps({"kind": "budget-backup"}).encode("utf-8"))


def test_a_word_without_russian_is_said_in_english() -> None:
    words.set_lang("ru")
    assert words.t("no.such.key", "Plain {x}", x=1) == "Plain 1"
    assert words.t("no.such.key", "Unfilled {x}") == "Unfilled {x}"
    assert words.t("closed", "This month is closed - press Unlock at the top first.") \
        == words.RU["closed"]
    words.set_lang("de")
    assert words.LANG == "en"


_FIELD = re.compile(r"\{(\w+)(?:\|[^{}]*)?\}")


def _word_calls() -> list[tuple[str, ast.Call]]:
    calls = []
    for name in ("main.py", "data.py", "send.py"):
        for node in ast.walk(ast.parse((SRC / name).read_text(encoding="utf-8"))):
            f = getattr(node, "func", None)
            if isinstance(node, ast.Call) and (
                    (isinstance(f, ast.Name) and f.id == "t")
                    or (isinstance(f, ast.Attribute) and f.attr == "t"
                        and isinstance(f.value, ast.Name) and f.value.id == "words")):
                calls.append((f"{name}:{node.lineno}", node))
    return calls


def test_every_phone_word_has_russian_with_the_same_values() -> None:
    calls = _word_calls()
    assert len(calls) > 100
    english_of: dict[str, str] = {}
    for where, call in calls:
        key, english = call.args[0], call.args[1]
        if not isinstance(key, ast.Constant):
            continue
        key, english = key.value, english.value
        given = {k.arg for k in call.keywords}
        assert key in words.RU, (where, key)
        en, ru = set(_FIELD.findall(english)), set(_FIELD.findall(words.RU[key]))
        assert en == given, (where, key, en, given)
        assert ru <= en and en - ru <= {"s"}, (where, key, en, ru)
        assert english_of.setdefault(key, english) == english, (where, key, "two Englishes")
        filled = words.fill(words.RU[key], {name: 2 for name in given})
        assert "{" not in filled and filled.strip(), (where, key, filled)
    shown = set(english_of) | {"size." + kind for kind in Look.SIZES} \
        | {"month." + name for name in (*words.MONTHS, "undated")}
    assert set(words.RU) == shown, set(words.RU) ^ shown
    assert len(words.MONTHS_SHORT_RU) == 12


def majors(budget: Budget) -> list[str]:
    return [m["name"] for m in budget.call(action="config")["majors"]]


def household_majors(lang: str) -> list[str]:
    rules = tomllib.loads(bundled.HOUSEHOLDS[lang]["rules"])
    return [m["name"] for m in rules["groups"]["majors"]]


def marker(folder: Path) -> str:
    return (folder / "rules.origin").read_text(encoding="utf-8")


def russian_first(folder: Path) -> Budget:
    folder.mkdir(parents=True, exist_ok=True)
    look = Look(folder)
    look.language = "ru"
    look.save()
    return Budget(folder)


def test_one_start_in_each_language() -> None:
    assert list(bundled.HOUSEHOLDS) == ["en", "ru"]
    assert household_majors("en") == ["Rent", "Food", "Road", "Medicine", "Refunds", "Set aside"]
    assert household_majors("ru") == ["Аренда", "Еда", "Дорога", "Медицина", "Возвраты",
                                      "Отложено"]
    for lang in ("en", "ru"):
        rules = tomllib.loads(bundled.HOUSEHOLDS[lang]["rules"])
        rent, *three = rules["groups"]["majors"][:4]
        assert rent["minors"] == [] and "limit" not in rent
        assert [(m["minors"], m["limit"]) for m in three] == [([m["name"]], limit) for m, limit
                                                                 in zip(three, (30, 10, 8))]
        assert list(bundled.HOUSEHOLDS[lang]["examples"]) == ["month-1", "month-2", "month-3"]
    assert HINTS == {"en": "12.01\n26 bus\n180 soup\n26 bus\nLeft: purse 2.9, account 61110",
                     "ru": "12.01\n26 автобус\n180 суп\n26 автобус\n"
                           "Остаток: наличные 2,9, счёт 61110"}


def test_a_russian_first_start_gets_the_russian_household(tmp_path: Path) -> None:
    budget = russian_first(tmp_path / "ru")
    assert majors(budget) == household_majors("ru") != household_majors("en")
    assert (budget.household, marker(budget.folder), budget.own_rules) == ("ru", "invented:ru", False)
    assert budget.rules.read_text(encoding="utf-8") == bundled.HOUSEHOLDS["ru"]["rules"]
    assert budget.examples() == list(bundled.HOUSEHOLDS["ru"]["examples"])
    assert budget.example_hint() == HINTS["ru"]

    english = Budget(tmp_path / "en")
    assert (english.household, marker(english.folder)) == ("en", "invented:en")
    assert majors(english) == household_majors("en") and english.example_hint() == HINTS["en"]


def test_switching_an_untouched_phone_swaps_the_household(budget: Budget) -> None:
    assert budget.household == "en" and budget.untouched()
    words.set_lang("ru")
    assert budget.follow_language("ru")
    assert majors(budget) == household_majors("ru") and marker(budget.folder) == "invented:ru"
    assert budget.examples() == list(bundled.HOUSEHOLDS["ru"]["examples"])
    assert budget.example_hint() == HINTS["ru"]
    assert not budget.follow_language("ru")
    assert not budget.follow_language("de")
    assert Budget(budget.folder).household == "ru"

    words.set_lang("en")
    assert budget.follow_language("en")
    assert majors(budget) == household_majors("en") and marker(budget.folder) == "invented:en"

    budget.add_example("month-1")
    budget.start_over()
    assert budget.path.is_file() and budget.untouched()
    assert budget.follow_language("ru") and majors(budget) == household_majors("ru")


def test_switching_with_months_keeps_the_household(budget: Budget) -> None:
    budget.add_example("month-1")
    words.set_lang("ru")
    assert not budget.untouched() and not budget.follow_language("ru")
    assert majors(budget) == household_majors("en") and budget.household == "en"
    assert budget.examples() == list(bundled.EXAMPLES)
    assert budget.example_hint() == HINTS["en"]
    month = budget.months()[-1]["identity"]
    assert budget.month(month)["left"]["text"].startswith("Left: ")

    edited = Budget(budget.folder.parent / "edited")
    edited.call(action="configure", op="rename_major", major="Food", name="Renamed")
    assert not edited.untouched() and not edited.follow_language("ru")
    assert majors(edited) == household_majors("en")


def test_a_files_rules_are_never_swapped(tmp_path: Path) -> None:
    pc = Budget(tmp_path / "pc")
    document = json.loads(pc.backup()[1])
    document["rules"] = other_household()
    phone = Budget(tmp_path / "phone")
    phone.restore(json.dumps(document).encode("utf-8"))
    assert phone.own_rules and phone.household is None and phone.untouched()

    words.set_lang("ru")
    assert not phone.follow_language("ru") and not phone.follow_language("en")
    assert marker(phone.folder) == "file"
    assert phone.rules.read_text(encoding="utf-8") == other_household()
    assert phone.examples() == list(bundled.HOUSEHOLDS["ru"]["examples"])
    assert phone.example_hint() == HINTS["ru"]

    look = Look(tmp_path / "phone")
    look.language = "ru"
    look.save()
    for damage in (None, "garbage", ""):
        if damage is not None:
            (tmp_path / "phone" / "rules.origin").write_text(damage, encoding="utf-8")
        again = Budget(tmp_path / "phone")
        assert again.own_rules and not again.follow_language("ru"), damage
        assert again.rules.read_text(encoding="utf-8") == other_household(), damage


def test_start_over_brings_the_household_of_the_language(budget: Budget) -> None:
    budget.add_example("month-1")
    month = budget.months()[-1]["identity"]
    budget.call(action="move", period=month, raw="620 cough syrup", group="Food",
                override=True)
    words.set_lang("ru")
    assert not budget.follow_language("ru") and budget.household == "en"

    budget.start_over()
    assert budget.months() == [] and budget.household == "ru"
    assert majors(budget) == household_majors("ru") and marker(budget.folder) == "invented:ru"
    assert Budget(budget.folder).household == "ru"

    words.set_lang("en")
    budget.add_example("month-2")
    budget.start_over()
    assert budget.household == "en" and majors(budget) == household_majors("en")


def test_a_russian_household_survives_a_restart(tmp_path: Path) -> None:
    budget = russian_first(tmp_path)
    budget.add_example("month-1")
    look = Look(tmp_path)
    look.language = "en"
    look.save()

    again = Budget(tmp_path)
    assert again.household == "ru" and majors(again) == household_majors("ru")
    assert again.rules.read_text(encoding="utf-8") == bundled.HOUSEHOLDS["ru"]["rules"]
    month = again.months()[-1]["identity"]
    assert again.month(month)["left"]["text"].startswith("Остаток: ")

    again.rules.write_text(bundled.HOUSEHOLDS["ru"]["rules"] + "\n# older\n", encoding="utf-8")
    later = Budget(tmp_path)
    assert later.household == "ru" and marker(tmp_path) == "invented:ru"
    assert later.rules.read_text(encoding="utf-8") == bundled.HOUSEHOLDS["ru"]["rules"]


def test_the_old_invented_marker_reads_as_english(tmp_path: Path) -> None:
    Budget(tmp_path).add_example("month-1")
    (tmp_path / "rules.origin").write_text("invented", encoding="utf-8")
    look = Look(tmp_path)
    look.language = "ru"
    look.save()

    phone = Budget(tmp_path)
    assert (phone.household, phone.own_rules) == ("en", False)
    assert majors(phone) == household_majors("en") and phone.months()

    (tmp_path / "rules.toml").write_text(other_household(), encoding="utf-8")
    (tmp_path / "rules.origin").write_text("invented", encoding="utf-8")
    phone = Budget(tmp_path)
    assert phone.rules.read_text(encoding="utf-8") == bundled.RULES_TOML
    assert phone.household == "en" and marker(tmp_path) == "invented:en"
    assert food_limit(phone) == 30


def test_the_plain_start_reads_as_the_household_it_is_now(tmp_path: Path) -> None:
    for written, lang in (("invented:simple", "en"), ("invented:simple-ru", "ru")):
        folder = tmp_path / lang
        Budget(folder)
        (folder / "rules.toml").write_text(other_household(), encoding="utf-8")
        (folder / "rules.origin").write_text(written, encoding="utf-8")
        phone = Budget(folder)
        assert (phone.household, phone.own_rules) == (lang, False), written
        assert phone.rules.read_text(encoding="utf-8") == bundled.HOUSEHOLDS[lang]["rules"]
        assert marker(folder) == "invented:" + lang and majors(phone) == household_majors(lang)


def test_every_russian_example_books(tmp_path: Path) -> None:
    english = Budget(tmp_path / "en")
    for name in english.examples():
        outcome = english.add_example(name)
        assert outcome and all(o["outcome"] == "imported" for o in outcome), outcome
    read = [english.month(m["identity"]) for m in stored(english.months())]

    russian = russian_first(tmp_path / "ru")
    assert russian.examples() == english.examples()
    for name in russian.examples():
        outcome = russian.add_example(name)
        assert outcome and all(o["outcome"] == "imported" for o in outcome), outcome
    pairs = list(zip(stored(russian.months()), read, strict=True))
    assert [ru["month"] for ru, _ in pairs] == ["January", "February", "March"]
    for ru_month, en in pairs:
        ru = russian.month(ru_month["identity"])
        asked = russian.questions(ru_month["identity"])
        assert ru["totals"] == en["totals"] and ru["totals"]["necessary"] > 0
        assert len(asked) == ru["questions"] == en["questions"] > 0
        assert [g["value"] for g in ru["majors"]] == [g["value"] for g in en["majors"]]
        spending = [g for g in ru["majors"] if g["name"] in ("Аренда", "Еда", "Дорога", "Медицина")]
        assert len(spending) == 4 and all(g["value"] > 0 for g in spending)
        assert ru["left"]["text"].startswith("Остаток: ")
        assert [c["value"] for c in ru["left"]["cells"]] == [
            c["value"] for c in en["left"]["cells"]] and len(ru["left"]["cells"]) == len(
            tomllib.loads(bundled.HOUSEHOLDS["ru"]["rules"])["left"]["slots"])


def test_a_line_for_a_month_not_stored_makes_that_month(budget: Budget) -> None:
    budget.configure({"op": "add_major", "name": "Ladder", "tier": "OCCASIONAL"})
    budget.add("03.09\n+ 60 000\n4000 rent\n\n06.09\n"
               "+ 1800 ladder, do not count refers to August\n")
    months = budget.months()
    assert [(m["month"], m["moved"]) for m in months] == [("August", True), ("September", False)]
    august, september = months[0]["identity"], months[1]["identity"]
    month = budget.month(september)
    assert month["held"] == [] and not budget.questions(september)
    assert next(g for g in month["majors"] if g["name"] == "Set aside")["value"] == -56.0
    rent = next(r for r in month["minors"] if r["name"] == "Rent")
    assert (rent["amounts"], rent["total"]) == ([4000], 4000)
    assert next(g for g in month["majors"] if g["name"] == "Rent")["value"] == 4.0

    asked = budget.questions(august)
    assert [(q["raw"], q["candidates"]) for q in asked] == [
        ("+ 1800 ladder, do not count refers to August", ["Ladder"])]
    budget.answer(august, asked[0]["number"], "Ladder")
    budget.unlocked.add(august)
    budget.add("15.08\n300 bread\n", into=august)
    months = budget.months()
    assert [(m["month"], m["moved"]) for m in months] == [("August", False), ("September", False)]
    real = months[0]["identity"]
    assert next(g for g in budget.month(real)["majors"] if g["name"] == "Ladder")["value"] == -1.8
    assert [q["raw"] for q in budget.questions(real)] == ["300 bread"]


def test_the_setup_says_which_groups_do_a_job(budget: Budget) -> None:
    roles = {n["name"]: n["role"] for m in budget.setup()["majors"] for n in m["minors"]}
    assert roles["Salary"] == "salary" and roles["Withdrawal"] == "withdrawal"
    assert roles["Elsewhere"] == "elsewhere" and roles["Food"] is None


def test_a_name_one_letter_off_a_group_is_found() -> None:
    from data import near_group, one_letter_off
    assert one_letter_off("skitles", "skittles") and one_letter_off("skittles", "skitles")
    assert one_letter_off("food", "food.") and one_letter_off("road", "raod")
    assert one_letter_off("medicine", "medicane")
    assert not one_letter_off("food", "food") and not one_letter_off("road", "rope")
    groups = ["Food", "Road", "Skitles", "Set aside"]
    assert near_group("Skittles", groups) == "Skitles"
    assert near_group("skitles", groups) is None
    assert near_group("Rod", groups) is None
    assert near_group("Museum", groups) is None


def test_the_names_a_typed_group_is_held_against(budget: Budget) -> None:
    three_months(budget)
    march = budget.months()[-1]["identity"]
    names = budget.group_names(march)
    assert {"Rent", "Food", "Road", "Medicine", "Refunds", "Set aside", "Salary",
            "Withdrawal"} <= set(names)
    assert "Totally saved" not in names and len(names) == len(set(names))
