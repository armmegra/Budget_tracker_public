Русская версия: README.ru.md

# Budget tracker

A private budget book that runs on your own Windows computer. You write down
what you spend the way you would jot it on your phone, paste it in, and the app
sorts it into groups, adds each month up and shows it against your limits.

**Nothing leaves your computer.** There is no website and no cloud behind it:
the app, your notes and your password all stay in this folder.

---

## Starting it

- **Unzip the whole folder first**, somewhere you can save files: Documents or
  the Desktop. Windows lets you open a zip and look inside without extracting
  it, but the app cannot run from in there. Do not put it inside Program Files.
- **Double-click `budget.exe`.**
- **The first time, Windows may warn you** with *"Windows protected your PC"*.
  That appears because the app does not come from a known publisher, not
  because anything was found in it. Click **More info**, then **Run anyway**.
  Your antivirus may ask as well.
- **A black window opens.** That window *is* the app running: leave it open
  while you use it. Your browser opens the app by itself. If it does not, type
  `http://127.0.0.1:8765` into the address bar. Chrome, Edge, Firefox and Opera
  all work.
- **Make your account**: a name, a password, and at least two recovery
  questions. The questions are how you get back in if you forget the password,
  so choose answers you will remember exactly. There is one account per copy of
  the app.

To stop the app, close the black window. To start it again, double-click
`budget.exe`.

---

## Your first look

The app starts with **four groups to make your own**: Rent, and Food, Road and
Medicine with a limit each - plus Refunds, for money coming back, and Set aside,
for what a month is measured against. None of it belongs to anyone. Rename
them, remove any of them and add your own from inside the app until they look
like your own spending: the ⋯ buttons work before you have a single month. A
group you remove takes no money with it: the lines it held go to **Questions**,
to be placed again.

The **?** button at the top opens the manual, with pictures. It explains how to
write a day, what the questions are for, and how to shape the groups and limits.

To watch the app at work before writing anything yourself, open one of the
files in the `examples` folder, copy everything in it, and paste it into
**Add notes**. The three example months are January, February and March,
invented for these four groups, and they take the current year. The app locks a month
three months after it ends, so that an old figure cannot be changed by a stray
click: if an example month shows as locked, click **Unlock this month** at the
top of the month before answering or moving figures in it.

When you are ready for your own notes, clear the examples away: pick January,
the earliest example month, open the gear panel, and under **Start over**
choose *This month and every later month*. That keeps any changes you have made
to the groups. *Everything* would reset those too.

You can also read your notes from screenshots of your phone: **Add notes**,
then **Read screenshot(s)**. That works offline too.

**When it keeps asking about the same shop, teach it the word.** Gear →
**Words you teach…**: give it a word and the group it belongs to, and lines
carrying that word book there from then on, without a question. What you answer
or move by hand always wins over a taught word.

---

## Language

**The app starts in English; choose Русский in the gear** (**⚙** →
**Language**). Everything the app writes switches, the manual included; your
own groups, words and notes never do. To have Russian from the very start,
click **Русский** on the first page, before you make your account: the app then
starts in Russian, its groups named in Russian. Their example months are in
`examples\ru`, and their notes are written with Russian words: `Остаток:` in place
of `Left:`, and so on. While nothing has been added or changed, switching the
language swaps the groups for that language's too, and **Start over** →
*Everything* brings back the groups of the language you chose.

---

## Your data

- **It all lives in the `data` folder**, beside `budget.exe`: your months, your
  answers, your groups and limits, and your account. The password is stored
  scrambled and cannot be read back, not even by you.
- **Make backups.** The gear panel has **Download configuration**, which saves
  one file with everything in it. **Restore from a file** puts it back, on this
  computer or on another one.
- **Moving to a new computer**: copy the whole folder, `data` included, or make
  a backup and restore it into a fresh copy of the app.
- **Removing the app**: delete the folder. Nothing was installed anywhere else.
- **Never pass on your own folder once you have used it.** The `data` folder
  inside holds your notes. To give the app to someone else, send the zip you
  received, not your folder.

---

## If something goes wrong

- **The black window says it "cannot listen" on the port.** A copy of the app
  is probably already running, in another black window. Use that one, or close
  it and start again.
- **The browser says it cannot connect.** The black window is closed or showed
  an error. Start `budget.exe` again and read what the window says.
- **You forgot your password.** On the sign-in page, click *Forgotten your
  password?* and answer your recovery questions.
- **The black window closes straight away, or says Python is missing.** The
  folder was not unzipped completely. Delete it and unzip the zip again.

---

## What is inside

The app brings its own copy of Python and of Tesseract, the program that reads
screenshots, so nothing has to be installed. Both are free software;
[THIRD-PARTY.md](THIRD-PARTY.md) lists them and their licences.
