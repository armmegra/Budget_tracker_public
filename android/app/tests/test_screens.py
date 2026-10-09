from __future__ import annotations

import ast
import asyncio
import json
import re
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import flet as ft
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import bundled
import main as app
import words
from data import HINTS, Budget, Look, Refused, money, unbroken


class FakePicker:
    picked: list = []
    saved: list = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def pick_files(self, **kwargs):
        return FakePicker.picked.pop(0) if FakePicker.picked else []

    async def save_file(self, **kwargs):
        FakePicker.saved.append(kwargs)
        return "/storage/emulated/0/Download/" + kwargs["file_name"]


def chosen(raw: bytes) -> list:
    return [SimpleNamespace(bytes=raw, path=None)]


class StandInPage:
    def __init__(self) -> None:
        self.title = self.theme = self.dark_theme = self.theme_mode = self.padding = None
        self.appbar = self.navigation_bar = None
        self.added: list[ft.Control] = []
        self.dialogs: list[ft.Control] = []
        self.updates = 0

    def add(self, *controls: ft.Control) -> None:
        self.added.extend(controls)

    def update(self) -> None:
        self.updates += 1

    def show_dialog(self, dialog: ft.Control) -> None:
        self.dialogs.append(dialog)

    def pop_dialog(self) -> None:
        opened = [d for d in self.dialogs if not isinstance(d, ft.SnackBar)]
        if opened:
            self.dialogs.remove(opened[-1])

    def top(self, kind=None) -> ft.Control:
        return next(d for d in reversed(self.dialogs)
                    if not isinstance(d, ft.SnackBar) and (kind is None or isinstance(d, kind)))


def walk(control):
    yield control
    for name in ("content", "controls", "actions", "title", "subtitle", "leading", "trailing",
                 "segments", "label"):
        child = getattr(control, name, None)
        if isinstance(child, ft.Control):
            yield from walk(child)
        elif isinstance(child, list):
            for item in child:
                if isinstance(item, ft.Control):
                    yield from walk(item)


def texts(control) -> str:
    words = []
    for c in walk(control):
        if isinstance(c, ft.Text):
            if c.value:
                words.append(str(c.value))
            words += [s.text for s in (c.spans or []) if s.text]
        elif isinstance(getattr(c, "content", None), str):
            words.append(c.content)
    return " | ".join(words)


def press(button) -> None:
    done = button.on_click(SimpleNamespace(control=button))
    if asyncio.iscoroutine(done):
        asyncio.run(done)


def button(root, words: str):
    for c in walk(root):
        content = getattr(c, "content", None)
        label = content if isinstance(content, str) else texts(content) if content else None
        if getattr(c, "on_click", None) and label and words in str(label):
            return c
    raise AssertionError(f"no button reading {words!r} in: {texts(root)[:400]}")


def no_question(phone) -> bool:
    return not [d for d in phone.page.dialogs if isinstance(d, ft.AlertDialog)]


EMPTY_MONTH = "Nothing has been added yet — this is how your month will look."


@pytest.fixture()
def phone(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "phone"))
    monkeypatch.setattr(ft, "FilePicker", FakePicker)
    FakePicker.picked, FakePicker.saved = [], []
    page = StandInPage()
    app.main(page)

    def body() -> ft.ListView:
        return page.added[0].content

    def shown() -> ft.Column:
        column = ft.Column(controls=list(body().controls))
        assert "Something went wrong" not in texts(column), texts(column)[:1500]
        assert words.RU["failed"] not in texts(column), texts(column)[:1500]
        return column

    def tab(at: int) -> ft.Column:
        page.navigation_bar.on_change(
            SimpleNamespace(control=SimpleNamespace(selected_index=at)))
        return shown()

    def examples(*numbers: int) -> None:
        for number in numbers:
            press(button(tab(app.ADD), "Try an example month"))
            press(button(page.top(ft.AlertDialog), f"Example {number}"))

    return SimpleNamespace(page=page, body=body, shown=shown, tab=tab, examples=examples,
                           folder=Path(tmp_path) / "phone", elsewhere=Path(tmp_path))


def test_a_group_shows_each_figure_with_its_lines_and_their_days(phone) -> None:
    phone.examples(1)
    press(button(phone.shown(), "Medicine"))
    lines = texts(phone.page.top(ft.AlertDialog))
    assert "13.01" in lines and "900 doctor" in lines, lines


def test_a_figure_is_moved_from_the_phone(phone) -> None:
    phone.examples(1)
    press(button(phone.shown(), "Medicine"))
    press(button(phone.page.top(ft.AlertDialog), "13.01"))
    press(button(phone.page.top(ft.AlertDialog), "Other…"))
    press(button(phone.page.top(ft.AlertDialog), "Road"))
    assert "Unlock" in texts(phone.page.top(ft.AlertDialog))

    phone.page.dialogs.clear()
    press(button(phone.shown(), "Unlock"))
    press(button(phone.shown(), "Medicine"))
    figure = button(phone.page.top(ft.AlertDialog), "13.01")
    amount = texts(figure).split(" | ")[0]
    press(figure)
    press(button(phone.page.top(ft.AlertDialog), "Other…"))
    press(button(phone.page.top(ft.AlertDialog), "Road"))
    assert no_question(phone)
    month = texts(phone.shown())
    road = month[month.rindex("| Road |"):].split(" | ")[2]
    assert amount in road.split(", "), (amount, road)


def test_add_to_offers_a_new_month_and_every_stored_one(phone) -> None:
    phone.examples(1, 2)
    add = phone.tab(app.ADD)
    into = next(c for c in walk(add) if isinstance(c, ft.Dropdown))
    labels = [o.text for o in into.options]
    assert labels[0] == "A new month" and labels[1:] == ["February 2026", "January 2026",
                                                         "December 2025"]
    assert into.value == ""


def test_the_add_screen_offers_the_example_months_and_the_households_hint(phone) -> None:
    add = phone.tab(app.ADD)
    assert "opening salary line" in texts(add)
    assert next(c for c in walk(add) if isinstance(c, ft.TextField)).hint_text == HINTS["en"]
    press(button(add, "Try an example month"))
    offered = [c.content for c in phone.page.top(ft.AlertDialog).actions]
    assert offered == ["Example 1", "Example 2", "Example 3", "Cancel"]


def test_ask_them_all_again_asks_before_it_forgets(phone) -> None:
    phone.examples(2)
    press(button(phone.tab(app.QUESTIONS), "Ask them all again"))
    sure = phone.page.top(ft.AlertDialog)
    assert "the notes stay" in texts(sure)
    press(button(sure, "No, keep them"))
    assert no_question(phone)


def test_every_place_opens_on_a_fresh_app(phone) -> None:
    for at in (app.MONTH, app.QUESTIONS, app.ADD):
        phone.tab(at)
    assert "No months yet" in texts(phone.tab(app.QUESTIONS))
    assert EMPTY_MONTH in texts(phone.tab(app.MONTH))
    phone.tab(app.GUIDE)
    assert "Moving between months" in texts(phone.page.top(ft.AlertDialog))
    phone.tab(app.OPTIONS)
    options = texts(phone.page.top(ft.BottomSheet))
    assert "Text size" in options and "Start over" in options
    assert phone.page.navigation_bar.selected_index == app.MONTH


def test_an_example_month_is_drawn_as_it_was_chosen(phone) -> None:
    phone.examples(1)
    month = texts(phone.shown())
    for part in ("Total", "With occasional", "With a limit", "No limit", "Minor groups",
                 "saved", "overspent"):
        assert part in month, (part, month[:900])
    assert "Totally saved" not in month
    assert "January 2026" in texts(phone.page.appbar)
    badge = phone.page.navigation_bar.destinations[app.QUESTIONS].icon.badge
    assert badge is not None and int(badge.label) > 0


def test_the_arrows_step_through_the_months_in_order(phone) -> None:
    phone.examples(1, 2, 3)
    bar = phone.page.appbar
    assert "March 2026" in texts(bar) and bar.actions[0].disabled
    for _ in range(3):
        press(phone.page.appbar.leading)
    bar = phone.page.appbar
    assert "December 2025" in texts(bar) and bar.leading.disabled
    assert "Only lines written in other months" in texts(phone.shown())
    press(bar.actions[0])
    assert "January 2026" in texts(phone.page.appbar)
    assert "Only lines written in other months" not in texts(phone.shown())


def test_the_month_name_lists_the_months_under_their_year(phone) -> None:
    phone.examples(1, 3)
    press(phone.page.appbar.title)
    sheet = phone.page.top(ft.BottomSheet)
    years = [c for c in walk(sheet) if isinstance(c, ft.ExpansionTile)]
    assert [texts(y.title) for y in years] == ["2026", "2025"] and years[0].expanded
    cells = {texts(c.content) if not isinstance(c.content, str) else c.content: c
             for c in walk(years[0]) if isinstance(c, (ft.TextButton, ft.FilledButton,
                                                       ft.OutlinedButton))}
    assert len(cells) == 12 and cells["Feb"].disabled
    press(cells["Jan"])
    assert "January 2026" in texts(phone.page.appbar)


def test_a_closed_month_is_unlocked_and_a_question_answered(phone) -> None:
    phone.examples(2)
    questions = phone.tab(app.QUESTIONS)
    press(button(questions, "Unlock"))
    before = texts(phone.shown())
    assert "Unlocked until you close the app" in before, before[:800]

    cards = [c for c in walk(phone.shown()) if isinstance(c, ft.Card)]
    offered = [c for c in walk(cards[0]) if isinstance(c, ft.OutlinedButton)]
    listed = phone.body()
    press(offered[0])
    after = texts(phone.shown())
    count = lambda s: int(s.split(" line")[0].split("|")[-1].strip())
    assert count(after) == count(before) - 1, (before[:300], after[:300])
    assert phone.body() is listed, "answering threw away the list, and its place"
    phone.tab(app.MONTH)
    assert phone.body() is not listed, "another tab reused the list, and opens where it was"


def test_a_name_one_letter_off_a_group_asks_which_was_meant(phone) -> None:
    pc = Budget(phone.folder)
    pc.add("03.09\n+ 60 000\n\n06.09\n2700 skittles\n1100 skittles\n")
    pc.configure({"op": "add_major", "name": "Skitles", "tier": "FREQUENT", "limit": 5})
    month = pc.months()[-1]["identity"]

    def other(raw: str, typed: str) -> None:
        card = next(c for c in walk(phone.tab(app.QUESTIONS))
                    if isinstance(c, ft.Card) and raw in texts(c))
        press(button(card, "Other…"))
        fill(phone.page.top(ft.AlertDialog), typed, ok="Book it")

    other("2700 skittles", "Skittles")
    ask = phone.page.top(ft.AlertDialog)
    assert "Did you mean Skitles?" in texts(ask)
    assert "Skittles is one letter off Skitles, a group that already exists." in texts(ask)
    press(button(ask, "Yes, Skitles"))
    assert no_question(phone)
    groups = {g["name"]: g for g in pc.month(month)["majors"]}
    assert groups["Skitles"]["value"] == 2.7 and groups["Skitles"]["limit"] == 5

    other("1100 skittles", "Skittles")
    press(button(phone.page.top(ft.AlertDialog), "No, a new group Skittles"))
    groups = {g["name"]: g for g in pc.month(month)["majors"]}
    assert groups["Skittles"]["value"] == 1.1 and groups["Skittles"]["limit"] is None

    phone.tab(app.MONTH)
    press(button(phone.shown(), "Skittles"))
    press(button(phone.page.top(ft.AlertDialog), "06.09"))
    press(button(phone.page.top(ft.AlertDialog), "Other…"))
    fill(phone.page.top(ft.AlertDialog), "Skitle", ok="Move there")
    press(button(phone.page.top(ft.AlertDialog), "Yes, Skitles"))
    assert no_question(phone)
    groups = {g["name"]: g for g in pc.month(month)["majors"]}
    assert groups["Skitles"]["value"] == 3.8 and "Skittles" not in groups


