# Budget tracker — the guide

For someone opening this for the first time who has never set up groups or
limits before. It assumes nothing except that you write down what you spend.

You do not have to read it in order. To get going, read **The idea** and
**Writing a day**, add a month, and come back when a word on the screen stops
making sense.

- [The idea](#the-idea)
- [Signing in](#signing-in) — one account, and what protects it
- [Writing a day](#writing-a-day) — the only format you have to learn
- [Adding a month](#adding-a-month)
- [Questions](#questions) — why it asks instead of guessing, and how to teach it a word
- [Reading the month](#reading-the-month)
- [Groups](#groups) — **the one idea worth understanding**
- [Tiers, and the two Totals](#tiers-and-the-two-totals)
- [Limits](#limits)
- [Setting up your own, from scratch](#setting-up-your-own-from-scratch)
- [The Left line](#the-left-line)
- [Correcting a figure](#correcting-a-figure)
- [Comparing months, and printing](#comparing-months-and-printing)
- [Backups](#backups)
- [The gear menu](#the-gear-menu)
- [Where your data lives](#where-your-data-lives)
- [When something looks wrong](#when-something-looks-wrong)

---

## The idea

Most budget apps ask you to categorise a purchase at the moment you make it.
This one does not. You keep writing notes the way you already do — a date, a
list of amounts, a word or two each — and paste them in when it suits you. The
app reads them, sorts them into groups, adds them up, and asks you about the
handful of lines it could not place confidently.

So the loop is:

```
    write notes on your phone  →  paste them in  →  answer a few questions
                               →  read the month
```

**Amounts are shown in thousands.** A bar reading `12.0` means 12,000 of
whatever currency you write in. The app never converts anything; it only adds up
the numbers you wrote.

---

## Signing in

The app opens on a sign-in page hosted by AWS Cognito. There is **one account**
— yours — and sign-up is switched off, so nobody can create a second one.

**Signing in takes a second factor**, and the pool a Terraform instance builds
demands one: an authenticator app on your phone, enrolled from a QR code the
login page shows you the first time. A password can be guessed, phished or
reused; a six-digit code that changes every thirty seconds and lives on a
device in your pocket cannot be any of those things. It costs nothing — TOTP is
free, and it is SMS that bills per message.

If your pool was built by hand rather than by Terraform, check it: Cognito →
your user pool → **Sign-in** (or *Authentication methods*) → MFA. A pool
created through the console's quick flow has MFA **off**, and a pool with MFA
off will not let you set a preference on a user at all — it answers *"User does
not have delivery config set to turn on SOFTWARE_TOKEN_MFA"*. Set the pool to
**Required** with **Authenticator apps** ticked, and the user prompt appears at
the next sign-in.

**Nothing in the application is reachable without it.** The check does not
happen inside the app — it happens in front of it, at the API gateway, which
refuses any request that does not carry a valid token and never passes it on.
There is no page, no figure and no note behind that door for an unauthenticated
request to reach.

**Sign out** is at the top right. Your session expires on its own too, so a
window left open on a machine you walked away from stops working.

### If you lose access

There is no "forgotten password" link, on purpose. The way back in is the AWS
console for the account this instance belongs to: reset the password on the
Cognito user, or register a new MFA device. That is deliberate — the recovery
path is your cloud account, protected by its own MFA, rather than a set of
questions with guessable answers.

**Your notes are never involved in any of this.** They live in a database that
knows nothing about passwords.

---

## Writing a day

This is the only format you have to learn, and it is deliberately close to how
people already scribble.

```
10.01
+ 57 300
Left: 6.8, 61240

11.01
2340 grocer
135 eggs and cheese
160 taxi
Left: 4.3, 58605
```

Line by line:

| What you write | What it means |
| --- | --- |
| `11.01` | a date, `dd.mm`. It starts a new day. |
| `2340 grocer` | an amount, then what it was. The words decide the group. |
| `160 taxi` | a fare with its name on it, which is the version that needs no thought. |
| `45` | an amount and nothing else. Still treated as travel — see below. |
| `+ 57 300` | a **plus** makes it money coming in, not going out. |
| `Left: …` | optional. What you have left at the end of the day, in an order you decide. See [The Left line](#the-left-line). |
| a blank line | a break between separate outings in the same day. **This matters.** |

Three things worth knowing early:

**Spaces in numbers are fine.** `57 300` and `57300` are the same. Write
them however you write them.

**A blank line separates outings.** If you go to the cinema in the afternoon and
out to dinner in the evening, put a blank line between them. The app uses those
breaks to decide which taxi belongs to which outing — without them, the taxi
home from dinner can be charged to the cinema.

**Say what a fare was, if you can be bothered.** `160 taxi`, `26 bus`,
`850 fuel` — a named fare lands where you meant it to and costs you nothing
later.

A line that is only an amount still works: it is treated as travel belonging to
whatever outing it sits in, which is the habit most people already have. But if
it sits in no outing, nothing on the line says where you went, and the app has
to ask. Writing the word is how you avoid the question.

### Money coming back

Put a `+` in front. A refund, a reimbursement, a repayment. It subtracts from
whatever group it lands in, so a refunded purchase nets out to nothing rather
than being counted twice.

```
+ 740 boots returned
```

The app also matches a refund to the purchase it reverses **by amount**, so a
credit that names only the shop it came back through still lands in the group
that carried the thing you bought.

---

## Adding a month

**Add notes**, paste, **Add**.

Two things on that screen are worth understanding.

**"— new month —" versus picking a month by name.** The app works out which
month a paste belongs to from the income line that opens it — the salary, or
whatever regularly starts your month. If your paste has that opening line, leave
the box on "new month" and it sorts itself out. Pick a month by name only when
you are pasting a few extra days on their own, with no opening line to identify
them.

**Re-pasting is safe.** If a day is already stored, the fuller copy replaces the
shorter one. It is never doubled. So the easy habit is: each time you want to
catch up, copy the whole note from its very first line and paste the lot.

### Where one month ends and the next begins

**A month begins at its income line** — the salary, or whatever regularly opens
yours. That line is how the app tells one month from another, and it is why a
paste that has it needs nothing else.

**A month needs no end mark**, as long as you paste one month at a time. It ends
where the notes stop.

**Pasting several months at once is the one case that needs a mark.** Put a line
of at least three hashes between them, on a line of its own:

```
27.01
310 fruit
Left: 1, 32500

####

10.02
+ 58 650
```

Without it the two run together into a single enormous month. The app does not
start a new one when it meets a second income line, deliberately: a second
salary line mid-month is a real thing — a bonus, a repayment, a part payment —
and guessing that it means "new month" would split months that should not be
split. The hashes are you saying it, and nothing else does.

Any number of hashes from three up works; the length carries no meaning. If you
copy your notes out of an app that already writes a divider between months,
that divider probably already is one.

**A month is named for where most of its days fall.** If yours run from one
payday to the next, one straddles two calendar months — the 25th of May to the
24th of June, say. Twenty-four of those days are in June, so the app calls it
June, which is what you would call it too. You never name a month yourself; you only ever pick one
that is already there.

### From a screenshot

If your notes live in a phone app, photograph them and use **Read screenshot(s)**
instead of typing. The image goes to Amazon Textract, which reads the text and
sends it back into the box for you to check before it is added — **always check
it**, because OCR misreads digits occasionally and this is money.

The picture is used for that one call and is not kept.

---

## Questions

The app never silently guesses. When a line could reasonably belong to two
groups, or to none it knows, it asks — and until you answer, that line is not
counted anywhere.

Each question shows the day its line was written on: the date, then that day's
lines exactly as you wrote them — the blank lines, the credits and the Left line
too — with the one asked about in bold, in a box that opens on it and scrolls
through the rest of the day. It says what the doubt is,
and offers the answers it thinks likely. The buttons are shortcuts, not a menu:
**Other…** lets you type any group name, and if you type a name that does not
exist yet, it offers to start a new group with it. Pressing **Enter** confirms
what you typed.

The commonest kinds:

- **"no rule matched".** Nothing in the line matches a group the app knows. It
  picks the word that looks most like a name and offers it as a new group,
  which is one click rather than typing.
- **"a fare with nothing naming it".** A bare amount that belongs to no outing.
  Only you know where you went.
- **"alcohol — Food, or a celebration of its own?"** The line genuinely reads
  both ways, and which one you mean changes the month.
- **"this line names X and Y — which was it?"** Two groups' words on one line,
  and the app will not pick for you. The first match stays the default, so an
  unanswered month reads exactly as it did.
- **A word hiding inside another word.** The app matches `phone` to book your
  phone bill — and `phone` also sits inside `headphones`, which is not a phone
  bill at all. When a rule only matches in the middle of a longer word, the app
  will not book it. It asks *"headphones is not phone — which group is this?"*
  and offers `Headphones` first, as a group of its own.

**Your answers are remembered per month and per occurrence.** Answering
"wine → drinks" in July does not silently decide the same line in August; the
same words can mean different things in different months.

**An answer outranks every rule, including rules written after it.** When the
app later learns a word that would place a line you had already answered, your
answer still decides that line. The same holds for a figure you moved. So a month
keeps the picture you gave it, however the rules change.

**"Ask them all again"** forgets this month's answers and puts every question
back. The figures return to what the rules alone make of the notes.

### Teaching it a word

An answer settles one line in one month. When the same shop comes round next
month, it is asked about again, because which words belong to which group is
something the app knows only from the words it was built with, and your shops
are not those.

So you can teach it one. **Gear → Words you teach…** takes a word and the group
it belongs to. From then on every line carrying that word books straight there
and is not asked about. Teaching a word can only remove questions; it never adds
one.

A few things worth knowing:

- **It asks which months first**, the same as the group editors do: every month,
  this month only, or this month and every later one. A month that is already
  closed is protected, so teaching a word cannot quietly rewrite a month you
  have printed.
- **What you answer or move by hand still wins.** A taught word is about every
  line carrying it, an answer is about one line, and the particular beats the
  general.
- **Two words fitting one line: the longer one decides.** Teach `bakery` for
  Food and `bakery card` for the card, and a bakery card line takes the second.
- **A word, not a fragment.** `bakery` does not match inside `bakerycorp`, and
  you can teach two words together, such as `garden centre`, which then match
  with any spacing between them.
- **Choose the word narrowly.** A word is matched anywhere in the line, so a
  broad one reaches lines you did not mean. Teaching `coffee` for Food also
  takes a coffee machine and a coffee table, which are not food at all. A
  shop's name is a good word; a thing's name is usually not.
- **It reaches money coming back too.** A credit carrying the word books to that
  group like anything else.
- **Forget takes one back**, and its lines go back to being read by the rules,
  or asked about.

Words travel in a backup with everything else, so an instance restored from
another knows what you taught it.

---

## Reading the month

Four things are on this page.

**The bars** are your major groups, one per row, in a fixed order so the page
looks the same every month. A group that had no spending shows a dash rather
than vanishing — its absence is information too.

- **Green** is what you spent.
- **Yellow** beside the green is the room left under that group's limit.
- **Red** means you went past the limit, and the red section is the overspend.
- **Blue** means the group has no limit at all.
- **Yellow with a plus** is income — money that came in, reducing the total it
  sits in.
- The two bottom rows, **Totally saved** and **Totally overspent**, add up all
  the yellow and all the red. They are readings, not groups.

**The limits box** on the right is your monthly plan, in the order you choose.

**The two Totals** are explained in the next section.

**The minor group list** below them shows every individual amount, so you can
see what any figure is made of. That is the list's whole job: not a sample of
what you spent but **all of it, gathered by group**.

---

## Groups

This is the one idea worth understanding properly. Everything else follows from
it.

There are **two levels**.

A **minor group** is where a single line lands. `2340 grocer` lands in a
minor group; `850 fuel` lands in a different one.

A **major group** is what several minor groups roll up into. Majors are what you
see on the chart, what limits watch, and what the Totals are made of.

```
    Transport           ← major: one bar, one limit, one number (31.4)
      bus       6200    ← minor: a month of bus fares, added up
      train    17400    ← minor: three train tickets
      fuel      7800    ← minor: two fills of the tank
```

**Why bother with two levels?** Because you want two different things at once.
You want *one* number for getting about when you look at the month, and you want
to keep the buses, the trains and the fuel apart when you look closer. One level
would force you to choose. So: minors keep the detail, the major adds them up.

You do not have to use both levels. A major group with a single minor under it
is perfectly normal — most of the shipped ones are.

### Where the editors are

There is one **⋯** button beside each thing it edits, and clicking the word
**Left** on the closing line opens the fourth:

| Button | Where it is | What it edits |
| --- | --- | --- |
| **⋯** | above the chart, by "major groups" | major groups |
| **⋯** | inside the Limits box, before the word | limits |
| **⋯** | over the minor list, on the right | minor groups |
| **Left** | the closing line at the foot of the month | the Left line |

Each asks *which months should this apply to* before it opens, which is
explained under [Setting up your own](#setting-up-your-own-from-scratch).

#### Minor groups

Every one shows the major it lives under. **Route to…** moves it somewhere else
— this is how you reshape things: decide that fuel should not count as
transport, and route `fuel` under a `Car` major instead. Old months recompute at
once.

Several minors may share one major, which is exactly how a dozen scattered lines
become a single figure. **Add** asks for a name and which major it belongs
under, and refuses without both.

#### Major groups

**Rename** and **Remove**, and an **Add** that asks for a name, a
[tier](#tiers-and-the-two-totals) and — if you want one now — a limit.
**Remove** works on any major. If minor groups live under it, it first asks
which group they move to, offering only groups counted the same way, so none of
their money is lost; one group that spending can go to always stays. **Rename**
also renames the minor that shares the major's name — `Rent` inside `Rent` —
and a minor may take its own major's name, but no other group's.

**Names are labels, and permanent identities are underneath.** This is why you
can rename a group and every old month, every stored answer and every rule
still works. Only the word on screen changes.

### The groups it comes with are only a starting point

The app ships with a working set of groups so the first month you paste has
somewhere to go, rather than facing you with an empty page. **None of it is
meant to be yours.** See [Setting up your own](#setting-up-your-own-from-scratch).

---

## Tiers, and the two Totals

Every major group has a **tier**, and the tier decides how it reaches the
month's total. There are four.

| Tier | What it means | Where it lands |
| --- | --- | --- |
| **necessary** | the ordinary running of your life | the **first Total** |
| **frequent** | real spending, but not every month | added *after* the first Total |
| **occasional** | one-offs — a trip, a repair, a gift | added *after* the first Total |
| **excluded** | recorded, but counted in nothing | neither Total |

That is where the two Totals on the month page come from:

```
    Total: 30.3                                               ← "necessary" only
    Total: 30.3 + Garden 1.2 + Books 3.0 + Picture frame 0.4 : 34.9
```

**Why two?** Because "what does my life cost to run?" and "what did I actually
spend?" are different questions, and mixing them makes both useless. A month
with a holiday in it is not evidence that your groceries got more expensive. The
first Total is the comparable one, month to month. The second is the truth about
your bank balance.

**What "excluded" is for.** Some lines have to be written down but must not be
counted. Cash taken out of a machine is the clearest case: if the withdrawal
counted, and then the shopping you did with that cash also counted, you would
have spent it twice. Money moved to savings is the same — recorded, not spent.

### Choosing what the second Total counts

Click the word **Total** on the second line.

Every one-off group appears with a tick. Untick one and it drops out of that
Total — it keeps its bar and its detail, because it still happened, but it stops
colouring the month. Click the figure itself to enter a different one, for the
times when what you spent and what you want the month to carry are not the same.
A figure you set is marked, so you can never mistake it for a counted one.

**Moving a tick gives up the figure you set.** Unticking a group and putting it
back says "count this the way the notes do again" — otherwise a group could come
back still carrying a figure set for a reason that no longer applied.

---

## Limits

A limit is a monthly number you set for one major group. It changes nothing
about how spending is counted — it only draws the yellow and the red, and feeds
the two summary rows.

Each row watches one major group.

- **Value** sets the number, in thousands. `20` means 20,000.
- **Rename** changes what the box calls it, without renaming the group. Useful
  when the group is called `Transport` but you think of that budget as
  "Getting about".
- **Watch…** points the row at a different group.
- **Remove** takes the limit off, and the group's bar turns blue.

**Add a limit** starts on *Choose a group…* and never picks one for you. Choose
the group, or type its name: a name that is already a group's puts the limit on
that group, and a new name makes a new group carrying the limit. *Shown as* only
names the row in the box; it chooses no group.

The order of the rows is the order you set them in, and it is meant to be the
order you naturally read. A limit you add later joins the end of that order.

**Limits are optional.** A group with no limit still works perfectly; you just
lose the yellow-and-red reading for it.

---

## Setting up your own, from scratch

Here is a way to get from the shipped example to your own life in about ten
minutes. The point of doing it in this order is that you never lose data: you
reshape the groups first, and only then start adding months.

### 1. Clear the example, if you want a clean page

Gear (**⚙**) → **Start over** → *Everything — months, answers, groups and
limits, from scratch*. This cannot be undone, so do it before you have anything
worth keeping.

You do not have to. Renaming your way from the shipped set to your own works
just as well, and keeps a working example in front of you while you learn.

### 2. Decide your majors first

Write down, on paper, the headings you want to see when you look at a month —
the things you think of as your regular monthly spending. Most people's list
looks something like:

```
    Food        Home        Transport      Health
    Eating out  Bills       Clothes        Fun
```

**There is no right number, and the app is not the thing limiting you.** The
reason to keep the list short is that every extra group is another decision you
have to make about every line you write, forever. You can always add one later —
and the app will offer to, the first time a line does not fit anywhere.

### 3. Set their tiers

Ask of each: *does this happen every month, as part of the ordinary running of
things?* If yes, it is **necessary**. If it is real but sporadic — clothes,
electronics — make it **frequent**. Leave **occasional** alone; the app creates
those for you when a one-off turns up.

### 4. Add minors only where you want the detail

Under `Food` you might want `market` and `delivery`. Under `Bills` you
probably want one per bill: `water`, `heating`, `broadband`. Under `Fun` you
probably want nothing at all.

The test: *would I ever want to see these separately?* If not, do not split it.

### 5. Put limits on the ones you want to watch

Only the groups where a number would actually change your behaviour. A limit on
a group you cannot control is just a red bar telling you something you knew.

### 6. Choose the scope, then edit

Before you change anything, whichever **⋯** you press asks which months your
change applies to.

- **Every month** — the normal choice. Renaming something, or fixing a limit you
  set wrongly, should apply everywhere.
- **This month only** — when a group genuinely means something different in one
  month.
- **This month and all further months** — when your life changed. Your rent went
  up in the spring; the winter months should keep the old figure.

That last one is the reason this question is asked at all. Without it, raising a
limit would quietly rewrite every month you had already looked at.

When the scope is anything other than "every month", your edits are **staged** —
listed, and applied together when you press Apply — so a half-finished
reshaping never lands.

### 7. Now paste your first month

And answer the questions. The first month asks the most, because every shop you
write is new to it. Nothing is learned from your answers by itself: an answer
settles that one line in that one month. What makes later months quieter is
[teaching it a word](#teaching-it-a-word) for the shops you write often.

**A group's name is not a word.** Calling a group `Road` does not teach the app
the word *road*: a line reaches a group through the rules, a word you teach, or
your answer. Upper or lower case never matters — once *road* is taught, `ROAD`
and `Road` book there too.

### What the figures do while you reshape

Nothing is recomputed wrongly, because nothing is stored. Every total on the
page is worked out from your raw notes each time you look at it. Rename a group,
move a minor, change a limit — reload and the figures are simply right. The only
things stored are your notes and your answers.

---

## The Left line

Optional, and easy to skip on a first read. It answers a different question from
the rest of the app: not *what did I spend* but **what have I got left, right
now**.

If you already end each day by writing down where you stand, the app reads that
line, keeps it in step as the month goes on, and tells you what today's figures
ought to be.

You write bare numbers in a fixed order, and the app puts the names on:

```
    you write            Left: 4.3, 58605

    the app shows        Left: purse 4.3, account 58605
```

The order is yours and so are the names. A sensible pair to start from:

| Figure | What it is | What it is for |
| --- | --- | --- |
| **purse** | the cash you are actually spending from | the everyday figure |
| **account** | the balance of your bank account | it should match your banking app; when it does not, a day is missing |

Add more if you keep more: money put aside and not for spending, or an
allowance for one kind of spending that refills every week.

### The kinds, and why they matter

Each figure has a **kind**. The kind is not decoration — it is how the app
brings a half-written month up to date, so that today's line is right even
though you last wrote one on Tuesday.

| Kind | What the app does with it |
| --- | --- |
| **card balance** | every card payment comes off it |
| **cash in hand** | everything else comes off it |
| **weekly purse** | refills on a day you choose, and is spent down by groups you choose |
| **carried over** | stands unchanged until you write a new figure yourself |

A withdrawal moves money from the card to the cash, which is why those two are
one ledger and not two.

Click the word **Left** at the foot of the month to open the editor. You can
rename each figure, put its name before or after the number, reorder them, add
more, or remove the ones you do not keep. **Back to the original line** puts
back the set the app ships with. Like the group editors, it asks which months
first: a change for this month only, or this month onward, waits in a list
under the editor until you press **Apply**.

If you do not write such a line at all, ignore this section — nothing else
depends on it.

---

## Correcting a figure

Any amount on the month page can be clicked and moved, not only the ones you
were asked about.

The popup shows the day the figure's line was written on, as a question does —
the date, that day's lines as you wrote them, the figure's own line in bold, in
a box that scrolls — and offers somewhere to put it. The day is how you tell one
`26` from the next. If you
have moved it before, **Put it back** lifts your move and lets the rules decide
again.

Figures carry a mark saying how they got where they are: one you answered, one
you moved, and one the rules placed all look slightly different. Point at one to
be told which.

**Old months lock themselves.** Three months after a month ends it becomes
read-only, so a stray click cannot change a figure you have already acted on. If
you genuinely need to correct one, the bar at the top of the month unlocks it and
says plainly that you may be changing something you already printed. The unlock
lapses when you reload — it is not a setting you can leave on by accident.

---

## Comparing months, and printing

**Compare** puts months side by side in one table: every group, every month, and
an average. Tick the months you want — it opens on the two most recent, which is
usually the question. The table scrolls sideways when there are more months than
fit.

**Average** works out the average of exactly the months ticked. The year buttons
beside it tick a whole year and average that — but a year in progress ends with
a month still being written, and a month one week old drags the year's
averages down. Press the year, untick the month you are still in, press **Average**: the
same figures, over the months that are finished. Any set of months works — a
quarter, the summer, everything but a holiday month.

**Print…** produces the month, the whole year, or a comparison, as a Word or
text file laid out for paper. A comparison too wide for a page is dealt across
as many pages as it needs, and **every page repeats the group names down its
left edge** — reading a total means reading along a row, and a page of bare
figures has nothing to read along.

---

## Backups

Gear (**⚙**) → **Download configuration** saves everything — months, answers,
groups, limits, the ticks and the figures you set — as one file.
**Restore from a file…** reads it back.

The restore is the most destructive thing the app can do: it replaces every
stored month at once. So it asks three times, in order — *Are you sure?*, then
*Apply*, then a final irreversible *Yes* — and the last button is dead for a
moment so that a double-click cannot carry you through it.

Two habits worth having:

- Take one before any big reshaping of groups.
- Take one occasionally anyway, and keep it somewhere other than the cloud
  account this instance lives in.

A backup is also how you move between instances: download from one, restore into
another. It carries your data, not your login. A restore shows every month as it
was when you saved it, answers and moves included, even into an app whose rules
have grown since.

**The file carries the rules too.** Your months are notes, and notes become
figures only through the rules: which words go to which group, and what the
Left line's figures are. So the file holds a copy of the rules this app reads
with, and one file restores everything. The phone app puts those rules in place
when it restores, so its months read exactly as they do here.

This app does not. Its rules belong to the code it runs, so a restore here keeps
them and uses the file's rules only to compare. When they differ, the message
after the restore says so: the months then read by this app's rules, not by the
rules of the place the file came from.

Treat the file as private as your months. It holds your notes, your answers, and
now the words your household uses.

---

## The gear menu

The **⚙** button, top right, holds what you set once and rarely touch:

- **Bar colours and text sizes** — every colour on the chart and every type
  size, dragged live. These live in this browser, not in your data, so they do
  not travel in a backup.
- **Backup** — covered just above.
- **Words you teach** — the list of words you have taught and the group each one
  books to, with a Forget beside each. See
  [Teaching it a word](#teaching-it-a-word).
- **Start over** — wipes this month, this month onward, or everything. It asks
  twice and cannot be undone.

The app always **opens on the newest month**, the one you are living in. While
you work, the month on screen stays put when you add notes or restore a file.

---

## Where your data lives

Worth knowing, because it is the difference between this and an app on your own
machine.

Your notes and your answers are stored in **DynamoDB, in your own AWS account**,
in one table. Not on anyone else's server, not in a company's product, not
anywhere a support engineer can read them. The application is a single function
that runs for the length of one request and keeps nothing between calls.

**Nothing calculated is ever stored.** The table holds your notes exactly as you
typed them, plus the decisions you made about them — and every total on every
page is worked out fresh on each read. That is why improving a rule improves
every month you have already saved, with no migration and no rebuild.

The page itself holds no data at all: it asks the API for everything and draws
what comes back. Where it is *served* from therefore matters very little, and
there are two answers. A Terraform-built instance puts it in a private S3
bucket behind a CloudFront distribution, which is what gives it an HTTPS
address. An instance whose distribution has not been built — a new AWS account
cannot create one until AWS verifies it — serves the same file from your own
machine with `python -m http.server 5173 --bind 127.0.0.1 --directory web`,
against exactly the same API and the same table. Nothing else changes;
`http://localhost:5173` is a legal Cognito callback, which is the one thing that
makes it possible.

**`--bind 127.0.0.1` is not optional.** Without it Python's server listens on
every network interface, which puts the page on your home network for anyone
else connected to it. There is nothing behind it without a login, and the page
holds no figures of its own — but a thing that need not be reachable should not
be reachable.

---

## When something looks wrong

**A figure is in the wrong group.** Click it and move it. If it keeps landing
wrongly in later months too, the fix is usually to rename or reroute a group so
the word you write matches the group you mean.

**A total moved by 0.1 for no reason.** Each major group is rounded to one
decimal and only then added up, so moving one line between groups can shift a
total by a tenth. This is deliberate and matches how such figures are kept on
paper.

**A month is missing.** It probably has no opening income line, so nothing told
the app where it starts. Paste the notes again from the top of the note.

**A day appears twice.** It should not — the fuller copy replaces the shorter
one. If it does, the two copies have different dates written on them.

**Everything is a question.** Usually the first month, and it settles quickly.
If it does not, your notes probably use words the shipped rules have never seen,
which is expected: answer them once each and the answers stick.

**The page says a month is closed.** It is more than three months old. Open it
and use *Unlock this month*.

**The page says you are not signed in, or nothing loads.** Your session has
expired. Sign in again; nothing is lost, because nothing was being held in the
page.

**You cannot sign in at all.** See [Signing in](#signing-in) — the way back is
the AWS console for the account this instance belongs to.
