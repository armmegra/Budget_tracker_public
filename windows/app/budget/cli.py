"""The command-line front end: show a month, answer its questions, compare months."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from budget.api import _import_year, dispatch
from budget.classify import classify_period
from budget.display import compare, pending, render
from budget.export import PAGE_BREAK
from budget.groups import minor_names
from budget.api import _slots, _tax
from budget.review import run as review_run
from budget.totals import rent_fixed
from budget.store import Store, answer_key, month_of, _span

DEFAULT_STORE = Path(__file__).resolve().parents[2] / "data" / "store.json"


def _classified(store: Store, name: str):
    found = store.period(name)
    if found is None:
        spans = ", ".join(span for _, span in _listing(store)) or "(none imported yet)"
        sys.exit(f"no period matches {name!r} - stored: {spans}")
    identity, span, period = found
    results = classify_period(period, overlay=store.rulings(identity),
                              dropped=store.taxonomy_at(identity).dropped)
    return identity, span, period, results


def _listing(store: Store) -> list[tuple[str, str]]:
    from budget.store import _span

    return [(identity, _span(period)) for identity, period in store.assembled()]


def main(argv: list[str] | None = None) -> int:
    top = argparse.ArgumentParser(prog="budget", description=__doc__)
    top.add_argument("--store", type=Path, default=DEFAULT_STORE, help="path to store.json")
    sub = top.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("import", help="parse a notes file and store its periods")
    p_import.add_argument("file", type=Path)
    p_import.add_argument(
        "--replace",
        action="store_true",
        help="overwrite a stored period even when it looks fuller (the repair "
        "path: a corrupted copy is by construction fuller than the pristine file)",
    )

    p_import.add_argument(
        "--year", type=int, help="the calendar year these notes belong to "
        "(defaults to this year, pulled back one for a file opening after today)"
    )

    p_exp = sub.add_parser("export", help="write a month, or a year, laid out for printing")
    p_exp.add_argument("period", help="a month (june), or a year with --year")
    p_exp.add_argument("out", type=Path, help="file to write; .rtf opens in Word")
    p_exp.add_argument("--year", action="store_true", help="every month of that year")

    p_sy = sub.add_parser("setyear", help="correct the year recorded for a period")
    p_sy.add_argument("period")
    p_sy.add_argument("year", type=int)

    p_cfg = sub.add_parser("config", help="print the groups, limits and Left line in force")
    p_cfg.add_argument("period", nargs="?", help="whose month's version to show")

    p_om = sub.add_parser("omit", help="choose which groups a month's second Total counts")
    p_om.add_argument("period")
    p_om.add_argument(
        "groups", nargs="*",
        help="the groups to LEAVE OUT; none listed counts everything again",
    )
    p_om.add_argument("--override", action="store_true", help="edit a closed month anyway")

    p_wipe = sub.add_parser("reset", help="delete stored months - this cannot be undone")
    p_wipe.add_argument("scope", choices=["answers", "month", "onward", "all"])
    p_wipe.add_argument("period", nargs="?", help="required for month and onward")
    p_wipe.add_argument("--override", action="store_true", help="include a closed month")

    p_raw = sub.add_parser("raw", help="print a period's stored notes text verbatim")
    p_raw.add_argument("period")

    p_un = sub.add_parser("unanswer", help="take back a ruling so its question reappears")
    p_un.add_argument("period")
    p_un.add_argument("raw", help="the entry's raw line, exactly as the notes write it")
    p_un.add_argument("--occurrence", type=int, default=0)

    p_show = sub.add_parser("show", help="render a period as the sheets are written")
    p_show.add_argument("period", help="a month (april, 04) or a span (10.01..27.01)")

    p_q = sub.add_parser("questions", help="list what still needs an answer")
    p_q.add_argument("period")

    p_a = sub.add_parser("answer", help="record a ruling for one question")
    p_a.add_argument("period")
    p_a.add_argument("number", type=int, help="the question number from `questions`")
    p_a.add_argument("group", help="the minor group to book it to")
    p_a.add_argument(
        "--new",
        action="store_true",
        help="allow a group name that exists nowhere yet (starts an occasional group)",
    )

    p_r = sub.add_parser("review", help="answer a period's open questions interactively")
    p_r.add_argument("period")

    p_c = sub.add_parser("compare", help="major groups side by side across periods")
    p_c.add_argument("periods", nargs="+", help="two or more periods, e.g. may june")

    sub.add_parser("periods", help="list stored periods")

    args = top.parse_args(argv)
    store = Store.load(args.store)

    if args.command == "import":
        if not args.file.exists():
            sys.exit(f"no such file: {args.file}")
        text = args.file.read_text(encoding="utf-8")
        for span, outcome in store.import_text(
            text, replace=args.replace, year=_import_year(None, {"year": args.year}, text)
        ):
            print(f"{outcome:<22} {span}")
        store.save()

    elif args.command == "unanswer":
        found = store.period(args.period)
        if found is None:
            sys.exit(f"no period matches {args.period!r}")
        key = f"{found[0]}|{args.raw}|{args.occurrence}"
        if key not in store.answers:
            sys.exit(f"no answer recorded for {args.raw!r} (occurrence {args.occurrence})")
        del store.answers[key]
        store.save()
        print(f"question reopened: {args.raw!r}")

    elif args.command == "export":
        fmt = "rtf" if args.out.suffix.lower() == ".rtf" else "txt"
        event = {"action": "export", "format": fmt}
        if args.year:
            event["year"] = int(args.period)
        else:
            event["period"] = args.period
        reply = dispatch(store, event)
        if not reply["ok"]:
            sys.exit(reply["error"])
        body = reply["result"]["body"]
        pages = body.count("\\page" if fmt == "rtf" else PAGE_BREAK) + 1
        args.out.write_text(body, encoding="utf-8")
        print(f"{args.out}  ({pages} page{'s' if pages != 1 else ''})")

    elif args.command == "config":
        event = {"action": "config"}
        if args.period:
            event["period"] = args.period
        reply = dispatch(store, event)
        if not reply["ok"]:
            sys.exit(reply["error"])
        cfg = reply["result"]
        for major in cfg["majors"]:
            limit = f"  limit {major['limit']}" if major["limit"] else ""
            label = f" (shown as {major['limit_label']})" if major["limit_label"] else ""
            shown = major["label"]
            if shown != major["name"]:
                shown = f"{shown} [{major['name']}]"
            print(f"{shown:<28} {major['tier'].lower():<11}{limit}{label}")
            for minor in major["minors"]:
                name = minor["label"]
                if name != minor["name"]:
                    name = f"{name} [{minor['name']}]"
                print(f"    {name}")
        print("\nlimits box:", ", ".join(cfg["limit_order"]))
        print("Left line :", ", ".join(
            f"{sl['label'] or sl['id']} ({sl['kind']})" for sl in cfg["left"]["slots"]
        ))
        if cfg["versions"]:
            print("\nscoped edits:")
            for v in cfg["versions"]:
                note = f"  {v['note']}" if v["note"] else ""
                print(f"  #{v['id']} {v['scope']:<7} from {v['from']} {v['year']}{note}")
        if cfg["closed"]:
            print(f"\nclosed to edits: {len(cfg['closed'])} month(s)")

    elif args.command == "omit":
        event = {"action": "omit", "period": args.period, "groups": args.groups}
        if args.override:
            event["override"] = True
        reply = dispatch(store, event)
        if not reply["ok"]:
            sys.exit(reply["error"])
        left_out = reply["result"]["omitted"]
        print(f"{reply['result']['span']}: second Total leaves out "
              f"{', '.join(left_out) if left_out else 'nothing'}")

    elif args.command == "reset":
        if args.scope in ("answers", "month", "onward") and not args.period:
            sys.exit(f"reset {args.scope} needs a month")
        what = args.period or "EVERYTHING"
        typed = input(f'this deletes {what} and cannot be undone - type RESET to confirm: ')
        if typed.strip() != "RESET":
            sys.exit("not confirmed")
        event = {"action": "reset", "scope": args.scope, "confirm": "RESET"}
        if args.period:
            event["period"] = args.period
        if args.override:
            event["override"] = True
        reply = dispatch(store, event)
        if not reply["ok"]:
            sys.exit(reply["error"])
        done = reply["result"]
        print("wiped: " + ", ".join(f"{v} {k}" for k, v in done["wiped"].items())
              + (f"  ({', '.join(done['months'])})" if done.get("months") else ""))

    elif args.command == "setyear":
        reply = dispatch(store, {"action": "setyear", "period": args.period, "year": args.year})
        if not reply["ok"]:
            sys.exit(reply["error"])
        print(f"{reply['result']['month']} is {reply['result']['year']}")

    elif args.command == "raw":
        found = store.period(args.period)
        if found is None:
            sys.exit(f"no period matches {args.period!r}")
        print(store.periods[found[0]], end="")

    elif args.command == "periods":
        for _, period in store.assembled():
            print(f"{month_of(period):<10} {_span(period)}   ({len(period.dates)} days)")

    elif args.command == "show":
        identity, span, period, results = _classified(store, args.period)
        print(render(
            span, period, results,
            fixed=rent_fixed(store, identity),
            tax=_tax(store, identity),
            omitted=set(store.omitted.get(identity, ())),
            slots=_slots(store, identity),
        ))

    elif args.command == "review":
        identity, span, period, _ = _classified(store, args.period)
        print(f"reviewing {span}")
        review_run(store, identity, period)

    elif args.command == "compare":
        if len(args.periods) < 2:
            sys.exit("compare needs at least two periods")
        columns = []
        for name in args.periods:
            identity, _, period, results = _classified(store, name)
            year = store.years.get(identity)
            label = f"{month_of(period)} {year}" if year else month_of(period)
            columns.append((label, results, rent_fixed(store, identity)))
        print(compare(columns, _tax(store)))

    elif args.command == "questions":
        _, _, _, results = _classified(store, args.period)
        rows = pending(results)
        if not rows:
            print("nothing pending")
        for number, c in rows:
            options = f"  [{' / '.join(c.candidates)}]" if c.candidates else ""
            print(f"{number:>3}  {c.entry.raw!r}\n     {c.review}{options}")

    elif args.command == "answer":
        identity, span, period, results = _classified(store, args.period)
        rows = dict(pending(results))
        if args.number not in rows:
            sys.exit(f"no open question {args.number} - run: questions {args.period}")
        target = rows[args.number]

        known = set(minor_names()) | {c.minor for c in results if c.minor}
        if target.candidates and args.group not in target.candidates and not args.new:
            sys.exit(
                f"this question offers [{' / '.join(target.candidates)}] - "
                f"pass --new to book it to {args.group!r} anyway"
            )
        if args.group not in known and not args.new:
            sys.exit(
                f"{args.group!r} is not an existing group - pass --new to start it"
            )

        occurrence = sum(
            1 for c in results[: args.number] if c.entry.raw == target.entry.raw
        )
        store.answers[answer_key(identity, target, occurrence)] = args.group
        store.save()
        print(f"answered ({span}): {target.entry.raw!r} -> {args.group}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