def test_a_question_and_a_figure_show_their_day_as_written(phone) -> None:
    Budget(phone.folder).add("03.05\n+ 60 000\n\n14.05\n140\n310 bird seed\n\n"
                             "1400 window cleaner\n+ 1400 window cleaner\n\n3600 choir fees\n"
                             "Left: purse 3.1, account 41800\n")
    def bold(control) -> list[str]:
        return [t.value for t in walk(control)
                if isinstance(t, ft.Text) and t.weight == ft.FontWeight.BOLD]

    card = next(c for c in walk(phone.tab(app.QUESTIONS))
                if isinstance(c, ft.Card) and bold(c) == ["3600 choir fees"])
    box = next(c for c in walk(card) if isinstance(c, app.DayLines))
    assert "14.05" in texts(card)
    assert [row.value for row in box.controls] == [
        "140", "310 bird seed", " ", "1400 window cleaner", "+ 1400 window cleaner", " ", "3600 choir fees",
        "Left: purse 3.1, account 41800"]
    assert [row.value for row in box.controls if row.weight == ft.FontWeight.BOLD] == [
        "3600 choir fees"]
    assert box.scroll == ft.ScrollMode.AUTO and box.height
    marked = next(row for row in box.controls if row.weight == ft.FontWeight.BOLD)
    assert marked.size == 17 and marked.style.decoration == ft.TextDecoration.UNDERLINE
    assert all(row.size == 15 and row.style is None for row in box.controls if row is not marked)
    assert [row.value for row in box.controls if row.key is not None] == ["+ 1400 window cleaner"]

    phone.page.dialogs.clear()
    phone.examples(1)
    press(phone.page.appbar.leading)
    assert "January 2026" in texts(phone.page.appbar)
    press(button(phone.shown(), "Medicine"))
    press(button(phone.page.top(ft.AlertDialog), "13.01"))
    moving = phone.page.top(ft.AlertDialog)
    box = next(c for c in walk(moving) if isinstance(c, app.DayLines))
    assert "13.01" in texts(moving)
    assert [row.value for row in box.controls if row.weight == ft.FontWeight.BOLD] == [
        "900 doctor"]


def grand(phone) -> str:
    card = next(c for c in walk(phone.shown()) if isinstance(c, ft.Card))
    return texts(card).split("With occasional | ")[1].split(" | ")[0]


def with_heating(phone) -> None:
    phone.examples(2)
    pc = Budget(phone.folder)
    month = pc.months()[-1]["identity"]
    heating = next(q for q in pc.questions(month) if "heating" in q["raw"])
    pc.call(action="answer", period=month, number=heating["number"], group="Heating",
            new=False, override=True)
    phone.tab(app.MONTH)


def test_with_occasional_opens_what_it_counts_and_a_tick_leaves_one_out(phone) -> None:
    with_heating(phone)
    before = grand(phone)
    tap = next(c for c in walk(phone.shown())
               if isinstance(c, ft.Container) and c.on_click and "With occasional" in texts(c))
    press(tap)
    sheet = phone.page.top(ft.BottomSheet)
    assert "Counted in With occasional" in texts(sheet) and "Heating" in texts(sheet)
    boxes = [c for c in walk(sheet) if isinstance(c, ft.Checkbox)]
    assert boxes and all(b.value for b in boxes)

    boxes[0].value = False
    press(button(sheet, "Apply"))
    assert "closed" in phone.page.dialogs[-1].content.value
    assert grand(phone) == before

    press(button(phone.shown(), "Unlock"))
    press(tap := next(c for c in walk(phone.shown()) if isinstance(c, ft.Container)
                      and c.on_click and "With occasional" in texts(c)))
    sheet = phone.page.top(ft.BottomSheet)
    [c for c in walk(sheet) if isinstance(c, ft.Checkbox)][0].value = False
    press(button(sheet, "Apply"))
    assert grand(phone) != before and float(grand(phone)) < float(before)


def test_a_figure_set_in_with_occasional_and_put_back(phone) -> None:
    with_heating(phone)
    press(button(phone.shown(), "Unlock"))
    before = grand(phone)
    tap = next(c for c in walk(phone.shown())
               if isinstance(c, ft.Container) and c.on_click and "With occasional" in texts(c))
    press(tap)
    figure = next(c for c in walk(phone.page.top(ft.BottomSheet))
                  if isinstance(c, ft.TextButton) and isinstance(c.content, ft.Container))
    press(figure)
    dialog = phone.page.top(ft.AlertDialog)
    dialog.content.value = "0"
    press(button(dialog, "Set"))
    set_to = grand(phone)
    assert float(set_to) < float(before)
    assert phone.page.top(ft.BottomSheet) is not None

    figure = next(c for c in walk(phone.page.top(ft.BottomSheet))
                  if isinstance(c, ft.TextButton) and isinstance(c.content, ft.Container))
    assert figure.content.bgcolor == app.PC["adjusted"]
    press(figure)
    dialog = phone.page.top(ft.AlertDialog)
    dialog.content.value = ""
    press(button(dialog, "Set"))
    assert grand(phone) == before


def test_text_sizes_and_theme_are_kept_for_next_time(phone) -> None:
    phone.examples(1)
    phone.tab(app.OPTIONS)
    sheet = phone.page.top(ft.BottomSheet)
    sliders = [c for c in walk(sheet) if isinstance(c, ft.Slider)]
    assert len(sliders) == len(Look.SIZES)
    totals = sliders[list(Look.SIZES).index("totals")]
    totals.on_change_end(SimpleNamespace(control=SimpleNamespace(value=34)))
    big = [c for c in walk(phone.shown()) if isinstance(c, ft.Text) and c.size == 34]
    assert len(big) == 2, "both totals should be drawn at the new size"

    theme = next(c for c in walk(sheet) if isinstance(c, ft.SegmentedButton))
    theme.on_change(SimpleNamespace(control=SimpleNamespace(selected=["dark"])))
    assert phone.page.theme_mode == ft.ThemeMode.DARK
    again = Look(phone.folder)
    assert again.theme == "dark" and again.sizes["totals"] == 34


def test_start_over_empties_the_app(phone) -> None:
    phone.examples(1)
    phone.tab(app.OPTIONS)
    press(next(c for c in walk(phone.page.top(ft.BottomSheet))
               if isinstance(c, ft.ListTile) and "Start over" in texts(c)))
    press(button(phone.page.top(ft.AlertDialog), "Remove everything"))
    assert lines(phone.shown())[0] == EMPTY_MONTH


def test_one_scale_breaks_only_a_bar_far_longer_than_the_rest() -> None:
    group = lambda name, value, limit=None: {"name": name, "value": value, "limit": limit}
    scale, broken = app.one_scale([group("Food", 2, 19), group("Rent", 5, 5),
                                   group("Gym", 1, 2), group("Gift", 3)])
    assert scale == 5 and broken == {"Food"}
    scale, broken = app.one_scale([group("Food", 13, 14), group("Rent", 8, 8)])
    assert scale == 14 and broken == set()
    assert app.one_scale([]) == (1.0, set())


def options_row(phone, words: str) -> ft.ListTile:
    phone.tab(app.OPTIONS)
    return next(c for c in walk(phone.page.top(ft.BottomSheet))
                if isinstance(c, ft.ListTile) and words in texts(c))


def options_block(phone) -> ft.Card:
    phone.tab(app.OPTIONS)
    return next(c for c in walk(phone.page.top(ft.BottomSheet)) if isinstance(c, ft.Card))


def test_the_options_tell_the_rules_and_the_folder_rather_than_offer_a_row(phone) -> None:
    phone.tab(app.OPTIONS)
    sheet = phone.page.top(ft.BottomSheet)
    assert "Rules and folder" in texts(sheet)
    assert not [c for c in walk(sheet) if isinstance(c, ft.ListTile)
                and ("Rules in use" in texts(c) or "Where it is kept" in texts(c))]

    block = options_block(phone)
    said = texts(block)
    assert "Rules in use" in said and "The app's own starting groups, in English" in said
    assert "Where it is kept" in said and str(phone.folder) in said
    assert not [c for c in walk(block) if getattr(c, "on_click", None)]
    folder = next(c for c in walk(block)
                  if isinstance(c, ft.Text) and c.value == str(phone.folder))
    assert folder.selectable

    choose_language(phone, "ru")
    russian = texts(options_block(phone))
    assert words.RU["options.about"] in texts(phone.page.top(ft.BottomSheet))
    assert words.RU["options.rules"] in russian and words.RU["options.folder"] in russian
    assert words.RU["options.rules.ru"] in russian


def test_saving_offers_the_phone_telegram_and_whatsapp(phone, monkeypatch) -> None:
    phone.examples(2)
    press(options_row(phone, "Save the configuration"))
    menu = phone.page.top(ft.AlertDialog)
    for choice in ("Save to phone", "Telegram", "WhatsApp"):
        assert button(menu, choice)

    press(button(menu, "Save to phone"))
    saved = FakePicker.saved[-1]
    assert saved["file_name"].startswith("budget-backup-")
    document = json.loads(saved["src_bytes"])
    assert document["kind"] == "budget-backup" and document["months"] == 1
    assert document["rules"]
    assert phone.page.dialogs[-1].content.value == "Saved."

    sent = []
    monkeypatch.setattr(app.send, "send", lambda *args: sent.append(args))
    press(options_row(phone, "Save the configuration"))
    press(button(phone.page.top(ft.AlertDialog), "Telegram"))
    assert sent and sent[-1][0] == "Telegram" and json.loads(sent[-1][2])["months"] == 1

    def missing(messenger, name, data):
        raise app.send.NotHere(f"{messenger} is not installed on this phone.")
    monkeypatch.setattr(app.send, "send", missing)
    press(options_row(phone, "Save the configuration"))
    press(button(phone.page.top(ft.AlertDialog), "WhatsApp"))
    assert phone.page.dialogs[-1].content.value == "WhatsApp is not installed on this phone."


def test_a_file_from_elsewhere_replaces_everything_with_its_rules(phone) -> None:
    import bundled

    pc = Budget(phone.elsewhere / "pc")
    pc.add_example("month-2")
    document = json.loads(pc.backup()[1])
    assert bundled.RULES_TOML.count("limit = 30\n") == 1
    document["rules"] = bundled.RULES_TOML.replace("limit = 30\n", "limit = 32\n").replace(
        "limit_total = 48\n", "limit_total = 50\n")
    phone.examples(1)

    FakePicker.picked = [chosen(json.dumps(document).encode("utf-8"))]
    press(options_row(phone, "Restore from a file"))
    question = phone.page.top(ft.AlertDialog)
    assert "1 month(s)" in texts(question) and "limits and rules" in texts(question)
    press(button(question, "Replace everything"))

    month = texts(phone.shown())
    assert "February 2026" in texts(phone.page.appbar), month[:300]
    assert "of 32" in month
    assert "From your configuration file" in texts(options_block(phone))


def test_a_file_without_its_rules_is_refused_before_anything_is_asked(phone) -> None:
    pc = Budget(phone.elsewhere / "pc")
    pc.add_example("month-2")
    document = json.loads(pc.backup()[1])
    del document["rules"]
    phone.examples(1)

    FakePicker.picked = [chosen(json.dumps(document).encode("utf-8"))]
    press(options_row(phone, "Restore from a file"))
    said = phone.page.top(ft.AlertDialog)
    assert "no rules in it" in texts(said) and "Save a new configuration file" in texts(said)
    for dialog in phone.page.dialogs:
        assert "Replace everything" not in texts(dialog)
    assert FakePicker.picked == []
    phone.tab(app.MONTH)
    assert "January 2026" in texts(phone.page.appbar)
    assert "The app's own starting groups" in texts(options_block(phone))


def test_a_file_that_is_not_a_configuration_is_refused_in_words(phone) -> None:
    phone.examples(1)
    FakePicker.picked = [chosen(b"a photo, not a backup")]
    press(options_row(phone, "Restore from a file"))
    assert "not a configuration file" in phone.page.dialogs[-1].content.value
    assert "January 2026" in texts(phone.page.appbar)


def compare_sheet(phone) -> ft.BottomSheet:
    press(button(phone.shown(), "Compare"))
    return phone.page.top(ft.BottomSheet)


def ticks(sheet) -> dict[str, ft.Checkbox]:
    return {c.label: c for c in walk(sheet) if isinstance(c, ft.Checkbox) and not c.disabled}


def tick(box: ft.Checkbox, value: bool) -> None:
    box.value = value
    box.on_change(SimpleNamespace(control=box))


def switch(sheet) -> ft.Switch:
    return next(c for c in walk(sheet) if isinstance(c, ft.Switch))


def test_compare_opens_on_the_two_newest_months_and_lists_the_groups(phone) -> None:
    phone.examples(1, 2, 3)
    sheet = compare_sheet(phone)
    assert phone.page.top().fullscreen and "Compare months" in texts(sheet)
    assert {name: box.value for name, box in ticks(sheet).items()} == {
        "Dec": False, "Jan": False, "Feb": True, "Mar": True}
    pc = Budget(phone.folder)
    ids = [m["identity"] for m in pc.months()][1:]
    table = pc.compare(ids[1:])["table"]
    shown = lines(sheet)
    for row in table["groups"]:
        assert row["name"] in shown, row["name"]
    for part in ("Feb", "Mar", "2026", "delta", "Total", "With occasional"):
        assert part in shown, part
    assert "Total + occasional" not in shown
    for identity in ids[1:]:
        totals = pc.month(identity)["totals"]
        assert money(totals["necessary"]) in shown and money(totals["grand"]) in shown
    assert not switch(sheet).value and "Average of" not in texts(sheet)

    tick(ticks(sheet)["Jan"], True)
    shown = lines(sheet)
    assert "Jan" in shown and "delta" not in shown
    assert money(pc.month(ids[0])["totals"]["necessary"]) in shown
    for name in ("Feb", "Mar"):
        tick(ticks(sheet)[name], False)
    assert "Tick at least two." in texts(sheet) and "Food" not in lines(sheet)


