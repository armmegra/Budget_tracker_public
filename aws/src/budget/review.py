"""The interactive review loop of the command line: one question at a time."""

from __future__ import annotations

from typing import Callable

from budget.classify import Classification, classify_period
from budget.display import pending
from budget.groups import minor_names
from budget.notes import Period
from budget.store import Store, answer_key

__all__ = ["run"]


def _prompt_for(c: Classification) -> str:
    lines = [f"\n  {c.entry.raw}", f"  {c.review}"]
    for i, option in enumerate(c.candidates, 1):
        lines.append(f"    {i}. {option}")
    lines.append("  group (Enter = skip, q = stop): ")
    return "\n".join(lines)


def _one_reply(
    c: Classification,
    known: set[str],
    ask: Callable[[str], str],
    say: Callable[[str], None],
) -> str | None:
    while True:
        reply = ask(_prompt_for(c)).strip()
        if reply.lower() == "q":
            return "q"
        if not reply:
            return None
        if reply.isdigit():
            if c.candidates and 1 <= int(reply) <= len(c.candidates):
                return c.candidates[int(reply) - 1]
            say(f"  no option {reply} here - type a group name, Enter or q")
            continue
        if reply in known:
            return reply
        sure = ask(f"  {reply!r} is a new group - start it? (y/N): ").strip()
        if sure.lower() == "y":
            return reply
        return None


def run(
    store: Store,
    identity: str,
    period: Period,
    ask: Callable[[str], str] = input,
    say: Callable[[str], None] = print,
) -> int:
    answered = 0
    skipped: set[int] = set()
    while True:
        results = classify_period(period, overlay=store.rulings(identity))
        open_now = [(n, c) for n, c in pending(results) if n not in skipped]
        if not open_now:
            say(f"done - {answered} answered, {len(skipped)} skipped")
            break

        progress = False
        known = set(minor_names()) | {c.minor for c in results if c.minor}
        for number, c in open_now:
            group = _one_reply(c, known, ask, say)
            if group == "q":
                say(f"stopped - {answered} answered")
                return answered
            if group is None:
                skipped.add(number)
                continue

            settle = [(number, c)]
            if c.rule in ("occasional outing", "gift outing") or c.rule.startswith("context:"):
                settle += [
                    (n, other)
                    for n, other in open_now
                    if n != number and other.rule == c.rule and other.review == c.review
                ]
            for n, target in settle:
                occurrence = sum(
                    1 for r in results[:n] if r.entry.raw == target.entry.raw
                )
                store.answers[answer_key(identity, target, occurrence)] = group
            store.save()
            say(f"  -> {group}" + (f"  (settled {len(settle)} lines)" if len(settle) > 1 else ""))
            answered += len(settle)
            progress = True
            break
        if not progress:
            say(f"done - {answered} answered, {len(skipped)} skipped")
            break
    return answered
