"""The Android app's screens, written with Flet: the month with its bars and
totals, questions, adding notes, the editors, and saving or restoring the
configuration file.
"""

from __future__ import annotations

import traceback
from pathlib import Path
from types import SimpleNamespace

import flet as ft

import send
import words
from data import (Budget, Look, Refused, beside, by_year, grouped, money, near_group,
                  newest_real, spaced,
                  typed_number, unbroken)
from words import t


@ft.control
class DayLines(ft.Column):
    def did_mount(self):
        super().did_mount()
        try:
            self.page.run_task(self.scroll_to, scroll_key="near")
        except Exception:
            pass

MONTH, QUESTIONS, ADD, GUIDE, OPTIONS = range(5)
CALENDAR = ("January", "February", "March", "April", "May", "June", "July",
            "August", "September", "October", "November", "December")
PC = {"green": "#3f9d5a", "yellow": "#e5bc3c", "red": "#c8482f", "blue": "#4a8fc7",
      "saved": "#ffd84d", "overspent": "#ff4d3d", "adjusted": "#d8b4fe"}
CLOSED = frozenset({"closed", "paste_closed"})

GUIDE_TEXT = (
    ("The month",
     "Each group's spending against its limit, every bar drawn to one scale so "
     "lengths compare: green is spent, yellow is what is left before the limit, red "
     "is past it. A group far larger than the rest is drawn broken (≈), so the "
     "others stay readable. Groups with no limit are blue. Scroll down for every "
     "minor group with its amounts, and the Left line. Tap a group to see each of its "
     "figures with the lines it is made of, under the day each was written - and tap "
     "a figure to move it to another group, or to put it back: it shows the day as "
     "you wrote it, the figure's line in bold."),
    ("The totals",
     "Total is the month's necessary spending. Tap With occasional to see which "
     "occasional groups it counts: untick one to leave it out, or tap its figure to "
     "set a different one. An empty figure puts back what the notes make. Under them, "
     "Compare lays the months you tick side by side, with their Average if you switch "
     "it on, and Share saves this month to the phone as a text file for print or sends "
     "it to Telegram or WhatsApp."),
    ("Typing a figure yourself",
     "Every figure of the Left line can be tapped. Type a number and it takes the place "
     "of what the notes give for that month, marked as yours the way a figure set in "
     "With occasional is, and the notes' own figure is shown under the line. Back to the "
     "notes' figure takes yours away again. Where a figure has no value, a small value… "
     "button stands in its place. Before any month is added, the same buttons on the "
     "empty month set your starting figures: where your money stands now. A month whose "
     "notes carry no Left line of their own counts on from them through its days, and "
     "the next such month counts on from the one before it."),
    ("Moving between months",
     "‹ and › step to the month before or after, across the end of a year too. "
     "Tap the month's name to choose any month under its year."),
    ("Questions",
     "Lines the rules could not place, each in its day as you wrote it - the date, "
     "that day's lines in a box that scrolls, the one asked about in bold. Tap a "
     "suggested group, or Other… to type "
     "one; a line that names a group offers that group first, and a name one letter "
     "off a group that exists asks whether you meant that one. The red number is how "
     "many wait in this month. Ask them all again "
     "forgets the month's answers - the notes stay - and asks every question anew."),
    ("Closed months",
     "A month locks three months after it ends, so an old figure is not changed by "
     "accident. Unlock at the top opens it until you close the app."),
    ("Groups, limits and words",
     "Edit beside the bars changes the limits and the major groups; beside Minor groups, "
     "the minor groups; beside the Left line, its figures. Groups and limits and The Left "
     "line in the Options open them too, and Words you teach there teaches the app words: "
     "a line carrying one books to its group without a question. Remove takes a group "
     "away, and the lines it held go to Questions, to be placed again; one group spending "
     "can go to always stays. Once months are stored, a change to the groups first asks "
     "which months: the month shown and every later one, or every month, the earlier ones "
     "too, which counts them again under the new groups. A change from the month shown "
     "waits until Apply, which names the months and asks first. A limit never asks: it is "
     "set for every month at once. The groups set aside - Salary, Withdrawal and the rest "
     "counted nowhere - are listed below the other minor groups, to rename or remove; "
     "Salary asks first, since your salary line then goes to Questions."),
    ("Adding notes",
     "Paste the notes as you wrote them: dates, amounts, what each was. A month's "
     "opening salary line tells the app which month it is, and a line of ###### after "
     "its last day ends it: months pasted together without it run into one. A few "
     "days without the salary line go into the month you choose in Add to. Try an "
     "example month to see how the app reads notes. A line ending \"do not count, refers "
     "to August\" is August's, even with no August stored: this month neither counts nor "
     "shows it, and the app makes an August holding it, to be asked about there, until "
     "August's own notes - a new month, or added to it - join it."),
    ("Options",
     "Light or dark, the size of each kind of text, the groups, limits and words you "
     "teach, where your data is kept, and starting over."),
    ("The configuration file",
     "Save the configuration writes one file with every month, answer, group, limit "
     "and the rules: save it to the phone, or send it to a chat or Saved Messages in "
     "Telegram or WhatsApp. It restores here, on the PC and in the cloud. It holds "
     "all your figures, so keep it where only you can see it. Restore from a file "
     "replaces everything on this phone with what the file holds."),
    ("Your data",
     "Everything stays on this phone. The app needs no internet."),
)


def span(group: dict) -> float:
    return max(abs(group["value"]), group["limit"] or 0)


def one_scale(groups: list[dict]) -> tuple[float, set[str]]:
    spans = sorted((span(g) for g in groups), reverse=True)
    while len(spans) > 1 and spans[0] > 2 * spans[1]:
        spans.pop(0)
    scale = (spans[0] if spans else 0) or 1.0
    return scale, {g["name"] for g in groups if span(g) > scale}


def segments(group: dict) -> list[tuple[float, str]]:
    value, limit = abs(group["value"]), group["limit"]
    if not limit:
        return [(value, PC["blue"])]
    return [(min(value, limit), PC["green"]), (max(0, limit - value), PC["yellow"]),
            (max(0, value - limit), PC["red"])]


def drawn(text: str, text_size: float, bold: bool = False) -> float:
    ems = sum(0.72 if ch.isupper() else 0.6 if ch.isalpha() else 0.58 if ch.isdigit() else 0.32
              for ch in text)
    return ems * text_size * (1.06 if bold else 1.0)


def summary(group: dict) -> bool:
    return bool(group.get("saved") or group.get("overspent"))


CHOOSE_GROUP, NEW_GROUP = "", " "


def last_for_spending(majors: list[dict]) -> str | None:
    spending = [m["name"] for m in majors if m["tier"] != "EXCLUDED" and not m.get("income")]
    return spending[0] if len(spending) == 1 else None


def flutter_locale() -> ft.LocaleConfiguration:
    return ft.LocaleConfiguration(supported_locales=[ft.Locale(code) for code in words.LANGS],
                                  current_locale=ft.Locale(words.LANG))