def test_the_average_switch_adds_what_a_month_costs(phone) -> None:
    phone.examples(1, 2, 3)
    sheet = compare_sheet(phone)
    average = switch(sheet)
    average.value = True
    average.on_change(SimpleNamespace(control=average))
    pc = Budget(phone.folder)
    ids = [m["identity"] for m in pc.months()][1:]
    said = pc.compare(ids[1:], average=True)["table"]["average"]
    shown = texts(sheet)
    assert "Average of 2 months of 2026" in shown
    for row in said["rows"]:
        assert row["cells"][0] in shown

    tick(ticks(sheet)["Feb"], False)
    assert "Average of 1 month of 2026" in texts(sheet)
    tick(ticks(sheet)["Mar"], False)
    assert "Tick at least one." in texts(sheet)

    tick(ticks(sheet)["Jan"], True)
    close = next(c for c in walk(sheet) if isinstance(c, ft.IconButton)
                 and c.icon == ft.Icons.CLOSE)
    press(close)
    assert not [d for d in phone.page.dialogs if isinstance(d, ft.BottomSheet)]
    sheet = compare_sheet(phone)
    assert switch(sheet).value and ticks(sheet)["Jan"].value and not ticks(sheet)["Mar"].value
    assert "Average of 1 month of 2026" in texts(sheet)


def test_a_comparison_not_read_is_shown_as_the_engines_text(phone, monkeypatch) -> None:
    phone.examples(1, 2)
    monkeypatch.setattr(Budget, "compare", lambda self, ids, average=False: {
        "text": "a table of another shape", "table": None})
    sheet = compare_sheet(phone)
    shown = next(c for c in walk(sheet) if isinstance(c, ft.Text)
                 and c.value == "a table of another shape")
    assert shown.font_family == "monospace"

    def refused(self, ids, average=False):
        raise Refused("compare needs 'periods': a list of two or more")
    monkeypatch.setattr(Budget, "compare", refused)
    tick(ticks(sheet)["Jan"], True)
    assert "compare needs 'periods'" in texts(sheet)


def test_compare_needs_two_months(phone) -> None:
    Budget(phone.folder).add("03.09\n+ 60 000\n\n06.09\n2000 bread\n")
    phone.tab(app.MONTH)
    sheet = compare_sheet(phone)
    assert "Two months are needed to compare." in texts(sheet) and not ticks(sheet)


def test_compare_in_russian(phone) -> None:
    phone.examples(1, 2)
    choose_language(phone, "ru")
    phone.page.dialogs.clear()
    press(button(phone.shown(), "Сравнить"))
    sheet = phone.page.top(ft.BottomSheet)
    shown = lines(sheet)
    for part in ("Сравнение месяцев", "Янв", "Фев", "разница", "Итого", "С разовыми"):
        assert part in shown, part
    assert switch(sheet).label == "Среднее" and "Итого + разовые" not in shown


def test_share_offers_the_phone_telegram_and_whatsapp(phone, monkeypatch) -> None:
    phone.examples(1)
    press(button(phone.shown(), "Share"))
    menu = phone.page.top(ft.AlertDialog)
    assert "January 2026 as a text file for print" in texts(menu)
    for choice in ("Save to phone", "Telegram", "WhatsApp"):
        assert button(menu, choice)

    press(button(menu, "Save to phone"))
    saved = FakePicker.saved[-1]
    assert saved["file_name"] == "budget-January-2026.txt"
    assert saved["allowed_extensions"] == ["txt"] and saved["dialog_title"] == "Share this month"
    text = saved["src_bytes"].decode("utf-8")
    assert text.startswith("January 2026\n") and "Food" in text
    assert phone.page.dialogs[-1].content.value == "Saved."

    sent = []
    monkeypatch.setattr(app.send, "send", lambda *args: sent.append(args))
    for messenger in ("Telegram", "WhatsApp"):
        press(button(phone.shown(), "Share"))
        press(button(phone.page.top(ft.AlertDialog), messenger))
        assert sent[-1] == (messenger, "budget-January-2026.txt", saved["src_bytes"])

    press(options_row(phone, "Save the configuration"))
    press(button(phone.page.top(ft.AlertDialog), "Save to phone"))
    assert FakePicker.saved[-1]["allowed_extensions"] == ["json"]


def test_share_in_russian(phone) -> None:
    phone.examples(1)
    choose_language(phone, "ru")
    phone.page.dialogs.clear()
    press(button(phone.shown(), "Поделиться"))
    menu = phone.page.top(ft.AlertDialog)
    assert menu.title.value == "Поделиться месяцем"
    assert "Январь 2026 — текстовый файл для печати" in texts(menu)
    press(button(menu, "Сохранить в телефон"))
    saved = FakePicker.saved[-1]
    assert saved["file_name"] == "budget-January-2026.txt"
    assert saved["src_bytes"].decode("utf-8").startswith("Январь 2026\n")


def choices(question) -> dict[str, ft.ListTile]:
    return {texts(c.title): c for c in walk(question) if isinstance(c, ft.ListTile)}


def answer(question) -> str:
    return next(c for c in walk(question) if isinstance(c, ft.RadioGroup)).value


def editor(phone) -> ft.BottomSheet:
    return phone.page.top(ft.BottomSheet)


def row(sheet, tag: str) -> ft.Container:
    return next(c for c in walk(sheet) if isinstance(c, ft.Container) and c.data == tag)


def tags(sheet) -> list[str]:
    return [c.data for c in walk(sheet) if isinstance(c, ft.Container) and c.data]


def fill(dialog, text: str, ok: str = "OK") -> None:
    next(c for c in walk(dialog) if isinstance(c, ft.TextField)).value = text
    press(button(dialog, ok))


def field(sheet, label: str) -> ft.Control:
    return next(c for c in walk(sheet) if isinstance(c, (ft.TextField, ft.Dropdown))
                and c.label == label)


def choose(sheet, label: str, text: str) -> None:
    dropdown = field(sheet, label)
    dropdown.value = next(o.key for o in dropdown.options if o.text == text)
    if dropdown.on_select:
        dropdown.on_select(SimpleNamespace(control=dropdown))


def opened(dialogs, dialog) -> bool:
    return any(d is dialog for d in dialogs)


def edits(phone, word: str = "Edit") -> list[ft.TextButton]:
    return [c for c in walk(phone.shown()) if isinstance(c, ft.TextButton) and c.content == word]


def groups_now(phone) -> list[str]:
    return [m["name"] for m in Budget(phone.folder).call(action="config")["majors"]]


def cards_under(month: ft.Column) -> dict[str, str]:
    controls = month.controls
    return {(texts(controls[at - 1]).split(" | ")[0] if at else ""): texts(c)
            for at, c in enumerate(controls) if isinstance(c, ft.Card)}


def test_an_empty_app_shows_the_month_as_it_will_look(phone) -> None:
    month = phone.tab(app.MONTH)
    said = lines(month)
    assert said[:2] == [EMPTY_MONTH, "Every group is in its place, empty. Rename, add or remove "
                                     "them with Edit, then paste your first month in Add."]
    cards = cards_under(month)
    assert cards[EMPTY_MONTH] == ("Total | 0.0 | With occasional | 0.0 | saved 0.0 | "
                                  "overspent 0.0")
    assert cards["With a limit"] == ("Food | — |   of 30 | nothing spent | Road | — |   of 10 | "
                                     "nothing spent | Medicine | — |   of 8 | nothing spent")
    assert cards["No limit"] == "Rent | —"
    assert cards["Income and withdrawals"] == "Refunds · income | —"
    assert cards["Minor groups"] == ("Rent | — | Food | — | Road | — | Medicine | — | Refunds | — "
                                     "| Withdrawal | — | Salary | —")
    assert left_of(phone) == "Left: purse value…, account value…" and left_note(phone) is None
    assert texts(month.controls[-1]).startswith("Left: ")
    spending = [m["label"] for m in Budget(phone.folder).setup()["majors"]
                if m["tier"] != "EXCLUDED" and not m["income"]]
    bars = (cards["With a limit"] + " | " + cards["No limit"]).split(" | ")
    assert spending and all(bars[bars.index(name) + 1] == "—" for name in spending), bars

    shown = texts(month)
    for part in ("Compare", "Share", "Unlock", "No months yet"):
        assert part not in shown, part
    bar = phone.page.appbar
    assert texts(bar) == "Budget" and bar.leading is None and not bar.actions
    assert phone.page.navigation_bar.destinations[app.QUESTIONS].icon.badge is None
    totals = next(c for c in month.controls if isinstance(c, ft.Card))
    assert not [c for c in walk(totals) if getattr(c, "on_click", None)]

    press(button(month, "Add notes"))
    assert phone.page.navigation_bar.selected_index == app.ADD


def test_the_empty_months_doors_open_the_editors_with_no_question(phone) -> None:
    doors = edits(phone)
    assert len(doors) == 3
    press(doors[0])
    offer = phone.page.top(ft.AlertDialog)
    assert not choices(offer) and "Which months" not in texts(offer)
    assert [c.content for c in walk(offer) if isinstance(c, ft.FilledTonalButton)] == [
        "Edit limits…", "Edit major groups…"]
    phone.page.dialogs.clear()
    press(edits(phone)[1])
    assert no_question(phone) and "Minor groups" in texts(editor(phone))
    phone.page.dialogs.clear()
    press(edits(phone)[2])
    assert no_question(phone) and "The Left line" in texts(editor(phone))
    assert tags(editor(phone)) == ["purse", "account"]
    phone.page.dialogs.clear()

    press(edits(phone)[0])
    press(button(phone.page.top(ft.AlertDialog), "Edit major groups…"))
    press(button(row(editor(phone), "Food"), "Rename"))
    fill(phone.page.top(ft.AlertDialog), "Meals")
    sheet = editor(phone)
    field(sheet, "name").value = "Kayak"
    field(sheet, "limit (optional)").value = "5"
    press(button(sheet, "Add"))
    phone.page.dialogs.clear()
    month = phone.shown()
    cards = cards_under(month)
    assert cards["With a limit"].startswith("Meals | — |   of 30 | nothing spent | Road | ")
    assert "Kayak | — |   of 5 | nothing spent" in cards["With a limit"]
    assert cards["Minor groups"].startswith("Rent | — | Meals | — | ")
    assert "Food" not in texts(month) and lines(month)[0] == EMPTY_MONTH


def test_the_empty_month_in_russian(phone) -> None:
    choose_language(phone, "ru")
    phone.page.dialogs.clear()
    month = phone.tab(app.MONTH)
    said = lines(month)
    assert said[:2] == [words.RU["empty.month"], words.RU["empty.month.text"]]
    assert said[0] == "Пока ничего не добавлено — так будет выглядеть ваш месяц."
    assert (f"«{words.RU['setup.edit']}»" in said[1] and f"«{words.RU['add']}»" in said[1])
    cards = cards_under(month)
    assert cards[said[0]] == ("Итого | 0.0 | С разовыми | 0.0 | сэкономлено 0.0 | "
                              "перерасходовано 0.0")
    assert cards["С лимитом"] == ("Еда | — |   из 30 | ничего не потрачено | Дорога | — |   из 10 "
                                  "| ничего не потрачено | Медицина | — |   из 8 | ничего не "
                                  "потрачено")
    assert cards["Без лимита"] == "Аренда | —"
    assert cards["Доходы и снятия"] == "Возвраты · доход | —"
    assert cards["Подгруппы"] == ("Аренда | — | Еда | — | Дорога | — | Медицина | — | Возвраты | — "
                                  "| Снятие | — | Зарплата | —")
    assert left_of(phone, "Остаток: ") == "Остаток: наличные сумма…, счёт сумма…"
    assert "Total" not in texts(month) and "Left" not in texts(month)

    doors = edits(phone, "Изменить")
    assert len(doors) == 3
    press(doors[0])
    offer = phone.page.top(ft.AlertDialog)
    assert "К каким месяцам" not in texts(offer) and not choices(offer)
    assert [c.content for c in walk(offer) if isinstance(c, ft.FilledTonalButton)] == [
        "Изменить лимиты…", "Изменить основные группы…"]
    phone.page.dialogs.clear()
    press(doors[2])
    assert no_question(phone) and "Строка остатка" in texts(editor(phone))


