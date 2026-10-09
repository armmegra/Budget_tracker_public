"""Amounts: whole units in, thousands with one decimal out."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

__all__ = ["to_thousands"]

_ONE_DECIMAL = Decimal("0.1")


def to_thousands(amount: int) -> Decimal:
    return (Decimal(amount) / 1000).quantize(_ONE_DECIMAL, rounding=ROUND_HALF_UP)
