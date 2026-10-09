# The Android build

An app of its own for Android 10 and later: installed from a single APK, with
nothing else installed on the phone and no network needed.

## How it is put together

- **Screens** are drawn by Flutter and written in Python with
  [Flet](https://flet.dev): `app/src/main.py`.
- **The engine is the same Python library** as the other two builds, in
  `app/src/budget/`. Choosing Flet over rewriting the engine in another language
  was the point: there is one engine to keep right, a month reads the same on
  the phone, the PC and the cloud, and one configuration file moves between
  all three.
- **Python travels inside the APK**, so the phone needs nothing installed.
- **`app/src/data.py`** is everything the screens ask of the app, with no Flet
  in it, so it is tested without a phone. Each call goes to the same `dispatch`
  function the Lambda calls, over a JSON store in the app's private folder.
- **`app/src/bundled.py`** carries the invented households the app starts from,
  as text: inside an APK a file beside a module is not reliably a file on disk.

## What it does not have

**No network permission.** The app cannot reach the internet at all, which is
the simplest answer to where a household's notes go: nowhere. Moving data is
done by hand, with the configuration file — saved to a folder, or handed to
another app through Android's own share sheet, and restored the same way.

A file restored on the phone brings its rules with it. The phone starts from an
invented household, and notes become figures only through rules, so the rules in
the file are put in place before its months. If anything fails on the way, the
rules that were there are put back. A file saved before rules travelled inside
it is refused with a sentence saying why.

## Building and testing

```
pip install flet
cd app
python -m pytest            # the data layer and the screens, no phone needed
flet build apk              # needs the Android SDK and a JDK
```

`test_data.py` covers the data layer: adding notes, questions, moves, the
editors, saving and restoring the configuration file. `test_screens.py` drives
the real screens through Flet's own page object.

In the private repository the engine in `app/src/budget/` is not edited here:
a script copies it from the Windows build before every build, so the two can
never drift apart.