def test_start_over_asks_nothing_about_where_to_start(phone) -> None:
    phone.examples(1)
    phone.tab(app.OPTIONS)
    press(next(c for c in walk(phone.page.top(ft.BottomSheet))
               if isinstance(c, ft.ListTile) and "Start over" in texts(c)))
    ask = phone.page.top(ft.AlertDialog)
    assert not [c for c in walk(ask) if isinstance(c, (ft.RadioGroup, ft.ListTile))]
    assert "It cannot be undone." in texts(ask)
    press(button(ask, "Remove everything"))
    said = lines(phone.shown())
    assert said[0] == EMPTY_MONTH and "Food" in said
    assert groups_now(phone) == household_majors("en")


def test_the_setup_is_reached_from_the_options_before_any_month(phone) -> None:
    press(options_row(phone, "Groups and limits"))
    assert not [d for d in phone.page.dialogs if isinstance(d, ft.BottomSheet)]
    offer = phone.page.top(ft.AlertDialog)
    assert "Which months" not in texts(offer) and not choices(offer)
    assert "A limit is set for every month at once." not in texts(offer)
    for door in ("Edit limits…", "Edit major groups…", "Edit minor groups…"):
        assert button(offer, door)
    press(button(offer, "Edit limits…"))
    sheet = editor(phone)
    assert sheet.fullscreen and "Limits" in texts(sheet)
    assert "Changes apply to every month." in texts(sheet) and "Nothing staged" not in texts(sheet)

    press(button(row(sheet, "Food"), "Value"))
    fill(phone.page.top(ft.AlertDialog), "35")
    assert "Food · 35" in texts(editor(phone))
    phone.page.dialogs.clear()
    phone.examples(1)
    assert "  of 35" in texts(phone.shown())


def test_which_months_is_asked_only_once_a_month_is_stored(phone) -> None:
    press(options_row(phone, "The Left line"))
    assert no_question(phone) and "The Left line" in texts(editor(phone))
    phone.page.dialogs.clear()

    phone.examples(1)
    for name, door in (("Groups and limits", "Edit major groups…"),
                       ("The Left line", "Edit the Left line…"),
                       ("Words you teach", "Edit the words you teach…")):
        press(options_row(phone, name))
        question = phone.page.top(ft.AlertDialog)
        assert "Which months should the changes apply to?" in texts(question)
        assert list(choices(question)) == ["January 2026 and all further months",
                                           "Every month, the earlier ones too"]
        assert answer(question) == "onward"
        assert ("Earlier months are counted again under the new groups: their totals change, "
                "and the lines of a removed group become questions there.") in texts(question)
        assert button(question, door)
        phone.page.dialogs.clear()


def test_the_limits_editor_for_every_month(phone) -> None:
    press(options_row(phone, "Groups and limits"))
    press(button(phone.page.top(ft.AlertDialog), "Edit limits…"))

    press(button(row(editor(phone), "Food"), "Value"))
    value = phone.page.top(ft.AlertDialog)
    fill(value, "0")
    assert "A positive number of thousands." in texts(value)
    assert opened(phone.page.dialogs, value)
    fill(value, "35")
    assert not opened(phone.page.dialogs, value) and "Food · 35" in texts(editor(phone))

    press(button(row(editor(phone), "Medicine"), "Rename"))
    fill(phone.page.top(ft.AlertDialog), "Pharmacy")
    assert texts(row(editor(phone), "Medicine")).startswith("Pharmacy | Medicine · 8")

    press(button(row(editor(phone), "Road"), "Watch…"))
    press(button(phone.page.top(ft.AlertDialog), "Rent"))
    assert "Road" not in tags(editor(phone)) and "Rent · 10" in texts(row(editor(phone), "Rent"))

    press(button(row(editor(phone), "Medicine"), "Remove"))
    assert no_question(phone) and "Medicine" not in tags(editor(phone))

    sheet = editor(phone)
    choose(sheet, "Group", "Road")
    field(sheet, "thousands").value = "4"
    press(button(sheet, "Add"))
    assert "Road · 4" in texts(row(editor(phone), "Road"))

    sheet = editor(phone)
    choose(sheet, "Group", "— a new group —")
    field(sheet, "new group name").value = "Food"
    field(sheet, "thousands").value = "5"
    press(button(sheet, "Add"))
    assert "Food already has a limit - change it with Value on its row." in texts(sheet)
    field(sheet, "new group name").value = "Salary"
    press(button(sheet, "Add"))
    assert "'Salary' already names a group" in texts(sheet)
    field(sheet, "new group name").value = "Kayak"
    field(sheet, "shown as (optional)").value = "Driftwood"
    press(button(sheet, "Add"))
    assert texts(row(editor(phone), "Kayak")).startswith("Driftwood | Kayak · 5")

    phone.page.dialogs.clear()
    phone.examples(1)
    month = texts(phone.shown())
    assert "Driftwood" not in month and "Kayak" in month and "  of 5" in month


def limits_editor(phone) -> ft.BottomSheet:
    press(options_row(phone, "Groups and limits"))
    press(button(phone.page.top(ft.AlertDialog), "Edit limits…"))
    return editor(phone)


def limits_now(phone) -> dict:
    return {m["name"]: (m["limit"], m["limit_label"])
            for m in Budget(phone.folder).setup()["majors"]}


def test_add_a_limit_starts_on_no_group(phone) -> None:
    sheet = limits_editor(phone)
    group = field(sheet, "Group")
    assert group.value == app.CHOOSE_GROUP
    free = [m["label"] for m in Budget(phone.folder).setup()["majors"]
            if m["tier"] != "EXCLUDED" and m["limit"] is None]
    assert free == ["Rent", "Refunds"]
    assert [o.text for o in group.options] == ["Choose a group…", *free, "— a new group —"]
    assert not field(sheet, "new group name").visible

    before = limits_now(phone)
    field(sheet, "thousands").value = "6"
    field(sheet, "shown as (optional)").value = "Road"
    press(button(sheet, "Add"))
    assert "Pick a group, or name a new one." in texts(sheet) and limits_now(phone) == before

    choose(sheet, "Group", "— a new group —")
    assert field(sheet, "new group name").visible
    field(sheet, "new group name").value = "Kayak"
    choose(sheet, "Group", "Choose a group…")
    assert field(sheet, "new group name").visible
    press(button(sheet, "Add"))
    assert texts(row(editor(phone), "Kayak")).startswith("Road | Kayak · 6")
    assert field(editor(phone), "Group").value == app.CHOOSE_GROUP


def test_a_typed_name_means_the_group_it_names(phone) -> None:
    Budget(phone.folder).configure({"op": "rename_major", "major": "Rent", "name": "Home"})
    groups = len(Budget(phone.folder).setup()["majors"])
    sheet = limits_editor(phone)
    choose(sheet, "Group", "— a new group —")
    field(sheet, "new group name").value = "home"
    field(sheet, "thousands").value = "6"
    press(button(sheet, "Add"))
    assert texts(row(editor(phone), "Rent")).startswith("Home | Home · 6")
    assert len(Budget(phone.folder).setup()["majors"]) == groups

    sheet = editor(phone)
    choose(sheet, "Group", "— a new group —")
    field(sheet, "new group name").value = "FOOD"
    field(sheet, "thousands").value = "5"
    press(button(sheet, "Add"))
    assert "Food already has a limit - change it with Value on its row." in texts(sheet)

    choose(sheet, "Group", "Refunds")
    assert field(sheet, "new group name").visible
    press(button(sheet, "Add"))
    assert "You chose Refunds and typed FOOD - keep one." in texts(sheet)
    assert limits_now(phone)["Refunds"] == (None, None)
    field(sheet, "new group name").value = "refunds"
    press(button(sheet, "Add"))
    assert texts(row(editor(phone), "Refunds")).startswith("Refunds | Refunds · 5")


def two_totals(phone) -> list[str]:
    card = texts(next(c for c in walk(phone.shown()) if isinstance(c, ft.Card))).split(" | ")
    return [card[card.index(name) + 1] for name in ("Total", "With occasional")]


def removed(name: str) -> str:
    return f"the group {name} was removed - where does this go?"


def test_changes_from_a_month_on_wait_for_apply_and_land_there(phone) -> None:
    phone.examples(1, 2, 3)
    press(edits(phone)[0])
    question = phone.page.top(ft.AlertDialog)
    assert list(choices(question)) == ["March 2026 and all further months",
                                       "Every month, the earlier ones too"]
    assert answer(question) == "onward"
    press(button(question, "Edit major groups…"))
    sheet = editor(phone)
    assert "Changes apply to March 2026 and every later month, once applied." in texts(sheet)
    assert "Nothing staged yet - your changes will be listed here." in texts(sheet)

    press(button(row(sheet, "Road"), "Rename"))
    fill(phone.page.top(ft.AlertDialog), "Travel")
    press(button(row(editor(phone), "Medicine"), "Remove"))
    shown = texts(editor(phone))
    assert "1. rename Road to Travel" in shown and "2. remove the group Medicine" in shown
    assert "2 change(s) staged." in shown and "Medicine" in tags(editor(phone))

    press(button(editor(phone), "Apply"))
    confirm = phone.page.top(ft.AlertDialog)
    assert "2 change(s) to March 2026, and every later month." in texts(confirm)
    press(button(confirm, "No, keep staging"))
    assert "2 change(s) staged." in texts(editor(phone))
    press(button(editor(phone), "Apply"))
    press(button(phone.page.top(ft.AlertDialog), "Yes, apply"))
    sheet = editor(phone)
    assert "Nothing staged yet" in texts(sheet) and "Medicine" not in tags(sheet)
    assert texts(row(sheet, "Road")).startswith("Travel")
    march = lines(phone.shown())
    assert "Travel" in march and "Medicine" not in march
    phone.page.dialogs.clear()
    press(phone.page.appbar.leading)
    february = lines(phone.shown())
    assert "February 2026" in texts(phone.page.appbar)
    assert "Road" in february and "Medicine" in february and "Travel" not in february


def test_a_limit_never_asks_and_is_never_staged(phone) -> None:
    phone.examples(1, 2, 3)
    press(edits(phone)[0])
    question = phone.page.top(ft.AlertDialog)
    assert "A limit is set for every month at once." in texts(question)
    press(button(question, "Edit major groups…"))
    press(button(row(editor(phone), "Road"), "Remove"))
    assert "1 change(s) staged." in texts(editor(phone))

    phone.page.dialogs.clear()
    press(edits(phone)[0])
    press(button(phone.page.top(ft.AlertDialog), "Edit limits…"))
    sheet = editor(phone)
    assert "Changes apply to every month." in texts(sheet)
    assert "Nothing staged" not in texts(sheet) and "Apply" not in texts(sheet)
    press(button(row(sheet, "Food"), "Value"))
    fill(phone.page.top(ft.AlertDialog), "35")
    press(button(row(editor(phone), "Medicine"), "Remove"))
    assert no_question(phone)
    assert "Food · 35" in texts(editor(phone)) and "Medicine" not in tags(editor(phone))
    pc = Budget(phone.folder)
    for m in pc.months():
        limits = {g["name"]: g["limit"] for g in pc.month(m["identity"])["majors"]}
        assert (limits["Food"], limits["Medicine"]) == (35, None), m["month"]

    phone.page.dialogs.clear()
    press(edits(phone)[0])
    question = phone.page.top(ft.AlertDialog)
    assert answer(question) == "onward" and "discarded" not in texts(question)
    press(button(question, "Edit major groups…"))
    assert "1. remove the group Road" in texts(editor(phone))


def test_every_month_the_earlier_ones_too_is_changed_at_once(phone) -> None:
    phone.examples(1, 2, 3)
    before = two_totals(phone)
    press(edits(phone)[1])
    question = phone.page.top(ft.AlertDialog)
    press(choices(question)["Every month, the earlier ones too"])
    assert answer(question) == "always"
    press(button(question, "Edit minor groups…"))
    sheet = editor(phone)
    assert "Changes apply to every month." in texts(sheet)
    press(button(row(sheet, "Food"), "Remove"))
    assert no_question(phone) and "Food" not in tags(editor(phone))

    phone.page.dialogs.clear()
    assert float(two_totals(phone)[0]) < float(before[0])
    assert removed("Food") in texts(phone.tab(app.QUESTIONS))
    press(phone.page.appbar.leading)
    press(phone.page.appbar.leading)
    assert "January 2026" in texts(phone.page.appbar)
    assert removed("Food") in texts(phone.shown())


