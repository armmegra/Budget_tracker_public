# Budget tracker

A household budget kept as plain notes — a date, an amount, a word or two — and
an app that reads those notes exactly as written, sorts every line into a group,
totals each month against its limits, and asks only when it cannot tell.

One engine, three builds:

| Folder | What it is | Where it runs |
| --- | --- | --- |
| [`aws/`](aws/) | A serverless build: Cognito, API Gateway, Lambda, DynamoDB, S3, described twice — by hand-written runbooks and by Terraform | AWS |
| [`windows/`](windows/) | A local app with its own sign-in. No network, no cloud, a page in the browser | a Windows 11 PC |
| [`android/`](android/) | A phone app written with Flet over the same Python engine | Android 10 and later |

The three share one Python library (`budget/`) that parses the notes, classifies
each line, and computes every figure. **No figure is ever stored**: totals are
worked out from the notes each time, through whatever the groups are for that
month. A single configuration file carries the months, the answers, the group
edits and the rules, so a month restored on any of the three reads identically.

## What this copy is, and what it is not

This repository is a copy made for showing the work. It is built by a script
from a private repository, never edited by hand, and three things about it are
deliberate:

- **The household is invented.** The rules file, the example months and every
  figure in the tests belong to nobody. The original runs on a real household's
  notes, and none of that is here.
- **The code has no inline comments.** The original is commented throughout,
  and those comments quote real notes as their examples. Rather than promise
  that thousands of comment lines hold nothing private, the build removes them
  all and gives each module a short summary written for this copy. The code
  itself is unchanged: the build proves each file parses to the same program.
- **Cloud identifiers are placeholders.** Account numbers, endpoints, pool and
  client ids read `<account-id>`, `<api-id>` and so on. The Terraform and the
  runbooks are otherwise as they were used.

The tests here were chosen or written to run on the invented household. The
original suite is larger and runs against real months, which is exactly why it
could not come along.

## Running the tests

Python 3.13, and `pytest`. The engine itself has no dependencies.

```
cd aws      && python -m pytest
cd windows  && python -m pytest
cd android/app && python -m pytest      # needs Flet: pip install flet
```

The browser tests in `aws/` and `windows/` drive the real page in headless
Chrome or Edge and are skipped when neither is installed.

## How it was built

Over about seven weeks, by one person working with Claude Code. The person
decided what the notes mean, checked every month against a spreadsheet kept by
hand, did every step in AWS personally, and found the bugs; the assistant wrote
most of the code, the tests and the runbooks. Every rule in the engine exists
because a real month needed it.
