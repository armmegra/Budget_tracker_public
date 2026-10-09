# How the engine works

The same library runs in the Lambda, in the Windows app and on the phone. This
is what it does with a month of notes, and the handful of decisions that shape
everything else.

## From notes to figures

```
notes (text)  ->  periods, days, entries  ->  each entry in a minor group
                                                      |
        the person's rulings laid over the rules  <---+
                                                      |
              majors by tier, limits, the Totals  <---+
```

1. **`notes.py` parses.** A date starts a day. A line is an amount and
   whatever follows it; a leading `+` is money coming in. A month begins at the
   income that opens it and ends where the notes stop, or at a line of `###`.
   Amounts written with spaces, refunds written inline (`900 - 150 market`) and
   the closing `Left:` line are all read here.
2. **`classify.py` sorts.** In order: the context of the line's block (an
   outing claims the fares around it), an ordered table of words from the rules
   file where the first match wins, and a doubt rule — when words of two groups
   share a line, or a rule's word only appears inside a longer word, the engine
   does not guess. It books a default and asks. Later passes send a tip to the
   bill it follows and a refund to the purchase it returns.
3. **`totals.py` and `display.py` add up.** Minor groups roll into majors, and
   majors into two Totals by tier: the first is what a normal month costs, the
   second adds the occasional. Limits are compared group by group.

## Decisions worth knowing

**Nothing computed is stored.** The store holds the notes as written, the
person's rulings, and the edits to the groups. Every figure is worked out again
on each request. So a rule can be fixed, a group renamed or a limit changed and
every month is simply right the next time it is read. There is no migration
because there is nothing to migrate.

**The person outranks the rules.** There are three ways to say where a line
goes, and each outranks every rule, including rules written afterwards:

| | Reaches | Outranks |
| --- | --- | --- |
| a **move** | one line of one month | everything |
| an **answer** | one line of one month | taught words and rules |
| a **taught word** | every line carrying it, in the months chosen | rules |

An answer once applied only to lines the rules were unsure of. A rule added
later then took back a line the person had answered, without a word, and a
restored backup showed a different month from the one saved. That is why the
order above is absolute: a month keeps the picture it was given.

**Names are labels; identities are underneath.** A group can be renamed and
every stored answer, every taught word and every rule still finds it, because
they hold the group's permanent name and the page shows its label.

**An edit says which months it is for.** Every change to groups, limits, words
or the closing line is for every month, for one month, or for one month and all
later ones. Edits are layers composed in order for the month being read, so a
month already printed keeps its reading when the groups move on.

**Old months close.** Three months after a month ends it becomes read-only,
worked out from the date and never stored. A change to it is refused with a
sentence saying how to make it deliberately, for one request.

**The rules are data.** Which words send a line to which group, the limits, the
shape of the closing line, even the notes' own control words: all of it is one
TOML file per household (`rules.toml`), validated at start-up and refused by
name if it does not make sense. The engine holds no household.

**One file holds everything.** A backup carries the months, the rulings, the
edits and the rules. Because figures come only from notes read through rules, a
file restored on another build reads to the same figures. A build that keeps its
own rules — the cloud does — says so when a file's rules differ from its own.

## The request

Every front end calls one function:

```python
reply = dispatch(store, {"action": "totals", "period": "January"})
# {"ok": True, "result": {...}}  or  {"ok": False, "error": "...", "code": "..."}
```

`import`, `periods`, `totals`, `questions`, `answer`, `move`, `omit`, `adjust`,
`configure`, `compare`, `export`, `backup`, `restore`. A refusal is a sentence
meant for the person holding the app, with a code a page can act on, and it can
be said in English or Russian.

In the cloud the store is DynamoDB (`dynamo.py`); in the other two builds it is
a JSON file. Both present the same interface, loaded afresh for each request so
nothing is half-saved between two calls.

## Measuring a change

The classifier is a list of ordered rules and exceptions, and a rule that fixes
one month can quietly break another. The habit this project settled on: take a
snapshot of every figure of every month, make the change, take another, and
read the difference group by group before committing. More than once that
caught a change that would have shipped wrong.