def test_the_major_groups_editor_for_every_month(phone) -> None:
    press(options_row(phone, "Groups and limits"))
    press(button(phone.page.top(ft.AlertDialog), "Edit major groups…"))
    sheet = editor(phone)
    assert "Major groups" in texts(sheet) and "Set aside" not in tags(sheet)
    assert tags(sheet) == ["Rent", "Food", "Road", "Medicine", "Refunds"]
    assert texts(row(sheet, "Food")).startswith("Food | necessary · limit 30 · 1 minor |")
    assert texts(row(sheet, "Rent")).startswith("Rent | necessary | Rename")
    assert all(button(row(sheet, tag), "Remove") for tag in tags(sheet))
    assert ("Remove takes it away with its minor groups, and the lines they held go to "
            "Questions, to be placed again. One group spending can go to always stays."
            ) in texts(sheet)

    press(button(row(sheet, "Road"), "Rename"))
    rename = phone.page.top(ft.AlertDialog)
    fill(rename, "Food")
    assert "'Food' already names a group" in texts(rename) and opened(phone.page.dialogs, rename)
    fill(rename, "Travel")
    assert not opened(phone.page.dialogs, rename)
    assert texts(row(editor(phone), "Road")).startswith("Travel | necessary · limit 10 · 1 minor |")

    sheet = editor(phone)
    field(sheet, "name").value = "Kayak"
    field(sheet, "Tier").value = "OCCASIONAL"
    field(sheet, "limit (optional)").value = "six"
    press(button(sheet, "Add"))
    assert "A limit is a positive number of thousands, or blank." in texts(sheet)
    field(sheet, "limit (optional)").value = "6"
    press(button(sheet, "Add"))
    assert texts(row(editor(phone), "Kayak")).startswith("Kayak | occasional · limit 6 |")
    press(button(row(editor(phone), "Kayak"), "Remove"))
    assert "Kayak" not in tags(editor(phone))

    phone.page.dialogs.clear()
    phone.examples(1)
    month = lines(phone.shown())
    at = month.index("Minor groups")
    assert "Travel" in month[:at] and "Travel" in month[at:] and "Road" not in month


def test_remove_takes_a_major_with_its_minor_groups_from_a_month_on(phone) -> None:
    phone.examples(1, 2, 3)
    before = two_totals(phone)
    press(edits(phone)[0])
    press(button(phone.page.top(ft.AlertDialog), "Edit major groups…"))
    press(button(row(editor(phone), "Road"), "Remove"))
    assert no_question(phone)
    assert "1. remove the group Road" in texts(editor(phone)) and "Road" in tags(editor(phone))
    press(button(editor(phone), "Apply"))
    press(button(phone.page.top(ft.AlertDialog), "Yes, apply"))
    assert "Road" not in tags(editor(phone))

    phone.page.dialogs.clear()
    assert "Road" not in lines(phone.shown())
    assert float(two_totals(phone)[0]) == pytest.approx(float(before[0]) - 2.3, abs=0.15)
    assert removed("Road") in texts(phone.tab(app.QUESTIONS))
    press(phone.page.appbar.leading)
    assert "February 2026" in texts(phone.page.appbar)
    assert removed("Road") not in texts(phone.shown())
    assert "Road" in lines(phone.tab(app.MONTH))


def test_the_last_group_spending_can_go_to_offers_no_remove(phone) -> None:
    press(options_row(phone, "Groups and limits"))
    press(button(phone.page.top(ft.AlertDialog), "Edit major groups…"))
    for name in ("Rent", "Food", "Road"):
        press(button(row(editor(phone), name), "Remove"))
    sheet = editor(phone)
    assert tags(sheet) == ["Medicine", "Refunds"]
    assert "Remove" not in texts(row(sheet, "Medicine")) and button(row(sheet, "Refunds"), "Remove")


def test_the_last_group_spending_can_go_to(tmp_path) -> None:
    majors = Budget(tmp_path).setup()["majors"]
    by = {m["name"]: m for m in majors}
    assert app.last_for_spending(majors) is None
    assert app.last_for_spending([by["Food"], by["Refunds"], by["Set aside"]]) == "Food"


def test_a_renamed_major_takes_its_twin_and_its_words(phone) -> None:
    def open_editor(options: str, door: str | None = None) -> ft.BottomSheet:
        phone.page.dialogs.clear()
        press(options_row(phone, options))
        if door:
            press(button(phone.page.top(ft.AlertDialog), door))
        return editor(phone)

    sheet = open_editor("Words you teach")
    field(sheet, "a word, or two").value = "kiosk"
    choose(sheet, "Group", "Food")
    press(button(sheet, "Teach"))
    press(button(row(open_editor("Groups and limits", "Edit major groups…"), "Food"), "Rename"))
    fill(phone.page.top(ft.AlertDialog), "Meals")
    assert texts(row(editor(phone), "Food")).startswith("Meals | ")
    minors = open_editor("Groups and limits", "Edit minor groups…")
    assert texts(row(minors, "Food")).startswith("Meals | under Meals |")
    taught = open_editor("Words you teach")
    assert texts(row(taught, "kiosk")).startswith("kiosk | → Meals |")


def minors_editor(phone, options: str = "Groups and limits",
                  door: str = "Edit minor groups…") -> ft.BottomSheet:
    phone.page.dialogs.clear()
    press(options_row(phone, options))
    press(button(phone.page.top(ft.AlertDialog), door))
    return editor(phone)


def test_the_minor_groups_editor_for_every_month(phone) -> None:
    sheet = minors_editor(phone)
    assert "Minor groups" in texts(sheet)
    assert texts(row(sheet, "Medicine")).startswith("Medicine | under Medicine |")
    press(button(row(sheet, "Medicine"), "Rename"))
    fill(phone.page.top(ft.AlertDialog), "Pharmacy")
    press(button(row(editor(phone), "Medicine"), "Route to…"))
    press(button(phone.page.top(ft.AlertDialog), "Food"))
    assert texts(row(editor(phone), "Medicine")).startswith("Pharmacy | under Food |")

    sheet = editor(phone)
    field(sheet, "name").value = "Museum"
    press(button(sheet, "Add"))
    assert "Choose the major it belongs under." in texts(sheet)
    field(sheet, "under which major…").value = "Road"
    press(button(sheet, "Add"))
    assert texts(row(editor(phone), "Museum")).startswith("Museum | under Road |")

    phone.page.dialogs.clear()
    phone.examples(1)
    month = lines(phone.shown())
    at = month.index("Minor groups")
    assert "Pharmacy" in month[at:] and "Museum" in month[at:] and "Medicine" not in month[at:]


def test_any_minor_group_is_removed_at_once(phone) -> None:
    sheet = minors_editor(phone)
    assert ("Remove takes one away: the lines it held go to Questions, to be placed "
            "again.") in texts(sheet)
    press(button(row(sheet, "Food"), "Remove"))
    assert no_question(phone) and "Food" not in tags(editor(phone))

    sheet = editor(phone)
    field(sheet, "name").value = "Museum"
    field(sheet, "under which major…").value = "Road"
    press(button(sheet, "Add"))
    press(button(row(editor(phone), "Museum"), "Remove"))
    press(button(row(editor(phone), "Refunds"), "Remove"))
    assert no_question(phone) and tags(editor(phone)) == ["Road", "Medicine", *SET_ASIDE]

    sheet = minors_editor(phone, door="Edit major groups…")
    assert texts(row(sheet, "Food")).startswith("Food | necessary · limit 30 | Rename")
    press(button(row(sheet, "Food"), "Remove"))
    assert "Food" not in tags(editor(phone))


SET_ASIDE = ["Salary", "Savings", "Withdrawal", "Rent payment", "Elsewhere"]


def test_the_groups_set_aside_can_be_renamed_and_removed(phone) -> None:
    sheet = minors_editor(phone)
    assert "Counted in no Total - they can be renamed or removed, not routed." in texts(sheet)
    assert tags(sheet)[-5:] == SET_ASIDE
    assert texts(row(sheet, "Withdrawal")).startswith("Withdrawal | under Set aside | Rename")
    assert "Route to…" not in texts(row(sheet, "Withdrawal"))
    press(button(row(sheet, "Withdrawal"), "Remove"))
    assert no_question(phone) and "Withdrawal" not in tags(editor(phone))

    press(button(row(editor(phone), "Salary"), "Remove"))
    warning = phone.page.top(ft.AlertDialog)
    assert ("Salary holds your salary: without it, the salary line goes to Questions, and "
            "it is counted wherever you answer it. Remove it?") in texts(warning)
    press(button(warning, "Cancel"))
    assert no_question(phone) and "Salary" in tags(editor(phone))
    press(button(row(editor(phone), "Salary"), "Remove"))
    press(button(phone.page.top(ft.AlertDialog), "Yes, remove it"))
    assert "Salary" not in tags(editor(phone))
    assert Budget(phone.folder).setup()["overlay"]["minors"] == {
        "Withdrawal": {"removed": True}, "Salary": {"removed": True}}


def test_a_line_for_a_month_not_stored_makes_that_month(phone) -> None:
    pc = Budget(phone.folder)
    pc.configure({"op": "add_major", "name": "Ladder", "tier": "OCCASIONAL"})
    pc.add("03.09\n+ 60 000\n\n06.09\n+ 1800 ladder, do not count refers to August\n")
    month = texts(phone.tab(app.MONTH))
    assert "September 2026" in texts(phone.page.appbar)
    assert "Moved to another month" not in month and "ladder" not in month
    press(phone.page.appbar.leading)
    assert "August 2026" in texts(phone.page.appbar)
    assert ("Only lines written in other months that belong to this one. Add its own notes - "
            "as a new month, or with Add to - and they join them.") in texts(phone.shown())

    card = next(c for c in walk(phone.tab(app.QUESTIONS)) if isinstance(c, ft.Card))
    assert "+ 1800 ladder, do not count refers to August" in texts(card)
    press(button(card, "Ladder"))
    august = pc.months()[0]["identity"]
    assert next(g for g in pc.month(august)["majors"] if g["name"] == "Ladder")["value"] == -1.8

    add = phone.tab(app.ADD)
    next(c for c in walk(add) if isinstance(c, ft.TextField)).value = "15.08\n300 bread\n"
    into = next(c for c in walk(add) if isinstance(c, ft.Dropdown))
    into.value = next(o.key for o in into.options if o.text == "August 2026")
    press(next(c for c in walk(add) if isinstance(c, ft.FilledButton) and c.content == "Add"))
    assert "August 2026" in texts(phone.page.appbar)
    assert "Only lines written in other months" not in texts(phone.shown())
    real = pc.months()[0]["identity"]
    assert not real.startswith("moved:")
    assert next(g for g in pc.month(real)["majors"] if g["name"] == "Ladder")["value"] == -1.8


def test_a_removed_minor_groups_lines_are_asked_about_again(phone) -> None:
    phone.examples(1, 2, 3)
    pc = Budget(phone.folder)
    mar = pc.months()[-1]["identity"]
    medicine = next(r for r in pc.month(mar)["minors"] if r["name"] == "Medicine")
    held = sum(len(lines) for lines in medicine["marks"] if lines)
    before = len(pc.questions(mar))

    sheet = minors_editor(phone)
    assert "Changes apply to March 2026 and every later month, once applied." in texts(sheet)
    press(button(row(sheet, "Medicine"), "Remove"))
    assert no_question(phone) and "1. remove Medicine" in texts(editor(phone))
    press(button(editor(phone), "Apply"))
    press(button(phone.page.top(ft.AlertDialog), "Yes, apply"))
    assert "Medicine" not in tags(editor(phone))

    phone.page.dialogs.clear()
    asked = texts(phone.tab(app.QUESTIONS))
    assert asked.count(removed("Medicine")) == held > 0
    badge = phone.page.navigation_bar.destinations[app.QUESTIONS].icon.badge
    assert int(badge.label) == before + held
    press(phone.page.appbar.leading)
    assert "February 2026" in texts(phone.page.appbar)
    assert removed("Medicine") not in texts(phone.shown())


def test_a_minor_added_for_every_month_ends_for_some(phone) -> None:
    sheet = minors_editor(phone)
    field(sheet, "name").value = "Museum"
    field(sheet, "under which major…").value = "Road"
    press(button(sheet, "Add"))

    phone.page.dialogs.clear()
    phone.examples(1, 2, 3)
    press(button(row(minors_editor(phone), "Museum"), "Remove"))
    assert "1. remove Museum" in texts(editor(phone))
    press(button(editor(phone), "Apply"))
    press(button(phone.page.top(ft.AlertDialog), "Yes, apply"))
    assert "Museum" not in tags(editor(phone))
    pc = Budget(phone.folder)
    feb, mar = [m["identity"] for m in pc.months()][-2:]
    minors_of = lambda identity: [n["name"] for m in pc.setup(identity)["majors"]
                                  for n in m["minors"]]
    assert "Museum" in minors_of(feb) and "Museum" not in minors_of(mar)


