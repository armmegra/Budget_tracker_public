# The Windows build

The same application as the cloud one, running entirely on one computer. No AWS,
no installer, no internet: a folder that can be zipped, carried to another
Windows machine, unzipped and carried on from.

```
double-click budget.exe   ->   http://127.0.0.1:8765 opens in the browser
```

Everything it knows lives in `data/` beside it, which is never part of a
repository.

## How it is put together

| Piece | File | Notes |
| --- | --- | --- |
| Server | `serve.py` | Python's standard-library HTTP server, bound to `127.0.0.1` and never to every interface |
| Account | `accounts.py` | one user; the password is never stored, only a PBKDF2 hash made slow on purpose; sessions in a cookie script cannot read; recovery by security questions |
| Pages | `pages.py`, `web/index.html` | sign-in, set-up and recovery, then the same single-page app as the cloud build, in English and Russian |
| Engine | `app/budget/` | the shared library, over a JSON file store |
| Screenshots | `local_ocr.py` | a bundled Tesseract reads a photo of notes, where the cloud calls Textract |
| Launcher | `launcher/` | a small C# program compiled to `budget.exe`: starts the server, opens the browser |
| Runtime | `fetch_runtime.py` | downloads an embeddable Python and Tesseract into `vendor/`, each checked against a pinned SHA-256 |

The page talks to the engine through the same `dispatch` function the Lambda
calls, so a month reads the same here as in the cloud, and one configuration
file moves between them.

## Why a local server and not a desktop toolkit

The interface already existed as a web page. Serving it from the machine itself
kept one page for two builds, needed no installer, and left the security
question a simple one: the server listens on the loopback address only, so
nothing outside the computer can reach it, and it still asks for a password
because a shared PC has more than one person at it.

## Running and testing

```
python fetch_runtime.py        # once; optional if Python 3.11+ is installed
python serve.py                # or double-click budget.exe
python -m pytest
```

- `test_local_app.py` drives the real server over HTTP on an ephemeral port:
  that it binds to loopback and nothing else, the first account, a wrong
  password, sessions, recovery by security questions with a lock after five
  wrong guesses that survives a restart, and what is served to a stranger.
- `test_speech.py`, `test_grammar.py`, `test_households.py`,
  `test_setup_edits.py` run the engine on the invented households, in English
  and Russian.
- `test_browser.py` and `browser_*.js` drive the page in a headless browser.
- `test_guides.py` checks the guides against the pictures they show.

`GUIDE.md` is the manual a user reads, with pictures taken from the app running
on the invented household. `clean/` holds the invented households themselves,
English and Russian, and their example months.
