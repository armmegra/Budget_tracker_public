from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import words


@pytest.fixture(autouse=True)
def english():
    words.set_lang("en")
    yield
    words.set_lang("en")