def test_the_words_editor_teaches_and_forgets(phone) -> None:
    press(options_row(phone, "Words you teach"))
    assert no_question(phone)
    sheet = editor(phone)
    assert "Words you teach" in texts(sheet) and "Nothing taught yet." in texts(sheet)
    assert "Changes apply to every month." in texts(sheet)
    field(sheet, "a word, or two").value = "flapjack"
    press(button(sheet, "Teach"))
    press(button(row(editor(phone), "flapjack"), "Forget"))
    assert "Nothing taught yet." in texts(editor(phone))

    sheet = editor(phone)
    field(sheet, "a word, or two").value = " st "
    press(button(sheet, "Teach"))
    assert "A word of three letters or more." in texts(sheet)
    field(sheet, "a word, or two").value = "cinema"
    field(sheet, "Group").value = "Food"
    press(button(sheet, "Teach"))
    assert texts(row(editor(phone), "cinema")).startswith("cinema | → Food |")

    phone.page.dialogs.clear()
    phone.examples(1)
    asked = texts(phone.tab(app.QUESTIONS))
    assert "740 cinema" not in asked and "650 book" in asked


def test_the_left_line_editor_for_every_month(phone) -> None:
    press(options_row(phone, "The Left line"))
    sheet = editor(phone)
    assert "Changes apply to every month." in texts(sheet) and "read alike" not in texts(sheet)
    assert tags(sheet) == ["purse", "account"]
    assert texts(row(sheet, "purse")).startswith("purse | cash in hand · name before |")
    assert button(row(sheet, "purse"), "↑").disabled and button(row(sheet, "account"), "↓").disabled

    press(button(row(sheet, "purse"), "Name"))
    name = phone.page.top(ft.AlertDialog)
    assert next(c for c in walk(name) if isinstance(c, ft.TextField)).value == "purse"
    fill(name, "cash")
    press(button(row(editor(phone), "purse"), "→ after"))
    assert texts(row(editor(phone), "purse")).startswith("cash | cash in hand · name after |")
    press(button(row(editor(phone), "account"), "↑"))
    assert tags(editor(phone)) == ["account", "purse"]

    press(button(row(editor(phone), "purse"), "Kind…"))
    press(button(phone.page.top(ft.AlertDialog), "card balance"))
    assert "only one figure can be the card balance" in phone.page.dialogs[-1].content.value
    phone.page.pop_dialog()
    press(button(row(editor(phone), "purse"), "Kind…"))
    press(button(phone.page.top(ft.AlertDialog), "carried over"))
    assert "carried over · name after" in texts(row(editor(phone), "purse"))

    sheet = editor(phone)
    press(button(sheet, "Add"))
    assert "Give it a name." in texts(sheet)
    field(sheet, "name").value = "jar"
    press(button(sheet, "Add"))
    assert tags(editor(phone)) == ["account", "purse", "jar"]
    press(button(row(editor(phone), "jar"), "Remove"))
    press(button(editor(phone), "Back to the original line"))
    assert tags(editor(phone)) == ["purse", "account"]
    assert texts(row(editor(phone), "purse")).startswith("purse | cash in hand")

    press(button(row(editor(phone), "purse"), "Name"))
    fill(phone.page.top(ft.AlertDialog), "cash")
    phone.page.dialogs.clear()
    phone.examples(1)
    assert left_of(phone).startswith("Left: cash ")


def left_box(root, word: str = "Left: ") -> ft.Row:
    return next(c for c in walk(root) if isinstance(c, ft.Row) and c.wrap and c.controls
                and isinstance(c.controls[0], ft.Text) and c.controls[0].value == word)


def left_door(phone, word: str = "Left: ") -> ft.Control:
    month = phone.shown()
    box = left_box(month, word)
    line = next(c for c in walk(month) if isinstance(c, ft.Row)
                and any(x is box for x in c.controls))
    return next(c for c in line.controls if isinstance(c, ft.TextButton))


def left_of(phone, word: str = "Left: ") -> str:
    said = []
    for c in walk(left_box(phone.shown(), word)):
        if c.data == "left.note":
            break
        if isinstance(c, ft.Text) and c.value:
            said.append(str(c.value))
        elif isinstance(c, ft.OutlinedButton) and isinstance(c.content, str):
            said.append(c.content)
    return "".join(said)


def left_note(phone) -> str | None:
    note = next((c for c in walk(phone.shown()) if c.data == "left.note"), None)
    return note.content.value if note else None


def left_tap(phone, slot: str) -> ft.Control:
    return next(c for c in walk(phone.shown()) if c.data == f"left:{slot}")


def left_mark(phone, slot: str) -> str | None:
    tapped = left_tap(phone, slot)
    boxed = [c for c in walk(tapped) if isinstance(c, ft.Container) and c is not tapped]
    return boxed[0].bgcolor if boxed else None


def test_the_left_line_for_every_month_once_months_are_stored(phone) -> None:
    phone.examples(1)
    press(left_door(phone))
    question = phone.page.top(ft.AlertDialog)
    assert answer(question) == "onward"
    press(choices(question)["Every month, the earlier ones too"])
    press(button(question, "Edit the Left line…"))
    sheet = editor(phone)
    assert "Changes apply to every month." in texts(sheet)
    press(button(row(sheet, "purse"), "Name"))
    fill(phone.page.top(ft.AlertDialog), "cash")
    assert texts(row(editor(phone), "purse")).startswith("cash | ")
    assert left_of(phone).startswith("Left: cash ")


def test_the_left_line_changed_from_march_on_is_read_by_march_alone(phone) -> None:
    phone.examples(1, 2, 3)
    press(phone.page.appbar.leading)
    feb_line = left_of(phone)
    press(phone.page.appbar.actions[0])
    assert "March 2026" in texts(phone.page.appbar) and left_of(phone).startswith("Left: purse ")

    press(left_door(phone))
    question = phone.page.top(ft.AlertDialog)
    assert answer(question) == "onward"
    press(button(question, "Edit the Left line…"))
    sheet = editor(phone)
    assert "Changes apply to March 2026 and every later month, once applied." in texts(sheet)
    press(button(row(sheet, "purse"), "Name"))
    fill(phone.page.top(ft.AlertDialog), "cash")
    assert '1. call purse "cash"' in texts(editor(phone))
    assert left_of(phone).startswith("Left: purse ")

    press(button(editor(phone), "Apply"))
    confirm = phone.page.top(ft.AlertDialog)
    assert "1 change(s) to March 2026, and every later month." in texts(confirm)
    press(button(confirm, "Yes, apply"))
    assert "Nothing staged yet" in texts(editor(phone))
    assert texts(row(editor(phone), "purse")).startswith("cash | ")
    assert left_of(phone).startswith("Left: cash ")
    phone.page.dialogs.clear()
    press(phone.page.appbar.leading)
    assert "February 2026" in texts(phone.page.appbar) and left_of(phone) == feb_line


def test_every_left_line_change_waits_in_words(phone) -> None:
    phone.examples(1, 2, 3)
    press(left_door(phone))
    press(button(phone.page.top(ft.AlertDialog), "Edit the Left line…"))
    press(button(row(editor(phone), "purse"), "Name"))
    fill(phone.page.top(ft.AlertDialog), "cash")
    press(button(row(editor(phone), "purse"), "Kind…"))
    press(button(phone.page.top(ft.AlertDialog), "carried over"))
    press(button(row(editor(phone), "account"), "↑"))
    sheet = editor(phone)
    field(sheet, "name").value = "jar"
    press(button(sheet, "Add"))
    press(button(row(editor(phone), "account"), "Remove"))
    press(button(editor(phone), "Back to the original line"))
    shown = lines(editor(phone))
    for said in ('1. call purse "cash"', "2. purse counted as carried over",
                 "3. the Left line in a new order", "4. add jar to the Left line",
                 "5. remove account from the Left line", "6. the original Left line back"):
        assert said in shown, (said, shown)
    press(button(editor(phone), "Discard"))
    assert "Nothing staged yet" in texts(editor(phone))


def test_moving_a_left_name_reads_as_a_move_not_a_rename(phone) -> None:
    phone.examples(1, 2, 3)
    press(left_door(phone))
    press(button(phone.page.top(ft.AlertDialog), "Edit the Left line…"))
    press(button(row(editor(phone), "account"), "→ after"))
    shown = lines(editor(phone))
    assert "1. account: its name after the figure" in shown, shown
    assert 'call account "account"' not in shown
    press(button(editor(phone), "Discard"))
    words.set_lang("ru")
    try:
        assert words.t("op.left_after", "{slot}: its name after the figure",
                       slot="account") == "«account»: подпись после суммы"
    finally:
        words.set_lang("en")


def bare(text: str) -> str:
    return "\n".join(line for line in text.splitlines()
                     if not line.startswith(("Left:", "Остаток:")))


def paste(phone, text: str, add: str = "Add") -> None:
    screen = phone.tab(app.ADD)
    next(c for c in walk(screen) if isinstance(c, ft.TextField)).value = text
    press(next(c for c in walk(screen) if isinstance(c, ft.FilledButton) and c.content == add))


def typing(dialog) -> ft.TextField:
    return next(c for c in walk(dialog) if isinstance(c, ft.TextField))


def type_figure(phone, slot: str, typed: str, ok: str = "OK") -> None:
    press(left_tap(phone, slot))
    ask = phone.page.top(ft.AlertDialog)
    typing(ask).value = typed
    press(button(ask, ok))


def set_said(phone) -> list[str]:
    return [line for line in lines(phone.shown()) if "you set this" in line]


def test_each_left_figure_is_tapped_and_typed_for_its_month(phone) -> None:
    phone.examples(1)
    assert left_of(phone) == "Left: purse 1, account 32500" and left_note(phone) is None
    assert "value…" not in texts(phone.shown())
    press(left_tap(phone, "purse"))
    ask = phone.page.top(ft.AlertDialog)
    assert ask.title.value == "Left: purse"
    assert (typing(ask).label, typing(ask).value) == ("a figure", "1")
    assert "Back to the notes' figure" not in texts(ask)

    for wrong in ("abc", ""):
        typing(ask).value = wrong
        press(button(ask, "OK"))
        assert typing(ask).error == "Type a number." and opened(phone.page.dialogs, ask)
    typing(ask).value = "3,5"
    press(button(ask, "OK"))
    assert no_question(phone)
    assert phone.page.dialogs[-1].content.value == ("This month is closed - press Unlock at "
                                                    "the top first.")
    assert left_of(phone) == "Left: purse 1, account 32500"

    press(button(phone.shown(), "Unlock"))
    type_figure(phone, "purse", "3,5")
    assert no_question(phone) and left_of(phone) == "Left: purse 3.5, account 32500"
    assert left_mark(phone, "purse") == app.PC["adjusted"] and left_mark(phone, "account") is None
    said = "you set this; the notes make it 1 - tap to change it"
    assert set_said(phone) == ["purse: " + said] and left_tap(phone, "purse").tooltip == said
    pc = Budget(phone.folder)
    cell = pc.month(pc.months()[-1]["identity"])["left"]["cells"][0]
    assert (cell["value"], cell["set"], cell["noted"]) == (3.5, True, "1")

    press(left_tap(phone, "purse"))
    ask = phone.page.top(ft.AlertDialog)
    assert typing(ask).value == "3.5"
    press(button(ask, "Back to the notes' figure"))
    assert no_question(phone) and left_of(phone) == "Left: purse 1, account 32500"
    assert left_mark(phone, "purse") is None and not set_said(phone)


def test_a_month_with_no_left_line_offers_a_value_button_per_figure(phone) -> None:
    paste(phone, bare(bundled.EXAMPLES["month-1"]))
    assert "January 2026" in texts(phone.page.appbar)
    assert left_of(phone) == "Left: purse value…, account value…"
    assert left_note(phone) == "(these notes carry no closing line)"
    press(button(phone.shown(), "Unlock"))
    press(left_tap(phone, "account"))
    ask = phone.page.top(ft.AlertDialog)
    assert typing(ask).value == "" and ask.title.value == "Left: account"
    typing(ask).value = "38 500"
    press(button(ask, "OK"))
    assert left_of(phone) == "Left: purse value…, account 38500" and left_note(phone) is None
    assert left_mark(phone, "account") == app.PC["adjusted"] and not set_said(phone)


def test_starting_figures_are_typed_on_the_empty_month(phone, monkeypatch) -> None:
    sent = []
    real = Budget.left_value

    def spy(self, slot, value, identity=None):
        sent.append((slot, value, identity))
        return real(self, slot, value, identity)

    monkeypatch.setattr(Budget, "left_value", spy)
    type_figure(phone, "purse", "5,5")
    type_figure(phone, "account", "38 500")
    assert sent == [("purse", 5.5, None), ("account", 38500.0, None)]
    month = phone.shown()
    assert lines(month)[0] == EMPTY_MONTH and left_of(phone) == "Left: purse 5.5, account 38500"
    assert left_mark(phone, "purse") == left_mark(phone, "account") == app.PC["adjusted"]
    assert not set_said(phone)
    press(left_tap(phone, "purse"))
    press(button(phone.page.top(ft.AlertDialog), "Back to the notes' figure"))
    assert sent[-1] == ("purse", None, None)
    assert left_of(phone) == "Left: purse value…, account 38500"
    type_figure(phone, "purse", "5,55")
    press(left_tap(phone, "purse"))
    ask = phone.page.top(ft.AlertDialog)
    assert typing(ask).value == "5.55"
    press(button(ask, "Cancel"))

    paste(phone, bare(bundled.EXAMPLES["month-1"]))
    pc = Budget(phone.folder)
    january = pc.month(pc.months()[-1]["identity"])["left"]
    assert pc.month(pc.months()[0]["identity"])["left"]["counted_from"] == "start"
    assert january["counted_from"] == "before"
    assert left_of(phone) == unbroken(january["text"])
    assert left_note(phone) == "(counted on from the month before)"
    paste(phone, bare(bundled.EXAMPLES["month-2"]))
    assert "February 2026" in texts(phone.page.appbar)
    assert left_note(phone) == "(counted on from the month before)"


