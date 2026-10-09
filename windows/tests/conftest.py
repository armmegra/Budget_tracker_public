"""Fixtures for the Windows build's own suite.

The month used here is invented, written in the invented household's words.
Nothing in this repository is anybody's real notes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


@pytest.fixture(scope="session")
def sample_notes() -> str:
    """Four days: buses and a train, groceries, a pharmacy, a cafe, and the
    lines the rules cannot place and so ask about."""
    return (HERE / "sample_month.txt").read_text(encoding="utf-8")