def main(page: ft.Page) -> None:
    budget = Budget()
    look = Look(budget.folder)
    words.set_lang(look.language)

    page.title = "Budget"
    page.padding = 0
    page.theme = _theme(dark=False)
    page.dark_theme = _theme(dark=True)
    page.locale_configuration = flutter_locale()

    state = {"tab": MONTH, "month": None, "asked": 0, "compare": [], "average": False,
             "scope": None, "staged": []}
    frame = ft.SafeArea(expand=True, content=ft.ListView())
    picker = ft.FilePicker()

    def apply_theme() -> None:
        page.theme_mode = {"system": ft.ThemeMode.SYSTEM, "light": ft.ThemeMode.LIGHT,
                           "dark": ft.ThemeMode.DARK}[look.theme]


    def size(kind: str) -> int:
        return look.sizes[kind]

    def snack(text: str) -> None:
        page.show_dialog(ft.SnackBar(ft.Text(text)))

    def tell(text: str) -> None:
        page.show_dialog(ft.AlertDialog(
            content=ft.Text(text, size=16),
            actions=[ft.TextButton(t("ok", "OK"), on_click=lambda e: page.pop_dialog())]))

    def closed_said(why: Exception) -> str:
        return (t("closed", "This month is closed - press Unlock at the top first.")
                if getattr(why, "code", None) in CLOSED or "read-only" in str(why)
                else str(why))

    def muted(text: str, text_size: float = 13, **kw) -> ft.Text:
        return ft.Text(text, size=text_size, color=ft.Colors.ON_SURFACE_VARIANT, **kw)

    def section(title: str) -> ft.Control:
        return ft.Text(title, size=14, weight=ft.FontWeight.W_600, color=ft.Colors.PRIMARY)

    def card(controls: list[ft.Control], spacing: int = 14) -> ft.Control:
        return ft.Card(ft.Container(ft.Column(controls, spacing=spacing), padding=16))

    def tall() -> ft.ButtonStyle:
        return ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=16, vertical=14))

    def dot(color: str) -> ft.Control:
        return ft.Container(width=10, height=10, border_radius=5, bgcolor=color)

    def label(m: dict) -> str:
        return words.month_label(m["month"], m.get("year"))

    def current(months: list[dict]) -> dict:
        ids = [m["identity"] for m in months]
        if state["month"] not in ids:
            gone = state["month"] or ""
            name, _, year = gone.removeprefix("moved:").partition(" ")
            state["month"] = next(
                (m["identity"] for m in months if gone.startswith("moved:")
                 and m["month"] == name and (not year or str(m.get("year")) == year)),
                ids[-1])
        return next(m for m in months if m["identity"] == state["month"])

    def go_month(identity: str | None) -> None:
        if identity:
            state["month"] = identity
            show(state["tab"])

    def banner(text: str, button: ft.Control) -> ft.Control:
        return ft.Container(
            ft.Row([ft.Text(text, expand=True, size=13), button]),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=8, padding=12)

    def lock_bar(identity: str, closed: bool) -> ft.Control | None:
        if not closed:
            return None
        if identity in budget.unlocked:
            def lock(e) -> None:
                budget.unlocked.discard(identity)
                show(state["tab"])
            return banner(t("lock.unlocked", "Unlocked until you close the app."),
                          ft.TextButton(t("lock.lock", "Lock"), on_click=lock))

        def unlock(e) -> None:
            budget.unlocked.add(identity)
            show(state["tab"])
        return banner(t("lock.closed",
                        "This month is closed - months lock three months after they end, "
                        "so an old figure is not changed by accident."),
                      ft.TextButton(t("lock.unlock", "Unlock"), icon=ft.Icons.LOCK_OPEN,
                                    on_click=unlock))

    def nothing_yet() -> list[ft.Control]:
        state["asked"] = 0
        return [
            ft.Text(t("empty.title", "No months yet"), size=22, weight=ft.FontWeight.W_600),
            muted(t("empty.text", "Paste a month's notes in Add - or try one of the invented "
                                  "example months to see how the app reads them."), 15),
            ft.Row([ft.FilledButton(t("add.notes", "Add notes"), icon=ft.Icons.EDIT_NOTE,
                                    style=tall(), on_click=lambda e: show(ADD))]),
        ]

    def empty_banner() -> ft.Control:
        return ft.Container(ft.Column([
            ft.Text(t("empty.month", "Nothing has been added yet — this is how your month "
                                     "will look."), size=16, weight=ft.FontWeight.W_600),
            ft.Text(t("empty.month.text", "Every group is in its place, empty. Rename, add or "
                                          "remove them with Edit, then paste your first month "
                                          "in Add."), size=14),
            ft.Row([ft.FilledButton(t("add.notes", "Add notes"), icon=ft.Icons.EDIT_NOTE,
                                    style=tall(), on_click=lambda e: show(ADD))]),
        ], spacing=8), bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=8, padding=12)


    def top_bar(months: list[dict]) -> ft.AppBar:
        if state["tab"] == ADD or not months:
            return ft.AppBar(title=ft.Text(t("add.notes", "Add notes") if state["tab"] == ADD
                                           else t("budget", "Budget"),
                                           weight=ft.FontWeight.W_600))
        m = current(months)
        before = beside(months, m["identity"], -1)
        after = beside(months, m["identity"], +1)
        return ft.AppBar(
            leading=ft.IconButton(ft.Icons.CHEVRON_LEFT, icon_size=30,
                                  tooltip=t("top.before", "Month before"),
                                  disabled=before is None, on_click=lambda e: go_month(before)),
            title=ft.TextButton(
                content=ft.Row([ft.Text(label(m), size=20, weight=ft.FontWeight.W_600,
                                        color=ft.Colors.ON_SURFACE),
                                ft.Icon(ft.Icons.ARROW_DROP_DOWN, color=ft.Colors.ON_SURFACE)],
                               tight=True, spacing=2),
                on_click=lambda e: month_picker(months)),
            center_title=True,
            actions=[ft.IconButton(ft.Icons.CHEVRON_RIGHT, icon_size=30,
                                   tooltip=t("top.after", "Month after"),
                                   disabled=after is None, on_click=lambda e: go_month(after))],
        )

    def month_picker(months: list[dict]) -> None:
        closed = budget.closed()
        chosen = state["month"]
        chosen_year = next((m.get("year") for m in months if m["identity"] == chosen), None)

        def pick(identity: str):
            def handler(e) -> None:
                page.pop_dialog()
                go_month(identity)
            return handler

        years: list[ft.Control] = []
        for year, held in by_year(months).items():
            named = {m["month"]: m for m in held}
            cells: list[ft.Control] = []
            for name in CALENDAR:
                m = named.get(name)
                short = words.month_short(name)
                if m is None:
                    cells.append(ft.TextButton(short, disabled=True, expand=True))
                elif m["identity"] == chosen:
                    cells.append(ft.FilledButton(short, expand=True, on_click=pick(m["identity"])))
                else:
                    cells.append(ft.OutlinedButton(
                        short, expand=True, on_click=pick(m["identity"]),
                        icon=ft.Icons.LOCK_OUTLINE if m["identity"] in closed else None))
            grid = ft.Column([ft.Row(cells[i:i + 3], spacing=8) for i in range(0, 12, 3)],
                             spacing=8)
            years.append(ft.ExpansionTile(
                title=ft.Text(str(year) if year else t("picker.earlier", "Earlier"), size=20,
                              weight=ft.FontWeight.W_600),
                expanded=year == chosen_year,
                controls=[ft.Container(grid, padding=ft.Padding.only(left=16, right=16,
                                                                     bottom=12))],
            ))
        page.show_dialog(ft.BottomSheet(ft.Container(ft.Column([
            ft.Container(ft.Text(t("picker.title", "Choose a month"), size=20,
                                 weight=ft.FontWeight.W_600),
                         padding=ft.Padding.only(left=16)),
            *years,
        ], tight=True, spacing=4,
            scroll=ft.ScrollMode.AUTO if len(years) > 2 else None),
            padding=ft.Padding.only(top=8, bottom=16)),
            show_drag_handle=True, scrollable=True))


    def totals_card(identity: str | None, data: dict) -> ft.Control:
        totals, majors = data["totals"], data["majors"]
        saved = next((m["value"] for m in majors if m.get("saved")), 0)
        over = next((m["value"] for m in majors if m.get("overspent")), 0)

        def big(name: str, value: float, tap=None) -> ft.Control:
            head = ft.Row([muted(name, 14),
                           *([ft.Icon(ft.Icons.TUNE, size=16, color=ft.Colors.PRIMARY)]
                             if tap else [])], spacing=4)
            return ft.Container(
                ft.Column([head, ft.Text(money(value), size=size("totals"),
                                         weight=ft.FontWeight.W_700)], spacing=0),
                expand=True, on_click=tap, ink=tap is not None, border_radius=8,
                padding=ft.Padding.symmetric(horizontal=4, vertical=2))

        return card([
            ft.Row([big(t("totals.total", "Total"), totals["necessary"]),
                    big(t("totals.grand", "With occasional"), totals["grand"],
                        tap=(lambda e: occasional(identity)) if identity else None)]),
            ft.Row([dot(PC["saved"]),
                    ft.Text(t("totals.saved", "saved {x}", x=money(saved)),
                            size=size("limits") + 1),
                    ft.Container(width=12),
                    dot(PC["overspent"]),
                    ft.Text(t("totals.overspent", "overspent {x}", x=money(over)),
                            size=size("limits") + 1)], spacing=6),
        ], spacing=8)

    def occasional(identity: str) -> None:
        listed = budget.month(identity).get("appended", [])
        if not listed:
            snack(t("occasional.none", "No occasional groups this month."))
            return
        ticks: dict[str, ft.Checkbox] = {}
        rows: list[ft.Control] = []
        for group in listed:
            ticks[group["id"]] = ft.Checkbox(value=group["counted"])
            shown = ft.Container(
                ft.Text(money(group["value"]), size=17, weight=ft.FontWeight.W_600,
                        color=ft.Colors.BLACK if group["adjusted"] else None),
                bgcolor=PC["adjusted"] if group["adjusted"] else None, border_radius=4,
                padding=ft.Padding.symmetric(horizontal=6, vertical=2))
            rows.append(ft.Row([
                ticks[group["id"]],
                ft.Text(group["name"], size=16, expand=True),
                ft.TextButton(content=shown, on_click=set_figure(identity, group)),
            ], spacing=4))

        def apply(e) -> None:
            left_out = [gid for gid, box in ticks.items() if not box.value]
            try:
                budget.omit(identity, left_out)
            except Refused as why:
                snack(closed_said(why))
                return
            page.pop_dialog()
            show(MONTH)

        page.show_dialog(ft.BottomSheet(ft.Container(ft.Column([
            ft.Text(t("occasional.title", "Counted in With occasional"), size=20,
                    weight=ft.FontWeight.W_600),
            muted(t("occasional.help",
                    "Untick a group to leave it out. Tap a figure to set a different one - "
                    "the group's own bar keeps what the notes say."), 14),
            *rows,
            ft.Row([ft.TextButton(t("cancel", "Cancel"), on_click=lambda e: page.pop_dialog()),
                    ft.FilledButton(t("apply", "Apply"), on_click=apply)],
                   alignment=ft.MainAxisAlignment.END),
        ], tight=True, spacing=6, scroll=ft.ScrollMode.AUTO if len(rows) > 8 else None),
            padding=ft.Padding.only(left=20, right=20, top=4, bottom=20)),
            show_drag_handle=True, scrollable=True))

    def set_figure(identity: str, group: dict):
        def handler(e) -> None:
            field = ft.TextField(
                value=f"{group['value']:.1f}", label=group["name"], autofocus=True,
                keyboard_type=ft.KeyboardType.NUMBER,
                helper=t("figure.helper", "Empty puts back what the notes make: {x}",
                         x=money(group["actual"])))

            def done(e) -> None:
                typed = (field.value or "").strip().replace(",", ".").replace(" ", "")
                try:
                    value = None if typed == "" else float(typed)
                except ValueError:
                    field.error = t("figure.error", "A number in thousands, like 12.5")
                    page.update()
                    return
                if value is not None and abs(value - group["actual"]) < 1e-9:
                    value = None
                try:
                    budget.adjust(identity, group["id"], value)
                except Refused as why:
                    page.pop_dialog()
                    snack(closed_said(why))
                    return
                page.pop_dialog()
                page.pop_dialog()
                show(MONTH)
                occasional(identity)

            field.on_submit = done
            page.show_dialog(ft.AlertDialog(
                title=ft.Text(t("figure.title", "Set the figure")), content=field,
                actions=[ft.TextButton(t("cancel", "Cancel"), on_click=lambda e: page.pop_dialog()),
                         ft.FilledButton(t("figure.set", "Set"), on_click=done)]))
        return handler

    def scaled_bar(group: dict, scale: float, broken: bool) -> ft.Control:
        def bar(parts: list[tuple[float, str]]) -> ft.Control:
            cells = [ft.Container(expand=max(1, round(units * 1000)), bgcolor=color, height=10)
                     for units, color in parts if units > 0]
            return ft.Container(ft.Row(cells, spacing=0), border_radius=5,
                                clip_behavior=ft.ClipBehavior.HARD_EDGE)

        parts = segments(group)
        length = sum(units for units, _ in parts)
        if not broken:
            room = scale - length
            return ft.Row([ft.Container(bar(parts), expand=max(1, round(length * 1000))),
                           *([ft.Container(expand=round(room * 1000))] if room > scale / 1000
                             else [])], spacing=0)
        room, drawn, head = 0.85 * scale, 0.0, []
        for units, color in parts:
            take = min(units, room - drawn)
            if take > 0:
                head.append((take, color))
                drawn += take
        last = next(color for units, color in reversed(parts) if units > 0)
        return ft.Row([
            ft.Container(bar(head), expand=85),
            ft.Container(ft.Text("≈", size=16, color=ft.Colors.ON_SURFACE_VARIANT,
                                 text_align=ft.TextAlign.CENTER), expand=5),
            ft.Container(bgcolor=last, height=10, expand=10,
                         border_radius=ft.BorderRadius.only(top_right=5, bottom_right=5)),
        ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def bar_row(group: dict, scale: float, broken: set[str]) -> ft.Control:
        value, limit = group["value"], group["limit"]
        over = limit is not None and value > limit
        figures = [ft.TextSpan(money(value) if value else "—", ft.TextStyle(
            size=size("figures"), weight=ft.FontWeight.W_600,
            color=PC["red"] if over else None))]
        if limit:
            figures.append(ft.TextSpan(t("bar.of", "  of {limit}", limit=f"{limit:g}"),
                                       ft.TextStyle(size=size("limits"),
                                                    color=ft.Colors.ON_SURFACE_VARIANT)))
        parts: list[ft.Control] = [ft.Row([
            ft.Text(group["name"], size=size("names"), weight=ft.FontWeight.W_500, expand=True,
                    max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            ft.Text(spans=figures),
        ])]
        if value:
            parts.append(scaled_bar(group, scale, group["name"] in broken))
            if limit and over:
                parts.append(ft.Text(t("bar.over", "{x} over", x=money(value - limit)),
                                     size=size("limits"), color=PC["red"],
                                     weight=ft.FontWeight.W_600))
            elif limit:
                parts.append(muted(t("bar.left", "{x} left", x=money(limit - value)),
                                   size("limits")))
        elif limit:
            parts.append(muted(t("bar.nothing", "nothing spent"), size("limits")))
        return ft.Column(parts, spacing=6)

    def day_view(date: str | None, lines: list[dict] | None,
                 raw: str | None = None) -> ft.Control:
        if not lines:
            return ft.Text(raw or "", size=17, font_family="monospace", selectable=True)
        first = next((at for at, line in enumerate(lines) if line.get("this")), 0)
        marked = ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE, decoration_thickness=2)
        rows = [ft.Text(line["text"] or " ", size=17 if line.get("this") else 15,
                        font_family="monospace",
                        weight=ft.FontWeight.BOLD if line.get("this") else None,
                        style=marked if line.get("this") else None,
                        color=None if line.get("this") else ft.Colors.ON_SURFACE_VARIANT,
                        key=ft.ScrollKey("near") if at == max(0, first - 2) else None)
                for at, line in enumerate(lines)]
        box = DayLines(rows, spacing=0, scroll=ft.ScrollMode.AUTO,
                       height=sum(24 if line.get("this") else 21 for line in lines[:8]) + 4)
        return ft.Column([
            *([ft.Text(date, size=15, weight=ft.FontWeight.W_600)] if date else []),
            ft.Container(box, padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                         border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT), border_radius=8),
        ], spacing=4)

    def dated(lines: list[dict], text_size: float) -> list[ft.Control]:
        return [ft.Text(f"{line['date']}   {line['raw']}" if line.get("date") else line["raw"],
                        size=text_size - 1, color=ft.Colors.ON_SURFACE_VARIANT)
                for line in lines or []]

    def figure_lines(name: str, amounts: list[int], marks: list) -> None:
        text_size = size("minors")
        rows: list[ft.Control] = [muted(t("figures.tap", "Tap a figure to move it."), 13)]
        for amount, lines in zip(amounts, marks):
            if not lines:
                continue
            rows.append(ft.Container(
                ft.Column([ft.Text(spaced(amount), size=text_size, weight=ft.FontWeight.W_600),
                           *dated(lines, text_size)], spacing=2),
                ink=True, padding=ft.Padding.symmetric(vertical=4),
                on_click=lambda e, amount=amount, lines=lines: move_figure(amount, lines)))
        page.show_dialog(ft.AlertDialog(
            title=ft.Text(name), scrollable=True,
            content=ft.Column(rows, tight=True, spacing=4),
            actions=[ft.TextButton(t("guide.close", "Close"),
                                   on_click=lambda e: page.pop_dialog())]))

    def meant(typed: str, identity: str | None, go) -> None:
        try:
            near = near_group(typed, budget.group_names(identity))
        except Refused:
            near = None
        if near is None:
            go(typed)
            return

        def chose(name: str):
            def handler(e) -> None:
                page.pop_dialog()
                go(name)
            return handler

        page.show_dialog(ft.AlertDialog(
            title=ft.Text(t("near.ask", "Did you mean {near}?", near=near)),
            content=muted(t("near.help", "{typed} is one letter off {near}, a group that "
                                         "already exists.", typed=typed, near=near), 15),
            actions=[ft.TextButton(t("near.no", "No, a new group {typed}", typed=typed),
                                   on_click=chose(typed)),
                     ft.FilledButton(t("near.yes", "Yes, {near}", near=near),
                                     on_click=chose(near))]))

    def move_figure(amount: int, lines: list[dict]) -> None:
        identity = state["month"]
        offered = list(dict.fromkeys(c for line in lines for c in (line.get("candidates") or [])))

        def to(group: str | None, new: bool = False, layers: int = 2) -> None:
            try:
                budget.move(identity, lines, group, new)
            except Refused as why:
                tell(closed_said(why))
                return
            for _ in range(layers):
                page.pop_dialog()
            show(state["tab"])

        def other(e) -> None:
            field = ft.TextField(label=t("move.new", "or a new group"), dense=True)

            def typed(e) -> None:
                if (field.value or "").strip():
                    meant(field.value.strip(), identity,
                          lambda name: to(name, new=True, layers=3))

            page.show_dialog(ft.AlertDialog(
                title=ft.Text(t("move.choose", "Choose the group")), scrollable=True,
                content=ft.Column([
                    *[ft.TextButton(g, on_click=lambda e, g=g: to(g, layers=3),
                                    style=ft.ButtonStyle(alignment=ft.Alignment.CENTER_LEFT))
                      for g in budget.groups()],
                    field], tight=True, spacing=2,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                actions=[ft.TextButton(t("move.here", "Move there"), on_click=typed),
                         ft.TextButton(t("cancel", "Cancel"), on_click=lambda e: page.pop_dialog())]))

        buttons: list[ft.Control] = [ft.FilledTonalButton(g, on_click=lambda e, g=g: to(g))
                                     for g in offered]
        buttons.append(ft.OutlinedButton(t("move.other", "Other…"), on_click=other))
        if any(line.get("kind") == "moved" for line in lines):
            buttons.append(ft.TextButton(t("move.put_back", "Put it back"),
                                         on_click=lambda e: to(None)))
        try:
            days = [day_view(day["date"], day["lines"]) for day in budget.day(identity, lines)]
        except Refused:
            days = []
        page.show_dialog(ft.AlertDialog(
            title=ft.Text(t("move.title", "Move {amount}", amount=spaced(amount))), scrollable=True,
            content=ft.Column([*(days or dated(lines, size("minors"))),
                               muted(t("move.where", "Where should this go?"), 13),
                               ft.Row(buttons, wrap=True, spacing=6, run_spacing=6)],
                              tight=True, spacing=6),
            actions=[ft.TextButton(t("cancel", "Cancel"), on_click=lambda e: page.pop_dialog())]))

    def minor_line(name: str, total: int, amounts: list[int] | None,
                   indent: bool = False, marks: list | None = None) -> ft.Control:
        text_size = size("minors")
        parts: list[ft.Control] = [ft.Row([
            ft.Text(name, size=text_size, expand=True,
                    weight=ft.FontWeight.W_500 if indent else ft.FontWeight.W_600),
            ft.Text(spaced(total) if total else "—", size=text_size, weight=ft.FontWeight.W_600),
        ])]
        if amounts:
            parts.append(ft.Text(", ".join(spaced(a) for a in amounts), size=text_size - 1,
                                 color=ft.Colors.ON_SURFACE_VARIANT))
        opens = bool(amounts and marks)
        return ft.Container(ft.Column(parts, spacing=2),
                            padding=ft.Padding.only(left=18) if indent else None,
                            ink=opens,
                            on_click=(lambda e: figure_lines(name, amounts, marks)) if opens else None)

    def minor_rows(data: dict) -> list[ft.Control]:
        rows: list[ft.Control] = []
        for minor in data.get("minors", []):
            if minor.get("subgroups"):
                rows.append(minor_line(minor["name"], minor["total"], None))
                rows += [minor_line(sub["name"], sub["total"], sub["amounts"], indent=True,
                                    marks=sub.get("marks"))
                         for sub in minor["subgroups"]]
            else:
                rows.append(minor_line(minor["name"], minor["total"], minor["amounts"],
                                       marks=minor.get("marks")))
        return rows

    def month_page(months: list[dict]) -> list[ft.Control]:
        if not months:
            return [empty_banner(), *month_view(budget.empty(), None)]
        m = current(months)
        return month_view(budget.month(m["identity"]), m)

    def month_view(data: dict, m: dict | None) -> list[ft.Control]:
        identity = m["identity"] if m else None
        state["asked"] = data.get("questions", 0)

        out: list[ft.Control] = []
        bar = lock_bar(identity, bool(data.get("closed"))) if m else None
        if bar:
            out.append(bar)
        if m and m.get("moved"):
            out.append(muted(t("view.moved", "Only lines written in other months that belong "
                                             "to this one. Add its own notes - as a new month, "
                                             "or with Add to - and they join them."), 14))
        out.append(totals_card(identity, data))
        if m:
            out.append(ft.Row([
                ft.OutlinedButton(t("compare", "Compare"), icon=ft.Icons.COMPARE_ARROWS,
                                  height=48, expand=True, on_click=lambda e: compare_months()),
                ft.OutlinedButton(t("share", "Share"), icon=ft.Icons.SHARE, height=48,
                                  expand=True, on_click=lambda e: share_month(m)),
            ], spacing=12))

        majors = data["majors"]

        def kept(g: dict) -> bool:
            return bool(g["value"]) or (m is None and bool(g.get("chart")))

        spending = [g for g in majors if g.get("chart") and not g.get("income")
                    and not summary(g)]
        limited = [g for g in spending if g["limit"]]
        unlimited = [g for g in spending if not g["limit"] and kept(g)]
        scale, broken = one_scale(limited + unlimited)
        doors = [setup_door(("limits", "majors"))]
        if limited:
            out += [headed(t("view.limited", "With a limit"), doors.pop() if doors else None),
                    card([bar_row(g, scale, broken) for g in limited], 16)]
        if unlimited:
            out += [headed(t("view.unlimited", "No limit"), doors.pop() if doors else None),
                    card([bar_row(g, scale, broken) for g in unlimited], 16)]

        aside = [g for g in majors if (g.get("income") or not g.get("chart"))
                 and kept(g) and not summary(g)]
        if aside:
            out += [headed(t("view.aside", "Income and withdrawals"),
                           doors.pop() if doors else None), card([
                ft.Row([ft.Text(g["name"] + (t("view.income", " · income") if g.get("income")
                                             else ""),
                                size=size("names") - 1, expand=True),
                        ft.Text(money(g["value"]) if g["value"] else "—", size=size("figures"),
                                weight=ft.FontWeight.W_600)])
                for g in aside], 10)]

        minors = minor_rows(data)
        if minors:
            out += [headed(t("view.minors", "Minor groups"), setup_door(("minors",))),
                    card(minors, 12)]
        held = data.get("held") or []
        if held:
            out += [headed(t("view.held", "Moved to another month"), None), card([
                muted(t("view.held.help", "Not counted in this month - counted there once "
                                          "its notes are added."), 13),
                *[ft.Column([
                    ft.Text(h["raw"], size=size("minors") - 1),
                    muted(" ".join(filter(None, [
                        h.get("date"), "→",
                        words.month_label(h["month"]) if h.get("month")
                        else t("view.held.before", "the month before")])), 13)],
                    spacing=2) for h in held]], 8)]
        out += left_view(data.get("left"), identity)
        if data.get("span"):
            out.append(muted(words.span_label(data["span"]), 13))
        return out


    def left_view(left: dict | None, identity: str | None) -> list[ft.Control]:
        left = left or {}
        shown = left.get("computed") or left
        cells = shown.get("cells")
        door = setup_door(("left",))
        if not isinstance(cells, list):
            line = (ft.Text(unbroken(shown["text"]), size=size("left"), expand=True)
                    if shown.get("text") else
                    muted(t("left.none", "These notes carry no Left line."), size("left"),
                          expand=True))
            return [ft.Row([line, door], vertical_alignment=ft.CrossAxisAlignment.CENTER)]
        text_size = size("left")
        pieces: list[ft.Control] = [ft.Text(t("left", "Left") + ": ", size=text_size)]
        for at, cell in enumerate(cells):
            one = left_cell(cell, identity)
            pieces.append(ft.Row([one, ft.Text(", ", size=text_size)], spacing=0, tight=True)
                          if at < len(cells) - 1 else one)
        note = left_note(left)
        if note:
            pieces.append(ft.Container(muted(note, text_size - 2), data="left.note",
                                       padding=ft.Padding.only(left=6)))
        out: list[ft.Control] = [ft.Row([
            ft.Row(pieces, wrap=True, spacing=0, run_spacing=0, expand=True,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            door], vertical_alignment=ft.CrossAxisAlignment.CENTER)]
        out += [muted(unbroken(f"{cell.get('label') or cell['id']}: {left_set_said(cell)}"),
                      text_size - 2)
                for cell in cells if cell.get("set") and cell.get("noted") not in (None, "—")]
        return out

    def left_set_said(cell: dict) -> str:
        return t("left.value.set", "you set this; the notes make it {n} - tap to change it",
                 n=cell.get("noted") or "—")

    def left_note(left: dict) -> str:
        if left.get("computed"):
            n = left.get("days_after") or 0
            return t("left.recounted", "(recounted: {date}'s Left + {n} newer day{s})",
                     date=left.get("date"), n=n, s="" if n == 1 else "s")
        if left.get("counted_on"):
            return (t("left.counted_start", "(counted on from your starting figures)")
                    if left.get("counted_from") == "start" else
                    t("left.counted_before", "(counted on from the month before)"))
        if left.get("blank"):
            return t("left.no_line", "(these notes carry no closing line)")
        return ""

    def left_cell(cell: dict, identity: str | None) -> ft.Control:
        text_size = size("left")
        label = cell.get("label") or ""
        after = cell.get("place") == "after"
        join = cell.get("join", " ") if label else ""
        name = [ft.Text(join + label if after else label + join, size=text_size)] if label else []
        if not cell.get("id"):
            return ft.Text(unbroken(cell.get("text") or cell.get("figure") or ""), size=text_size)

        def tap(e) -> None:
            left_figure(identity, cell)

        if not cell.get("set") and cell.get("value") is None:
            figure = ft.OutlinedButton(
                t("left.value", "value…"), on_click=tap, height=36, data=f"left:{cell['id']}",
                style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=10)))
            return ft.Row([figure, *name] if after else [*name, figure], spacing=0, tight=True,
                          vertical_alignment=ft.CrossAxisAlignment.CENTER)
        mine = bool(cell.get("set"))
        figure = ft.Container(
            ft.Text(unbroken(cell["figure"]), size=text_size,
                    color=ft.Colors.BLACK if mine else None,
                    style=None if mine else ft.TextStyle(
                        decoration=ft.TextDecoration.UNDERLINE,
                        decoration_style=ft.TextDecorationStyle.DOTTED,
                        decoration_color=ft.Colors.PRIMARY)),
            bgcolor=PC["adjusted"] if mine else None, border_radius=4,
            padding=ft.Padding.symmetric(horizontal=6, vertical=2) if mine else None)
        return ft.Container(
            ft.Row([figure, *name] if after else [*name, figure], spacing=0, tight=True,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            on_click=tap, ink=True, border_radius=4, data=f"left:{cell['id']}",
            padding=ft.Padding.symmetric(vertical=8),
            tooltip=left_set_said(cell) if mine else None)

    def left_figure(identity: str | None, cell: dict) -> None:
        now = cell.get("value")
        if now is None:
            start = ""
        elif cell.get("set"):
            start = f"{now:.12g}"
            if "," in (cell.get("figure") or ""):
                start = start.replace(".", ",")
        else:
            start = cell.get("figure") or ""
        field = ft.TextField(label=t("left.value.prompt", "a figure"), value=start,
                             autofocus=True, keyboard_type=ft.KeyboardType.NUMBER)

        def send(value: float | None) -> None:
            try:
                budget.left_value(cell["id"], value, identity)
            except Refused as why:
                page.pop_dialog()
                snack(closed_said(why))
                return
            page.pop_dialog()
            show(state["tab"])

        def ok(e) -> None:
            value = typed_number(field.value)
            if value is None:
                field.error = t("left.value.nan", "Type a number.")
                page.update()
                return
            send(value)

        field.on_submit = ok
        back = ([ft.Row([ft.TextButton(t("left.value.back", "Back to the notes' figure"),
                                       icon=ft.Icons.RESTART_ALT,
                                       on_click=lambda e: send(None))])]
                if cell.get("set") else [])
        page.show_dialog(ft.AlertDialog(
            title=ft.Text(f"{t('left', 'Left')}: {cell.get('label') or cell['id']}"),
            content=ft.Column([field, *back], tight=True, spacing=8),
            actions=[ft.TextButton(t("cancel", "Cancel"), on_click=lambda e: page.pop_dialog()),
                     ft.FilledButton(t("ok", "OK"), on_click=ok)]))


    def compare_months() -> None:
        months = budget.months()
        head = ft.Row([
            ft.IconButton(ft.Icons.CLOSE, tooltip=t("guide.close", "Close"),
                          on_click=lambda e: page.pop_dialog()),
            ft.Text(t("compare.title", "Compare months"), size=22, weight=ft.FontWeight.W_600,
                    expand=True),
        ], spacing=4)
        body = (compare_body(months) if len(months) >= 2 else
                [muted(t("compare.need_two", "Two months are needed to compare."), 15)])
        page.show_dialog(ft.BottomSheet(
            ft.Container(ft.Column([head, ft.Column(body, spacing=8, scroll=ft.ScrollMode.AUTO,
                                                    expand=True)], spacing=8, expand=True),
                         padding=ft.Padding.only(left=16, right=16, top=8, bottom=16), expand=True),
            fullscreen=True))

    def compare_body(months: list[dict]) -> list[ft.Control]:
        ids = [m["identity"] for m in months]
        ticked = {i for i in state["compare"] if i in ids} or set(newest_real(months))
        boxes: dict[str, ft.Checkbox] = {}
        average = ft.Switch(label=t("compare.average", "Average"), value=state["average"])
        result = ft.Column(spacing=12)

        def draw() -> None:
            chosen = [i for i in ids if i in boxes and boxes[i].value]
            state["compare"], state["average"] = chosen, bool(average.value)
            result.controls = comparison(chosen, state["average"], months)

        def changed(e) -> None:
            draw()
            page.update()

        average.on_change = changed
        years: list[ft.Control] = []
        for at, (year, held) in enumerate(by_year(months).items()):
            named = {m["month"]: m for m in held}
            cells: list[ft.Control] = []
            for name in CALENDAR:
                m = named.get(name)
                box = ft.Checkbox(label=words.month_short(name), expand=True,
                                  value=bool(m) and m["identity"] in ticked,
                                  disabled=m is None, on_change=changed if m else None)
                if m:
                    boxes[m["identity"]] = box
                cells.append(box)
            grid = [ft.Row(cells[i:i + 3], spacing=0) for i in range(0, 12, 3)
                    if any(name in named for name in CALENDAR[i:i + 3])]
            years.append(ft.ExpansionTile(
                title=ft.Text(str(year) if year else t("picker.earlier", "Earlier"), size=18,
                              weight=ft.FontWeight.W_600),
                expanded=at == 0 or any(m["identity"] in ticked for m in held),
                controls=[ft.Container(ft.Column(grid, spacing=0),
                                       padding=ft.Padding.only(left=4, right=4, bottom=8))]))
        draw()
        return [muted(t("compare.tick", "Tick the months to compare."), 14), *years,
                average,
                muted(t("compare.average.help", "The average of exactly the months ticked - "
                                                "untick a month still being written."), 13),
                ft.Divider(),
                result]

    def comparison(chosen: list[str], average: bool, months: list[dict]) -> list[ft.Control]:
        if len(chosen) < (1 if average else 2):
            return [muted(t("compare.tick_one", "Tick at least one.") if average
                          else t("compare.tick_two", "Tick at least two."), 15)]
        try:
            said = budget.compare(chosen, average)
        except Refused as why:
            return [ft.Text(str(why), size=15, color=ft.Colors.ERROR)]
        table = said["table"]
        if table is None:
            return [ft.Row([ft.Text(said["text"], size=size("minors") - 2, font_family="monospace",
                                    no_wrap=True, selectable=True)], scroll=ft.ScrollMode.AUTO)]
        named = {m["identity"]: m for m in months}
        heads = [(words.month_short(named[i]["month"]), str(named[i].get("year") or ""))
                 for i in chosen]
        return [comparison_table(table, heads),
                *([average_card(table["average"])] if table["average"] else [])]

    def comparison_table(table: dict, heads: list[tuple[str, str]]) -> ft.Control:
        names_size, figures_size, heads_size = size("names"), size("figures"), size("limits") + 1
        totals = table["totals"]
        if len(totals) == 2:
            totals = [dict(totals[0], name=t("totals.total", "Total")),
                      dict(totals[1], name=t("totals.grand", "With occasional"))]
        rows = [(row, False) for row in table["groups"]] + [(row, True) for row in totals]
        change = table["delta"]

        room = (getattr(page, "width", None) or 400) - 32
        widths = [max([drawn(short, heads_size, True), drawn(year, heads_size)]
                      + [drawn(grouped(row["cells"][i]), figures_size, bold) for row, bold in rows])
                  + 16 for i, (short, year) in enumerate(heads)]
        if change:
            widths.append(max([drawn(change, heads_size)]
                              + [drawn(row["delta"] or "", figures_size - 2) for row, _ in rows])
                          + 16)
        names_w = min(max(drawn(row["name"], names_size, bold) for row, bold in rows) + 16,
                      max(room * 0.45, room - sum(widths)))
        spare = room - names_w - sum(widths)
        if spare > 0:
            widths = [w + spare / len(widths) for w in widths]

        def line(text_size: float) -> float:
            return text_size * 1.3

        shade = ft.Colors.SURFACE_CONTAINER_HIGHEST
        rule = ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)

        def cell(content, width: float, height: float, left: bool = False, bg=None,
                 border=None) -> ft.Control:
            return ft.Container(
                content, width=width, height=height, bgcolor=bg, border=border,
                alignment=ft.Alignment.CENTER_LEFT if left else ft.Alignment.CENTER_RIGHT,
                padding=ft.Padding.symmetric(horizontal=8))

        head_h, under = 2 * line(heads_size) + 12, ft.Border.only(bottom=rule)
        names = [cell(None, names_w, head_h, left=True, border=under)]
        heading = [cell(ft.Column([ft.Text(short, size=heads_size, weight=ft.FontWeight.W_600),
                                   muted(year, heads_size - 1)], spacing=0, tight=True,
                                  horizontal_alignment=ft.CrossAxisAlignment.END),
                        width, head_h, border=under)
                   for (short, year), width in zip(heads, widths)]
        if change:
            heading.append(cell(muted(change, heads_size), widths[-1], head_h, border=under))
        across = [ft.Row(heading, spacing=0)]
        for at, (row, bold) in enumerate(rows):
            wrapped = drawn(row["name"], names_size, bold) > names_w - 16
            high = max(line(names_size) * (2 if wrapped else 1), line(figures_size)) + 12
            bg = shade if at % 2 and not bold else None
            border = ft.Border.only(top=rule) if at == len(table["groups"]) else None
            weight = ft.FontWeight.W_700 if bold else ft.FontWeight.W_500
            names.append(cell(ft.Text(row["name"], size=names_size, weight=weight,
                                      max_lines=2 if wrapped else 1,
                                      overflow=ft.TextOverflow.ELLIPSIS),
                              names_w, high, left=True, bg=bg, border=border))
            figures = [cell(ft.Text(grouped(value), size=figures_size, weight=weight, no_wrap=True,
                                    color=ft.Colors.ON_SURFACE_VARIANT if value == "-" else None),
                            width, high, bg=bg, border=border)
                       for value, width in zip(row["cells"], widths)]
            if change:
                figures.append(cell(muted(grouped(row["delta"]) if row["delta"] else "",
                                          figures_size - 2, no_wrap=True),
                                    widths[-1], high, bg=bg, border=border))
            across.append(ft.Row(figures, spacing=0))
        return ft.Row([ft.Column(names, spacing=0, width=names_w),
                       ft.Row([ft.Column(across, spacing=0)], spacing=0, expand=True,
                              scroll=ft.ScrollMode.AUTO)],
                      spacing=0, vertical_alignment=ft.CrossAxisAlignment.START)

    def average_card(average: dict) -> ft.Control:
        rows = average["rows"]
        names = ([t("totals.total", "Total"), t("totals.grand", "With occasional")]
                 if len(rows) == 2 else [row["name"] for row in rows])
        return card([
            ft.Text(average["title"], size=16, weight=ft.FontWeight.W_600),
            ft.Row([ft.Column([muted(name, 14),
                               ft.Text(grouped(row["cells"][0]), size=size("totals"),
                                       weight=ft.FontWeight.W_700)], spacing=0, expand=True)
                    for name, row in zip(names, rows)]),
        ], spacing=8)

    def share_month(m: dict) -> None:
        offer(t("share.title", "Share this month"),
              t("share.text", "{month} as a text file for print, on two A4 pages: the major "
                              "groups and the totals, then the minor groups and the Left line. "
                              "Answered figures are underlined.", month=label(m)),
              lambda: budget.export(m["identity"], m.get("year")))


    def setup_door(editors: tuple[str, ...]) -> ft.Control:
        return ft.TextButton(t("setup.edit", "Edit"), icon=ft.Icons.EDIT_OUTLINED, height=48,
                             on_click=lambda e: which_months(editors))

    def headed(title: str, door: ft.Control | None) -> ft.Control:
        if door is None:
            return section(title)
        return ft.Row([ft.Container(section(title), expand=True), door],
                      vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def editor_title(kind: str) -> str:
        return {"limits": t("limits.title", "Limits"),
                "majors": t("majors.title", "Major groups"),
                "minors": t("minors.title", "Minor groups"),
                "words": t("words.title", "Words you teach"),
                "left": t("left.title", "The Left line")}[kind]

    def editor_door(kind: str) -> str:
        return {"limits": t("editor.limits", "Edit limits…"),
                "majors": t("editor.majors", "Edit major groups…"),
                "minors": t("editor.minors", "Edit minor groups…"),
                "left": t("editor.left", "Edit the Left line…"),
                "words": t("editor.words", "Edit the words you teach…")}[kind]

    def month_of(identity: str | None) -> str:
        return next((label(m) for m in budget.months() if m["identity"] == identity), "")

    def under_the_setup() -> None:
        if state["tab"] != ADD:
            show(state["tab"])

    def which_months(editors: tuple[str, ...]) -> None:
        months = budget.months()
        ids = [m["identity"] for m in months]
        shown = state["month"] if state["month"] in ids else (ids[-1] if ids else None)

        def go(kind: str):
            def handler(e) -> None:
                page.pop_dialog()
                open_editor(kind)
            return handler

        def doors(asked: bool) -> list[ft.Control]:
            out: list[ft.Control] = []
            for kind in editors:
                out.append(ft.Row([ft.FilledTonalButton(editor_door(kind), expand=True,
                                                        style=tall(), on_click=go(kind))]))
                if asked and kind == "limits":
                    out.append(muted(t("scope.limits", "A limit is set for every month at once."),
                                     13))
            return out

        cancel = ft.TextButton(t("cancel", "Cancel"), on_click=lambda e: page.pop_dialog())
        if shown is None:
            state["scope"], state["staged"] = None, []
        if shown is None or all(kind == "limits" for kind in editors):
            if len(editors) == 1:
                open_editor(editors[0])
                return
            page.show_dialog(ft.AlertDialog(
                scrollable=True, content=ft.Column(doors(False), tight=True, spacing=8),
                actions=[cancel]))
            return

        named = next((label(m) for m in months if m["identity"] == shown), "")
        said = muted("", 14, visible=False)

        def dropped(n: int) -> None:
            if n:
                said.value = t("scope.dropped", "{n} unapplied change(s) discarded.", n=n)
                said.visible = True

        if state["scope"] is None or state["scope"]["month"] != shown:
            dropped(len(state["staged"]))
            state["scope"], state["staged"] = {"mode": "onward", "month": shown}, []

        def choose(mode: str) -> None:
            if mode == state["scope"]["mode"]:
                return
            n = len(state["staged"])
            state["scope"], state["staged"] = {"mode": mode, "month": shown}, []
            group.value, said.visible = mode, False
            dropped(n)
            page.update()

        choices = [("onward", t("scope.further", "{period} and all further months",
                                period=named)),
                   ("always", t("scope.every", "Every month, the earlier ones too"))]
        group = ft.RadioGroup(
            ft.Column([ft.ListTile(leading=ft.Radio(value=mode), title=ft.Text(text, size=16),
                                   content_padding=0, on_click=lambda e, mode=mode: choose(mode))
                       for mode, text in choices], spacing=0),
            value=state["scope"]["mode"], on_change=lambda e: choose(e.control.value))
        warned = ft.Container(muted(t("scope.every_warn",
                                      "Earlier months are counted again under the new groups: "
                                      "their totals change, and the lines of a removed group "
                                      "become questions there."), 13),
                              padding=ft.Padding.only(left=40))

        page.show_dialog(ft.AlertDialog(
            title=ft.Text(t("scope.ask", "Which months should the changes apply to?"), size=20),
            scrollable=True,
            content=ft.Column([group, warned, said, ft.Divider(height=1), *doors(True)],
                              tight=True, spacing=8),
            actions=[cancel]))

    def scope_said(mode: str, named: str) -> str:
        if mode == "onward":
            return t("scope.line.onward",
                     "Changes apply to {period} and every later month, once applied.",
                     period=named)
        return t("scope.line.always", "Changes apply to every month.")

    def described(op: dict, setup: dict) -> str:
        majors = setup.get("majors", [])
        major_shown = {m["name"]: m["label"] for m in majors}
        minor_shown = {n["name"]: n["label"] for m in majors for n in m.get("minors", [])}
        slots_now = {s["id"]: s for s in (setup.get("left") or {}).get("slots", [])}
        slot_shown = {key: s.get("label") or key for key, s in slots_now.items()}

        def major(key: str) -> str:
            return major_shown.get(op.get(key), op.get(key))

        def minor(key: str) -> str:
            return minor_shown.get(op.get(key), op.get(key))

        def slot() -> str:
            return slot_shown.get(op.get("slot"), op.get("slot"))

        what = op.get("op")
        if what == "add_major":
            return t("op.add_major", "add the group {name}{limit}", name=op["name"],
                     limit=t("op.limit", ", limit {n}", n=op["limit"]) if op.get("limit") else "")
        if what == "remove_major":
            return t("op.remove_major", "remove the group {major}", major=major("major"))
        if what == "rename_major":
            return t("op.rename", "rename {old} to {new}", old=major("major"), new=op["name"])
        if what == "rename_minor":
            return t("op.rename", "rename {old} to {new}", old=minor("minor"), new=op["name"])
        if what == "reroute_minor":
            return t("op.reroute", "count {minor} under {major}", minor=minor("minor"),
                     major=major("major"))
        if what == "add_minor":
            return t("op.add_minor", "add {name} under {major}", name=op["name"],
                     major=major("major"))
        if what == "remove_minor":
            return t("op.remove_minor", "remove {minor}", minor=minor("minor"))
        if what == "set_limit" and op.get("value") is None:
            return t("op.drop_limit", "remove the limit on {major}", major=major("major"))
        if what == "set_limit":
            return t("op.set_limit", "limit {major} to {value}", major=major("major"),
                     value=op["value"])
        if what == "rename_limit":
            return t("op.rename_limit", "call {major}'s limit \"{label}\"", major=major("major"),
                     label=op["label"])
        if what == "move_limit":
            return t("op.move_limit", "move {major}'s limit to {to}", major=major("major"),
                     to=major("to"))
        if what == "learn_word":
            return t("op.learn_word", "teach {word} → {group}", word=op["word"],
                     group=minor("group"))
        if what == "forget_word":
            return t("op.forget_word", "forget {word}", word=op["word"])
        if what == "left_rename_slot":
            was = slots_now.get(op.get("slot"), {})
            if (op.get("label") == was.get("label") and op.get("place")
                    and op.get("place") != was.get("place")):
                if op["place"] == "after":
                    return t("op.left_after", "{slot}: its name after the figure", slot=slot())
                return t("op.left_before", "{slot}: its name before the figure", slot=slot())
            return t("op.left_rename", "call {slot} \"{label}\"", slot=slot(),
                     label=op.get("label", ""))
        if what == "left_set_kind":
            return t("op.left_kind", "{slot} counted as {kind}", slot=slot(),
                     kind=kind_word(op.get("kind", "")))
        if what == "left_add_slot":
            return t("op.left_add", "add {label} to the Left line", label=op.get("label", ""))
        if what == "left_remove_slot":
            return t("op.left_remove", "remove {slot} from the Left line", slot=slot())
        if what == "left_reorder":
            return t("op.left_reorder", "the Left line in a new order")
        if what == "left_reset":
            return t("op.left_reset", "the original Left line back")
        return str(what).replace("_", " ")

    def open_editor(kind: str) -> None:
        scope = state["scope"] or {"mode": "always", "month": None}
        mode = "always" if kind == "limits" else scope["mode"]
        month = scope["month"] if mode != "always" else None
        named = month_of(scope["month"])
        body = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)
        foot = ft.Column(spacing=6)
        ed = SimpleNamespace(kind=kind, cfg={}, draws=0)

        def draw(cfg: dict | None = None) -> None:
            try:
                ed.cfg = cfg if cfg is not None else budget.setup(month)
                rows = EDITORS[kind](ed)
            except Refused as why:
                rows = [ft.Text(str(why), size=15, color=ft.Colors.ERROR)]
            ed.draws += 1
            body.controls = [*(waiting() if month else []), *rows]
            foot.controls = pinned() if month else []
            page.update()

        def send(ops: list[dict]) -> Refused | None:
            if month:
                state["staged"] += [dict(op) for op in ops]
                draw()
                return None
            cfg = None
            for op in ops:
                try:
                    cfg = budget.configure(op)
                except Refused as why:
                    if cfg is not None:
                        draw(cfg)
                        under_the_setup()
                    return why
            draw(cfg)
            under_the_setup()
            return None

        def now(ops: list[dict], said: ft.Text | None = None) -> bool:
            drawn = ed.draws
            why = send(ops)
            if why is None:
                return True
            if said is not None and ed.draws == drawn:
                said.value, said.visible = str(why), True
                page.update()
            else:
                tell(str(why))
            return False

        def ask(title: str, what: str, ops_of, value: str = "", number: bool = False) -> None:
            box = ft.TextField(label=what, value=value, autofocus=True,
                               keyboard_type=ft.KeyboardType.NUMBER if number
                               else ft.KeyboardType.TEXT)
            said = ft.Text("", size=14, color=ft.Colors.ERROR, visible=False)

            def ok(e) -> None:
                typed = (box.value or "").strip()
                if not typed:
                    return
                ops = ops_of(typed)
                if isinstance(ops, str):
                    said.value, said.visible = ops, True
                    page.update()
                    return
                why = send(ops)
                if why is None:
                    page.pop_dialog()
                else:
                    said.value, said.visible = str(why), True
                    page.update()

            box.on_submit = ok
            page.show_dialog(ft.AlertDialog(
                title=ft.Text(title), content=ft.Column([box, said], tight=True, spacing=8),
                actions=[ft.TextButton(t("cancel", "Cancel"), on_click=lambda e: page.pop_dialog()),
                         ft.FilledButton(t("ok", "OK"), on_click=ok)]))

        def pick(title: str, options: list[tuple[str, str]], ops_of) -> None:
            def chosen(value: str):
                def handler(e) -> None:
                    page.pop_dialog()
                    now(ops_of(value))
                return handler

            page.show_dialog(ft.AlertDialog(
                title=ft.Text(title), scrollable=True,
                content=ft.Column([ft.TextButton(text, on_click=chosen(value),
                                                 style=ft.ButtonStyle(
                                                     alignment=ft.Alignment.CENTER_LEFT))
                                   for value, text in options], tight=True, spacing=2,
                                  horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                actions=[ft.TextButton(t("cancel", "Cancel"), on_click=lambda e: page.pop_dialog())]))

        def waiting() -> list[ft.Control]:
            if not state["staged"]:
                return [muted(t("staged.none", "Nothing staged yet - your changes will be "
                                               "listed here."), 14)]
            return [card([ft.Text(f"{at}. {described(op, ed.cfg)}", size=15)
                          for at, op in enumerate(state["staged"], 1)], 6)]

        def pinned() -> list[ft.Control]:
            n = len(state["staged"])
            if not n:
                return []
            return [ft.Divider(height=1),
                    muted(t("staged.count", "{n} change(s) staged.", n=n), 14),
                    ft.Row([ft.OutlinedButton(t("staged.discard", "Discard"), height=48,
                                              expand=True, on_click=discard),
                            ft.FilledButton(t("apply", "Apply"), height=48, expand=True,
                                            on_click=apply)], spacing=12)]

        def discard(e) -> None:
            state["staged"] = []
            draw()

        def apply(e) -> None:
            ops = [dict(op) for op in state["staged"]]
            try:
                said = budget.configure_months(month, mode, ops)
            except Refused as why:
                tell(str(why))
                return

            def yes(e) -> None:
                page.pop_dialog()
                try:
                    cfg = budget.configure_months(month, mode, ops, confirm=True)
                except Refused as why:
                    tell(str(why))
                    return
                state["staged"] = []
                draw(cfg)
                under_the_setup()

            page.show_dialog(ft.AlertDialog(
                scrollable=True,
                content=ft.Column([
                    ft.Text(t("staged.confirm", "{n} change(s) to {months}.", n=len(ops),
                              months=", ".join(said["months"])), size=16,
                            weight=ft.FontWeight.W_600),
                    *[muted(f"{at}. {described(op, ed.cfg)}", 14)
                      for at, op in enumerate(ops, 1)]], tight=True, spacing=6),
                actions=[ft.TextButton(t("staged.no", "No, keep staging"),
                                       on_click=lambda e: page.pop_dialog()),
                         ft.FilledButton(t("staged.yes", "Yes, apply"), on_click=yes)]))

        ed.now, ed.ask, ed.pick = now, ask, pick
        head = ft.Row([ft.IconButton(ft.Icons.CLOSE, tooltip=t("guide.close", "Close"),
                                     on_click=lambda e: page.pop_dialog()),
                       ft.Text(editor_title(kind), size=22, weight=ft.FontWeight.W_600,
                               expand=True)], spacing=4)
        draw()
        page.show_dialog(ft.BottomSheet(
            ft.Container(ft.Column([head, muted(scope_said(mode, named), 14), body, foot],
                                   spacing=8, expand=True),
                         padding=ft.Padding.only(left=16, right=16, top=8, bottom=16), expand=True),
            fullscreen=True))


    def entry(name: str, detail: str, buttons: list[ft.Control], tag: str) -> ft.Control:
        return ft.Container(ft.Column([
            ft.Text(name, size=17, weight=ft.FontWeight.W_600),
            *([muted(detail, 14)] if detail else []),
            ft.Row(buttons, wrap=True, spacing=4, run_spacing=0),
        ], spacing=2), data=tag, padding=ft.Padding.symmetric(vertical=4))

    def small(text: str, on_click, disabled: bool = False) -> ft.Control:
        return ft.TextButton(text, height=48, on_click=on_click, disabled=disabled)

    def rows_of(entries: list[ft.Control]) -> list[ft.Control]:
        out: list[ft.Control] = []
        for at, one in enumerate(entries):
            out += [ft.Divider(height=1)] if at else []
            out.append(one)
        return out

    def form(title: str, help_text: str | None, fields: list[ft.Control], button: str,
             go) -> list[ft.Control]:
        said = ft.Text("", size=14, color=ft.Colors.ERROR, visible=False)

        def pressed(e) -> None:
            said.visible = False
            go(said)

        return [ft.Container(height=8), section(title),
                *([muted(help_text, 14)] if help_text else []), *fields,
                ft.Row([ft.FilledButton(button, icon=ft.Icons.ADD, height=48, on_click=pressed)]),
                said]

    def wrong(said: ft.Text, text: str) -> None:
        said.value, said.visible = text, True
        page.update()

    def thousands(typed: str) -> int | None:
        typed = typed.strip()
        return int(typed) if typed.isdecimal() and int(typed) > 0 else None

    def limits_rows(ed) -> list[ft.Control]:
        majors = [m for m in ed.cfg["majors"] if m["tier"] != "EXCLUDED"]
        named = {m["name"]: m for m in majors}
        limited = [named[n] for n in ed.cfg.get("limit_order", []) if n in named]
        free = [m for m in majors if m["limit"] is None]

        def value(m: dict):
            return lambda e: ed.ask(
                m["limit_label"] or m["label"], t("limits.thousands", "thousands"),
                lambda typed: ([{"op": "set_limit", "major": m["name"], "value": thousands(typed)}]
                               if thousands(typed) else
                               t("limits.positive", "A positive number of thousands.")),
                number=True)

        def rename(m: dict):
            return lambda e: ed.ask(
                m["limit_label"] or m["label"], t("limits.shown_name", "shown name"),
                lambda typed: [{"op": "rename_limit", "major": m["name"], "label": typed}])

        def watch(m: dict):
            def handler(e) -> None:
                if not free:
                    tell(t("limits.all_have", "Every group already carries a limit."))
                    return
                ed.pick(m["limit_label"] or m["label"], [(g["name"], g["label"]) for g in free],
                        lambda to: [{"op": "move_limit", "major": m["name"], "to": to}])
            return handler

        rows = [muted(t("limits.help", "Each row watches one major group. Remove frees the "
                                       "group; Watch points the row at another."), 14),
                *rows_of([entry(m["limit_label"] or m["label"], f"{m['label']} · {m['limit']}", [
                    small(t("limits.value", "Value"), value(m)),
                    small(t("rename", "Rename"), rename(m)),
                    small(t("limits.watch", "Watch…"), watch(m)),
                    small(t("remove", "Remove"), lambda e, m=m: ed.now(
                        [{"op": "set_limit", "major": m["name"], "value": None}])),
                ], m["name"]) for m in limited])]

        target = ft.Dropdown(label=t("questions.group", "Group"), value=CHOOSE_GROUP,
                             options=[ft.DropdownOption(key=CHOOSE_GROUP,
                                                        text=t("limits.choose", "Choose a group…")),
                                      *[ft.DropdownOption(key=g["name"], text=g["label"])
                                        for g in free],
                                      ft.DropdownOption(key=NEW_GROUP,
                                                        text=t("limits.new_group",
                                                               "— a new group —"))])
        fresh = ft.TextField(label=t("limits.new_name", "new group name"), visible=False)
        amount = ft.TextField(label=t("limits.thousands", "thousands"),
                              keyboard_type=ft.KeyboardType.NUMBER)
        shown = ft.TextField(label=t("limits.shown_as", "shown as (optional)"),
                             helper=t("limits.shown_as.help",
                                      "the boxed name, when it differs from the group's"))

        def chosen(e) -> None:
            fresh.visible = target.value == NEW_GROUP or bool((fresh.value or "").strip())
            page.update()

        target.on_select = chosen

        def meant(typed: str) -> dict | None:
            key = typed.lower()
            return next((m for m in ed.cfg["majors"]
                         if key in (m["name"].lower(), m["label"].lower())), None)

        def add(said: ft.Text) -> None:
            n = thousands(amount.value or "")
            choice, new = target.value or CHOOSE_GROUP, (fresh.value or "").strip()
            boxed = (shown.value or "").strip()
            group = named.get(choice) if choice not in (CHOOSE_GROUP, NEW_GROUP) else None
            if not n:
                return wrong(said, t("limits.positive", "A positive number of thousands."))
            if group is None and not new:
                return wrong(said, t("limits.pick", "Pick a group, or name a new one."))
            if group is not None and new and meant(new) is not group:
                return wrong(said, t("limits.keep_one",
                                     "You chose {group} and typed {name} - keep one.",
                                     group=group["label"], name=new))
            if group is None:
                group = meant(new)
                if group is not None and group["limit"] is not None:
                    return wrong(said, t("limits.has_one", "{name} already has a limit - change "
                                                           "it with Value on its row.",
                                         name=group["label"]))
            ops = ([{"op": "set_limit", "major": group["name"], "value": n}] if group else
                   [{"op": "add_major", "name": new, "tier": "NECESSARY", "limit": n}])
            if boxed:
                ops.append({"op": "rename_limit", "major": group["name"] if group else new,
                            "label": boxed})
            ed.now(ops, said)

        return rows + form(t("limits.add", "Add a limit"),
                           t("limits.add.help", "Choose a group that has none yet, or type a "
                                                "name: a group's own name means that group, and "
                                                "a new name makes a new group carrying the "
                                                "limit."),
                           [target, fresh, amount, shown], t("add", "Add"), add)

    def tier_word(tier: str) -> str:
        return {"NECESSARY": t("tier.necessary", "necessary"),
                "FREQUENT": t("tier.frequent", "frequent"),
                "OCCASIONAL": t("tier.occasional", "occasional")}.get(tier, tier.lower())

    def majors_rows(ed) -> list[ft.Control]:
        majors = [m for m in ed.cfg["majors"] if m["tier"] != "EXCLUDED"]
        kept = last_for_spending(ed.cfg["majors"])

        def detail(m: dict) -> str:
            n = len(m["minors"])
            return (tier_word(m["tier"])
                    + (t("majors.limit", " · limit {n}", n=m["limit"]) if m["limit"] else "")
                    + (t("majors.minors", " · {n} minor{s}", n=n, s="" if n == 1 else "s")
                       if n else ""))

        def rename(m: dict):
            return lambda e: ed.ask(m["label"], t("groups.new_name", "new name"), lambda typed: [
                {"op": "rename_major", "major": m["name"], "name": typed}])

        def remove(m: dict):
            return lambda e: ed.now([{"op": "remove_major", "major": m["name"]}])

        rows = [muted(t("majors.help", "A major is a heading: one bar on the chart, one figure "
                                       "in a Total, and at most one limit. Remove takes it away "
                                       "with its minor groups, and the lines they held go to "
                                       "Questions, to be placed again. One group spending can "
                                       "go to always stays."), 14),
                *rows_of([entry(m["label"], detail(m), [
                    small(t("rename", "Rename"), rename(m)),
                    *([] if m["name"] == kept else [small(t("remove", "Remove"), remove(m))]),
                ], m["name"]) for m in majors])]

        name = ft.TextField(label=t("groups.name", "name"))
        tier = ft.Dropdown(label=t("majors.tier", "Tier"), value="NECESSARY",
                           options=[ft.DropdownOption(key=k, text=tier_word(k))
                                    for k in ("NECESSARY", "FREQUENT", "OCCASIONAL")])
        limit = ft.TextField(label=t("majors.limit_optional", "limit (optional)"),
                             keyboard_type=ft.KeyboardType.NUMBER)

        def add(said: ft.Text) -> None:
            new, typed = (name.value or "").strip(), (limit.value or "").strip()
            if not new:
                return wrong(said, t("groups.no_name", "Give the group a name."))
            if typed and not thousands(typed):
                return wrong(said, t("groups.bad_limit",
                                     "A limit is a positive number of thousands, or blank."))
            op = {"op": "add_major", "name": new, "tier": tier.value or "NECESSARY"}
            if typed:
                op["limit"] = thousands(typed)
            ed.now([op], said)

        return rows + form(t("majors.add", "Add a major group"),
                           t("majors.add.help", "The tier decides which Total it reaches. A limit "
                                                "is optional and can be set later."),
                           [name, tier, limit], t("add", "Add"), add)

    def minors_rows(ed) -> list[ft.Control]:
        majors = [m for m in ed.cfg["majors"] if m["tier"] != "EXCLUDED"]
        pairs = [(n, m) for m in majors for n in m["minors"]]
        aside = [(n, m) for m in ed.cfg["majors"] if m["tier"] == "EXCLUDED"
                 for n in m["minors"]]

        def rename(n: dict):
            return lambda e: ed.ask(n["label"], t("groups.new_name", "new name"), lambda typed: [
                {"op": "rename_minor", "minor": n["name"], "name": typed}])

        def route(n: dict):
            return lambda e: ed.pick(n["label"], [(m["name"], m["label"]) for m in majors],
                                     lambda to: [{"op": "reroute_minor", "minor": n["name"],
                                                  "major": to}])

        def remove(n: dict):
            ops = [{"op": "remove_minor", "minor": n["name"]}]
            if n.get("role") != "salary":
                return lambda e: ed.now(ops)

            def sure(e) -> None:
                def yes(e) -> None:
                    page.pop_dialog()
                    ed.now(ops)

                page.show_dialog(ft.AlertDialog(
                    title=ft.Text(n["label"]),
                    content=ft.Text(t("minors.salary.sure",
                                      "{name} holds your salary: without it, the salary line "
                                      "goes to Questions, and it is counted wherever you "
                                      "answer it. Remove it?", name=n["label"]), size=16),
                    actions=[ft.TextButton(t("cancel", "Cancel"),
                                           on_click=lambda e: page.pop_dialog()),
                             ft.FilledButton(t("minors.salary.yes", "Yes, remove it"),
                                             on_click=yes)]))
            return sure

        rows = [muted(t("minors.help", "Every minor lives under one major, and several may "
                                       "share the same one - that is how three lines add up to "
                                       "a single figure. Route moves one somewhere else. Remove "
                                       "takes one away: the lines it held go to Questions, to be "
                                       "placed again."), 14)]
        rows += (rows_of([entry(n["label"], t("minors.under", "under {name}", name=m["label"]), [
                    small(t("rename", "Rename"), rename(n)),
                    small(t("minors.route", "Route to…"), route(n)),
                    small(t("remove", "Remove"), remove(n)),
                ], n["name"]) for n, m in pairs]) if pairs
                 else [muted(t("minors.none", "No minor groups yet."), 14)])
        if aside:
            rows += [ft.Divider(height=1),
                     muted(t("minors.aside", "Counted in no Total - they can be renamed or "
                                             "removed, not routed."), 14)]
            rows += rows_of([entry(n["label"], t("minors.under", "under {name}", name=m["label"]), [
                small(t("rename", "Rename"), rename(n)),
                small(t("remove", "Remove"), remove(n)),
            ], n["name"]) for n, m in aside])

        name = ft.TextField(label=t("groups.name", "name"))
        under = ft.Dropdown(label=t("minors.which_major", "under which major…"),
                            options=[ft.DropdownOption(key=m["name"], text=m["label"])
                                     for m in majors])

        def add(said: ft.Text) -> None:
            new = (name.value or "").strip()
            if not new:
                return wrong(said, t("groups.no_name", "Give the group a name."))
            if not under.value:
                return wrong(said, t("groups.no_major", "Choose the major it belongs under."))
            ed.now([{"op": "add_minor", "name": new, "major": under.value}], said)

        return rows + form(t("minors.add", "Add a minor group"), None, [name, under],
                           t("add", "Add"), add)

    def words_rows(ed) -> list[ft.Control]:
        taught = ed.cfg.get("words") or []
        groups = [(n["name"], n["label"] if n["label"] == m["label"] else f"{m['label']} · {n['label']}")
                  for m in ed.cfg["majors"] for n in m["minors"]]
        rows = [muted(t("words.help", "A line carrying one of these books to its group without "
                                      "being asked about. What you answer or move yourself "
                                      "still wins, and where two words fit one line the longer "
                                      "one decides it."), 14)]
        rows += (rows_of([entry(w["word"], "→ " + w["label"], [
                    small(t("words.forget", "Forget"), lambda e, w=w: ed.now(
                        [{"op": "forget_word", "word": w["word"]}])),
                ], w["word"]) for w in taught]) if taught
                 else [muted(t("words.none", "Nothing taught yet."), 14)])

        word = ft.TextField(label=t("words.placeholder", "a word, or two"))
        group = ft.Dropdown(label=t("questions.group", "Group"),
                            value=groups[0][0] if groups else None,
                            options=[ft.DropdownOption(key=key, text=text) for key, text in groups])

        def teach(said: ft.Text) -> None:
            typed = (word.value or "").strip()
            if sum(ch.isalnum() for ch in typed) < 3:
                return wrong(said, t("words.too_short", "A word of three letters or more."))
            ed.now([{"op": "learn_word", "word": typed, "group": group.value}], said)

        return rows + form(t("words.teach_one", "Teach one"), None, [word, group],
                           t("words.teach", "Teach"), teach)

    def kind_word(kind: str) -> str:
        return {"card": t("kind.card", "card balance"),
                "cash": t("kind.cash", "cash in hand"),
                "purse": t("kind.purse", "weekly purse"),
                "carry": t("kind.carry", "carried over")}.get(kind, kind)

    def left_rows(ed) -> list[ft.Control]:
        left = ed.cfg.get("left") or {}
        slots = left.get("slots") or []
        kinds = left.get("kinds") or ["card", "cash", "purse", "carry"]
        order = [s["id"] for s in slots]

        def swapped(at: int, to: int) -> list[str]:
            moved = list(order)
            moved[at], moved[to] = moved[to], moved[at]
            return moved

        def one(at: int, s: dict) -> ft.Control:
            name = s.get("label") or s["id"]
            after = s.get("place") == "after"
            side = t("left.name_after", "name after") if after else t("left.name_before",
                                                                      "name before")
            return entry(name, f"{kind_word(s['kind'])} · {side}", [
                small(t("left.rename", "Name"), lambda e: ed.ask(
                    name, t("left.name", "name"), lambda typed: [
                        {"op": "left_rename_slot", "slot": s["id"], "label": typed,
                         "place": s.get("place"), "join": s.get("join")}],
                    value=s.get("label") or "")),
                small(t("left.to_before", "→ before") if after else t("left.to_after", "→ after"),
                      lambda e: ed.now([{"op": "left_rename_slot", "slot": s["id"],
                                         "label": s.get("label", ""),
                                         "place": "before" if after else "after",
                                         "join": " " if after else ""}])),
                small(t("left.kind", "Kind…"), lambda e: ed.pick(
                    name, [(k, kind_word(k)) for k in kinds],
                    lambda k: [{"op": "left_set_kind", "slot": s["id"], "kind": k}])),
                small("↑", lambda e: ed.now([{"op": "left_reorder", "order": swapped(at, at - 1)}]),
                      disabled=at == 0),
                small("↓", lambda e: ed.now([{"op": "left_reorder", "order": swapped(at, at + 1)}]),
                      disabled=at == len(slots) - 1),
                small(t("remove", "Remove"), lambda e: ed.now(
                    [{"op": "left_remove_slot", "slot": s["id"]}]), disabled=len(slots) <= 1),
            ], s["id"])

        rows = [muted(t("left.help", "One row per figure, in the order they are written. The "
                                     "name prints before or after its figure; the kind decides "
                                     "how a month still being written is recounted."), 14),
                *rows_of([one(at, s) for at, s in enumerate(slots)])]

        name = ft.TextField(label=t("left.name", "name"))
        kind = ft.Dropdown(label=t("left.kind_of", "Kind"),
                           value="carry" if "carry" in kinds else kinds[0],
                           options=[ft.DropdownOption(key=k, text=kind_word(k)) for k in kinds])

        def add(said: ft.Text) -> None:
            typed = (name.value or "").strip()
            if not typed:
                return wrong(said, t("left.no_name", "Give it a name."))
            ed.now([{"op": "left_add_slot", "label": typed, "kind": kind.value or "carry"}], said)

        return (rows + form(t("left.add", "Add a figure"), None, [name, kind], t("add", "Add"), add)
                + [ft.Row([ft.OutlinedButton(t("left.reset", "Back to the original line"),
                                             icon=ft.Icons.RESTART_ALT, style=tall(),
                                             on_click=lambda e: ed.now([{"op": "left_reset"}]))])])

    EDITORS = {"limits": limits_rows, "majors": majors_rows, "minors": minors_rows,
               "words": words_rows, "left": left_rows}


    def questions_page(months: list[dict]) -> list[ft.Control]:
        if not months:
            return nothing_yet()
        m = current(months)
        out: list[ft.Control] = []
        bar = lock_bar(m["identity"], m["identity"] in budget.closed())
        if bar:
            out.append(bar)
        asked = budget.questions(m["identity"])
        state["asked"] = len(asked)

        def ask_again(e) -> None:
            def yes(e) -> None:
                page.pop_dialog()
                try:
                    done = budget.ask_again(m["identity"])
                except Refused as why:
                    snack(closed_said(why))
                    return
                snack(t("questions.again.done",
                        "{answers} answer(s) forgotten - {questions} question(s) again.",
                        answers=done["wiped"]["answers"], questions=done["questions"]))
                show(QUESTIONS)

            page.show_dialog(ft.AlertDialog(
                title=ft.Text(t("questions.again", "Ask them all again")),
                content=ft.Text(t("questions.again.sure",
                                  "This forgets your answers for this month - the notes stay.")),
                actions=[ft.TextButton(t("questions.again.no", "No, keep them"),
                                       on_click=lambda e: page.pop_dialog()),
                         ft.FilledButton(t("questions.again.yes", "Yes, ask them again"),
                                         on_click=yes)]))

        again = ft.OutlinedButton(t("questions.again", "Ask them all again"),
                                  icon=ft.Icons.REFRESH, on_click=ask_again)
        if not asked:
            out.append(muted(t("questions.none", "Nothing to ask about this month."), 15))
            out.append(again)
            return out
        out.append(again)

        def answer(q: dict, group: str, new: bool) -> None:
            try:
                budget.answer(m["identity"], q["number"], group, new)
                snack(f"{q['raw']} → {group}")
            except Refused as why:
                snack(closed_said(why))
            show(QUESTIONS)

        def other(q: dict):
            def handler(e) -> None:
                field = ft.TextField(label=t("questions.group", "Group"), autofocus=True)

                def ok(e) -> None:
                    page.pop_dialog()
                    if (field.value or "").strip():
                        meant(field.value.strip(), m["identity"],
                              lambda name: answer(q, name, True))

                field.on_submit = ok
                page.show_dialog(ft.AlertDialog(
                    title=ft.Text(q["raw"]), content=field,
                    actions=[ft.TextButton(t("cancel", "Cancel"),
                                           on_click=lambda e: page.pop_dialog()),
                             ft.FilledButton(t("questions.book", "Book it"), on_click=ok)]))
            return handler

        n = len(asked)
        out.append(muted(t("questions.count", "{n} line{s} the rules could not place.",
                           n=n, s="s" if n != 1 else ""), 14))
        for q in asked:
            buttons: list[ft.Control] = [
                ft.OutlinedButton(c, on_click=lambda e, q=q, c=c: answer(q, c, False))
                for c in q.get("candidates") or []]
            buttons.append(ft.TextButton(t("questions.other", "Other…"), on_click=other(q)))
            out.append(ft.Card(ft.Container(ft.Column([
                day_view(q.get("date"), q.get("day"), q["raw"]),
                muted(q.get("review") or "", 14),
                ft.Row(buttons, wrap=True, spacing=8),
            ], spacing=8), padding=16)))
        return out


    def add_page(months: list[dict]) -> list[ft.Control]:
        notes = ft.TextField(
            label=t("add.field", "Your notes"), multiline=True, min_lines=8, max_lines=18,
            hint_text=budget.example_hint(),
        )
        into = ft.Dropdown(
            label=t("add.to", "Add to"), value="",
            options=[ft.DropdownOption(key="", text=t("add.new_month", "A new month"))]
            + [ft.DropdownOption(key=m["identity"], text=label(m)) for m in reversed(months)])

        def stored(outcomes: list[dict], month: str | None = None) -> None:
            said = "; ".join(f"{o.get('said') or o['outcome']} {words.span_label(o['span'])}"
                             for o in outcomes) or t("add.stored", "stored")
            state["month"] = month or budget.months()[-1]["identity"]
            snack(said)
            show(MONTH)

        def add(e) -> None:
            chosen = into.value or None
            try:
                stored(budget.add(notes.value or "", into=chosen), month=chosen)
            except Refused as why:
                snack(closed_said(why) if chosen else str(why))

        def example(e) -> None:
            def take(name: str):
                def handler(e) -> None:
                    page.pop_dialog()
                    try:
                        stored(budget.add_example(name))
                    except Refused as why:
                        snack(str(why))
                return handler

            page.show_dialog(ft.AlertDialog(
                title=ft.Text(t("add.example", "Try an example month")),
                content=ft.Text(t("add.example.text",
                                  "Invented notes from an invented household - nothing "
                                  "real. Start over, in the Options, clears them away.")),
                actions=[ft.TextButton(t("add.example.button", "Example {i}", i=i),
                                       on_click=take(name))
                         for i, name in enumerate(budget.examples(), 1)]
                + [ft.TextButton(t("cancel", "Cancel"), on_click=lambda e: page.pop_dialog())],
            ))

        buttons = [ft.FilledButton(t("add", "Add"), icon=ft.Icons.ADD, style=tall(),
                                   on_click=add)]
        if budget.examples():
            buttons.append(ft.OutlinedButton(t("add.example", "Try an example month"),
                                             style=tall(), on_click=example))
        return [
            muted(t("add.help",
                    "Paste the notes exactly as written: dates, amounts, what each was. "
                    "A month's opening salary line is what tells the app which month it is."),
                  14),
            muted(t("add.to.help",
                    "A few days without that line? Choose their month in Add to."), 14),
            into,
            notes,
            ft.Row(buttons, wrap=True),
        ]


    def guide() -> None:
        parts: list[ft.Control] = []
        for title, text in words.guide(GUIDE_TEXT):
            parts += [ft.Text(title, size=17, weight=ft.FontWeight.W_600),
                      ft.Text(text, size=15)]
        page.show_dialog(ft.AlertDialog(
            title=ft.Text(t("guide", "Guide")), scrollable=True,
            content=ft.Column(parts, tight=True, spacing=6),
            actions=[ft.TextButton(t("guide.close", "Close"),
                                   on_click=lambda e: page.pop_dialog())]))

    def speak() -> None:
        page.locale_configuration = flutter_locale()
        for destination, name in zip(nav.destinations, tab_labels()):
            destination.label = name

    def rules_in_use() -> str:
        if budget.own_rules:
            return t("options.rules.file", "From your configuration file")
        return (t("options.rules.ru", "The app's own starting groups, in Russian")
                if budget.household == "ru" else
                t("options.rules.en", "The app's own starting groups, in English"))

    def options() -> None:
        def theme_chosen(e) -> None:
            picked = list(e.control.selected or [])
            look.theme = picked[0] if picked else "system"
            look.save()
            apply_theme()
            page.update()

        def language_chosen(e) -> None:
            picked = getattr(e.control, "value", None) or getattr(e, "data", None)
            if picked not in words.LANGS:
                return
            words.set_lang(picked)
            look.language = picked
            look.save()
            budget.follow_language(picked)
            speak()
            page.pop_dialog()
            show(state["tab"])
            options()

        language = ft.Dropdown(
            value=look.language, on_select=language_chosen,
            options=[ft.DropdownOption(key=code, text=words.NAMES[code]) for code in words.LANGS])

        theme = ft.SegmentedButton(
            selected=[look.theme], on_change=theme_chosen,
            segments=[ft.Segment(value="system", label=t("theme.system", "Like the phone")),
                      ft.Segment(value="light", label=t("theme.light", "Light"),
                                 icon=ft.Icons.LIGHT_MODE),
                      ft.Segment(value="dark", label=t("theme.dark", "Dark"),
                                 icon=ft.Icons.DARK_MODE)])

        sliders: list[ft.Control] = []
        for kind, (name, _, low, high) in Look.SIZES.items():
            shown = ft.Text(str(look.sizes[kind]), size=15, width=32,
                            text_align=ft.TextAlign.RIGHT)

            def moved(e, shown=shown) -> None:
                shown.value = str(round(e.control.value))
                shown.update()

            def settled(e, kind=kind) -> None:
                look.set_size(kind, e.control.value)
                look.save()
                show(state["tab"])

            sliders.append(ft.Column([
                ft.Row([ft.Text(t("size." + kind, name), size=15, expand=True), shown]),
                ft.Slider(min=low, max=high, divisions=high - low, value=look.sizes[kind],
                          on_change=moved, on_change_end=settled),
            ], spacing=0))

        def normal(e) -> None:
            look.normal_sizes()
            look.save()
            page.pop_dialog()
            show(state["tab"])
            options()

        def from_options(editors: tuple[str, ...]):
            def handler(e) -> None:
                page.pop_dialog()
                which_months(editors)
            return handler

        def start_over(e) -> None:
            def yes(e) -> None:
                page.pop_dialog()
                page.pop_dialog()
                try:
                    budget.start_over()
                    budget.unlocked.clear()
                    state["month"] = None
                    state["scope"], state["staged"] = None, []
                    snack(t("start.done", "Everything is gone. The app is as it was installed."))
                except Refused as why:
                    snack(str(why))
                show(MONTH)

            page.show_dialog(ft.AlertDialog(
                title=ft.Text(t("start.title", "Start over?")),
                content=ft.Text(t("start.text",
                                  "Every month, every answer and every change to the "
                                  "groups is removed from this phone. It cannot be undone."),
                                size=16),
                actions=[ft.TextButton(t("cancel", "Cancel"),
                                       on_click=lambda e: page.pop_dialog()),
                         ft.FilledButton(t("start.yes", "Remove everything"), on_click=yes)]))

        page.show_dialog(ft.BottomSheet(ft.Container(ft.Column([
            ft.Text(t("options", "Options"), size=22, weight=ft.FontWeight.W_600),
            section(t("options.language", "Language")),
            language,
            section(t("options.theme", "Theme")),
            theme,
            section(t("options.sizes", "Text size")),
            muted(t("options.sizes.help",
                    "One line for each kind of text. The page changes when you let go."), 13),
            *sliders,
            ft.Row([ft.TextButton(t("options.normal", "Back to normal sizes"),
                                  icon=ft.Icons.RESTART_ALT, on_click=normal)]),
            ft.Divider(),
            section(t("options.setup", "Groups and words")),
            ft.ListTile(leading=ft.Icon(ft.Icons.CATEGORY_OUTLINED),
                        title=ft.Text(t("options.groups", "Groups and limits")),
                        subtitle=ft.Text(t("options.groups.what", "Limits, major and minor groups")),
                        on_click=from_options(("limits", "majors", "minors"))),
            ft.ListTile(leading=ft.Icon(ft.Icons.NOTES),
                        title=ft.Text(t("left.title", "The Left line")),
                        subtitle=ft.Text(t("options.left.what", "Its figures, their names and kinds")),
                        on_click=from_options(("left",))),
            ft.ListTile(leading=ft.Icon(ft.Icons.SCHOOL_OUTLINED),
                        title=ft.Text(t("words.title", "Words you teach")),
                        subtitle=ft.Text(t("gear.words.text",
                                           "Teach the app a word - a shop's name, say - and lines "
                                           "carrying it book to the group you choose, instead of "
                                           "being asked about every month.")),
                        on_click=from_options(("words",))),
            ft.Divider(),
            section(t("options.data", "Your data")),
            ft.ListTile(leading=ft.Icon(ft.Icons.SAVE_ALT),
                        title=ft.Text(t("options.save", "Save the configuration")),
                        subtitle=ft.Text(t("options.save.where",
                                           "To the phone, Telegram or WhatsApp")),
                        on_click=save_menu),
            ft.ListTile(leading=ft.Icon(ft.Icons.RESTORE),
                        title=ft.Text(t("options.restore", "Restore from a file")),
                        subtitle=ft.Text(t("options.restore.where",
                                           "Saved here, on the PC or in the cloud")),
                        on_click=restore_from_file),
            ft.ListTile(leading=ft.Icon(ft.Icons.DELETE_FOREVER),
                        title=ft.Text(t("options.start", "Start over")),
                        subtitle=ft.Text(t("options.start.what",
                                           "Remove every month, answer and change")),
                        on_click=start_over),
            ft.Divider(),
            section(t("options.about", "Rules and folder")),
            card([ft.Column([muted(t("options.rules", "Rules in use"), 13),
                             ft.Text(rules_in_use(), size=15)], spacing=2),
                  ft.Column([muted(t("options.folder", "Where it is kept"), 13),
                             ft.Text(str(budget.folder), size=15, selectable=True)],
                            spacing=2)], 12),
            muted(t("options.footer", "A private budget book. It works without internet, "
                                      "and everything stays on this phone."), 13),
        ], tight=True, scroll=ft.ScrollMode.AUTO, spacing=8),
            padding=ft.Padding.only(left=20, right=20, top=4, bottom=24)),
            show_drag_handle=True))


    def save_to_phone(title: str, make):
        async def handler(e) -> None:
            page.pop_dialog()
            try:
                name, data = make()
                where = await picker.save_file(
                    dialog_title=title, file_name=name, src_bytes=data,
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=[name.rsplit(".", 1)[-1]])
            except Exception as why:
                tell(t("save.failed", "Could not save the file: {why}", why=why))
                return
            tell(t("save.saved", "Saved.") if where else t("save.not", "Not saved."))
        return handler

    def to_messenger(messenger: str, make):
        def handler(e) -> None:
            page.pop_dialog()
            try:
                name, data = make()
                send.send(messenger, name, data)
            except send.NotHere as why:
                tell(str(why))
            except Exception as why:
                tell(t("save.messenger", "Could not open {messenger}: {why}",
                       messenger=messenger, why=why))
        return handler

    def offer(title: str, text: str, make) -> None:
        wide = dict(height=52, expand=True)
        page.show_dialog(ft.AlertDialog(
            title=ft.Text(title),
            content=ft.Column([
                muted(text, 14),
                ft.Row([ft.FilledButton(t("save.phone", "Save to phone"), icon=ft.Icons.DOWNLOAD,
                                        on_click=save_to_phone(title, make), **wide)]),
                ft.Row([ft.FilledTonalButton("Telegram", icon=ft.Icons.SEND,
                                             on_click=to_messenger("Telegram", make), **wide)]),
                ft.Row([ft.FilledTonalButton("WhatsApp", icon=ft.Icons.CHAT,
                                             on_click=to_messenger("WhatsApp", make), **wide)]),
            ], tight=True, spacing=12),
            actions=[ft.TextButton(t("cancel", "Cancel"), on_click=lambda e: page.pop_dialog())]))

    def save_menu(e) -> None:
        offer(t("options.save", "Save the configuration"),
              t("save.text",
                "One file with every month, answer, group, limit and the rules. It "
                "restores here, on the PC and in the cloud. It holds all your "
                "figures - keep it where only you can see it."),
              budget.backup)

    async def pick_configuration() -> bytes | None:
        picked = await picker.pick_files(
            dialog_title=t("options.restore", "Restore from a file"), allow_multiple=False,
            with_data=True, file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["json"])
        if not picked:
            return None
        chosen = picked[0]
        return chosen.bytes if chosen.bytes is not None else Path(chosen.path).read_bytes()

    async def restore_from_file(e) -> None:
        try:
            raw = await pick_configuration()
            if raw is None:
                return
            held = budget.read_backup(raw)
        except Refused as why:
            tell(str(why))
            return
        except Exception as why:
            tell(t("restore.unreadable", "Could not read the file: {why}", why=why))
            return
        confirm_restore(raw, held)

    def confirm_restore(raw: bytes, held: dict) -> None:
        async def go(e) -> None:
            page.pop_dialog()
            try:
                result = budget.restore(raw)
            except Refused as why:
                tell(str(why))
                return
            except Exception as why:
                tell(t("restore.failed", "Nothing was restored: {why}", why=why))
                return
            fresh = Look(budget.folder)
            look.theme, look.sizes = fresh.theme, fresh.sizes
            look.language = fresh.language
            words.set_lang(look.language)
            speak()
            apply_theme()
            state["month"] = None
            state["scope"], state["staged"] = None, []
            page.pop_dialog()
            show(MONTH)
            snack(t("restore.done", "Restored {months} month(s) and {answers} answer(s).",
                    months=result["restored"]["months"], answers=result["restored"]["answers"]))

        page.show_dialog(ft.AlertDialog(
            title=ft.Text(t("restore.title", "Replace everything on this phone?")),
            content=ft.Text(t(
                "restore.text",
                "The file holds {months} month(s) and {answers} answer(s){saved}, with its "
                "groups, limits and rules. Every month and answer now on this phone is "
                "replaced by them, and that cannot be undone.",
                months=held["months"], answers=held["answers"],
                saved=t("restore.saved", ", saved {date}", date=held["saved"])
                if held["saved"] else "")),
            actions=[ft.TextButton(t("cancel", "Cancel"), on_click=lambda e: page.pop_dialog()),
                     ft.FilledButton(t("restore.yes", "Replace everything"), on_click=go,
                                     bgcolor=ft.Colors.ERROR, color=ft.Colors.ON_ERROR)]))


    def asked_icon(n: int) -> ft.Control:
        return ft.Icon(ft.Icons.QUESTION_ANSWER_OUTLINED,
                       badge=ft.Badge(label=str(n)) if n else None)

    def chosen_tab(e) -> None:
        at = e.control.selected_index
        if at in (GUIDE, OPTIONS):
            nav.selected_index = state["tab"]
            page.update()
            (guide if at == GUIDE else options)()
        else:
            show(at)

    def tab_labels() -> list[str]:
        return [t("tab.month", "Month"), t("tab.questions", "Questions"), t("add", "Add"),
                t("guide", "Guide"), t("options", "Options")]

    labels = tab_labels()
    nav = ft.NavigationBar(
        selected_index=MONTH, on_change=chosen_tab,
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.CALENDAR_MONTH_OUTLINED,
                                        selected_icon=ft.Icons.CALENDAR_MONTH,
                                        label=labels[MONTH]),
            ft.NavigationBarDestination(icon=asked_icon(0), label=labels[QUESTIONS]),
            ft.NavigationBarDestination(icon=ft.Icons.ADD_CIRCLE_OUTLINE,
                                        selected_icon=ft.Icons.ADD_CIRCLE, label=labels[ADD]),
            ft.NavigationBarDestination(icon=ft.Icons.HELP_OUTLINE, label=labels[GUIDE]),
            ft.NavigationBarDestination(icon=ft.Icons.SETTINGS_OUTLINED, label=labels[OPTIONS]),
        ],
    )
    pages = {MONTH: month_page, QUESTIONS: questions_page, ADD: add_page}

    def show(tab: int) -> None:
        if tab != state["tab"] or not frame.content.controls:
            frame.content = ft.ListView(expand=True, spacing=12, padding=16)
        state["tab"] = tab
        nav.selected_index = tab
        body = frame.content
        try:
            months = budget.months()
            body.controls = pages[tab](months)
            page.appbar = top_bar(months)
        except Exception as why:
            page.appbar = ft.AppBar(title=ft.Text(t("budget", "Budget"),
                                                  weight=ft.FontWeight.W_600))
            body.controls = [
                ft.Text(t("failed", "Something went wrong"), size=20,
                        weight=ft.FontWeight.W_600, color=ft.Colors.ERROR),
                muted(str(why), 15),
                ft.Text(traceback.format_exc(), size=11, font_family="monospace",
                        selectable=True),
            ]
        nav.destinations[QUESTIONS].icon = asked_icon(state["asked"])
        page.update()

    apply_theme()
    page.navigation_bar = nav
    page.add(frame)
    show(MONTH)


def _theme(dark: bool) -> ft.Theme:
    return ft.Theme(
        color_scheme_seed=ft.Colors.TEAL,
        system_overlay_style=ft.SystemOverlayStyle(
            status_bar_color=ft.Colors.TRANSPARENT,
            status_bar_icon_brightness=ft.Brightness.LIGHT if dark else ft.Brightness.DARK,
            status_bar_brightness=ft.Brightness.DARK if dark else ft.Brightness.LIGHT,
            system_navigation_bar_color=ft.Colors.BLACK,
            system_navigation_bar_icon_brightness=ft.Brightness.LIGHT,
        ),
    )


if __name__ == "__main__":
    ft.run(main)