def test_a_month_still_being_written_shows_its_recounted_line(phone) -> None:
    notes = bundled.EXAMPLES["month-3"].splitlines()
    last = [at for at, line in enumerate(notes) if line.startswith("Left:")][-3:]
    paste(phone, "\n".join(line for at, line in enumerate(notes) if at not in last))
    pc = Budget(phone.folder)
    march = pc.month(pc.months()[-1]["identity"])["left"]
    assert march["days_after"] == 3 and left_of(phone) == unbroken(march["computed"]["text"])
    assert left_of(phone) != unbroken(march["text"])
    assert left_note(phone) == f"(recounted: {march['date']}'s Left + 3 newer days)"

    press(button(phone.shown(), "Unlock"))
    type_figure(phone, "account", "72000")
    assert left_of(phone).endswith(", account 72000")
    assert left_mark(phone, "account") == app.PC["adjusted"]
    noted = march["computed"]["cells"][1]["figure"]
    assert set_said(phone) == [f"account: you set this; the notes make it {noted} - tap to "
                               "change it"]


def test_left_figures_in_russian(phone) -> None:
    choose_language(phone, "ru")
    phone.page.dialogs.clear()
    phone.tab(app.MONTH)
    word = "Остаток: "
    assert left_of(phone, word) == "Остаток: наличные сумма…, счёт сумма…"
    press(left_tap(phone, "purse"))
    ask = phone.page.top(ft.AlertDialog)
    assert ask.title.value == "Остаток: наличные" and typing(ask).label == "сумма"
    typing(ask).value = "пять"
    press(button(ask, "ОК"))
    assert typing(ask).error == "Введите число."
    typing(ask).value = "5,5"
    press(button(ask, "ОК"))
    assert left_of(phone, word) == "Остаток: наличные 5,5, счёт сумма…"
    press(left_tap(phone, "purse"))
    assert typing(phone.page.top(ft.AlertDialog)).value == "5,5"
    press(button(phone.page.top(ft.AlertDialog), "Вернуть сумму из записей"))
    assert left_of(phone, word) == "Остаток: наличные сумма…, счёт сумма…"
    type_figure(phone, "purse", "5,5", ok="ОК")

    paste(phone, bare(bundled.HOUSEHOLDS["ru"]["examples"]["month-1"]), add="Добавить")
    assert "Январь 2026" in texts(phone.page.appbar)
    assert left_note(phone) == "(посчитано от остатка прошлого месяца)"
    assert left_of(phone, word).endswith(", счёт сумма…")
    type_figure(phone, "purse", "3", ok="ОК")
    assert phone.page.dialogs[-1].content.value == words.RU["closed"]
    press(button(phone.shown(), "Открыть"))
    pc = Budget(phone.folder)
    noted = pc.month(pc.months()[-1]["identity"])["left"]["cells"][0]["figure"]
    type_figure(phone, "purse", "3", ok="ОК")
    assert left_of(phone, word).startswith("Остаток: наличные 3, ")
    assert [line for line in lines(phone.shown()) if "задали вы" in line] == [
        f"наличные: эту сумму задали вы; по записям выходит {noted} — нажмите, чтобы изменить"]
    paste(phone, bare(bundled.HOUSEHOLDS["ru"]["examples"]["month-2"]), add="Добавить")
    assert left_note(phone) == "(посчитано от остатка прошлого месяца)"
    assert [words.t("left.recounted", "(recounted: {date}'s Left + {n} newer day{s})",
                    date="24.03", n=n, s="") for n in (1, 3, 5)] == [
        "(пересчитано: остаток на 24.03 + ещё 1 день)",
        "(пересчитано: остаток на 24.03 + ещё 3 дня)",
        "(пересчитано: остаток на 24.03 + ещё 5 дней)"]


def test_each_door_on_the_month_opens_what_is_beside_it(phone) -> None:
    phone.examples(1)
    doors = edits(phone)
    assert len(doors) == 3
    offered = []
    for door in doors:
        press(door)
        question = phone.page.top(ft.AlertDialog)
        offered.append([c.content for c in walk(question) if isinstance(c, ft.FilledTonalButton)])
        phone.page.pop_dialog()
    assert offered == [["Edit limits…", "Edit major groups…"], ["Edit minor groups…"],
                       ["Edit the Left line…"]]


def test_the_setup_in_russian(phone) -> None:
    phone.examples(1, 2, 3)
    choose_language(phone, "ru")
    phone.page.dialogs.clear()
    press(button(phone.shown(), "Изменить"))
    question = phone.page.top(ft.AlertDialog)
    assert "К каким месяцам применить изменения?" in texts(question)
    assert list(choices(question)) == ["Март 2026 и все последующие месяцы",
                                       "Все месяцы, и прошлые тоже"]
    assert ("Прошлые месяцы пересчитаются по новым группам: их итоги изменятся, а строки "
            "удалённой группы станут там вопросами.") in texts(question)
    assert "Лимит задаётся сразу для всех месяцев." in texts(question)
    press(button(question, "Изменить лимиты…"))
    sheet = editor(phone)
    assert "Лимиты" in texts(sheet) and "Изменения касаются всех месяцев." in texts(sheet)
    assert texts(row(sheet, "Food")).startswith("Food | Food · 30 | Изменить сумму |")
    press(button(row(sheet, "Food"), "Изменить сумму"))
    fill(phone.page.top(ft.AlertDialog), "35", ok="ОК")
    assert "Food · 35" in texts(editor(phone))
    phone.page.dialogs.clear()
    assert "  из 35" in texts(phone.shown())

    press(button(phone.shown(), "Изменить"))
    press(button(phone.page.top(ft.AlertDialog), "Изменить основные группы…"))
    sheet = editor(phone)
    assert "После применения изменения коснутся месяца Март 2026 и всех последующих." in texts(sheet)
    press(button(row(sheet, "Road"), "Удалить"))
    assert "1. удалить группу «Road»" in texts(editor(phone))
    assert "В очереди 1 изменение." in texts(editor(phone))
    press(button(editor(phone), "Применить"))
    confirm = phone.page.top(ft.AlertDialog)
    assert "1 изменение для месяцев: Март 2026, и все последующие месяцы." in texts(confirm)
    press(button(confirm, "Да, применить"))
    assert "Пока в очереди ничего нет" in texts(editor(phone))
    phone.page.dialogs.clear()
    assert "группу «Road» удалили — куда это отнести?" in texts(phone.tab(app.QUESTIONS))

    phone.tab(app.MONTH)
    press(left_door(phone, "Остаток: "))
    press(button(phone.page.top(ft.AlertDialog), "Изменить строку остатка…"))
    sheet = editor(phone)
    assert "Строка остатка" in texts(sheet) and "наличные на руках · подпись до" in texts(sheet)
    press(button(row(sheet, "purse"), "Подписать"))
    fill(phone.page.top(ft.AlertDialog), "копилка", ok="ОК")
    press(button(row(editor(phone), "purse"), "Вид…"))
    press(button(phone.page.top(ft.AlertDialog), "перенесено"))
    press(button(row(editor(phone), "account"), "↑"))
    field(editor(phone), "подпись").value = "банка"
    press(button(editor(phone), "Добавить"))
    press(button(row(editor(phone), "account"), "Удалить"))
    press(button(editor(phone), "Вернуть исходную строку"))
    shown = lines(editor(phone))
    for said in ("1. подписать «purse» как «копилка»", "2. «purse» считается как «перенесено»",
                 "3. строка остатка в новом порядке", "4. добавить «банка» в строку остатка",
                 "5. убрать «account» из строки остатка", "6. вернуть исходную строку остатка"):
        assert said in shown, (said, shown)


def test_add_a_limit_and_remove_in_russian(phone) -> None:
    phone.examples(1)
    choose_language(phone, "ru")
    phone.page.dialogs.clear()
    press(options_row(phone, "Группы и лимиты"))
    press(button(phone.page.top(ft.AlertDialog), "Изменить лимиты…"))
    sheet = editor(phone)
    assert "Выберите группу, у которой лимита ещё нет, или введите название" in texts(sheet)
    group = field(sheet, "Группа")
    assert group.value == app.CHOOSE_GROUP and group.options[0].text == "Выберите группу…"
    field(sheet, "в тысячах").value = "5"
    press(button(sheet, "Добавить"))
    assert "Выберите группу или введите название новой." in texts(sheet)
    choose(sheet, "Группа", "— новая группа —")
    field(sheet, "название новой группы").value = "food"
    press(button(sheet, "Добавить"))
    assert ("У группы «Food» уже есть лимит — измените его кнопкой «Изменить сумму» в её "
            "строке.") in texts(sheet)
    choose(sheet, "Группа", "Rent")
    press(button(sheet, "Добавить"))
    assert "Выбрана группа «Rent» и введено «food» — оставьте что-то одно." in texts(sheet)

    phone.page.dialogs.clear()
    press(options_row(phone, "Группы и лимиты"))
    press(button(phone.page.top(ft.AlertDialog), "Изменить основные группы…"))
    sheet = editor(phone)
    assert ("«Удалить» убирает её вместе с подгруппами, а их строки уходят в «Вопросы», чтобы "
            "вы отнесли их заново. Одна группа для расходов остаётся всегда.") in texts(sheet)
    press(button(row(sheet, "Road"), "Удалить"))
    assert no_question(phone)
    assert "1. удалить группу «Road»" in texts(editor(phone))


def test_removing_a_minor_group_in_russian(phone) -> None:
    phone.examples(1)
    choose_language(phone, "ru")
    sheet = minors_editor(phone, "Группы и лимиты", "Изменить подгруппы…")
    assert ("«Удалить» убирает её: строки, которые в ней были, уходят в «Вопросы», чтобы вы "
            "отнесли их заново.") in texts(sheet)
    press(button(row(sheet, "Food"), "Удалить"))
    assert no_question(phone) and "1. удалить «Food»" in texts(editor(phone))
    press(button(editor(phone), "Применить"))
    press(button(phone.page.top(ft.AlertDialog), "Да, применить"))
    phone.page.dialogs.clear()
    assert "группу «Food» удалили — куда это отнести?" in texts(phone.tab(app.QUESTIONS))


def test_a_new_answer_to_which_months_lets_the_waiting_changes_go(phone) -> None:
    phone.examples(1, 2, 3)
    press(edits(phone)[1])
    press(button(phone.page.top(ft.AlertDialog), "Edit minor groups…"))
    press(button(row(editor(phone), "Food"), "Remove"))
    assert "1. remove Food" in texts(editor(phone))
    press(button(editor(phone), "Discard"))
    assert "Nothing staged yet" in texts(editor(phone))
    press(button(row(editor(phone), "Food"), "Remove"))

    phone.page.dialogs.clear()
    press(edits(phone)[1])
    question = phone.page.top(ft.AlertDialog)
    assert answer(question) == "onward" and "discarded" not in texts(question)
    press(choices(question)["Every month, the earlier ones too"])
    assert "1 unapplied change(s) discarded." in texts(question)
    press(button(question, "Edit minor groups…"))
    assert "Changes apply to every month." in texts(editor(phone))

    phone.page.dialogs.clear()
    press(edits(phone)[1])
    question = phone.page.top(ft.AlertDialog)
    assert answer(question) == "always"
    press(choices(question)["March 2026 and all further months"])
    press(button(question, "Edit minor groups…"))
    press(button(row(editor(phone), "Food"), "Remove"))

    phone.page.dialogs.clear()
    press(phone.page.appbar.leading)
    press(edits(phone)[1])
    question = phone.page.top(ft.AlertDialog)
    assert answer(question) == "onward" and "February 2026 and all further months" in choices(
        question)
    assert "1 unapplied change(s) discarded." in texts(question)


def choose_language(phone, code: str) -> None:
    phone.tab(app.OPTIONS)
    choice = next(c for c in walk(phone.page.top(ft.BottomSheet)) if isinstance(c, ft.Dropdown))
    choice.on_select(SimpleNamespace(control=SimpleNamespace(value=code)))


