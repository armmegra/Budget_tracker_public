"""Reads screenshots with a bundled Tesseract, in place of the cloud's Textract."""

from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

__all__ = ["extract", "languages", "tesseract_path", "TesseractMissing"]

HERE = Path(__file__).resolve().parent
BUNDLED = HERE / "vendor" / "tesseract" / "tesseract.exe"

_DATA_URL = re.compile(r"^data:image/[a-zA-Z.+-]+;base64,", re.IGNORECASE)

_LANGUAGES = re.compile(r"[a-z_]{3,}(?:\+[a-z_]{3,})*")

_LATIN = "AaBCcEeHKkMOoPpTXxYy"
_CYRILLIC = ("АаВСсЕеНКк"
             "МОоРрТХхУу")
_TO_CYRILLIC = str.maketrans(_LATIN, _CYRILLIC)
_TO_LATIN = str.maketrans(_CYRILLIC, _LATIN)
_WORD = re.compile(r"[^\W\d_]+")

_SAID: set[str] = set()


class TesseractMissing(RuntimeError):
    pass


def tesseract_path() -> Path | None:
    if BUNDLED.exists():
        return BUNDLED
    found = shutil.which("tesseract")
    return Path(found) if found else None


def _say_once(line: str) -> None:
    if line in _SAID:
        return
    _SAID.add(line)
    try:
        print(line, file=sys.stderr)
    except (OSError, ValueError):
        pass


def _household() -> str:
    rules = getattr(sys.modules.get("budget.rules"), "RULES", None)
    notes = rules.get("notes") if isinstance(rules, dict) else None
    wanted = notes.get("ocr") if isinstance(notes, dict) else None
    if isinstance(wanted, str) and _LANGUAGES.fullmatch(wanted):
        return wanted
    return "eng"


def _models(engine: Path) -> set[str] | None:
    folder = engine.parent / "tessdata"
    if not folder.is_dir():
        return None
    return {model.stem for model in folder.glob("*.traineddata")}


def languages(engine: Path | None = None) -> str:
    wanted = _household()
    engine = engine if engine is not None else tesseract_path()
    have = _models(engine) if engine is not None else None
    missing = [code for code in wanted.split("+") if have is not None and code not in have]
    if not missing:
        return wanted
    _say_once(f"! OCR: the rules ask for {wanted}, and the OCR engine has no "
              f"{', '.join(code + '.traineddata' for code in missing)} - screenshots "
              "are read in English (eng)."
              + ((" python fetch_runtime.py --ocr fetches the Russian model." if _fetcher()
                  else " A fresh download of the app has it in vendor/tesseract/tessdata.")
                 if "rus" in missing else ""))
    return "eng"


def _fetcher() -> bool:
    return (HERE / "fetch_runtime.py").is_file()


def _one_alphabet(text: str) -> str:
    def one(word: re.Match) -> str:
        found = word.group()
        cyrillic = [c for c in found if "Ѐ" <= c <= "ӿ"]
        latin = [c for c in found if c.isascii()]
        if not cyrillic or not latin:
            return found
        if all(c in _LATIN for c in latin):
            return found.translate(_TO_CYRILLIC)
        if all(c in _CYRILLIC for c in cyrillic):
            return found.translate(_TO_LATIN)
        return found

    return _WORD.sub(one, text)


def extract(image: str) -> str:
    engine = tesseract_path()
    if engine is None:
        raise TesseractMissing(
            ("no OCR engine found - put Tesseract in vendor/tesseract/ "
             "(python fetch_runtime.py will do it) or install it on PATH. " if _fetcher() else
             "no OCR engine found - vendor/tesseract/ is missing from this copy "
             "of the app: download the app again, or install Tesseract on PATH. ")
            + "Everything else in the app works without it; only reading a "
            "screenshot needs it."
        )

    raw = base64.b64decode(_DATA_URL.sub("", image or "").strip() or "", validate=False)
    if not raw:
        raise ValueError("ocr needs 'image': a base64 screenshot")

    args = [str(engine), "stdin", "stdout"]
    env = dict(os.environ)
    if (engine.parent / "tessdata").is_dir():
        args += ["--tessdata-dir", "tessdata"]
        env.pop("TESSDATA_PREFIX", None)
    wanted = languages(engine)
    done = subprocess.run(
        args + ["-l", wanted, "--psm", "6"],
        input=raw,
        capture_output=True,
        timeout=120,
        cwd=str(engine.parent),
        env=env,
    )
    if done.returncode != 0:
        detail = (done.stderr or done.stdout or b"").decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(
            "Tesseract could not read that image"
            + (f": {detail[-1]}" if detail else "")
        )
    text = done.stdout.decode("utf-8", errors="replace").replace("\r\n", "\n")

    said = (done.stderr or b"").decode("utf-8", "replace")
    failed = [code for code in wanted.split("+")
              if f"Failed loading language '{code}'" in said]
    if failed:
        _say_once(f"! OCR: Tesseract could not load {'+'.join(failed)} and read "
                  "the screenshot without it.")
    if "rus" in wanted.split("+") and "rus" not in failed:
        text = _one_alphabet(text)
    return text