def lines(root) -> list[str]:
    return [str(c.value) for c in walk(root) if isinstance(c, ft.Text) and c.value]


def test_options_offers_the_language_first(phone) -> None:
    phone.tab(app.OPTIONS)
    sheet = phone.page.top(ft.BottomSheet)
    title, heading, choice = sheet.content.content.controls[:3]
    assert (title.value, heading.value) == ("Options", "Language")
    assert isinstance(choice, ft.Dropdown) and choice.value == "en"
    assert [(o.key, o.text) for o in choice.options] == [("en", "English"), ("ru", "Русский")]
    assert [c for c in walk(sheet) if isinstance(c, ft.Dropdown)] == [choice]


def test_switching_to_russian_relabels_the_tabs_and_redraws(phone) -> None:
    phone.examples(1)
    tabs = [d.label for d in phone.page.navigation_bar.destinations]
    month, bar = texts(phone.shown()), texts(phone.page.appbar)
    groups = [m["name"] for m in Budget(phone.folder).call(action="config")["majors"]]
    shown_groups = [g for g in groups if g in lines(phone.shown())]
    assert tabs == ["Month", "Questions", "Add", "Guide", "Options"] and shown_groups

    choose_language(phone, "ru")
    assert [d.label for d in phone.page.navigation_bar.destinations] == [
        "Месяц", "Вопросы", "Добавить", "Справка", "Настройки"]
    russian = texts(phone.shown())
    for part in ("Итого", "С разовыми", "С лимитом", "Подгруппы", "сэкономлено", "Остаток: "):
        assert part in russian, (part, russian[:900])
    for part in ("Total", "With occasional", "With a limit", "Minor groups", "Left: "):
        assert part not in russian, (part, russian[:900])
    assert [g for g in groups if g in lines(phone.shown())] == shown_groups
    assert "Январь 2026" in texts(phone.page.appbar)
    sheet = phone.page.top(ft.BottomSheet)
    assert texts(sheet).startswith("Настройки | Язык")
    assert next(c for c in walk(sheet) if isinstance(c, ft.Dropdown)).value == "ru"
    assert Look(phone.folder).language == "ru"
    assert phone.page.locale_configuration.current_locale.language_code == "ru"

    choose_language(phone, "en")
    assert [d.label for d in phone.page.navigation_bar.destinations] == tabs
    assert texts(phone.shown()) == month and texts(phone.page.appbar) == bar
    assert phone.page.locale_configuration.current_locale.language_code == "en"


def test_a_file_saved_in_russian_turns_the_phone_russian(phone) -> None:
    pc = Budget(phone.elsewhere / "pc")
    pc.add_example("month-2")
    document = json.loads(pc.backup()[1])
    document["lang"] = "ru"
    phone.examples(1)
    FakePicker.picked = [chosen(json.dumps(document).encode("utf-8"))]
    press(options_row(phone, "Restore from a file"))
    press(button(phone.page.top(ft.AlertDialog), "Replace everything"))
    assert phone.page.dialogs[-1].content.value == "Восстановлено: 1 месяц и 0 ответов."
    assert [d.label for d in phone.page.navigation_bar.destinations][0] == "Месяц"
    assert "Февраль 2026" in texts(phone.page.appbar) and "Итого" in texts(phone.shown())
    assert Look(phone.folder).language == "ru"


def test_the_month_label_and_picker_in_russian(phone) -> None:
    phone.examples(1, 3)
    choose_language(phone, "ru")
    assert "Март 2026" in texts(phone.page.appbar)
    press(phone.page.appbar.title)
    sheet = phone.page.top(ft.BottomSheet)
    assert "Выберите месяц" in texts(sheet)
    years = [c for c in walk(sheet) if isinstance(c, ft.ExpansionTile)]
    cells = {texts(c.content) if not isinstance(c.content, str) else c.content: c
             for c in walk(years[0]) if isinstance(c, (ft.TextButton, ft.FilledButton,
                                                       ft.OutlinedButton))}
    assert list(cells) == list(words.MONTHS_SHORT_RU)
    assert cells["Фев"].disabled and not cells["Янв"].disabled
    press(cells["Янв"])
    assert "Январь 2026" in texts(phone.page.appbar)


def test_russian_plurals(phone) -> None:
    words.set_lang("ru")
    counts = (1, 2, 5, 11, 21, 22)
    said = [words.t("questions.count", "{n} line{s} the rules could not place.",
                    n=n, s="s" if n != 1 else "") for n in counts]
    assert said == [f"Правила не смогли отнести {n} {form}." for n, form in zip(
        counts, ("строку", "строки", "строк", "строк", "строку", "строки"))]
    said = [words.t("restore.done", "Restored {months} month(s) and {answers} answer(s).",
                    months=n, answers=n) for n in counts]
    assert said == [f"Восстановлено: {n} {m} и {n} {a}." for n, m, a in zip(
        counts, ("месяц", "месяца", "месяцев", "месяцев", "месяц", "месяца"),
        ("ответ", "ответа", "ответов", "ответов", "ответ", "ответа"))]
    assert [words.plural(n, "1", "2", "5") for n in (0, 12, 14, 111, 104, 1.5, None)] == [
        "5", "5", "5", "5", "2", "5", "5"]

    words.set_lang("en")
    phone.examples(2)
    choose_language(phone, "ru")
    pc = Budget(phone.folder)
    asked = len(pc.questions(pc.months()[-1]["identity"]))
    form = words.plural(asked, "строку", "строки", "строк")
    assert f"Правила не смогли отнести {asked} {form}." in texts(phone.tab(app.QUESTIONS))


def test_the_guide_quotes_only_its_own_labels() -> None:
    quoted = {q for _, text in words.GUIDE_RU for q in re.findall(r"«([^»]+)»", text)}
    assert quoted >= {"С разовыми", "Другое…", "Открыть", "Попробовать пример месяца",
                      "Сохранить конфигурацию", "Восстановить из файла", "Удалить", "Вопросы"}
    assert quoted - {"Избранное"} <= set(words.RU.values()), quoted - set(words.RU.values())
    source = (Path(app.__file__)).read_text(encoding="utf-8")
    english = {node.args[1].value for node in ast.walk(ast.parse(source))
               if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "t"
               and isinstance(node.args[1], ast.Constant)}
    guide = " ".join(text for _, text in app.GUIDE_TEXT)
    for label in ("Total", "With occasional", "Other…", "Unlock", "Try an example month",
                  "Save the configuration", "Restore from a file", "Remove", "Questions",
                  "Apply"):
        assert label in guide and label in english, label
    assert [len(section) for section in words.GUIDE_RU] == [2] * len(app.GUIDE_TEXT)


def test_the_guide_opens_in_russian(phone) -> None:
    choose_language(phone, "ru")
    phone.tab(app.GUIDE)
    guide = phone.page.top(ft.AlertDialog)
    assert guide.title.value == "Справка" and "Переход между месяцами" in texts(guide)
    assert "Moving between months" not in texts(guide)


def test_the_summary_rows_are_found_by_flag(phone, monkeypatch) -> None:
    assert app.summary({"name": "x", "saved": True}) and app.summary({"name": "y", "overspent": 1})
    assert not app.summary({"name": "Totally saved"})
    phone.examples(1)
    before = texts(phone.shown())
    real = Budget.month

    def renamed(self, identity: str) -> dict:
        data = real(self, identity)
        for group in data["majors"]:
            if group.get("saved") or group.get("overspent"):
                group["name"] = group["id"] = ("Всего сэкономлено" if group.get("saved")
                                               else "Всего перерасходовано")
        return data

    monkeypatch.setattr(Budget, "month", renamed)
    after = texts(phone.tab(app.MONTH))
    assert "Всего" not in after and after == before


def test_the_left_line_takes_the_screens_word_and_the_engines_figures(phone) -> None:
    phone.examples(1)
    pc = Budget(phone.folder)
    line = unbroken(pc.month(pc.months()[-1]["identity"])["left"]["text"])
    assert line.startswith("Left: ") and left_of(phone) == line
    choose_language(phone, "ru")
    assert left_of(phone, "Остаток: ") == "Остаток: " + line[len("Left: "):]


def test_a_russian_import_shows_the_engines_russian_outcome(phone, monkeypatch) -> None:
    real = Budget.add

    def said(self, text: str) -> list[dict]:
        return [dict(o, said="добавлено") for o in real(self, text)] + [
            {"span": "undated", "outcome": "skipped: no dated days",
             "said": "пропущено: нет дней с датой"}]

    monkeypatch.setattr(Budget, "add", said)
    choose_language(phone, "ru")
    press(button(phone.tab(app.ADD), "Попробовать пример месяца"))
    press(button(phone.page.top(ft.AlertDialog), "Пример 1"))
    snack = phone.page.dialogs[-1]
    assert isinstance(snack, ft.SnackBar)
    assert snack.content.value.startswith("добавлено ")
    assert snack.content.value.endswith("; пропущено: нет дней с датой без даты")
    assert "Январь 2026" in texts(phone.page.appbar)


def test_a_closed_refusal_is_known_by_its_code(phone, monkeypatch) -> None:
    with_heating(phone)
    choose_language(phone, "ru")

    def refused(self, identity: str, groups: list[str]) -> None:
        raise Refused("Февраль 2026 закрыт", code="closed")

    monkeypatch.setattr(Budget, "omit", refused)
    tap = next(c for c in walk(phone.shown())
               if isinstance(c, ft.Container) and c.on_click and "С разовыми" in texts(c))
    press(tap)
    sheet = phone.page.top(ft.BottomSheet)
    assert "Учитывается в «С разовыми»" in texts(sheet)
    press(button(sheet, "Применить"))
    assert phone.page.dialogs[-1].content.value == words.RU["closed"]


def test_a_closed_month_says_so_in_russian(phone) -> None:
    phone.examples(2)
    choose_language(phone, "ru")
    pc = Budget(phone.folder)
    month = pc.months()[-1]["identity"]
    question = pc.questions(month)[0]
    with pytest.raises(Refused) as refused:
        pc.answer(month, question["number"], (question["candidates"] or ["Heating"])[0])
    said = str(refused.value)
    assert refused.value.code == "closed" and "Февраль 2026" in said and "закрыт" in said, said
    assert "read-only" not in said and "override" not in said

    cards = [c for c in walk(phone.tab(app.QUESTIONS)) if isinstance(c, ft.Card)]
    press([c for c in walk(cards[0]) if isinstance(c, ft.OutlinedButton)][0])
    assert phone.page.dialogs[-1].content.value == words.RU["closed"]


def test_questions_come_in_russian(phone) -> None:
    phone.examples(1)
    pc = Budget(phone.folder)
    month = pc.months()[-1]["identity"]
    english = [q["review"] for q in pc.questions(month)]
    shown = texts(phone.tab(app.QUESTIONS))
    assert english and all(review in shown for review in english)

    choose_language(phone, "ru")
    shown = texts(phone.tab(app.QUESTIONS))
    russian = [q["review"] for q in pc.questions(month)]
    assert len(russian) == len(english)
    for en, ru in zip(english, russian):
        assert ru in shown, (ru, shown[:600])
        assert re.search("[а-яё]", ru, re.IGNORECASE) and ru != en, (en, ru)
    assert any("Food" in en for en in english) and any("Food" in ru for ru in russian)
    n = len(russian)
    assert f"Правила не смогли отнести {n} {words.plural(n, 'строку', 'строки', 'строк')}." in shown


def household_majors(lang: str) -> list[str]:
    import bundled

    return [m["name"] for m in
            tomllib.loads(bundled.HOUSEHOLDS[lang]["rules"])["groups"]["majors"]]


def test_russian_chosen_first_brings_the_russian_household(phone) -> None:
    assert "The app's own starting groups, in English" in texts(options_block(phone))
    choose_language(phone, "ru")
    assert words.RU["options.rules.ru"] in texts(options_block(phone))
    add = phone.tab(app.ADD)
    assert next(c for c in walk(add) if isinstance(c, ft.TextField)).hint_text == HINTS["ru"]
    press(button(add, "Попробовать пример месяца"))
    press(button(phone.page.top(ft.AlertDialog), "Пример 1"))

    month = lines(phone.shown())
    drawn = [g for g in household_majors("ru") if g in month]
    assert drawn and not [g for g in household_majors("en") if g in month], month[:40]
    assert "Январь 2026" in texts(phone.page.appbar)
    assert any(line.startswith("Остаток: ") for line in month)

    choose_language(phone, "en")
    assert "The app's own starting groups, in Russian" in texts(options_block(phone))
    assert [g for g in household_majors("ru") if g in lines(phone.tab(app.MONTH))] == drawn
    add = phone.tab(app.ADD)
    assert next(c for c in walk(add) if isinstance(c, ft.TextField)).hint_text == HINTS["ru"]
